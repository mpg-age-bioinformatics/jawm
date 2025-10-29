#!/usr/bin/env python3
"""
nf_to_jawm.py
Convert a Nextflow repo (Git URL, GitHub URL, or local path) into a JAWM mirror.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import textwrap

# -------------------------- regex helpers --------------------------

PROCESS_RE = re.compile(r"process\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{(.*?)\n\}", re.DOTALL)
SECTION_RE = re.compile(r"(?m)^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*$")
TRIPLE_QUOTE_RE = re.compile(r'(?s)"""(.*?)"""|\'\'\'(.*?)\'')

CONTAINER_LINE_RE = re.compile(r'(?m)^\s*container\b\s*(?:=)?\s*(.+?)\s*$')
LABEL_RE = re.compile(r'(?m)^\s*label\s+[\'"]([^\'"]+)[\'"]\s*$')
PARAMS_DOT_RE = re.compile(r"\bparams\.([A-Za-z_][A-Za-z0-9_]*)")
TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

WITHNAME_RE = re.compile(r'withName:\s*(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z_][\w\.-]*))', re.IGNORECASE)
WITHLABEL_RE = re.compile(r'withLabel:\s*(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z_][\w\.-]*))', re.IGNORECASE)

GLOBAL_CONTAINER_ANY_RE = re.compile(
    r'process\.container\s*=\s*(.+?)\s*(?:$|\n|\r|\})',
    re.DOTALL | re.IGNORECASE
)
CONTAINERS_MAP_BLOCK_RE = re.compile(
    r'(?:^|\s)(?:params\.)?containers\s*=\s*\[([^\]]+)\]',
    re.DOTALL | re.IGNORECASE
)
CONTAINERS_DOT_ASSIGN_RE = re.compile(
    r'(?:^|\s)(?:params\.)?containers\.([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*[\'"]([^\'"]+)[\'"]',
    re.IGNORECASE
)
MAP_PAIR_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*[\'"]([^\'"]+)[\'"]')

# slurm overrides
EXECUTOR_RE = re.compile(r'(?m)^\s*executor\s*=?\s*[\'"]?\s*slurm\s*[\'"]?\s*$')
CPUS_FIELD_RE = re.compile(r'(?m)^\s*cpus\s*=?\s*([^\n\r#;]+)')
MEM_FIELD_RE  = re.compile(r'(?m)^\s*memory\s*=?\s*([^\n\r#;]+)')
TIME_FIELD_RE = re.compile(r'(?m)^\s*time\s*=?\s*([^\n\r#;]+)')

def debug(msg: str):
    print(f"[nf_to_jawm] {msg}", file=sys.stderr)

# -------------------------- repo handling --------------------------

def is_github_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.netloc.lower().endswith("github.com")
    except Exception:
        return False

def download_github_zip(url: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) >= 2:
        owner, repo = parts[0], parts[1].replace(".git", "")
    else:
        raise ValueError(f"Unrecognized GitHub URL: {url!r}")
    for branch in ("main", "master"):
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
        debug(f"Downloading {zip_url}")
        zpath = dest_dir / f"{repo}-{branch}.zip"
        try:
            subprocess.run(["curl", "-L", "-o", str(zpath), zip_url], check=True)
            shutil.unpack_archive(str(zpath), str(dest_dir))
            for child in dest_dir.iterdir():
                if child.is_dir() and child.name.startswith(f"{repo}-"):
                    debug(f"Using repo at: {child}")
                    return child
        except subprocess.CalledProcessError:
            continue
        except Exception as e:
            debug(f"Zip fetch/extract failed for {branch}: {e}")
            continue
    raise FileNotFoundError("Could not download GitHub zip for branches 'main' or 'master'.")

def git_clone(url: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    debug(f"Cloning {url} -> {dest_dir}")
    subprocess.run(["git", "clone", "--depth", "1", url, str(dest_dir)], check=True)
    return dest_dir

def get_repo(src: str) -> Path:
    src_path = Path(src)
    if src_path.exists():
        return src_path.resolve()
    if is_github_url(src):
        tmp = Path(tempfile.mkdtemp(prefix="nf_repo_zip_"))
        try:
            return download_github_zip(src, tmp)
        except Exception:
            tmp2 = Path(tempfile.mkdtemp(prefix="nf_repo_git_"))
            return git_clone(src, tmp2)
    if src.startswith(("http://", "https://")) or src.endswith(".git"):
        tmp = Path(tempfile.mkdtemp(prefix="nf_repo_git_"))
        return git_clone(src, tmp)
    raise FileNotFoundError(f"Can't resolve src {src!r} as local path or repo URL.")

# -------------------------- file loading --------------------------

def slurp_nf_texts(repo_dir: Path) -> dict:
    texts = {}
    for p in repo_dir.rglob("*.nf"):
        try:
            texts[str(p.relative_to(repo_dir))] = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
    return texts

def slurp_config_texts(repo_dir: Path) -> dict:
    """
    Container configs (exclude slurm.config here):
      1) configs/local.config
      2) nextflow.config
      3) conf/*.config
      4) configs/*.config (excluding local.config)
    """
    texts = {}
    def add_cfg(path: Path, key: str):
        try:
            texts[key] = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    local_cfg = repo_dir / "configs" / "local.config"
    if local_cfg.exists():
        add_cfg(local_cfg, "configs/local.config")
    root_cfg = repo_dir / "nextflow.config"
    if root_cfg.exists():
        add_cfg(root_cfg, str(root_cfg.relative_to(repo_dir)))
    conf_dir = repo_dir / "conf"
    if conf_dir.exists():
        for p in sorted(conf_dir.rglob("*.config")):
            if p.name == "slurm.config":
                continue
            add_cfg(p, str(p.relative_to(repo_dir)))
    configs_dir = repo_dir / "configs"
    if configs_dir.exists():
        for p in sorted(configs_dir.rglob("*.config")):
            if p.name in ("local.config", "slurm.config"):
                continue
            add_cfg(p, str(p.relative_to(repo_dir)))
    return texts

def slurp_slurm_config(repo_dir: Path) -> dict:
    """Load only slurm config text (used for cpus/memory/time when executor='slurm')."""
    texts = {}
    for candidate in [
        repo_dir / "configs" / "slurm.config",
        repo_dir / "conf" / "slurm.config",
        repo_dir / "slurm.config",
    ]:
        if candidate.exists():
            try:
                texts[str(candidate.relative_to(repo_dir))] = candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
    return texts

# -------------------------- NF parsing --------------------------

def split_sections(body: str) -> dict:
    sections = {}
    matches = list(SECTION_RE.finditer(body))
    if not matches:
        return sections
    for i, m in enumerate(matches):
        name = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[name] = body[start:end].rstrip()
    return sections

def extract_script_text(script_like: str) -> str:
    if not script_like:
        return ""
    m = TRIPLE_QUOTE_RE.search(script_like)
    if m:
        return (m.group(1) or m.group(2) or "").strip("\n")
    return script_like.strip("\n")

def parse_labels(body: str) -> set:
    labels = set()
    for m in LABEL_RE.finditer(body):
        raw = m.group(1)
        parts = [x.strip() for x in raw.split(",") if x.strip()]
        labels.update(parts)
    return labels

def parse_processes(text: str) -> list:
    procs = []
    for m in PROCESS_RE.finditer(text):
        name = m.group(1)
        body = m.group(2)
        sections = split_sections(body)
        p_container = None
        mcontline = CONTAINER_LINE_RE.search(body)
        if mcontline:
            rhs = mcontline.group(1).split("//", 1)[0].strip()
            rhs = _strip_quotes(rhs)
            p_container = rhs
        procs.append({
            "name": name,
            "container": p_container,
            "labels": parse_labels(body),
            "input": sections.get("input", ""),
            "output": sections.get("output", ""),
            "script": extract_script_text(sections.get("script", sections.get("shell", sections.get("exec", "")))),
        })
    return procs

# -------------------------- container config parsing --------------------------

def _strip_quotes(s: str) -> str:
    s = s.strip()
    s = re.sub(r'[;\s]+$', '', s)
    if (len(s) >= 2) and ((s[0] == s[-1]) and s[0] in ("'", '"')):
        s = s[1:-1]
    return s.strip()

def _resolve_container_value(val: str, containers_map: dict) -> str:
    if not val:
        return val
    v = _strip_quotes(val)
    if v.startswith("${") and v.endswith("}"):
        v = v[2:-1].strip()
    m = re.match(r'(?:(?:params\.)?containers\.)([A-Za-z_][A-Za-z0-9_-]*)$', v)
    if m:
        key = m.group(1).lower()
        if key in containers_map:
            return containers_map[key]
    return v

def _name_from_match(m: re.Match) -> str:
    for i in (1, 2, 3):
        g = m.group(i)
        if g:
            return g
    return ""

def parse_config_containers(texts: dict):
    global_c_raw = None
    withname_raw = {}
    withlabel_raw = {}
    containers_map = {}
    for _, txt in texts.items():
        for block in CONTAINERS_MAP_BLOCK_RE.findall(txt):
            for k, v in MAP_PAIR_RE.findall(block):
                key = k.lower()
                if key not in containers_map:
                    containers_map[key] = v
        for k, v in CONTAINERS_DOT_ASSIGN_RE.findall(txt):
            key = k.lower()
            if key not in containers_map:
                containers_map[key] = v
        for m in WITHNAME_RE.finditer(txt):
            name = _name_from_match(m).lower()
            # find the block body with brace balancing
            body = _extract_balanced_block(txt, m.end())
            if body is None:
                continue
            mcont = CONTAINER_LINE_RE.search(body)
            if mcont and name not in withname_raw:
                rhs = mcont.group(1).split("//", 1)[0].strip()
                rhs = _strip_quotes(rhs)
                withname_raw[name] = rhs
        for m in WITHLABEL_RE.finditer(txt):
            lbl = _name_from_match(m).lower()
            body = _extract_balanced_block(txt, m.end())
            if body is None:
                continue
            mcont = CONTAINER_LINE_RE.search(body)
            if mcont and lbl not in withlabel_raw:
                rhs = mcont.group(1).split("//", 1)[0].strip()
                rhs = _strip_quotes(rhs)
                withlabel_raw[lbl] = rhs
        mg = GLOBAL_CONTAINER_ANY_RE.search(txt)
        if mg and not global_c_raw:
            rhs = mg.group(1).split("//", 1)[0].strip()
            rhs = _strip_quotes(rhs)
            global_c_raw = rhs
    return global_c_raw, withname_raw, withlabel_raw, containers_map

# -------------------------- slurm parsing (brace-balanced) --------------------------

def _extract_balanced_block(text: str, start_pos: int) -> str | None:
    """
    Given a position right before a '{' (or right after the 'withName:...' match),
    find the next '{' and return the brace-balanced body between that '{' and its matching '}'.
    Returns None if no proper block was found.
    """
    # find the first '{' after start_pos
    i = text.find('{', start_pos)
    if i == -1:
        return None
    depth = 0
    j = i
    while j < len(text):
        c = text[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                # return inside without outer braces
                return text[i+1:j]
        j += 1
    return None

def parse_slurm_overrides(texts: dict):
    """
    Return two dicts (withname_map, withlabel_map) mapping process-name/label -> {'cpus','memory','time'}
    Works for top-level or nested blocks thanks to brace-balanced parsing.
    """
    name_map = {}
    label_map = {}

    def clean_rhs(val: str):
        if val is None:
            return None
        v = val.strip()
        v = v.split("//", 1)[0].strip()
        v = re.sub(r'[;\s]+$', '', v)
        v = _strip_quotes(v)
        return v

    def parse_body(body: str):
        if not EXECUTOR_RE.search(body):
            return None
        d = {}
        cpus = CPUS_FIELD_RE.search(body)
        mem  = MEM_FIELD_RE.search(body)
        tim  = TIME_FIELD_RE.search(body)
        if cpus:
            raw = clean_rhs(cpus.group(1))
            d["cpus"] = int(raw) if raw and re.fullmatch(r"\d+", raw) else raw
        if mem:
            d["memory"] = clean_rhs(mem.group(1))
        if tim:
            d["time"] = clean_rhs(tim.group(1))
        return d or None

    for _, txt in texts.items():
        # scan all withName blocks
        for m in WITHNAME_RE.finditer(txt):
            key = _name_from_match(m).lower()
            body = _extract_balanced_block(txt, m.end())
            if body is None:
                continue
            d = parse_body(body)
            if d:
                name_map[key] = d
        # scan all withLabel blocks
        for m in WITHLABEL_RE.finditer(txt):
            key = _name_from_match(m).lower()
            body = _extract_balanced_block(txt, m.end())
            if body is None:
                continue
            d = parse_body(body)
            if d and key not in label_map:
                label_map[key] = d

    return name_map, label_map

# -------------------------- transformations --------------------------

def transform_text_for_templates(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"\$\{params\.([A-Za-z_][A-Za-z0-9_]*)\}", r"{{\1}}", s)
    s = re.sub(r"\$\{task\.cpus\}", r"{{cpus}}", s)
    s = s.replace("\\$", "$")
    return s

def extract_template_vars(text: str) -> set:
    return set(TEMPLATE_VAR_RE.findall(text or ""))

# -------------------------- emitters --------------------------

MODULE_TEMPLATE = """import jawm
import os

# Auto-generated from Nextflow by nf_to_jawm.

{process_defs}

if __name__ == "__main__":
    import sys
    from jawm.utils import workflow
    from pathlib import Path

    workflows, var, args, unknown_args = jawm.utils.parse_arguments(['main','{module_tag}','test'])

    if workflow(["main","{module_tag}","test"], workflows):

{explicit_chain}
        jawm.Process.wait()

    if workflow("test", workflows):

        with open(os.path.join(var["project_folder"], "test.txt"), 'w') as out:
            out.write("Test completed.")

        # for the test workflow we might also do something more
        print("Test completed.")
"""

def _make_explicit_chain(proc_names):
    indent = " " * 8
    if not proc_names:
        return f"{indent}# (no processes discovered)"
    lines = [f"{indent}{proc_names[0]}.execute()"]
    for prev, cur in zip(proc_names[:-1], proc_names[1:]):
        lines.append(f"{indent}{cur}.execute({prev}.hash)")
    return "\n".join(lines)

def _format_manager_slurm(d: dict) -> str:
    if not d:
        return ""
    items = []
    if "cpus" in d and d["cpus"] is not None:
        items.append(f'"-c": {d["cpus"]}' if isinstance(d["cpus"], int) else f'"-c": "{transform_text_for_templates(str(d["cpus"]))}"')
    if "memory" in d and d["memory"]:
        items.append(f'"--mem": "{transform_text_for_templates(str(d["memory"]))}"')
    if "time" in d and d["time"]:
        items.append(f'"-t": "{transform_text_for_templates(str(d["time"]))}"')
    if not items:
        return ""
    return "{ " + ", ".join(items) + " }"

def write_module(out_dir: Path, module_name: str, processes: list):
    code_blocks = []
    proc_names = []
    for p in processes:
        script = transform_text_for_templates(p.get("script", "") or "")
        script = re.sub(r'^\s*[\'"]{3}', '', script)
        script = re.sub(r'[\'"]{3}\s*$', '', script)
        script = script.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
        script = textwrap.dedent(script) or "# (no script section found)"

        container = transform_text_for_templates(p.get("container") or "")
        mslurm = _format_manager_slurm(p.get("manager_slurm"))

        # --- NEW: collect per-process variables for desc={} ---
        vars_in_proc = set()
        vars_in_proc.update(extract_template_vars(script))
        vars_in_proc.update(extract_template_vars(container))
        if p.get("manager_slurm"):
            for key in ("cpus", "memory", "time"):
                v = p["manager_slurm"].get(key)
                if isinstance(v, str):
                    vars_in_proc.update(extract_template_vars(transform_text_for_templates(v)))

        # format desc block (always present, even if empty)
        if vars_in_proc:
            desc_entries = ",\n        ".join([f'"{k}": ""' for k in sorted(vars_in_proc)])
        else:
            desc_entries = ""
        desc_block = f",\n    desc={{\n        {desc_entries}\n    }}"

        # >>> CHANGED: insert when=True immediately before script
        block = (
            f"{p['name']}=jawm.Process(\n"
            f"    name=\"{p['name']}\",\n"
            f"    when=True,\n"
            f"    script=\"\"\"\\\n{script}\n\"\"\"{desc_block},\n"
            f"    container=\"{container}\""
        )
        if mslurm:
            block += f",\n    manager_slurm={mslurm}"
        block += "\n)"
        code_blocks.append(block)
        proc_names.append(p["name"])

    explicit_chain = _make_explicit_chain(proc_names)
    code = MODULE_TEMPLATE.format(
        process_defs="\n\n".join(code_blocks),
        module_tag=module_name,
        explicit_chain=explicit_chain
    )
    mod_path = out_dir / f"{module_name}.py"
    mod_path.write_text(code, encoding="utf-8")
    return mod_path

def write_yaml_scaffold(out_dir: Path, params: set):
    yml_dir = out_dir / "yaml"
    yml_dir.mkdir(parents=True, exist_ok=True)
    vars_lines = [
        "- scope: global",
        '  environment: "docker"',
        "  parallel: false",
        "  var:"
    ]
    if params:
        for k in sorted(params):
            vars_lines.append(f'    {k}: ""  # from params.* or {{ {k} }} placeholders')
    else:
        vars_lines.append("    # add key:value vars here; mapped from Nextflow params.* or {{var}} placeholders")
    (yml_dir / "vars.yaml").write_text("\n".join(vars_lines) + "\n", encoding="utf-8")

    docker_lines = [
        "- scope: global",
        "  docker:",
        "    enabled: true",
        "    pulls: false",
        "    mounts:",
        "      - /tmp:/tmp"
    ]
    (yml_dir / "docker.yaml").write_text("\n".join(docker_lines) + "\n", encoding="utf-8")

def write_test_scaffold(out_dir: Path, module_name: str):
    tests_dir = out_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_py = f'''# minimal smoke test for {module_name}
import importlib

def test_import():
    m = importlib.import_module("{module_name}")
    attrs = [a for a in dir(m) if not a.startswith("_")]
    assert any(attrs), "No public symbols found"
'''
    (tests_dir / f"test_{module_name}.py").write_text(test_py, encoding="utf-8")

def write_readme(out_dir: Path, module_name: str, src: str):
    module_name_=module_name.split('nf_')[-1].split("_main")[0]
    txt = f"""# jawm_{module_name_}_mirror

This is an automated jawm mirror of a nexflow-{module_name_}.

You will have to control and correct the code.

Initiate a jawm_{module_name_} somewhere else to have a full jawm backbone:
```
cd ~/
jawm-dev init {module_name_}
```
"""
    (out_dir / "README.md").write_text(txt, encoding="utf-8")


def write_raven_yaml(out_dir: Path, processes: list):
    """
    Write yaml/raven.yaml with:
      - a hardcoded global block for the Raven cluster (apptainer + slurm)
      - per-process blocks:
         * if process has NO manager_slurm -> manager: local
         * if process HAS manager_slurm and its script contains {{cpus}} and slurm cpus is numeric,
           then write var.cpus = double(slurm cpus) as a string
    """
    yml_dir = out_dir / "yaml"
    yml_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    # hardcoded global raven block
    lines.extend([
        "- scope: global",
        "  before_script: 'module load apptainer'",
        '  environment: "apptainer"',
        '  environment_apptainer: { "-B":"/nexus:/nexus" }',
        "  manager: slurm",
        '  manager_slurm: { "-p":"general,small" , "--ntasks-per-core":2 }',
        "",
    ])

    def is_numeric(val):
        if isinstance(val, int):
            return True
        if isinstance(val, str) and val.strip().isdigit():
            return True
        return False

    def to_int(val):
        return val if isinstance(val, int) else int(val.strip())

    for p in processes:
        name = p["name"]
        script = p.get("script") or ""
        mslurm = p.get("manager_slurm") or {}

        # Case 1: no slurm manager for the process -> force local
        if not mslurm:
            lines.extend([
                "- scope: process",
                f"  name: {name}",
                "  manager: local",
                "",
            ])
            continue

        # Case 2: has slurm manager -> maybe set doubled cpus if {{cpus}} is used AND cpus numeric
        uses_cpus_var = "{{cpus}}" in script
        cpus_val = mslurm.get("cpus", None)
        if uses_cpus_var and is_numeric(cpus_val):
            doubled = to_int(cpus_val) * 2
            lines.extend([
                "- scope: process",
                f"  name: {name}",
                "  var:",
                f"    cpus: '{doubled}'",
                "",
            ])
        # If cpus not numeric or {{cpus}} not used, we don't add a block here:
        # global slurm settings apply.

    (yml_dir / "raven.yaml").write_text("\n".join(lines), encoding="utf-8")


def write_studio_yaml(out_dir: Path, processes: list):
    """
    Write yaml/studio.yaml with:
      - hardcoded global block (apptainer + slurm on studio)
      - per-process blocks:
         * if NO manager_slurm -> manager: local
         * if HAS manager_slurm AND script uses {{cpus}} AND slurm cpus is numeric,
           then var.cpus = slurm cpus (same value, not doubled)
    """
    yml_dir = out_dir / "yaml"
    yml_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    # hardcoded global studio block
    lines.extend([
        "- scope: global",
        '  environment: "apptainer"',
        '  environment_apptainer: { "-B":"/nexus:/nexus" }',
        "  manager: slurm",
        '  manager_slurm: { "-p":"cluster,dedicated" }',
        "",
    ])

    def is_numeric(val):
        if isinstance(val, int):
            return True
        if isinstance(val, str) and val.strip().isdigit():
            return True
        return False

    def to_int(val):
        return val if isinstance(val, int) else int(val.strip())

    for p in processes:
        name = p["name"]
        script = p.get("script") or ""
        mslurm = p.get("manager_slurm") or {}

        # If no slurm manager -> force local
        if not mslurm:
            lines.extend([
                "- scope: process",
                f"  name: {name}",
                "  manager: local",
                "",
            ])
            continue

        # If has slurm manager and script uses {{cpus}}, set cpus to SAME value as slurm
        uses_cpus_var = "{{cpus}}" in script
        cpus_val = mslurm.get("cpus", None)
        if uses_cpus_var and is_numeric(cpus_val):
            same = to_int(cpus_val)
            lines.extend([
                "- scope: process",
                f"  name: {name}",
                "  var:",
                f"    cpus: '{same}'",
                "",
            ])
        # else: rely on global slurm, no per-process block

    (yml_dir / "studio.yaml").write_text("\n".join(lines), encoding="utf-8")

def write_build_yaml(out_dir: Path):
    """
    Write yaml/build.yaml — static configuration for the build machine.
    """
    yml_dir = out_dir / "yaml"
    yml_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# this is an extra yaml that we require",
        "# when using our build machine",
        "- scope: global",
        "  automated_mount: False",
        "  docker_run_as_user: True",
        "  environment_docker:",
        '      "-v": ["/nexus:/nexus"]',
        "",
    ]
    (yml_dir / "build.yaml").write_text("\n".join(lines), encoding="utf-8")


# -------------------------- main --------------------------

def main():
  ap = argparse.ArgumentParser(description="Convert a Nextflow repo (URL or path) into a JAWM mirror.")
  ap.add_argument("--src", required=True, help="GitHub URL, git URL, or local path to a Nextflow repo")
  ap.add_argument("--out", help="Output directory for the generated JAWM mirror "
                              "(default: repo name with 'nf-' -> 'jawm_' and '_mirror' appended)")  
  ap.add_argument("--module", help="Python module name to generate (default: derived from repo name)")
  args = ap.parse_args()

  repo = get_repo(args.src)
  debug(f"Using repo at: {repo}")

  # --- derive default output folder if not provided ---
  repo_name = Path(repo).name
  # Strip branch suffixes like "-main", "-master", or trailing "-something"
  repo_base = re.sub(r"[-_](main|master|dev|nextflow)$", "", repo_name)
  # Replace leading "nf-" with "jawm_"
  repo_base = re.sub(r"^nf[-_]", "jawm_", repo_base)
  # Ensure it ends with "_mirror"
  default_out_name = f"{repo_base}_mirror"

  out_path = args.out or default_out_name

  nf_texts = slurp_nf_texts(repo)
  if not nf_texts:
      raise SystemExit("No .nf files found in the repository.")

  cfg_texts   = slurp_config_texts(repo)     # containers (local.config precedence)
  slurm_texts = slurp_slurm_config(repo)     # only for executor slurm overrides

  # Parse processes from .nf
  processes = []
  for rel, txt in nf_texts.items():
      procs = parse_processes(txt)
      if procs:
          debug(f"Found {len(procs)} processes in {rel}")
          processes.extend(procs)

  # Containers
  global_c_raw, withname_raw, withlabel_raw, containers_map = parse_config_containers(cfg_texts)

  # Slurm overrides (balanced)
  slurm_name, slurm_label = parse_slurm_overrides(slurm_texts)
  debug(f"Slurm overrides discovered: withName={len(slurm_name)}, withLabel={len(slurm_label)}")

  # Resolve container + attach slurm per process
  for p in processes:
      # container
      resolved = p.get("container")

      def resolve_val(val: str) -> str:
          if not val:
              return ""
          s = _resolve_container_value(val, containers_map)
          s = _strip_quotes(s)
          return s

      if not resolved:
          pname_lc = p["name"].lower()
          if pname_lc in withname_raw:
              resolved = resolve_val(withname_raw[pname_lc])
          if (not resolved) and p.get("labels"):
              for lbl in p["labels"]:
                  lbl_lc = lbl.lower()
                  if lbl_lc in withlabel_raw:
                      resolved = resolve_val(withlabel_raw[lbl_lc])
                      break
          if (not resolved) and p.get("labels"):
              for lbl in p["labels"]:
                  lbl_lc = lbl.lower()
                  if lbl_lc in containers_map:
                      resolved = containers_map[lbl_lc]
                      break
          if (not resolved) and pname_lc in containers_map:
              resolved = containers_map[pname_lc]
          if (not resolved) and global_c_raw:
              resolved = resolve_val(global_c_raw)

      p["container"] = transform_text_for_templates(resolved or "")

      # slurm manager overrides (name wins, label fills gaps)
      m = {}
      pname_lc = p["name"].lower()
      if pname_lc in slurm_name:
          m.update(slurm_name[pname_lc])
      if p.get("labels"):
          for lbl in p["labels"]:
              lbl_lc = lbl.lower()
              if lbl_lc in slurm_label:
                  for k, v in slurm_label[lbl_lc].items():
                      m.setdefault(k, v)
      p["manager_slurm"] = m or None
      if p["manager_slurm"]:
          dbg = []
          if "cpus" in p["manager_slurm"]:   dbg.append(f'cpus={p["manager_slurm"]["cpus"]}')
          if "memory" in p["manager_slurm"]: dbg.append(f'memory={p["manager_slurm"]["memory"]}')
          if "time" in p["manager_slurm"]:   dbg.append(f'time={p["manager_slurm"]["time"]}')
          debug(f"SLURM for {p['name']}: " + ", ".join(dbg))

  # Collect vars
  params = set()
  for txt in nf_texts.values():
      params.update(PARAMS_DOT_RE.findall(txt))
  for txt in cfg_texts.values():
      params.update(PARAMS_DOT_RE.findall(txt))
  for txt in slurm_texts.values():
      params.update(PARAMS_DOT_RE.findall(txt))

  template_vars = set()
  for p in processes:
      p["script"] = transform_text_for_templates(p["script"])
      template_vars.update(extract_template_vars(p["script"]))
      template_vars.update(extract_template_vars(p.get("container", "")))
      if p.get("manager_slurm"):
          for key in ("cpus", "memory", "time"):
              v = p["manager_slurm"].get(key)
              if isinstance(v, str):
                  template_vars.update(extract_template_vars(transform_text_for_templates(v)))

  all_vars = set(params) | template_vars
  debug(f"Vars for vars.yaml: {sorted(all_vars)}")
    
  out_dir = Path(out_path).resolve()
  out_dir.mkdir(parents=True, exist_ok=True)

  def sanitize(name: str) -> str:
      name = re.sub(r"[^A-Za-z0-9_]", "_", name)
      name = re.sub(r"_+", "_", name).strip("_")
      if not name:
          name = "module"
      if name[0].isdigit():
          name = "_" + name
      return name.lower()

  module_name = args.module or sanitize(Path(repo).name)

  _ = write_module(out_dir, module_name, processes)
  write_yaml_scaffold(out_dir, all_vars)
  write_raven_yaml(out_dir, processes)   # ← NEW
  write_studio_yaml(out_dir, processes)   # ← NEW
  write_build_yaml(out_dir)   # ← NEW
  # write_test_scaffold(out_dir, module_name)
  write_readme(out_dir, module_name, args.src)

  print(f"OK: wrote JAWM mirror to {out_dir}", file=sys.stderr)
  print(str(out_dir))

if __name__ == "__main__":
  main()
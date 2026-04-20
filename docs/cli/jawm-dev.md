# jawm-dev

`jawm-dev` is the developer companion to `jawm`. It provides utilities for module authors — scaffolding new modules from a template and inspecting what variables a module expects.

```bash
jawm-dev <command> [args]
```

Currently two commands are available: `init` and `lsvar` (there will be more devloper supporting commands soon).

---

### Commands

| Command | Description |
|---------|-------------|
| [`init`](#init) | Scaffold a new module from the `jawm_demo` template |
| [`lsvar`](#lsvar) | Extract `{{variable}}` placeholders from a module file |

---

## init

Scaffolds a new jawm module from the [`jawm_demo`](https://github.com/mpg-age-bioinformatics/jawm_demo) template. It downloads the template, renames all references to match your module name, initialises a Git repository, and optionally creates a private remote on GitHub, GitLab, or Gitea.

```bash
jawm-dev init <name> [flags]
```

### What it does

1. Downloads the `jawm_demo` template ZIP from GitHub
2. Extracts it into a new directory named `<prefix><name>` (default: `jawm_<name>`)
3. Renames the Python entry point, submodule directory and file, and all internal references to match your module name
4. Removes template-only files (`notebook.ipynb`, `notebook.py`, `simple.py`, etc.)
5. Cleans up the `README.md` and disables push/PR/schedule triggers in the CI workflow until you're ready
6. Initialises a Git repository, makes an initial commit, and (unless `--server local`) adds an SSH remote and pushes

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `name` | _(required)_ | Base module name. The repository and directory will be `<prefix><name>`, the Python file will be `<name>.py`. |
| `-s`, `--server` | `github.com` | Git server host. Use `local` to skip remote creation entirely. |
| `-u`, `--user` | `mpg-age-bioinformatics` | Git user or organisation for the remote. |
| `-p`, `--prefix` | `jawm_` | Repository/directory name prefix. |

### Examples

```bash
# Scaffold jawm_myproject/ on GitHub (default)
jawm-dev init myproject

# Scaffold on GitLab with your own org
jawm-dev init myproject --server gitlab.com --user my-org

# Scaffold on a self-hosted Gitea instance
jawm-dev init myproject --server gitea.example.org --user my-team

# Local only — no remote, no push
jawm-dev init myproject --server local

# Custom prefix: creates wf_myproject/ instead of jawm_myproject/
jawm-dev init myproject --prefix wf_
```

### What you get

After `jawm-dev init myproject` completes, you have a ready-to-use module directory:

```
jawm_myproject/
├── myproject.py                          # module entry point — edit this
├── submodules/
│   └── jawm_myproject_submodule/
│       └── myproject_submodule.py        # sub-module example
├── yaml/
│   ├── docker.yaml                       # Docker environment config
│   └── modules.yaml                      # module loading config
├── test/
│   ├── tests.txt                         # jawm-test definitions
│   └── data.txt                          # test data checksums
├── .github/workflows/
│   └── test.yaml                         # CI workflow (triggers disabled until you enable them)
└── README.md
```

Test it immediately:

```bash
cd jawm_myproject

# Run with Docker
jawm myproject.py -p ./yaml/docker.yaml

# Run the test workflow
jawm-test
```

### Remote repository creation

When `--server` is not `local`, `jawm-dev init` attempts to create a **private, empty** repository on the remote before pushing. How it authenticates depends on the platform:

| Platform | Method |
|----------|--------|
| GitHub | `gh` CLI (if installed), or `GITHUB_TOKEN` / `GH_TOKEN` env var |
| GitLab | `GITLAB_TOKEN` env var |
| Gitea | `GITEA_TOKEN` env var |
| Other hosts | No auto-create — the remote is added and push is attempted, but the repo must already exist |

If the remote repository already exists, `init` exits with an error rather than overwriting it.

If authentication is not available (no token, no `gh` CLI), the local directory and Git repository are still created — only the remote creation and push are skipped, with a warning.

---

## lsvar

Reads a jawm module file and extracts all `{{variable}}` placeholders used inside `Process` script blocks. Outputs them as a YAML list — one entry per Process — which you can use as a starting point for your `var` dictionaries.

```bash
jawm-dev lsvar <file>
```

### Output format

```yaml
- scope: process
  name: "bwa_align"
  var:
    genome: ""
    output_bam: ""
    reads_1: ""
    reads_2: ""
    threads: ""
- scope: process
  name: "fastqc"
  var:
    output_dir: ""
    reads_1: ""
    reads_2: ""
    threads: ""
```

Variables are sorted alphabetically. Empty string values (`""`) indicate slots that need to be filled — either in a `var={}` dict in the Process definition, via a `-v` YAML file, or via CLI override.

### Warnings and notes

`lsvar` also inspects the `desc={}` dictionary in each Process and reports mismatches to stderr:

- **WARNING** — a variable is used in the script (`{{variable}}`) but not listed in `desc`. This is a documentation gap — the variable works but has no description.
- **NOTE** — a variable is listed in `desc` but never used in the script. This might be a leftover or a typo in the placeholder name.

```bash
$ jawm-dev lsvar mymodule.py
WARNING: variable 'output_bam' used in script of process 'bwa_align' but not defined in desc{}
NOTE: variable 'output_file' defined in desc{} of process 'bwa_align' but not used in the script.
```

### Example

Given a module file:

```python
align = jawm.Process(
    name="bwa_align",
    script="""#!/bin/bash
set -euo pipefail
bwa mem -t {{threads}} {{genome}} {{reads_1}} {{reads_2}} \
  | samtools sort -o {{output_bam}}
""",
    var={"threads": "8", "genome": "", "reads_1": "", "reads_2": "", "output_bam": ""},
    desc={"threads": "CPU threads", "genome": "Reference genome path"},
)
```

Running `jawm-dev lsvar mymodule.py` outputs:

```yaml
- scope: process
  name: "bwa_align"
  var:
    genome: ""
    output_bam: ""
    reads_1: ""
    reads_2: ""
    threads: ""
```

### Limitations

`lsvar` uses static analysis — it parses the file as text rather than importing it. This means:

- It only finds `{{variable}}` placeholders in inline `script="""..."""` blocks. Variables in `script_file` external scripts are not detected
- Dynamically constructed script strings (e.g. `script=f"..."` or `script=build_script()`) may not be parsed correctly
- Process definitions spread across multiple files or generated programmatically are not followed

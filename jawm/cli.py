import argparse
import runpy
import sys
import os
import glob
import hashlib
import logging
import datetime
import io
import atexit
import threading
import time
import yaml
import fnmatch
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
import tarfile
import shutil
import traceback
import platform
import json
from pathlib import Path


# ------------------------------------------------------------
#   Version detection (module scope)
# ------------------------------------------------------------
try:
    from importlib import metadata as md  # py>=3.8
except Exception:
    import importlib_metadata as md

_PKG_NAME = (__package__ or "jawm").split(".")[0]

try:
    _VERSION = md.version(_PKG_NAME)
except md.PackageNotFoundError:
    _VERSION = "dev"  
# ------------------------------------------------------------
#   End of version detection (module scope)
# ------------------------------------------------------------


# ------------------------------------------------------------
#   Logging and teeing
# ------------------------------------------------------------
def _start_global_tee(path, mode="a"):
    """
    Mirror everything written to sys.stdout and sys.stderr to the given file,
    while still showing it on the real terminal. Lives until process exit.
    """
    f = open(path, mode, buffering=1, encoding="utf-8")  # line-buffered

    class _Tee(io.TextIOBase):
        def __init__(self, stream, file_obj, lock=None):
            self.stream = stream
            self.file = file_obj
            self.lock = lock or threading.Lock()
        def write(self, data):
            # write to both console and file atomically to preserve ordering
            with self.lock:
                # console side (keep strict)
                self.stream.write(data)
                self.stream.flush()
                # file side (be tolerant at shutdown)
                try:
                    if not getattr(self.file, "closed", False):
                        self.file.write(data)
                        self.file.flush()
                except Exception:
                    pass
            return len(data)

        def flush(self):
            with self.lock:
                try:
                    self.stream.flush()
                except Exception:
                    pass
                try:
                    if not getattr(self.file, "closed", False):
                        self.file.flush()
                except Exception:
                    pass
        def isatty(self):
            # preserve TTY semantics for libraries that check this
            return getattr(self.stream, "isatty", lambda: False)()

        def writable(self):
            return True

        def fileno(self):
            # some libs probe fileno(); prefer the real stream,
            # fall back to the logfile if needed
            try:
                return self.stream.fileno()
            except Exception:
                return self.file.fileno()

    lock = threading.Lock()
    # Redirect program-visible stdio to Tee that writes to the real console and the file
    sys.stdout = _Tee(sys.__stdout__, f, lock)
    sys.stderr = _Tee(sys.__stderr__, f, lock)

    # Make sure unhandled exceptions in threads are printed to stderr (captured by tee)
    def _thread_excepthook(args):
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = _thread_excepthook

    @atexit.register
    def _cleanup():
        # flush & restore real stdio so other atexit handlers behave
        try:
            sys.stdout.flush(); sys.stderr.flush()
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            f.close()


class _EmojiFormatter(logging.Formatter):
        EMOJI_MAP = {
            logging.ERROR: "❌",
            logging.WARNING: "⚠️",
            logging.CRITICAL: "🚨",
        }
        def format(self, record):
            emoji = self.EMOJI_MAP.get(record.levelno, "")
            record.msg = f"{emoji}  {record.msg}" if emoji else record.msg
            return super().format(record)            
# ------------------------------------------------------------
#   End of logging and teeing
# ------------------------------------------------------------


# ------------------------------------------------------------
#   Git related vars and method
# ------------------------------------------------------------
GIT_PAT = re.compile(
    r"""
    ^(?P<scheme>(?:https://|ssh://|git@|gh:|file://)?)
    (?P<host_repo>
        (?:
            # HTTPS or SSH URL form (allow optional user@)
            (?:[\w\-.]+@)?[\w\-.]+(?:\.[\w\-.]+)+(?::\d+)?(?:/[~\w\-.]+){2,}(?:\.git)?
          | # SCP-like: git@host:org/repo(.git optional)
            [\w\-.]+:(?:[~\w\-.]+/){1,}[~\w\-.]+(?:\.git)?
          | # file:// absolute path
            file://(?:/[^\s@]+)+
          | # gh:org/repo shortcut
            gh:[\w\-.]+/[\w\-.]+
        )
    )
    (?:@(?P<ref>[\w./\-]+?))?             # optional @ref (non-greedy)
    (?:\/\/(?P<subdir>.*))?              # optional //subdir
    $
    """,
    re.X,
)

_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")

def _looks_like_sha(s):
    return bool(_SHA_RE.match(s or ""))


def _is_git_target(s):
    if os.path.exists(s):            # never treat existing paths as git
        return False
    return bool(GIT_PAT.match(s))


def _normalize_git_url(target):

    m = GIT_PAT.match(target)
    if not m:
        return None

    scheme   = m.group("scheme") or ""          # "https://", "git@", "ssh://", "gh:" or ""
    host_repo = m.group("host_repo")            # e.g. "github.com:org/repo.git"
    ref      = m.group("ref")                   # may accidentally include "//subdir"
    subdir   = (m.group("subdir") or "").strip("/")

    # If ref accidentally captured the //subdir, split it here.
    if ref and "//" in ref:
        ref, extra = ref.split("//", 1)
        subdir = (extra + ("/" + subdir if subdir else "")).strip("/")

    # gh: shortcut → https
    if host_repo.startswith("gh:") or scheme == "gh:":
        org_repo = host_repo.split(":", 1)[1] if host_repo.startswith("gh:") else host_repo
        url = f"https://github.com/{org_repo}"
        if not url.endswith(".git"):
            url += ".git"
        return url, ref, subdir

    # SSH / SCP forms
    if scheme == "git@":
        url = f"git@{host_repo}"
        return url, ref, subdir
    if scheme == "ssh://":
        url = f"ssh://{host_repo}"
        return url, ref, subdir

    # SCP-like without explicit scheme (e.g., "gitlab.com:group/repo")
    if (":" in host_repo) and (not host_repo.startswith("http")) and (not host_repo.startswith("ssh://")):
        return host_repo, ref, subdir

    # Default to HTTPS
    url = host_repo
    if not url.startswith("https://"):
        url = "https://" + url
    if not url.endswith(".git"):
        url += ".git"
    return url, ref, subdir


def _git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}\n{r.stderr or r.stdout}")
    return r


def _resolve_git_to_local(target, cache_root):
    """
    Resolve a git target to a local cached folder or subpath.

    External helpers assumed to exist:
      - _normalize_git_url(target) -> (url, ref, subpath)
      - _git(*args, cwd=None) -> subprocess.CompletedProcess
      - _looks_like_sha(s: str) -> bool   # checks hex-ness (not the length)
    """
    CACHE_TTL_SECS = 120  # 2 minutes for "no-ref" freshness

    url, ref, subpath = _normalize_git_url(target)

    tmp = Path(tempfile.mkdtemp(prefix="jawm_git_"))
    try:
        _git("clone", "--filter=blob:none", "--no-checkout", "--depth=1", url, str(tmp))

        _SCP_RE = re.compile(r'^(?:(?P<user>[\w\-.]+)@)?(?P<host>[\w\-.]+):(?P<path>.+)$')

        def sanitize_repo(u):
            s = u.strip()
            if '//' in s:
                s = s.split('//', 1)[1]
            else:
                if s.startswith('gh:'):
                    s = s[3:]
                else:
                    m = _SCP_RE.match(s)
                    if m:
                        s = f"{m.group('host')}/{m.group('path')}"
            s = re.sub(r'[^A-Za-z0-9_.\-/@]+', "_", s)
            s = s.replace("@", "/")
            s = re.sub(r'/+', '/', s)
            return s

        def _find_latest_cached_dir(base):
            """Return the newest 7-hex-named subdir (used only for no-ref caches)."""
            if not base.exists():
                return None
            candidates = [
                p for p in base.iterdir()
                if p.is_dir() and len(p.name) == 7 and all(c in "0123456789abcdef" for c in p.name.lower())
            ]
            if not candidates:
                return None
            return max(candidates, key=lambda p: p.stat().st_mtime)

        def _write_full_sha_marker(dest, full_sha):
            try:
                (dest / ".commit").write_text(full_sha + "\n", encoding="utf-8")
            except Exception:
                pass  # non-fatal

        def _folder_label(user_ref, full_sha):
            """
            Cache folder segment representing what the user asked for:
              - no ref      -> <shortsha>
              - commit-ish  -> <short-of-user-input>  (e.g., 'f5b27c5')
              - tag/branch  -> <sanitized-ref>@<shortsha>
            """
            short = full_sha[:7]
            if not user_ref:
                return short
            if _looks_like_sha(user_ref):
                return user_ref[:7]
            safe_ref = re.sub(r'[^A-Za-z0-9_.-]+', "_", user_ref)
            return f"{safe_ref}@{short}"

        def _rev_parse_commit(expr):
            r = subprocess.run(
                ["git", "rev-parse", f"{expr}^{{commit}}"],
                cwd=tmp, text=True, capture_output=True
            )
            return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

        def _resolve_short_sha(prefix):
            """
            Try to resolve a short SHA by fetching lightweight refs first,
            then progressively deepening history (blobless) until the prefix resolves.
            Returns a full 40-char SHA or None if not found within limits.
            """
            # 1) Fetch default refs (heads); try resolve
            _git("fetch", "--filter=blob:none", "--depth=1", "origin", cwd=tmp)
            full = _rev_parse_commit(prefix)
            if full:
                return full

            # 2) Fetch tags; try resolve
            _git("fetch", "--filter=blob:none", "--tags", "--depth=1", "origin", cwd=tmp)
            full = _rev_parse_commit(prefix)
            if full:
                return full

            # 3) Progressive deepen (no blobs) to find older commits
            for deepen in (32, 128, 512, 2048, 8192):
                r = subprocess.run(
                    ["git", "fetch", "--filter=blob:none", f"--deepen={deepen}", "origin"],
                    cwd=tmp, text=True, capture_output=True
                )
                # Ignore non-zero return; still try to resolve
                full = _rev_parse_commit(prefix)
                if full:
                    return full

            # 4) Last resort: unshallow (still blobless); can be heavy on very large repos
            r = subprocess.run(
                ["git", "fetch", "--filter=blob:none", "--unshallow", "origin"],
                cwd=tmp, text=True, capture_output=True
            )
            full = _rev_parse_commit(prefix)
            return full

        safe_repo = sanitize_repo(url)

        # --- Resolve the exact commit SHA we want ----------------------------
        sha = None

        if ref:
            if _looks_like_sha(ref):
                # Full SHA or abbreviated SHA: resolve by actually fetching/checking the object
                if len(ref) == 40:
                    sha = ref
                    # try to ensure object is present
                    r = subprocess.run(
                        ["git", "fetch", "--depth=1", "origin", sha],
                        cwd=tmp, text=True, capture_output=True
                    )
                    # even if that fails, do a regular fetch and verify below
                    _git("fetch", "--filter=blob:none", "--depth=1", "origin", cwd=tmp)
                    if not _rev_parse_commit(sha):
                        # grab tags/heads and try again
                        _git("fetch", "--filter=blob:none", "--tags", "--depth=1", "origin", cwd=tmp)
                        if not _rev_parse_commit(sha):
                            # deepen to try to reach it
                            sha2 = _resolve_short_sha(sha)
                            if not sha2:
                                raise RuntimeError("Commit not reachable from the remote.")
                            sha = sha2
                else:
                    # Abbreviated SHA → resolve by fetch/deepen until it resolves
                    sha = _resolve_short_sha(ref)
                    if not sha:
                        raise RuntimeError("Could not resolve the abbreviated commit.")
            else:
                # branch/tag
                _git("fetch", "--filter=blob:none", "--depth=1", "origin", ref, cwd=tmp)
                sha = _git("rev-parse", "FETCH_HEAD", cwd=tmp).stdout.strip()

        else:
            # No ref → try cache freshness before hitting the network
            repo_base = cache_root / safe_repo
            latest_cached = _find_latest_cached_dir(repo_base)
            if latest_cached is not None:
                age = time.time() - latest_cached.stat().st_mtime
                if age <= CACHE_TTL_SECS:
                    # Fresh → reuse immediately if it already has contents
                    dest = latest_cached
                    subpath_norm = (subpath or "").strip("/")
                    if subpath_norm:
                        target_path = dest / os.path.normpath(subpath_norm).replace("\\", "/")
                        if target_path.exists():
                            return target_path
                    if any(dest.iterdir()):
                        return dest
                    # Empty dir (rare). Try to read .commit for SHA; otherwise fetch below.
                    marker = dest / ".commit"
                    if marker.exists():
                        sha = marker.read_text(encoding="utf-8").strip()

            if not sha:
                # Fetch default refs to learn current default-branch commit
                _git("fetch", "--filter=blob:none", "--depth=1", "origin", cwd=tmp)
                r = subprocess.run(
                    ["git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"],
                    cwd=tmp, text=True, capture_output=True
                )
                if r.returncode == 0 and r.stdout.strip():
                    head_ref = r.stdout.strip()  # e.g. "origin/main"
                    sha = _git("rev-parse", f"{head_ref}^{{commit}}", cwd=tmp).stdout.strip()
                else:
                    for candidate in ("origin/main", "origin/master"):
                        rr = subprocess.run(
                            ["git", "rev-parse", f"{candidate}^{{commit}}"],
                            cwd=tmp, text=True, capture_output=True
                        )
                        if rr.returncode == 0 and rr.stdout.strip():
                            sha = rr.stdout.strip()
                            break
                    else:
                        raise RuntimeError("Could not determine default remote HEAD.")

        # Now that we have the full SHA, compute the destination folder
        label = _folder_label(ref, sha)
        dest = cache_root / safe_repo / label
        dest.mkdir(parents=True, exist_ok=True)

        # --- Normalize subpath and safety checks -----------------------------
        subpath = (subpath or "").strip("/")
        if subpath:
            norm = os.path.normpath(subpath).replace("\\", "/")
            if norm.startswith(".."):
                raise RuntimeError(f"Unsafe subpath: {subpath!r}")
            subpath = norm

        # === No subpath → full tree snapshot =================================
        if not subpath:
            # already exported?
            if any(dest.iterdir()):
                return dest
            # export whole tree
            proc = subprocess.run(
                ["git", "archive", "--format=tar", sha],
                cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if proc.returncode != 0:
                raise RuntimeError(f"git archive failed: {proc.stderr.decode().strip() or proc.stdout.decode().strip()}")
            with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
                tf.extractall(path=dest)
            _write_full_sha_marker(dest, sha)
            return dest

        # === Subpath present → return cached result if it already exists ======
        target_path = dest / subpath
        if target_path.exists():
            return target_path

        # Fast existence probe: does <sha>:<subpath> exist at all?
        exists_probe = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}:{subpath}"],
            cwd=tmp
        )
        if exists_probe.returncode != 0:
            # Build a helpful message listing near matches under the same directory (if any)
            parent = os.path.dirname(subpath)
            ls_cmd = ["git", "ls-tree", "--name-only", sha]
            if parent:
                ls_cmd = ["git", "ls-tree", "--name-only", f"{sha}:{parent}"]
            ls = subprocess.run(ls_cmd, cwd=tmp, text=True, capture_output=True)
            hint_list = ""
            if ls.returncode == 0 and ls.stdout.strip():
                lines = [ln.strip() for ln in ls.stdout.splitlines() if ln.strip()]
                if parent:
                    lines = [f"{parent}/{ln}" for ln in lines]
                hint_list = "\n  - " + "\n  - ".join(lines[:50])  # cap for safety
            raise RuntimeError(
                f"Path not found at commit {sha[:12]}: {subpath}\n"
                f"Check the exact path and whether it existed at that commit."
                f"{hint_list}"
            )

        # === Detect object type (blob or tree) ================================
        probe = subprocess.run(
            ["git", "cat-file", "-t", f"{sha}:{subpath}"],
            cwd=tmp, text=True, capture_output=True
        )
        objtype = probe.stdout.strip() if probe.returncode == 0 else None

        # --- Blob (single file) ----------------------------------------------
        if objtype == "blob":
            target_path.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(
                ["git", "show", f"{sha}:{subpath}"],
                cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if r.returncode != 0:
                raise RuntimeError(f"git show failed: {r.stderr.decode().strip() or r.stdout.decode().strip()}")
            with open(target_path, "wb") as f:
                f.write(r.stdout)
            _write_full_sha_marker(dest, sha)
            return target_path

        # --- Tree (directory) -------------------------------------------------
        if objtype == "tree" or objtype is None:
            proc = subprocess.run(
                ["git", "archive", "--format=tar", f"--prefix={subpath.rstrip('/')}/", f"{sha}:{subpath}"],
                cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"git export failed for {subpath!r} at {sha[:12]}:\n"
                    f"  cat-file: {probe.stderr.strip() if probe.stderr else '(no stderr)'}\n"
                    f"  archive:  {proc.stderr.decode().strip() or proc.stdout.decode().strip()}"
                )
            with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tf:
                tf.extractall(path=dest)
            _write_full_sha_marker(dest, sha)
            return target_path

        raise RuntimeError(f"Unsupported git object type for {subpath!r}: {objtype}")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _git_cache_root(cli_flag_path=None):
    """
    Return the cache root:
      - If CLI flag is ".", use "<cwd>/git".
      - Else if CLI flag is set, use it as-is (resolved).
      - Else if env JAWM_GIT_CACHE is ".", use "<cwd>/git".
      - Else if env JAWM_GIT_CACHE is set, use it as-is (resolved).
      - Else default to "~/.jawm/git".
    """
    def _normalize(p):
        # treat "." or "./" specially → <cwd>/git
        s = str(p)
        if s in (".", "./"):
            return Path.cwd() / "git"
        return p.expanduser().resolve()

    if cli_flag_path is not None:
        return _normalize(Path(cli_flag_path))

    env = os.getenv("JAWM_GIT_CACHE")
    if env:
        return _normalize(Path(env))

    return Path("~/.jawm/git").expanduser()


def _synth_git_target(module, server, user):
    """
    Build a git SSH target from server/user/module.
    Supports optional @ref suffix:
        repo
        repo@tag
        org/repo
        org/repo@commit
    """
    name, sep, ref = module.partition('@')

    # If user did not specify org, assume provided --user
    if '/' not in name:
        name = f"{user}/{name}"

    target = f"git@{server}:{name}.git"
    if sep:  # module had @ref
        target = f"{target}@{ref}"
    return target


def _parse_git_target(target):
    """
    Split a git target like 'org/repo@tag' into ('repo', 'tag' or None).
    """
    name = target.split("/")[-1]
    repo, sep, ref = name.partition("@")
    repo = repo.replace(".git", "")
    return repo, ref or None
# ------------------------------------------------------------
#   End of git related vars and method
# ------------------------------------------------------------


# ------------------------------------------------------------
#   Hashing helper methods
# ------------------------------------------------------------
def _collect_hash_cfg_from_param_sources_cli(param_sources):
    """
    Look through param file(s)/dir for entries with `scope: hash`
    and merge them into a single cfg.

    Returns a dict like:
    {
        "paths": [...],                # from `include` entries (glob/literal)
        "allowed_extensions": [...],   # or None
        "exclude_dirs": [...],         # or None
        "exclude_files": [...],        # or None
        "recursive": True/False,
        "overwrite": True/False,
        "reference": hash string/path
    }
    or {} if nothing found.
    """
    def _as_list(x):
        if not x: return []
        return x if isinstance(x, list) else [x]

    # Gather YAML files from -p (file/dir/list)
    yaml_files = []
    if not param_sources:
        return {}
    sources = param_sources if isinstance(param_sources, list) else [param_sources]
    for src in sources:
        src = os.path.abspath(str(src))
        if os.path.isdir(src):
            for f in os.listdir(src):
                if f.lower().endswith((".yaml", ".yml")):
                    yaml_files.append(os.path.join(src, f))
        elif os.path.isfile(src) and src.lower().endswith((".yaml", ".yml")):
            yaml_files.append(src)

    if not yaml_files:
        return {}

    # Merge all scope: hash entries
    merged = {
        "include": [],
        "allowed_extensions": None,
        "exclude_dirs": None,
        "exclude_files": None,
        "recursive": True,
        "overwrite": False,
        "reference": None
    }

    def _merge_list_field(key, new_val):
        if new_val is None:
            return
        existing = merged.get(key)
        if existing is None:
            merged[key] = _as_list(new_val)
        else:
            merged[key] = _as_list(existing) + _as_list(new_val)

    def _take_last_scalar(key, new_val):
        if new_val is not None:
            merged[key] = new_val

    for yf in yaml_files:
        try:
            data = yaml.safe_load(Path(yf).read_text()) or []
        except Exception:
            continue
        # Allow either a single dict or a list of dicts
        docs = data if isinstance(data, list) else [data]
        for entry in docs:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("scope", "")).lower() != "hash":
                continue
            # same schema as --hash YAML
            _merge_list_field("include", entry.get("include"))
            _take_last_scalar("allowed_extensions", entry.get("allowed_extensions"))
            _take_last_scalar("exclude_dirs", entry.get("exclude_dirs"))
            _take_last_scalar("exclude_files", entry.get("exclude_files"))
            _take_last_scalar("recursive", entry.get("recursive"))
            _take_last_scalar("overwrite", entry.get("overwrite"))
            _take_last_scalar("reference", entry.get("reference"))

    if not merged["include"]:
        return {}

    # Expand globs
    expanded, seen = [], set()
    for pat in _as_list(merged["include"]):
        hits = glob.glob(pat, recursive=True) or [pat]
        for h in hits:
            if h not in seen:
                expanded.append(h); seen.add(h)

    return {
        "paths": expanded,
        "allowed_extensions": merged["allowed_extensions"],
        "exclude_dirs": merged["exclude_dirs"],
        "exclude_files": merged["exclude_files"],
        "recursive": True if merged["recursive"] is None else bool(merged["recursive"]),
        "overwrite": False if merged["overwrite"] is None else bool(merged["overwrite"]),
        "reference": merged.get("reference"),
    }


def _resolve_reference_hash_cli(ref):
    """
    Resolve a reference to a SHA-256 hex string.
    - If 'ref' is a readable file path, read its first non-empty line.
    - Else, treat 'ref' as a literal hash string.
    Returns a normalized lowercase hex string, or None if invalid.
    """
    candidate = None
    try:
        if isinstance(ref, str) and os.path.isfile(ref):
            txt = Path(ref).read_text(encoding="utf-8", errors="ignore")
            for line in txt.splitlines():
                line = line.strip()
                if line:
                    candidate = line
                    break
        else:
            candidate = str(ref).strip()
    except Exception:
        return None

    if not candidate:
        return None

    h = candidate.lower().strip()
    # allow optional "sha256:" prefix
    if h.startswith("sha256:"):
        h = h.split(":", 1)[1].strip()

    # minimal validation for sha256
    if re.fullmatch(r"[0-9a-f]{64}", h):
        return h
    return None

def _enumerate_hash_inputs_cli(paths, *, allowed_extensions=None, exclude_dirs=None, exclude_files=None, recursive=True):
    """
    Return a sorted list of concrete files that would be considered for hashing,
    using the same policy (ext filter, exclude lists, recursion) as hash_content.
    """
    if paths is None:
        return []
    if isinstance(paths, (str, Path)):
        paths = [paths]

    allowed_exts = None
    if allowed_extensions:
        allowed_exts = set(("." + e.lower().lstrip(".")) for e in allowed_extensions)

    exclude_dirs = exclude_dirs or []
    exclude_files = exclude_files or []

    collected = []

    def _file_ok(fname):
        base = os.path.basename(fname)
        if any(fnmatch.fnmatch(base, pat) for pat in exclude_files):
            return False
        if allowed_exts is not None:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in allowed_exts:
                return False
        return True

    for p in paths:
        p = os.path.abspath(str(p))
        if os.path.isfile(p):
            if _file_ok(p):
                collected.append(p)
        elif os.path.isdir(p):
            if recursive:
                for root, dirs, files in os.walk(p):
                    # apply dir excludes (by name pattern)
                    dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d, pat) for pat in (exclude_dirs or []))]
                    for f in files:
                        fp = os.path.join(root, f)
                        if _file_ok(fp):
                            collected.append(fp)
            else:
                for f in os.listdir(p):
                    fp = os.path.join(p, f)
                    if os.path.isfile(fp) and _file_ok(fp):
                        collected.append(fp)
        else:
            # ignore non-existent, same as the hasher
            continue

    return sorted(set(collected))


def _default_hash_output_path_cli(logs_dir, module_path):
    """
    Default hash file under <logs_dir>/jawm_hashes/<module_stem>.hash
    (single canonical location to compare runs).
    """
    wf_stem = os.path.splitext(os.path.basename(module_path))[0]
    out_dir = os.path.join(os.path.abspath(logs_dir), "jawm_hashes")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{wf_stem}.hash")


def _input_history_path_cli(logs_dir, module_path):
    """
    Always-written auto history:
    <logs_dir>/jawm_hashes/<module>_input.history
    """
    wf_stem = os.path.splitext(os.path.basename(module_path))[0]
    out_dir = os.path.join(os.path.abspath(logs_dir), "jawm_hashes")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{wf_stem}_input.history")


def _user_defined_history_path_cli(logs_dir, module_path):
    """
    Written only when -p contains `scope: hash`:
    <logs_dir>/jawm_hashes/<module>_user_defined.history
    """
    wf_stem = os.path.splitext(os.path.basename(module_path))[0]
    out_dir = os.path.join(os.path.abspath(logs_dir), "jawm_hashes")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{wf_stem}_user_defined.history")


def _append_history_line_cli(logger, history_path, ts, hash_value, log_file, files_csv="-", user_provided=False):
    """
    Append: "<timestamp>\t<hash>\t<cli_log_file>\t<comma_separated_files>"
    to the given history file path.
    """
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(f"{ts}\t{hash_value}\t{log_file}\t{files_csv}\n")
    if user_provided:
        logger.info(f"[hash] Appended history based on user definitions → {history_path}")


def _write_and_compare_hash_cli(logger, hash_value, out_path, overwrite=False):
    """
    Compare with existing file (if any), print a clear log, and write the new hash.
    Returns True if written or matched, False if mismatch (but still writes).
    """
    outp = Path(out_path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    matched = True
    new = True
    if outp.exists():
        stored = outp.read_text().strip()
        new = False
        if stored != hash_value:
            matched = False
            # Required: log mismatch to CLI output
            logger.warning(f"[hash] Mismatch for {outp.name}: \nStored={stored} \nComputed={hash_value}")
        else:
            logger.info(f"[hash] Matches existing file {outp.name}")
    if not outp.exists() or overwrite:
        outp.write_text(hash_value + "\n")
        logger.info(f"[hash] Wrote current hash to: {outp}")
    return matched, new


def _compute_run_hash_from_process_prefixes_cli():
    """
    Default/auto mode: use the first 6 chars of *executed* Processes' hashes.

    We read them via the public API to avoid reaching into internals.
    Deterministic: sort prefixes; hash the concatenated string.
    """
    try:
        from jawm import Process
    except Exception:
        return None  # jawm not available; likely shouldn't happen

    items = Process.list_all()  # [{name, hash, log_path, finished, ...}, ...]
    prefixes = []
    for p in items:
        h = p.get("hash")
        # consider "executed" as those that have an execution_start timestamp
        if not h:
            continue
        # keep those that actually ran (have an exit code OR are marked finished)
        # This still includes successful/failed/skipped, which is fine for a run signature.
        prefixes.append(str(h)[:6])

    if not prefixes:
        return None

    prefixes = sorted(set(prefixes))
    payload = "\n".join(prefixes).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()   
# ------------------------------------------------------------
#   End of hashing helper methods
# ------------------------------------------------------------


# ------------------------------------------------------------
#   Start of recording stats helper methods
# ------------------------------------------------------------

def _collect_stats_op(Process, logger, stop_event):
    """
    Periodically collect active processes and run stats collecting operations by manager.

    Structure:
        { manager: { proc.runtime_id: proc.log_path } }
    """
    try:
        interval = float(os.getenv("JAWM_STATS_INTERVAL", "30"))
        if interval < 5:
            interval = 5
    except Exception:
        interval = 30

    while not stop_event.is_set():
        try:
            grouped = {}

            for proc in list(Process.registry.values()):
                if not isinstance(proc, Process):
                    continue
                if proc.finished_event.is_set():
                    continue
                if not proc.manager or not proc.log_path:
                    continue
                rid = getattr(proc, "runtime_id", None)
                if not rid:
                    continue

                grouped.setdefault(proc.manager, {})[str(rid)] = proc.log_path

            # Dispatch manager-specific collectors if implemented
            for manager, items in grouped.items():
                if not items:
                    continue

                func_name = f"_collect_stats_{manager}"
                collector = globals().get(func_name)

                if callable(collector):
                    try:
                        collector(items, logger)
                    except Exception as e:
                        logger.debug("[stats] %s failed: %s", func_name, e)

        except Exception as e:
            logger.debug("[stats] error while stats collection: %s", e)

        # waits up to interval, but returns immediately if stop_event is set
        stop_event.wait(interval)


def _atomic_write_json(path, obj, logger=None):
    """
    Atomic JSON write: write to <path>.tmp then os.replace to final path.
    """
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, path)
        return True
    except Exception as e:
        if logger:
            logger.debug("[stats] atomic write failed: %s -> %s : %s", tmp, path, e)
        # best-effort tmp cleanup
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False

########## Methods for local stats collection ##########

# Helper for local stats collection
def _ps_sample_many(pids, timeout_s=1.0):
    """
    Batch-sample CPU% and RSS (MiB) for a list of PIDs using a single 'ps' call.
    Works on Linux + macOS that has ps command.

    Returns:
        dict[str, tuple[float, float]]: { pid_str: (cpu_pct, rss_mib) }
    """
    if not pids:
        return {}

    # keep only digit-like PIDs
    pids = [str(p) for p in pids if str(p).isdigit()]
    if not pids:
        return {}

    pid_arg = ",".join(pids)

    try:
        r = subprocess.run(
            ["ps", "-o", "pid=", "-o", "%cpu=", "-o", "rss=", "-p", pid_arg],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except Exception:
        return {}

    if not r.stdout:
        return {}

    out = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        pid = parts[0]
        try:
            cpu_pct = float(parts[1])
            rss_mib = float(parts[2]) / 1024.0  # rss is KB
        except Exception:
            continue
        out[pid] = (cpu_pct, rss_mib)

    return out


def _collect_stats_local(items, logger):
    """
    items: { "<pid>": "<log_path>", ... }
    Writes: <log_path>/stats.json
    """
    if not items:
        return

    samples = _ps_sample_many(list(items.keys()))
    if not samples:
        return

    for pid, (cpu_pct, rss_mib) in samples.items():
        log_path = items.get(pid)
        if not log_path:
            continue

        stats_path = os.path.join(log_path, "stats.json")

        try:
            with open(stats_path, "r") as f:
                s = json.load(f)
        except Exception:
            s = {
                "poll_count": 0,
                "cpu_sum_pct": 0.0,
                "cpu_peak_pct": 0.0,
                "cpu_avg_pct": 0.0,
                "rss_sum_mib": 0.0,
                "rss_peak_mib": 0.0,
                "rss_avg_mib": 0.0,
            }

        # update aggregates
        s["poll_count"] = int(s.get("poll_count", 0)) + 1
        s["cpu_sum_pct"] = float(s.get("cpu_sum_pct", 0.0)) + float(cpu_pct)
        s["cpu_peak_pct"] = max(float(s.get("cpu_peak_pct", 0.0)), float(cpu_pct))
        s["cpu_avg_pct"] = s["cpu_sum_pct"] / float(s["poll_count"])
        s["rss_sum_mib"] = float(s.get("rss_sum_mib", 0.0)) + float(rss_mib)
        s["rss_peak_mib"] = max(float(s.get("rss_peak_mib", 0.0)), float(rss_mib))
        s["rss_avg_mib"] = s["rss_sum_mib"] / float(s["poll_count"])

        try:
            os.makedirs(log_path, exist_ok=True)
            _atomic_write_json(stats_path, s, logger=logger)
        except Exception as e:
            logger.debug("[stats] write failed for %s: %s", stats_path, e)


########## Methods for slurm stats collection ##########
# Slurm stats collection (100% = one full core, sstat-only)

def _get_slurm_parsers():
    # function attribute cache (no module-level globals needed elsewhere)
    if hasattr(_get_slurm_parsers, "_cache"):
        return _get_slurm_parsers._cache

    rss_re = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([KMGTP]?)\s*$", re.IGNORECASE)
    rss_to_mib = {
        "": 1.0 / 1024.0,  # K -> MiB
        "K": 1.0 / 1024.0,
        "M": 1.0,
        "G": 1024.0,
        "T": 1024.0**2,
        "P": 1024.0**3,
    }
    cpu_re = re.compile(r"^\s*(\d+):(\d+)(?::(\d+))?(?:\.(\d+))?\s*$")

    _get_slurm_parsers._cache = (rss_re, rss_to_mib, cpu_re)
    return _get_slurm_parsers._cache


def _has_sstat(logger=None):
    # cache result + one-time warning
    if hasattr(_has_sstat, "_cached"):
        return _has_sstat._cached

    ok = shutil.which("sstat") is not None
    _has_sstat._cached = ok

    if not ok and logger and not getattr(_has_sstat, "_warned", False):
        logger.warning("[stats] slurm stats collection disabled (sstat required): 'sstat' not found in PATH")
        _has_sstat._warned = True

    return ok


def _slurm_rss_to_mib(val):
    rss_re, rss_to_mib, _ = _get_slurm_parsers()
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.upper() in {"N/A", "NA", "UNKNOWN"}:
        return None

    m = rss_re.match(s)
    if not m:
        return None

    try:
        num = float(m.group(1))
    except Exception:
        return None

    unit = (m.group(2) or "").upper()

    # Some Slurm setups output AveRSS as a bare integer (no suffix) in BYTES.
    if unit == "":
        return num / 1024.0

    factor = rss_to_mib.get(unit)
    if factor is None:
        return None
    return num * factor


def _slurm_cpu_time_to_s(val):
    _, _, cpu_re = _get_slurm_parsers()
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.upper() in {"N/A", "NA", "UNKNOWN"}:
        return None
    m = cpu_re.match(s)
    if not m:
        return None

    a = int(m.group(1))
    b = int(m.group(2))
    c = m.group(3)
    frac = m.group(4)

    # MM:SS or HH:MM:SS
    if c is None:
        total = a * 60 + b
    else:
        total = a * 3600 + b * 60 + int(c)

    if frac:
        total += float("0." + frac)

    return float(total)


def _slurm_tres_cpu_to_s(val):
    """
    Extract cpu=HH:MM:SS(.ms) from a TRESUsageInTot-like string.
    Example: "cpu=00:00:35,energy=0,mem=310992K,..."
    """
    if val is None:
        return None
    s = str(val)
    i = s.find("cpu=")
    if i < 0:
        return None
    j = s.find(",", i)
    cpu_str = s[i + 4 :] if j < 0 else s[i + 4 : j]
    return _slurm_cpu_time_to_s(cpu_str.strip())


def _sstat_sample_many(jobids, timeout_s=2.0):
    """
    Returns:
      { jobid: (cpu_time_s_or_None, ave_rss_mib_or_None, max_rss_mib_or_None) }

    - sstat-only, -P for parseable output.
    - Ignores sstat error lines (e.g. "no steps running for job ...").
    - CPU time prefers TRESUsageInTot cpu=... if present, else AveCPU.
    - Aggregates over steps by base job id, keeping max RSS peak.
    """
    jobids = [str(j) for j in jobids if str(j).isdigit()]
    if not jobids:
        return {}

    try:
        cmd = ["sstat", "-a", "-n", "-P", "-j", ",".join(jobids), "--format=JobID,TRESUsageInTot,AveCPU,AveRSS,MaxRSS",]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        except Exception:
            return {}

        if not r.stdout:
            return {}

        out = {}
        for raw in r.stdout.splitlines():
            line = raw.strip()
            if not line or line.startswith("sstat:"):
                continue

            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5:
                continue

            job_step = parts[0]              # e.g. 594905.batch / 594905.0
            base = job_step.split(".", 1)[0] # e.g. 594905
            if not base.isdigit():
                continue

            cpu_time_s = _slurm_tres_cpu_to_s(parts[1]) or _slurm_cpu_time_to_s(parts[2])
            ave_rss_mib = _slurm_rss_to_mib(parts[3])
            max_rss_mib = _slurm_rss_to_mib(parts[4])

            prev = out.get(base)
            if prev is None:
                out[base] = (cpu_time_s, ave_rss_mib, max_rss_mib)
            else:
                p_cpu, p_ave, p_max = prev

                # CPU time: keep max across steps (prevents .batch cpu=0 overwriting .0)
                if p_cpu is None:
                    cpu_keep = cpu_time_s
                elif cpu_time_s is None:
                    cpu_keep = p_cpu
                else:
                    cpu_keep = max(p_cpu, cpu_time_s)

                # AveRSS: keep max across steps (prevents tiny .batch winning, stable with .0)
                if p_ave is None:
                    ave_keep = ave_rss_mib
                elif ave_rss_mib is None:
                    ave_keep = p_ave
                else:
                    ave_keep = max(p_ave, ave_rss_mib)

                if p_max is None:
                    max_keep = max_rss_mib
                elif max_rss_mib is None:
                    max_keep = p_max
                else:
                    max_keep = max(p_max, max_rss_mib)

                out[base] = (cpu_keep, ave_keep, max_keep)

        return out
    except Exception:
        return {}


# Primary method for slurm stats collection
def _collect_stats_slurm(items, logger):
    """
    items: { "<jobid>": "<log_path>", ... }
    Writes: <log_path>/stats.json
    CPU meaning:
      100% ~= one full core
      500% ~= five cores fully busy
    """
    if not items:
        return

    if not _has_sstat(logger):
        return

    jobids = list(items.keys())
    samples = _sstat_sample_many(jobids)
    if not samples:
        return

    now = time.time()

    for jobid, (cpu_time_s, ave_rss_mib, max_rss_mib) in samples.items():
        log_path = items.get(jobid)
        if not log_path:
            continue

        stats_path = os.path.join(log_path, "stats.json")

        try:
            with open(stats_path, "r") as f:
                s = json.load(f)
        except Exception:
            s = {
                "poll_count": 0,
                "cpu_sum_pct": 0.0,
                "cpu_peak_pct": 0.0,
                "cpu_avg_pct": 0.0,
                "rss_sum_mib": 0.0,
                "rss_peak_mib": 0.0,
                "rss_avg_mib": 0.0,
                "_cpu_baseline_t": 0.0,
                "_cpu_baseline_time_s": 0.0,
                "_cpu_sample_count": 0,
            }

        rss_sample = max_rss_mib if max_rss_mib is not None else ave_rss_mib
        if cpu_time_s is None and rss_sample is None:
            continue

        # poll tick (consistent with local)
        poll_count = int(s.get("poll_count", 0)) + 1
        s["poll_count"] = poll_count

        # RSS aggregates
        if rss_sample is not None:
            rss_sum = float(s.get("rss_sum_mib", 0.0)) + float(rss_sample)
            s["rss_sum_mib"] = rss_sum

            peak_candidate = max_rss_mib if max_rss_mib is not None else rss_sample
            s["rss_peak_mib"] = max(float(s.get("rss_peak_mib", 0.0)), float(peak_candidate))
            s["rss_avg_mib"] = rss_sum / float(poll_count)

        # CPU aggregates: 100% = one full core (no alloccpus normalization)
        if cpu_time_s is not None:
            prev_t = float(s.get("_cpu_baseline_t", 0.0) or 0.0)
            prev_cpu = float(s.get("_cpu_baseline_time_s", 0.0) or 0.0)

            # first baseline: store and skip computing cpu_pct
            if prev_t > 0.0:
                dt = now - prev_t
                if dt >= 0.5:  # avoid tiny/unstable intervals
                    dcpu = float(cpu_time_s) - prev_cpu
                    if dcpu < 0:
                        dcpu = 0.0

                    cpu_pct = 100.0 * (dcpu / dt)

                    cpu_sum = float(s.get("cpu_sum_pct", 0.0)) + cpu_pct
                    s["cpu_sum_pct"] = cpu_sum
                    s["cpu_peak_pct"] = max(float(s.get("cpu_peak_pct", 0.0)), cpu_pct)

                    cpu_n = int(s.get("_cpu_sample_count", 0)) + 1
                    s["_cpu_sample_count"] = cpu_n
                    s["cpu_avg_pct"] = cpu_sum / float(cpu_n)

            # always refresh baseline
            s["_cpu_baseline_t"] = float(now)
            s["_cpu_baseline_time_s"] = float(cpu_time_s)

        try:
            _atomic_write_json(stats_path, s, logger=logger)
        except Exception as e:
            logger.debug("[stats] slurm write failed for %s: %s", stats_path, e)


########## Collection of additional sacct field retrival at the end ##########

def _get_slurm_additional_fields():
    raw = os.getenv("JAWM_STATS_SLURM_FIELDS", "").strip()
    if not raw:
        return []
    out, seen = [], set()
    for f in raw.split(","):
        f = f.strip()
        if not f or f in seen:
            continue
        if re.fullmatch(r"[A-Za-z0-9_]+", f):
            seen.add(f)
            out.append(f)
    return out


def _sacct_valid_fields(logger=None, timeout_s=3.0):
    """
    Return map {UPPER: canonical_field} from `sacct -e`.
    No caching (called once during finalize anyway).
    """
    if shutil.which("sacct") is None:
        return {}

    try:
        r = subprocess.run(["sacct", "-e"], capture_output=True, text=True, timeout=timeout_s, check=False)
        m = {}
        for ln in (r.stdout or "").splitlines():
            for name in ln.split():
                if re.fullmatch(r"[A-Za-z0-9_]+", name):
                    m[name.upper()] = name
        return m
    except Exception as e:
        if logger:
            logger.debug("[stats] sacct -e failed for recording additional fields: %s", e)
        return {}


def _sacct_fetch_additional(logger, jobids, fields, timeout_s=5.0):
    """
    Returns { base_jobid: {requested_field: value_str_or_NA, ...}, ... }
    - Invalid fields => NA (soft)
    - Values stored as-is from sacct
    """
    jobids = [str(j) for j in jobids if str(j).isdigit()]
    fields = [str(f).strip() for f in (fields or []) if str(f).strip()]
    if not jobids or not fields:
        return {}

    if shutil.which("sacct") is None:
        return {j: {f: "NA" for f in fields} for j in jobids}

    valid_map = _sacct_valid_fields(logger=logger)

    pairs, invalid = [], []
    for f in fields:
        canon = valid_map.get(f.upper())
        if canon:
            pairs.append((f, canon))
        else:
            invalid.append(f)

    if invalid and logger and not getattr(_sacct_fetch_additional, "_warned_invalid", False):
        logger.warning("[stats] sacct: ignoring invalid keys for recording additional fields: %s", ",".join(invalid))
        _sacct_fetch_additional._warned_invalid = True

    # If nothing valid, return predictable NA for all jobs/fields
    if not pairs:
        return {j: {f: "NA" for f in fields} for j in jobids}

    fmt = ["JobID"] + [canon for (_req, canon) in pairs]
    cmd = ["sacct", "-n", "-P", "-j", ",".join(jobids), "--format=" + ",".join(fmt)]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    except Exception as e:
        if logger:
            logger.warning("[stats] sacct failed for recording additional fields: %s", e)
        return {j: {f: "NA" for f in fields} for j in jobids}

    if not r.stdout:
        if logger:
            err = (r.stderr or "").strip()
            if err:
                logger.debug("[stats] sacct for recording additional fields returned no stdout (rc=%s): %s", r.returncode, err)
        return {j: {f: "NA" for f in fields} for j in jobids}

    out = {}
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split("|")
        base = (parts[0] or "").split(".", 1)[0].strip()
        if not base.isdigit():
            continue

        row = {f: "NA" for f in fields}  # include invalid ones too (NA)
        for i, (req, _canon) in enumerate(pairs, start=1):
            if i < len(parts):
                v = (parts[i] or "").strip()
                if v and v.upper() not in {"N/A", "NA", "UNKNOWN"}:
                    row[req] = v

        # keep best row among steps (most non-NA)
        prev = out.get(base)
        if prev is None:
            out[base] = row
        else:
            if sum(v != "NA" for v in row.values()) >= sum(v != "NA" for v in prev.values()):
                out[base] = row

    for j in jobids:
        out.setdefault(j, {f: "NA" for f in fields})

    return out


def _additional_slurm_stats_from_sacct(Process, logger):
    """
    Append-only, fail-safe shutdown finalizer.
    - Only runs if JAWM_STATS_SLURM_FIELDS is set
    - Adds s["additional_fields"] once
    """
    fields = _get_slurm_additional_fields()
    if not fields:
        return

    try:
        items = {}
        for proc in list(Process.registry.values()):
            try:
                if not isinstance(proc, Process):
                    continue
                if getattr(proc, "manager", None) != "slurm":
                    continue
                rid = getattr(proc, "runtime_id", None)
                log_path = getattr(proc, "log_path", None)
                if rid and log_path:
                    items[str(rid)] = log_path
            except Exception:
                continue

        if not items:
            return

        final_map = _sacct_fetch_additional(logger, list(items.keys()), fields=fields)
        if not final_map:
            return

        for jobid, add in final_map.items():
            log_path = items.get(jobid)
            if not log_path:
                continue

            stats_path = os.path.join(log_path, "stats.json")
            try:
                with open(stats_path, "r") as f:
                    s = json.load(f)
            except Exception:
                s = {}

            if "additional_fields" in s:
                continue

            s["additional_fields"] = add
            try:
                _atomic_write_json(stats_path, s, logger=logger)
            except Exception as e:
                logger.debug("[stats] slurm write failed for %s: %s", stats_path, e)

    except Exception as e:
        logger.debug("[stats] operations for recording additional fields failed: %s", e)


########## Methods for finalize summary at the end of jawm call ##########

def _log_stats_summary_from_registry(Process, logger, max_items=1000, budget_s=3.0):
    """
    Read-only aggregation of per-process <log_path>/stats.json.

    - Dedupes by log_path (prevents double-counting if registry has aliases).
    - Best-effort: never raises.
    - Non-blocking: only local file reads (no subprocess calls).
    """
    try:
        entries = []
        seen_lp = set()
        deadline = time.monotonic() + float(budget_s or 0.0)
        _mib_to_gb = 1048576.0 / 1_000_000_000.0

        for i, proc in enumerate(Process.registry.values()):
            if i >= max_items or time.monotonic() >= deadline:
                break
            try:
                if not isinstance(proc, Process):
                    continue

                lp = getattr(proc, "log_path", None)
                if not lp or lp in seen_lp:
                    continue
                seen_lp.add(lp)

                name = getattr(proc, "name", None) or ""
                label = name.split("|", 1)[0] if name else (str(getattr(proc, "runtime_id", "")) or "process")

                sp = os.path.join(lp, "stats.json")
                try:
                    with open(sp, "r") as f:
                        s = json.load(f)
                except Exception:
                    continue

                if isinstance(s, dict) and s:
                    entries.append((label, lp, s))
            except Exception:
                continue

        if not entries:
            logger.info("[stats] :::SUMMARY:::\n\tNumber of jawm Processes: 0")
            return

        def _f(x, default=None):
            try:
                return float(x)
            except Exception:
                return default

        cpu_avgs = []
        rss_avgs = []

        cpu_peak = -1.0
        cpu_peak_label = None
        cpu_peak_lp = None

        rss_peak = -1.0
        rss_peak_label = None
        rss_peak_lp = None

        for label, lp, s in entries:
            # CPU avg per process
            cpu_avg = _f(s.get("cpu_avg_pct"))
            if cpu_avg is None:
                cpu_sum = _f(s.get("cpu_sum_pct"), 0.0)
                try:
                    denom = int(s.get("_cpu_sample_count") or 0) or int(s.get("poll_count") or 0)
                except Exception:
                    denom = 0
                if denom > 0:
                    cpu_avg = cpu_sum / float(denom)

            if cpu_avg is not None:
                cpu_avgs.append(cpu_avg)

            # CPU peak per process
            cpk = _f(s.get("cpu_peak_pct"))
            if cpk is not None and cpk > cpu_peak:
                cpu_peak = cpk
                cpu_peak_label = label
                cpu_peak_lp = lp

            # RSS avg per process
            rss_avg = _f(s.get("rss_avg_mib"))
            if rss_avg is None:
                rss_sum = _f(s.get("rss_sum_mib"), 0.0)
                try:
                    denom = int(s.get("poll_count") or 0)
                except Exception:
                    denom = 0
                if denom > 0:
                    rss_avg = rss_sum / float(denom)

            if rss_avg is not None:
                rss_avgs.append(rss_avg)

            # RSS peak per process
            rpk = _f(s.get("rss_peak_mib"))
            if rpk is not None and rpk > rss_peak:
                rss_peak = rpk
                rss_peak_label = label
                rss_peak_lp = lp

        n = len(entries)
        cpu_avg_all = (sum(cpu_avgs) / len(cpu_avgs)) if cpu_avgs else None
        rss_avg_all = (sum(rss_avgs) / len(rss_avgs)) if rss_avgs else None

        lines = ["[stats] :::SUMMARY::: (CPU: ~100% = 1 full core; memory in GB decimal)"]
        lines.append(f"\tNumber of jawm Processes: {n}")

        lines.append(
            f"\tAverage CPU usage across jawm Processes: ~{cpu_avg_all:.1f}%"
            if cpu_avg_all is not None else
            "\tAverage CPU usage across jawm Processes: NA"
        )

        if cpu_peak >= 0 and cpu_peak_label:
            lines.append(f"\tPeak CPU usage across jawm Processes: {cpu_peak:.1f}%")
            lines.append(f"\tPeak CPU jawm Process: {cpu_peak_label} (log path: {cpu_peak_lp})")
        else:
            lines.append("\tPeak CPU usage across jawm Processes: NA")

        lines.append(
            f"\tAverage memory (RSS) usage across jawm Processes: ~{(rss_avg_all * _mib_to_gb):.3f} GB"
            if rss_avg_all is not None else
            "\tAverage memory (RSS) usage across jawm Processes: NA"
        )

        if rss_peak >= 0 and rss_peak_label:
            lines.append(f"\tPeak memory (RSS) usage across jawm Processes: {(rss_peak * _mib_to_gb):.3f} GB")
            lines.append(f"\tPeak memory (RSS) jawm Process: {rss_peak_label} (log path: {rss_peak_lp})")
        else:
            lines.append("\tPeak memory (RSS) usage across jawm Processes: NA")

        logger.info("\n".join(lines))

    except Exception as e:
        logger.debug("[stats] summary aggregation failed: %s", e)

# ------------------------------------------------------------
#   End of recording stats helper methods
# ------------------------------------------------------------


# ------------------------------------------------------------
#   Other internal helper methods
# ------------------------------------------------------------
def _log_system_info(logger):
    """
    Log system and runtime metadata; never raises.
    """
    try:
        # Core system info
        logger.info(f"[sys] jawm: {str(_VERSION)}")
        logger.info(f"[sys] Python: {platform.python_version()}")
        logger.info(f"[sys] OS: {platform.platform()}")
        logger.info(f"[sys] Machine/Arch: {platform.machine()}")

        # Helper for optional external tools
        def _try_version(cmd, name):
            try:
                r = subprocess.run(
                    cmd, shell=True,
                    text=True, capture_output=True, timeout=2
                )
                out = (r.stdout or r.stderr or "").splitlines()
                if r.returncode == 0 and out:
                    logger.info(f"[sys] {name}: {out[0].strip()}")
            except Exception:
                pass

        # External tools
        _try_version("sbatch --version", "Slurm")
        _try_version("docker --version", "Docker")
        _try_version("apptainer --version", "Apptainer")
        _try_version("kubectl version --short", "Kubernetes (kubectl)")

    except Exception as e:
        logger.warning(f"[sys] Could not collect system info: {e}")


#   Helper/values for nested CLI overrides (--global.*, --process.*)
_GLOBAL_RE = re.compile(r"^--global\.(.+?)=(.+)$")
_PROCESS_RE = re.compile(r"^--process\.([^.]+)\.(.+?)=(.+)$")

def _nested_insert(target, key_path, value):
    """
    Insert a nested key path (list of strings) into the dict target.
    Example:
        key_path = ['var','sub','x']
        value = '10'
    Result:
        target['var']['sub']['x'] = '10'
    """
    cur = target
    for k in key_path[:-1]:
        cur = cur.setdefault(k, {})
    cur[key_path[-1]] = value


def _coalesce_var_prefix(keypath, skeys=("mk", "map")):
    """
    Keep var.mk.* and var.map.* as dotted keys instead of nesting.
    ["var","mk","output_folder"] -> ["var","mk.output_folder"]
    """
    try:
        if isinstance(keypath, list) and len(keypath) >= 3 and keypath[0] == "var" and keypath[1] in skeys:
            return ["var", keypath[1] + "." + ".".join(keypath[2:])]
    except Exception:
        pass
    return keypath


# Custom action class for args --help
class _IgnoreAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        # Never called — these are dummy help-only flags
        pass
# ------------------------------------------------------------
#   End of other internal helper methods
# ------------------------------------------------------------













# ------------------------------------------------------------
#   Start of the main method
# ------------------------------------------------------------
def main():
    """Entry point for the `jawm` CLI: parse args, configure logging, and run the workflow module."""
    # ------------------------------------------------------------
    #   Parse CLI arguments
    # ------------------------------------------------------------
    parser = argparse.ArgumentParser(description="jawm - Just Another Workflow Manager")
    parser.add_argument("module", help="Path to a jawm Python script or directory containing the jawm module script with jawm.py or main.py or single .py ('.' for current directory)")
    parser.add_argument("-p", "--parameters", nargs="+", default=None, help="YAML file(s) or directory of parameter config files to be used as default param_file.")
    parser.add_argument("-v", "--variables", nargs="+", default=None, help="YAML or .rc file(s) or directory of files of script variables to inject into the module script.")
    parser.add_argument("-l", "--logs-directory", dest="logs_directory", default=None, help="Directory to store logs; sets default logs_directory. CLI logs are saved in <logs_directory>/jawm_runs (default: ./logs/jawm_runs).")
    parser.add_argument("-w", "--workdir", dest="workdir", default=None, help="Change/set custom working directory before resolving paths.")
    parser.add_argument("-r", "--resume", action="store_true", default=None, help="Resume mode: skip executing already successfully completed processes.")
    parser.add_argument("-n", "--no-override", dest="no_override", nargs="?", const="ALL", help="Disable override for all or specific parameters (comma-separated).")
    parser.add_argument("--git-cache", help="Path for jawm's git cache (default: ~/.jawm/git)")
    parser.add_argument("--server", default="github.com", help="Git server host or URL (use 'local' to skip remote). Default: github.com")
    parser.add_argument("--user", default="mpg-age-bioinformatics", help="Git username/organization for remote. Default: mpg-age-bioinformatics")
    parser.add_argument("--no-web", dest="no_web", action="store_true", default=False, help="Disable online workflow lookup when workflow not found locally. Default: online scanning is enabled.")
    parser.add_argument("--stats", dest="stats", action="store_true", default=False, help="Possibly record per-process resource stats (avg/peak cpu+rss).")
    parser.add_argument("-V", "--version", action="version", version=f"jawm {_VERSION}")

    override_group = parser.add_argument_group("override syntax")
    override_group.add_argument("--global.<key>[.<subkey>]=<value>", help="Override global parameters (e.g. --global.var.x=10).", action=_IgnoreAction, nargs=0)
    override_group.add_argument("--process.<name>.<key>[.<subkey>]=<value>", help="Override process-specific parameters (e.g. --process.p1.retries=3).", action=_IgnoreAction, nargs=0)

    args, unknown_args = parser.parse_known_args()

    # ------------------------------------------------------------
    #   Apply workdir early so relative paths behave as expected
    # ------------------------------------------------------------
    if args.workdir:
        _wd = os.path.abspath(os.path.expanduser(args.workdir))
        if os.path.exists(_wd) and not os.path.isdir(_wd):
            print(f"[jawm] ERROR: user defined workdir exists but is not a directory: {_wd}", file=sys.stderr)
            sys.exit(2)
        if not os.path.isdir(_wd):
            try:
                os.makedirs(_wd, exist_ok=True)
            except Exception as e:
                print(f"[jawm] ERROR: could not create user defined workdir: {_wd} ({e})", file=sys.stderr)
                sys.exit(2)
        os.chdir(_wd)

    # ------------------------------------------------------------
    #   Module label and timestamp
    # ------------------------------------------------------------
    module_raw = args.module
    module_label = os.path.basename(os.path.abspath(args.module)).replace(".py", "")
    now = datetime.datetime.now()
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    timestamp_iso = now.strftime("%Y-%m-%dT%H:%M:%S")


    # ------------------------------------------------------------
    #   Support //subpath syntax for git repos
    # ------------------------------------------------------------
    subpath = None
    if "//" in args.module:
        # Detect true URL-style prefixes to avoid breaking schemes
        if re.match(r"^(?:https://|http://|ssh://|file://|git\+https://)", args.module):
            # URL-based repos → split only on the last // (keeps protocol intact)
            if args.module.count("//") > 1:
                args.module, subpath = args.module.rsplit("//", 1)
                args.module = args.module.rstrip("/")
                subpath = subpath.strip("/")
        else:
            # Shorthand or pseudo-schemes (gh:, git@, github.com/repo)
            args.module, subpath = args.module.split("//", 1)
            args.module = args.module.rstrip("/")
            subpath = subpath.strip("/")

    # ------------------------------------------------------------
    #   CLI log file path & logging with exit method
    # ------------------------------------------------------------
    base_logs_dir = os.path.abspath(args.logs_directory) if args.logs_directory else os.path.abspath("./logs")
    run_logs_dir = os.path.join(base_logs_dir, "jawm_runs")
    os.makedirs(run_logs_dir, exist_ok=True)
    cli_log_file = os.path.join(run_logs_dir, f"{module_label}_{timestamp}.log")

    # Start global tee BEFORE any prints/logging so we catch everything
    _start_global_tee(cli_log_file, mode="w")

    # Configure logging: stream ONLY (to sys.stdout which is tee'd), no FileHandler needed
    log_formatter = logging.Formatter(
        "[%(asctime)s] - %(levelname)s - %(name)s :: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)  # goes through tee
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    if os.getenv("JAWM_LOG_EMOJI", "1").strip().lower() not in {"0", "false", "no", "off"}:
        for h in root_logger.handlers:
            if isinstance(h, logging.StreamHandler) and isinstance(h.formatter, logging.Formatter):
                h.setFormatter(_EmojiFormatter(h.formatter._fmt, h.formatter.datefmt))

    logger = logging.getLogger(f"jawm.cli|{module_label}")
    logger.info("Initiating jawm module script from jawm command")

    # Define helper for consistent error exits
    def _errlog_exit(excode=1):
        """
        Generic helper to log a final error and exit cleanly with the given code.
        """
        logger.error(f"Ending jawm module script from jawm command with exit code {excode}")
        sys.exit(excode)


    # ------------------------------------------------------------
    #   Handle git repo as module
    # ------------------------------------------------------------
    # Only synthesize git URL if:
    #  (1) module path does NOT exist locally, AND
    #  (2) module is NOT already a git URL / git-like target.
    try:
        if not Path(args.module).exists() and not _is_git_target(args.module) and (not args.no_web):
            args.module = _synth_git_target(args.module, args.server, args.user)

        # If module is a git repo target, clone/cache and rewrite args.module to local 
        _git_info_line = None
        _original_module = args.module

        if _is_git_target(args.module) and (not args.no_web):
            cache_root = _git_cache_root(getattr(args, "git_cache", None))
            cache_root.mkdir(parents=True, exist_ok=True)

            # Handle case where local folder already exists for <repo>@<tag>
            repo_part = args.module.split("/")[-1]
            repo_name, sep, ref = repo_part.partition("@")
            repo_name = repo_name.replace(".git", "")
            ref = ref or None

            dst = Path.cwd() / repo_name
            if dst.exists():
                logger.info(f"Found existing local folder: {dst}")

                commit_file = dst / ".commit"
                if not commit_file.exists():
                    logger.error(f"[git] Local folder '{dst}' exists but is missing .commit — cannot verify tag/ref.")
                    logger.error("Please delete or rename the folder and re-run.")
                    _errlog_exit(1)

                local_commit = commit_file.read_text(encoding="utf-8", errors="ignore").strip()

                # Try to resolve commit hash for requested ref/tag
                try:
                    ref_commit = None
                    if ref:
                        remote_url = f"git@{args.server}:{args.user}/{repo_name}.git"
                        result = subprocess.run(
                            ["git", "ls-remote", remote_url, ref],
                            capture_output=True, text=True, check=True
                        )
                        for line in result.stdout.splitlines():
                            if line.endswith(f"refs/tags/{ref}") or line.endswith(f"refs/heads/{ref}"):
                                ref_commit = line.split()[0]
                                break
                    else:
                        ref_commit = local_commit  # no tag given → accept current hash

                    if not ref_commit:
                        logger.error(f"[git] Could not resolve remote ref '{ref}' for {repo_name}")
                        _errlog_exit(1)

                    if local_commit != ref_commit:
                        logger.error(
                            f"[git] Existing folder '{dst}' has commit {local_commit[:8]}, "
                            f"but requested tag/ref '{ref}' points to {ref_commit[:8]}."
                        )
                        logger.error("Please delete or rename the folder and re-run.")
                        _errlog_exit(1)

                    # Matching hash — reuse folder, but continue execution
                    logger.info(f"[git] Local folder '{dst}' already matches requested ref '{ref}' — reusing.")
                    args.module = str(dst)
                    _git_info_line = f"[git] Reused local folder '{dst}' (commit {local_commit[:8]}) for '{module_raw}'"

                    # Do NOT return or exit — just skip cloning and continue
                    skip_clone = True

                except subprocess.CalledProcessError as e:
                    logger.error(f"[git] Failed to verify remote ref '{ref}' for {repo_name}: {e}")
                    _errlog_exit(1)
            else:
                skip_clone = False

            # --- Only perform clone if skip_clone is False ---
            if not skip_clone:
                logger.info(f"Module '{module_raw}' not found locally — attempting online lookup...")
                try:
                    resolved = _resolve_git_to_local(args.module, cache_root)
                except Exception as e:
                    logger.error(
                        f"[git] Failed to fetch workflow '{args.module}' from remote.\n"
                        f"Reason: {e}"
                    )
                    logger.error("Could not locate the workflow locally or online. Exiting gracefully.")
                    _errlog_exit(1)
            else:
                # logger.info(f"Reusing existing local folder '{dst}' (commit {local_commit[:8]}) — skipping online lookup.")
                resolved = str(dst)

            # Determine repo_name from: cache_root/<safe_repo>/<sha>/repo_name/<...>
            try:
                rel = Path(resolved).resolve().relative_to(cache_root.resolve())
                parts = rel.parts
                # parts[0] = safe_repo, parts[1] = sha, parts[2] = repo_name (if subpath used)
                repo_name = parts[2] if len(parts) >= 3 else parts[-1]
            except Exception:
                # fallback if resolved is not under cache_root (should not happen, but safe)
                repo_name = Path(resolved).name

            # Strip a trailing .git
            repo_name = re.sub(r"\.git$", "", repo_name, flags=re.IGNORECASE) or "repo"

            # Destination in current working directory
            dst = Path.cwd() / repo_name

            if not skip_clone:
                # Ensure resolved is a directory
                resolved_path = Path(resolved)
                if not resolved_path.is_dir():
                    raise RuntimeError(f"Resolved git path is not a directory: {resolved}")

                # Copy (clean replace)
                if dst.exists():
                    shutil.rmtree(dst)

                shutil.copytree(resolved_path, dst)
            else:
                # Skipped cloning — reusing local folder
                resolved_path = Path(resolved)
                logger.info(f"[git] Reusing existing folder: {resolved_path}")

            # Point args.module at the **local working copy**
            args.module = str(dst)

            if not skip_clone:
                _git_info_line = f"[git] resolved '{_original_module}' → '{resolved}' (copied to '{dst}')"

            # Append subpath inside the repo if provided
            if subpath:
                target_path = Path(dst) / subpath
                if not target_path.exists():
                    logger.error(f"[git] Specified subpath '{subpath}' not found in repo '{repo_name}'. Please check the path.")
                    _errlog_exit(1)
                args.module = str(target_path)
                logger.info(f"Targeting subpath inside repo: {target_path}")
            else:
                args.module = str(dst)

            # args.module = str(resolved)
            # _git_info_line = f"[git] resolved '{_original_module}' → '{resolved}'"

        # normalize -p and -v: single item → string; many → list
        if args.parameters is not None and isinstance(args.parameters, list) and len(args.parameters) == 1:
            args.parameters = args.parameters[0]
        if args.variables is not None and isinstance(args.variables, list) and len(args.variables) == 1:
            args.variables = args.variables[0]

        # ------------------------------------------------------------
        #   Handle parameter file from remote url
        # ------------------------------------------------------------
        def _is_https_url(x):
            try:
                s = str(x)
                if not s.startswith("https://"):
                    return False
                u = urllib.parse.urlparse(s)
                return bool(u.netloc)
            except Exception:
                return False

        def _download_url(url):
            try:
                if str(os.getenv("JAWM_ALLOW_URL_CONFIG", "1")).strip().lower() in {"0","false","no","off",""}:
                    raise RuntimeError("URL config from remote is disabled")

                cache_dir = os.path.expanduser(os.getenv("JAWM_URL_CACHE_DIR") or "~/.jawm/remote_params")
                os.makedirs(cache_dir, exist_ok=True)

                max_bytes = int(os.getenv("JAWM_URL_MAX_BYTES", str(1024 * 1024)))
                timeout = float(os.getenv("JAWM_URL_TIMEOUT", "10"))

                parsed = urllib.parse.urlparse(url)
                ext = os.path.splitext(parsed.path)[1].lower() or ".yaml"
                fname = hashlib.sha256(url.encode("utf-8")).hexdigest() + ext
                out_path = os.path.join(cache_dir, fname)

                force = str(os.getenv("JAWM_URL_FORCE_REFRESH", "0")).strip().lower() in {"1","true","yes","on"}

                if not force and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    logger.info(f"[url] Using cached remote file for url: {url}")
                    return out_path

                logger.info(f"[url] Fetching remote file for url: {url}")

                def _fetch_url(u):
                    req = urllib.request.Request(u, headers={"User-Agent": "jawm/1 (config-fetch)"})
                    with urllib.request.urlopen(req, timeout=timeout) as r:
                        final_url = r.geturl()
                        if not str(final_url).startswith("https://"):
                            raise RuntimeError("redirected to non-https")
                        data = r.read(max_bytes + 1)
                        if len(data) > max_bytes:
                            raise RuntimeError("remote file too large")
                        return data

                def _append_raw_url(u):
                    p = urllib.parse.urlparse(u)
                    q = urllib.parse.parse_qs(p.query)
                    if "raw" in q:
                        return None
                    new_query = (p.query + "&" if p.query else "") + "raw=1"
                    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, p.fragment))

                data = _fetch_url(url)
                sample = data.lstrip()[:256].lower()
                if sample.startswith(b"<!doctype html") or sample.startswith(b"<html") or b"<html" in sample:
                    alt = _append_raw_url(url)
                    if alt:
                        logger.info(f"[url] URL returned HTML, Retrying with ?raw=1: {alt}")
                        data = _fetch_url(alt)
                        sample2 = data.lstrip()[:256].lower()
                        if sample2.startswith(b"<!doctype html") or sample2.startswith(b"<html") or b"<html" in sample2:
                            raise RuntimeError("URL did not return raw file (got HTML)")
                    else:
                        raise RuntimeError("URL did not return raw file (got HTML)")

                fd, tmp_path = tempfile.mkstemp(prefix="jawm_url_", dir=cache_dir)
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(data)
                    os.replace(tmp_path, out_path)
                finally:
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass

                return out_path

            except Exception as e:
                logger.error(f"Failed to fetch remote config file: {url}\nError: {e}")
                _errlog_exit(2)

        def _resolve_urls(value):
            if not value:
                return value
            if isinstance(value, (list, tuple)):
                return [_download_url(v) if _is_https_url(v) else v for v in value]
            return _download_url(value) if _is_https_url(value) else value

        # Convert CLI URL inputs to local files before path validation
        args.parameters = _resolve_urls(args.parameters)
        args.variables = _resolve_urls(args.variables)

        if _git_info_line:
            logger.info(_git_info_line)
        logger.info(f"Logging terminal output to: {cli_log_file}")

    except Exception as e:
        logger.error(f"[git] Unexpected failure during workflow resolution: {e}")
        _errlog_exit(1)


    # ------------------------------------------------------------
    #   Validate and process/modify/inject values
    # ------------------------------------------------------------
    # Validate paths for -p / --parameters and -v / --variables
    def _validate_paths(label, paths):
        if not paths:
            return
        # Normalize into a list for consistent checking
        items = paths if isinstance(paths, (list, tuple)) else [paths]
        for p in items:
            if not os.path.exists(p):
                logger.error(f"{label} path not found: {p} (*** TRIGGERING EXIT ***)")
                _errlog_exit(2)

    _validate_paths("Parameter", args.parameters)
    _validate_paths("Variable", args.variables)

    # Import Process and set defaults or overrides
    from jawm import Process

    # Initiate stats collection thread if stats collection is enabled
    _record_stat = bool(args.stats) or (str(os.getenv("JAWM_RECORD_STAT", "0")).strip().lower() in {"1", "true", "yes", "on"})
    if _record_stat:
        _stats_stop = threading.Event()
        _t_stats = threading.Thread(target=_collect_stats_op, args=(Process, logger, _stats_stop), daemon=True, name="jawm-stats-collector")
        _t_stats.start()
        logger.debug("[stats] stats collector initiated")

    # Parse/override values
    no_override_params = (
        ["ALL"] if args.no_override and args.no_override.strip().upper() == "ALL"
        else [p.strip() for p in args.no_override.split(",") if p.strip()] if args.no_override else []
    )

    def _apply_param(key, value):
        """Helper to decide whether to use set_default or set_override."""
        if "ALL" in no_override_params or key in no_override_params:
            Process.set_default(**{key: value})
            logger.info(f"Default {key} set to: {value}")
        else:
            Process.set_override(**{key: value})
            logger.info(f"Override {key} set to: {value}")

    # Parse nested CLI overrides (--global.* / --process.*.*)
    global_overrides = {}
    process_overrides = {}

    for raw in sys.argv[1:]:
        m = _GLOBAL_RE.match(raw)
        if m:
            keypath = _coalesce_var_prefix(m.group(1).split("."))
            value = m.group(2)
            _nested_insert(global_overrides, keypath, value)
            continue

        m = _PROCESS_RE.match(raw)
        if m:
            pname = m.group(1)
            keypath = _coalesce_var_prefix(m.group(2).split("."))
            value = m.group(3)
            entry = process_overrides.setdefault(pname, {})
            _nested_insert(entry, keypath, value)
            continue

    Process._cli_global_overrides = global_overrides or {}
    Process._cli_process_overrides = process_overrides or {}

    # Apply flags values
    if args.parameters:
        _apply_param("param_file", args.parameters)
    if args.logs_directory:
        _apply_param("logs_directory", args.logs_directory)
    if args.resume is not None:
        _apply_param("resume", True)

    # Load and inject variables into script namespace
    exec_namespace = {}
    if args.variables:
        try:
            from jawm._utils import read_variables, _sanitize_vars
            injected_vars = read_variables(args.variables, output_type="dict")
            exec_namespace.update(_sanitize_vars(injected_vars))
            logger.info(f"Injected {len(injected_vars)} variable(s) from: {args.variables} to the script")
            _apply_param("var_file", args.variables)
        except Exception as e:
            logger.error(f"Failed to load variables from {args.variables} — {e}")
            _errlog_exit(2)

    # Resolve module path
    source_path = os.path.abspath(args.module)
    if os.path.isfile(source_path) and source_path.endswith(".py"):
        module_path = source_path
    elif os.path.isdir(source_path):
        py_files = [f for f in os.listdir(source_path) if f.endswith(".py")]
        if "jawm.py" in py_files:
            module_path = os.path.join(source_path, "jawm.py")
        elif "main.py" in py_files:
            module_path = os.path.join(source_path, "main.py")
        elif len(py_files) == 1:
            module_path = os.path.join(source_path, py_files[0])
        else:
            logger.error(f"Directory {source_path} must contain only one .py file or a main.py")
            _errlog_exit(2)
    else:
        logger.error(f"Invalid module path: {module_raw}")
        _errlog_exit(2)

    
    # ------------------------------------------------------------
    #  Final operations before running the module 
    # ------------------------------------------------------------
    # Distinct exit code so callers/CI can detect reference mismatches
    EXIT_HASH_REFERENCE_MISMATCH = 73

    # Handle already pulled git module with .commit
    module_dir = Path(module_path).parent

    commit_file = module_dir.joinpath(".commit")
    if commit_file.exists():
        try:
            commit = commit_file.read_text(encoding="utf-8", errors="ignore").strip()
            logger.info(f"[git] Found git stamp commit: {commit[:8]}")

            commit_mtime = commit_file.stat().st_mtime

            # Calculate latest mtime inside the module directory
            latest_mtime = 0
            for root, dirs, files in os.walk(module_dir):
                dirs[:] = [
                    d for d in dirs
                    if d not in {"logs", "__pycache__", ".ipynb_checkpoints", ".mypy_cache"}
                ]
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        latest_mtime = max(latest_mtime, os.path.getmtime(fp))
                    except:
                        pass

            if latest_mtime > commit_mtime:
                logger.warning(f"[git] Local directory modified since export of commit {commit[:8]}")
            else:
                logger.info(f"[git] Local directory likely unchanged since the stamp commit")
        except Exception as e:
            logger.warning(f"[git] Could not check commit status: {e}")

    # Detect if module_dir is a real git repository
    git_dir = module_dir.joinpath(".git")

    if git_dir.exists() and git_dir.is_dir():
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(module_dir),
                text=True,
                capture_output=True,
            )
            head = result.stdout.strip()
            if head:
                logger.info(f"[git] Git repository HEAD commit: {head[:8]}")

            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(module_dir),
                text=True,
                capture_output=True,
            )

            status_output = result.stdout.strip()

            if status_output:
                logger.warning("[git] Local git repository is MODIFIED (uncommitted changes present)")
            else:
                logger.info("[git] Local git repository is clean (no uncommitted changes)")

        except Exception as e:
            logger.warning(f"[git] Found local git repo, but could not inspect: {e}")

    
    # ------------------------------------------------------------
    #  Run the module script 
    # ------------------------------------------------------------
    exit_code_from_script = None
    exit_code_def = 0
    _log_system_info(logger)

    try:
        logger.info(f"Running jawm module: {module_path}")
        try:
            runpy.run_path(module_path, run_name="__main__", init_globals=exec_namespace)
        except SystemExit as e:
            # Defer exiting until after we perform cleanup + hashing
            exit_code_from_script = e.code if isinstance(e.code, int) else 0
            logger.info(f"Module ended with exitcode ({exit_code_from_script}); Initiating post run procedures.")

        exit_code_def = 0 if exit_code_from_script is None else exit_code_from_script

        # Wait for all processes to finish before post-run and cleanup
        try:
            wait_cli = os.getenv("JAWM_WAIT_CLI", "1").lower() not in {"0", "false", "no", "off"}
            if wait_cli:
                timeout_val = 86400  # default: 24 hours
                env_val = os.getenv("JAWM_WAIT_TIMEOUT")
                if env_val is not None:
                    try:
                        timeout_val = int(env_val)
                    except ValueError:
                        logger.warning(f"Invalid JAWM_WAIT_TIMEOUT='{env_val}'. Falling back to default (24h).")

                # Wait for all processes to finish before hashing
                Process.wait("all", timeout=timeout_val, log=False, dynamic=True)

        except Exception as e:
            logger.warning(f"Could not complete jawm default wait for processes before exit: {e}")

        # Wait for process to fully end and cleaned up
        deadline = time.time() + 120
        while Process.list_monitoring_threads():
            if time.time() >= deadline:
                logger.warning("Timed out after 2 minutes waiting for processes to finish/clean up; CLOSING ANYWAY!")
                break
            time.sleep(1)


        # ------------------------------------------------------------
        #  Post-run hashing & histories
        # ------------------------------------------------------------
        # Always reached, even if module sys.exit'ed
        from jawm._utils import hash_content  # canonical hasher

        def _extend_inputs_from_arg(val):
            if not val:
                return []
            if isinstance(val, list):
                return [os.path.abspath(v) for v in val]
            return [os.path.abspath(val)]

        resolved_module_path = module_path
        logs_dir = os.path.abspath(args.logs_directory) if args.logs_directory else os.path.abspath("./logs")

        # === Always write AUTO INPUT HISTORY ====
        # hash value: prefix-hash if available, else file-content hash on fallback.
        # files list: enumerate module + -p + -v (even if prefix-mode succeeds).
        auto_files_csv = "-"
        auto_history_path = _input_history_path_cli(logs_dir, resolved_module_path)

        # Enumerate candidate inputs (for history files list)
        auto_inputs = [resolved_module_path]
        auto_inputs += _extend_inputs_from_arg(args.parameters)
        auto_inputs += _extend_inputs_from_arg(args.variables)
        auto_files_considered = _enumerate_hash_inputs_cli(
            auto_inputs,
            allowed_extensions=None,
            exclude_dirs=[".git", "__pycache__", ".mypy_cache", ".ipynb_checkpoints"],
            exclude_files=["*.tmp", "*.swp"],
            recursive=True,
        )
        if auto_files_considered:
            auto_files_csv = ",".join(auto_files_considered)
        
        # Compute auto hash (prefix-mode preferred)
        auto_hash = _compute_run_hash_from_process_prefixes_cli()
        if not auto_hash:
            if auto_inputs:
                auto_hash = hash_content(
                    auto_inputs,
                    allowed_extensions=None,
                    exclude_dirs=[".git", "__pycache__", ".mypy_cache", ".ipynb_checkpoints"],
                    exclude_files=["*.tmp", "*.swp"],
                    recursive=True,
                )
            else:
                auto_hash = hashlib.sha256(b"").hexdigest()

        # Append to <wf>_input.history
        _append_history_line_cli(
            logger,
            history_path=auto_history_path,
            ts=timestamp_iso,
            hash_value=auto_hash,
            log_file=cli_log_file,
            files_csv=auto_files_csv,
        )


        # ------------------------------------------------------------
        #  Hashing & optional USER-DEFINED HASH from -p (scope: hash)
        # ------------------------------------------------------------
        # If present: compute content hash using that policy, write <wf>.hash, and append <wf>_user_defined.history
        # Hash schema (from yaml)
        """
        YAML schema for user-defined hash:

        - scope: hash                         # required marker to activate hashing
            include:                          # required, list of files/dirs/globs to hash
                - main.py
                - logs/**/*.out

            # Optional filters:
            allowed_extensions: [py, out]     # only include files with these extensions
            exclude_dirs: [__pycache__]       # skip directories by pattern
            exclude_files: ["*.tmp", "*.swp"] # skip files by pattern
            recursive: true                   # default: true

            # Output policies:
            overwrite: false                  # default: false; overwrite <wf>.hash if true
            reference: hash str or hash path  # optional; hex hash or path to file with hash
                                              # mismatch exits with EXIT_HASH_REFERENCE_MISMATCH (73)

        Behavior:
        - Always writes <wf>_input.history (auto run hash, independent of scope: hash)
        - If scope: hash present:
            * writes <wf>.hash (content hash)
            * appends <wf>_user_defined.history
            * validates against `reference` if provided
        """
        param_hash_cfg = {}
        try:
            param_hash_cfg = _collect_hash_cfg_from_param_sources_cli(args.parameters)
        except Exception as e:
            logger.warning(f"[hash] Failed to read scope: hash from param file(s): {e}")
            param_hash_cfg = {}

        if param_hash_cfg:
            cfg = param_hash_cfg
            paths = cfg.get("paths") or []
            overwrite = cfg.get("overwrite", False)
            reference = cfg.get("reference")

            # Validate that all included paths exist before hashing
            missing = []
            for p in paths:
                if not os.path.exists(p):
                    missing.append(os.path.abspath(str(p)))

            if missing:
                logger.error("[hash] The following included paths were not found:")
                for m in missing:
                    logger.error(f"[hash] Missing - {m}")
                logger.error("[hash] Aborting user-defined hash computation — missing files detected.")
                if overwrite:
                    logger.error("[hash] The .hash file will NOT be overwritten even if 'overwrite: true' is set.")
                _errlog_exit(EXIT_HASH_REFERENCE_MISMATCH)

            userdef_files_csv = "-"
            if paths:
                userdef_files_considered = _enumerate_hash_inputs_cli(
                    paths,
                    allowed_extensions=cfg.get("allowed_extensions"),
                    exclude_dirs=cfg.get("exclude_dirs"),
                    exclude_files=cfg.get("exclude_files"),
                    recursive=cfg.get("recursive", True),
                )
                if userdef_files_considered:
                    userdef_files_csv = ",".join(userdef_files_considered)

                userdef_hash = hash_content(
                    paths,
                    allowed_extensions=cfg.get("allowed_extensions"),
                    exclude_dirs=cfg.get("exclude_dirs"),
                    exclude_files=cfg.get("exclude_files"),
                    recursive=cfg.get("recursive", True),
                )
            else:
                logger.warning("[hash] No paths found in user hashing definitions")
                userdef_hash = hashlib.sha256(b"").hexdigest()

            # write <wf>.hash (same as before)
            hash_out_path = _default_hash_output_path_cli(logs_dir, resolved_module_path)
            logger.info(f"[hash] Generated hash from user definitions → {userdef_hash}")
            matched, new = _write_and_compare_hash_cli(logger, userdef_hash, hash_out_path, overwrite=overwrite)

            # status logging only for user-defined hash
            if matched:
                if new:
                    logger.info("[hash] STATUS: NEW  ✅")
                else:
                    logger.info("[hash] STATUS: MATCHED  ✅")
            else:
                logger.info("[hash] STATUS: MISMATCHED  ❌")

            userdef_history_path = _user_defined_history_path_cli(logs_dir, resolved_module_path)
            _append_history_line_cli(
                logger,
                history_path=userdef_history_path,
                ts=timestamp_iso,
                hash_value=userdef_hash,
                log_file=cli_log_file,
                files_csv=userdef_files_csv,
                user_provided=True
            )

            # Reference check (AFTER history append & status logging)
            if reference:
                expected = _resolve_reference_hash_cli(reference)
                if not expected:
                    logger.error(f"[hash] Invalid reference provided: {reference!r}")
                    _errlog_exit(EXIT_HASH_REFERENCE_MISMATCH)
                if userdef_hash != expected:
                    logger.error("[hash] ❌  Generated user-defined hash does NOT match reference ❌")
                    _errlog_exit(EXIT_HASH_REFERENCE_MISMATCH)
                else:
                    logger.info("[hash] ✅  Generated user-defined hash matched reference  ✅")
    
    
    # ------------------------------------------------------------
    #  Final exception handling and logging
    # ------------------------------------------------------------
    except Exception:
        logger.exception("Failed to execute module script")
        try:
            logger.warning("Cleaning up any active process(es) due to exception!")
            Process.kill_all()
        except Exception as e:
            logger.warning(f"Cleanup up during exception failed: {e}")
        # If module raised SystemExit, prefer that code; else generic failure
        sys.exit(exit_code_from_script if exit_code_from_script is not None else 1)

    finally:
        try:
            if _record_stat:
                _stats_stop.set()
                _t_stats.join(timeout=2.0)
        except Exception:
            pass

        try:
            if _record_stat:
                _additional_slurm_stats_from_sacct(Process, logger)
        except Exception:
            pass

        try:
            if _record_stat:
                _log_stats_summary_from_registry(Process, logger)
        except Exception:
            pass

        time.sleep(0.2)
        if exit_code_def == 0:
            logger.info("Ending jawm module script from jawm command")
        else:
            logger.error(f"Ending jawm module script from jawm command with exit code {exit_code_def}")
        # Now, if the script wanted to exit with a specific code, honor it
        if exit_code_from_script is not None:
            sys.exit(exit_code_from_script)



# ------------------------------------------------------------
#   jawm command from python jawm.cli.run()
# ------------------------------------------------------------
def run(argv=None, *, cwd=None, inprocess=False, capture=False, check=False):
    """
    Run jawm from Python with the same argv style as the CLI.

    Parameters
    ----------
    argv : list[str] | str | None
        CLI args excluding program name.
        - As a list: ["module.py", "--option", "value"]
        - As a string: 'module.py --option value' (will be split like a shell command)
    cwd : str | None
        Working directory to run from.
    inprocess : bool
        If False (default), run in a separate process (CLI-faithful, no side effects).
        If True, call main() in-process (faster, but may affect logging/stdout).
    capture : bool
        If True, return (rc, stdout, stderr). In subprocess mode capture is reliable.
        In in-process mode capture is best-effort (CLI may tee/replace stdout/stderr).
    check : bool
        If True, raise RuntimeError on non-zero exit code.

    Returns
    -------
    int OR (int, str, str)
        If capture=False: rc
        If capture=True: (rc, stdout, stderr)

    Examples
    --------
    Equivalent to running on the command line:
        $ jawm module.py --some-flag --param value -l logs_dir

    From Python (recommended, subprocess mode by default):

    >>> from jawm import cli
    >>> rc = cli.run(["module.py", "--some-flag", "--param", "value", "-l", "logs_dir"])
    >>> assert rc == 0

    You can also pass a single string (supports quotes):

    >>> rc = cli.run('module.py --some-flag --param "value with spaces" -l logs_dir')

    Run from a specific working directory (like `cd /path && jawm ...`):

    >>> rc = cli.run(["module.py", "--some-flag"], cwd="/path/to/project")

    Run in-process (faster, but may affect logging/stdout of the caller):

    >>> rc = cli.run(["module.py", "--some-flag"], inprocess=True)

    Capture output (especially useful in subprocess mode):

    >>> rc, out, err = cli.run(["--help"], capture=True)
    >>> print(out)
    """
    import contextlib
    import shlex

    if argv is None:
        argv = []
    elif isinstance(argv, str):
        argv = shlex.split(argv)
    else:
        argv = list(argv)

    if not inprocess:
        cmd = [sys.executable, "-m", "jawm.cli"] + argv
        if capture:
            r = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
            rc, out, err = int(r.returncode), (r.stdout or ""), (r.stderr or "")
        else:
            r = subprocess.run(cmd, cwd=cwd, check=False)
            rc, out, err = int(r.returncode), "", ""
    else:
        old_argv = sys.argv[:]
        old_cwd = os.getcwd()
        out_buf = io.StringIO() if capture else None
        err_buf = io.StringIO() if capture else None
        try:
            if cwd is not None:
                os.chdir(cwd)
            sys.argv = ["jawm"] + argv

            if capture:
                with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                    try:
                        main()
                        rc = 0
                    except SystemExit as e:
                        code = getattr(e, "code", 0)
                        rc = int(code) if isinstance(code, int) else (0 if code is None else 1)
            else:
                try:
                    main()
                    rc = 0
                except SystemExit as e:
                    code = getattr(e, "code", 0)
                    rc = int(code) if isinstance(code, int) else (0 if code is None else 1)

            out = out_buf.getvalue() if capture else ""
            err = err_buf.getvalue() if capture else ""
        finally:
            sys.argv = old_argv
            try:
                os.chdir(old_cwd)
            except Exception:
                pass

    if check and rc != 0:
        raise RuntimeError(f"[jawm] ERROR: jawm cli run failed with exit code {rc}")

    return (rc, out, err) if capture else rc


# ------------------------------------------------------------
#   Call the main
# ------------------------------------------------------------
if __name__ == "__main__":
    raise SystemExit(main())


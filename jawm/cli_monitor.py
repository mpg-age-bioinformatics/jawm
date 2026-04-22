"""
jawm-monitor — inspect running and completed jawm processes.

Reads the monitoring directory (~/.jawm/monitoring/ by default) and prints a
tabular summary of process state without touching the per-process log directories.
"""

import argparse
import os
import shutil
import sys
import time
from datetime import datetime

# ----------------------------------------------------------
#   Version detection
# ----------------------------------------------------------

try:
    from importlib import metadata as _md
except Exception:
    import importlib_metadata as _md  # type: ignore

_PKG_NAME = (__package__ or "jawm").split(".")[0]

try:
    _VERSION = _md.version(_PKG_NAME)
except Exception:
    _VERSION = "dev"

# ----------------------------------------------------------
#   Constants
# ----------------------------------------------------------

_DEFAULT_MON_DIR = os.environ.get(
    "JAWM_MONITORING_DIRECTORY",
    os.path.expanduser("~/.jawm/monitoring"),
)
_DEFAULT_GIT_DIR = os.path.expanduser("~/.jawm/git")
_DEFAULT_LOG_DIR = "logs"   # relative to cwd; override with -l/--log-dir

_STALE_S      = 48 * 3600        # 48 h  → show as STALE
_UNRESOLVED_S = 7  * 24 * 3600   # 7 days → hide, count in footer

_VALID_CMDS = {"ps", "clean"}

# ANSI colour codes (only applied when stdout is a tty)
_C = {
    "RUNNING":    "\033[33m",   # yellow
    "STALE":      "\033[35m",   # magenta
    "OK":         "\033[32m",   # green
    "FAILED":     "\033[31m",   # red
    "UNRESOLVED": "\033[90m",   # dark grey
    "DIM":        "\033[2m",
    "RESET":      "\033[0m",
}


# ----------------------------------------------------------
#   Monitoring file helpers
# ----------------------------------------------------------

def _mon_dir(override):
    """Resolve the monitoring directory from arg override or environment."""
    d = override or os.environ.get("JAWM_MONITORING_DIRECTORY") or os.path.expanduser("~/.jawm/monitoring")
    return os.path.expanduser(str(d))


def _parse_file(path):
    """
    Parse a key-value monitoring text file into a dict.
    Lines are "Key: value" pairs.  Returns {} on any error.
    """
    data = {}
    try:
        with open(path, "r") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if ": " in line:
                    key, _, val = line.partition(": ")
                    data[key.strip()] = val.strip()
                elif line.endswith(":"):
                    data[line[:-1].strip()] = ""
    except Exception:
        pass
    return data


def _parse_dt(s):
    """Parse a jawm datetime string ('20260407_095002') → datetime, or None."""
    if not s or s.strip() in ("NA", "", "None"):
        return None
    try:
        return datetime.strptime(s.strip(), "%Y%m%d_%H%M%S")
    except Exception:
        return None


def _fmt_dt(dt):
    """Format datetime for display, or return '-'."""
    if dt is None:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _fmt_duration(total_s):
    """Format a duration in seconds as a compact human-readable string."""
    total_s = int(total_s)
    if total_s < 0:
        return "-"
    h, rem = divmod(total_s, 3600)
    m, s   = divmod(rem, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    if m > 0:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def _fname_parse_running(fname):
    """
    Parse '<manager>.<id>.txt' → (manager, job_id).
    Manager has no dots; id may (e.g. k8s pod names).
    """
    base = fname[:-4]  # strip .txt
    dot  = base.find(".")
    if dot >= 0:
        return base[:dot], base[dot + 1:]
    return base, ""


def _fname_parse_completed(fname):
    """
    Parse '<manager>.<id>.<exitcode>.txt' → (manager, job_id, exitcode_str).
    Manager has no dots; id may contain dots; exitcode is an integer string.
    """
    base = fname[:-4]  # strip .txt
    dot  = base.find(".")
    if dot < 0:
        return base, "", ""
    manager   = base[:dot]
    rest      = base[dot + 1:]
    last_dot  = rest.rfind(".")
    if last_dot >= 0:
        return manager, rest[:last_dot], rest[last_dot + 1:]
    return manager, rest, ""


# ----------------------------------------------------------
#   Entry loading
# ----------------------------------------------------------

def _load_running(mon_dir):
    """Return a list of dicts for all files in Running/, sorted by Run Start asc."""
    running_dir = os.path.join(mon_dir, "Running")
    entries = []
    if not os.path.isdir(running_dir):
        return entries
    for fname in os.listdir(running_dir):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(running_dir, fname)
        data  = _parse_file(fpath)
        if not data:
            continue
        mgr, jid = _fname_parse_running(fname)
        data.setdefault("Manager", mgr)
        data.setdefault("Job ID", jid)
        data["_status"] = "RUNNING"
        data["_mtime"]  = os.path.getmtime(fpath)
        data["_fpath"]  = fpath
        data["_fname"]  = fname
        entries.append(data)
    entries.sort(key=lambda e: e.get("Run Start") or "")
    return entries


def _sort_key_completed(data, mtime):
    """
    Return a sort key (string, sortable lexicographically) for a completed entry.

    Preference order for OK / FAILED:
      1. Run End   — actual completion time
      2. Run Start — fallback if Run End is missing
      3. mtime     — last resort

    For UNRESOLVED entries Run End is set to when 'clean -u' ran, not when
    the process actually did anything useful.  We deliberately skip it and
    use Run Start so that old abandoned processes sort by when they started,
    not by when the operator resolved them.
    """
    run_end   = data.get("Run End", "")
    run_start = data.get("Run Start", "")
    ec        = data.get("Exit Code", "")

    # jawm datetime strings are lexicographically sortable (YYYYMMDD_HHMMSS)
    if ec.upper() != "UNRESOLVED":
        if run_end and run_end not in ("NA", "None"):
            return run_end
    if run_start and run_start not in ("NA", "None"):
        return run_start
    # Fallback: convert mtime epoch to a comparable string
    return datetime.fromtimestamp(mtime).strftime("%Y%m%d_%H%M%S")


def _load_completed(mon_dir, last_n):
    """
    Return a list of dicts for files in Completed/, sorted oldest-first.
    last_n=0 means no limit.

    Entries are ordered by actual process time (Run End > Run Start > mtime),
    not by filesystem mtime.  This prevents UNRESOLVED entries — whose file
    mtime is set to when 'clean -u' ran rather than when the process started —
    from dominating the 'last N' window.
    """
    completed_dir = os.path.join(mon_dir, "Completed")
    entries = []
    if not os.path.isdir(completed_dir):
        return entries

    raw = []
    for fname in os.listdir(completed_dir):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(completed_dir, fname)
        mtime = os.path.getmtime(fpath)
        data  = _parse_file(fpath)
        if not data:
            continue
        mgr, jid, ec_fname = _fname_parse_completed(fname)
        data.setdefault("Manager", mgr)
        data.setdefault("Job ID", jid)
        ec = data.get("Exit Code", ec_fname).strip()
        data["Exit Code"] = ec
        data["_mtime"] = mtime
        data["_fpath"] = fpath
        data["_fname"] = fname
        if ec.upper() == "UNRESOLVED":
            data["_status"] = "UNRESOLVED"
        else:
            try:
                data["_status"] = "OK" if int(ec) == 0 else "FAILED"
            except Exception:
                data["_status"] = "DONE"
        data["_sort_key"] = _sort_key_completed(data, mtime)
        raw.append(data)

    # Select the most recent N entries by process time, then display oldest-first
    raw.sort(key=lambda d: d["_sort_key"], reverse=True)
    if last_n > 0:
        raw = raw[:last_n]
    raw.reverse()  # oldest at top, newest at bottom

    return raw


# ----------------------------------------------------------
#   Display helpers
# ----------------------------------------------------------

def _trunc(s, n):
    """Truncate string to n chars, adding an ellipsis character if needed."""
    s = str(s) if s is not None else ""
    if len(s) > n:
        return s[: n - 1] + "…"
    return s


def _colorize(text, code, use_color):
    if not use_color or not code:
        return text
    return f"{code}{text}{_C['RESET']}"


def _build_rows(entries, wide, now):
    """
    Convert entry dicts into display rows (list of string lists).

    Columns: STATUS  NAME  HASH  MANAGER  ID  STARTED  ELAPSED  ENDED  EXIT  [PATH]

    ELAPSED:
      - RUNNING / STALE  → time from Run Start to now  (live duration)
      - Completed        → time from Run Start to Run End  (final duration)
    ENDED:
      - RUNNING / STALE  → "-"
      - Completed        → Run End datetime
    """
    rows = []
    for e in entries:
        status   = e.get("_status", "?")
        name     = e.get("Job Name", "-")
        hash_    = e.get("Job Hash", "-")
        manager  = e.get("Manager", "-")
        job_id   = e.get("Job ID", "-")
        start_dt = _parse_dt(e.get("Run Start"))
        started  = _fmt_dt(start_dt)

        if status in ("RUNNING", "STALE"):
            elapsed   = _fmt_duration((now - start_dt).total_seconds()) if start_dt else "pending"
            ended     = "-"
            exit_code = "-"
        elif status == "UNRESOLVED":
            # We don't know when the process actually ended — the Run End timestamp
            # is just when clean -u ran, not real completion. Show nothing meaningful.
            elapsed   = "-"
            ended     = "-"
            exit_code = "UNRESOLVED"
        else:
            end_dt    = _parse_dt(e.get("Run End"))
            elapsed   = _fmt_duration((end_dt - start_dt).total_seconds()) if (start_dt and end_dt) else "-"
            ended     = _fmt_dt(end_dt)
            exit_code = str(e.get("Exit Code", "-"))

        row = [status, name, hash_, manager, job_id, started, elapsed, ended, exit_code]
        if wide:
            row.append(e.get("Path", "-"))
        rows.append(row)
    return rows


# ----------------------------------------------------------
#   Column format helpers
# ----------------------------------------------------------

# Canonical column names → index in the row produced by _build_rows  (ps)
_COL_INDEX = {
    "status":   0,
    "name":     1,
    "hash":     2,
    "manager":  3,
    "id":       4,
    "started":  5,
    "elapsed":  6,
    "ended":    7,
    "exit":     8,
    "path":     9,   # only present when --wide is active
}

# Column names → index for `logs --ls` rows (different layout from ps)
_LOG_LS_COL_INDEX = {
    "status":   0,
    "name":     1,
    "hash":     2,
    "started":  3,
    "ended":    4,
    "elapsed":  5,
    "exit":     6,
    "dir":      7,   # only present when --wide is active
}


def _parse_fmt(fmt_str, col_map=None):
    """
    Parse a --fmt string such as "name:60,id:30" into {col_index: width}.

    Accepted separators between name and width: ':' or '='.
    Column names are case-insensitive.
    col_map defaults to _COL_INDEX (ps columns); pass _LOG_LS_COL_INDEX for logs --ls.
    Returns a dict mapping column index → new cap width.
    Raises ValueError on unrecognised column names or non-integer widths.
    """
    if col_map is None:
        col_map = _COL_INDEX
    overrides = {}
    if not fmt_str:
        return overrides
    for token in fmt_str.split(","):
        token = token.strip()
        if not token:
            continue
        # accept both 'name:60' and 'name=60'
        if ":" in token:
            col, _, val = token.partition(":")
        elif "=" in token:
            col, _, val = token.partition("=")
        else:
            raise ValueError(
                f"Invalid format token {token!r}. Expected 'col:width' or 'col=width'."
            )
        col = col.strip().lower()
        if col not in col_map:
            known = ", ".join(sorted(col_map))
            raise ValueError(
                f"Unknown column {col!r}. Known columns: {known}."
            )
        try:
            width = int(val.strip())
        except ValueError:
            raise ValueError(
                f"Column width for {col!r} must be an integer, got {val.strip()!r}."
            )
        if width < 1:
            raise ValueError(f"Column width must be ≥ 1, got {width} for {col!r}.")
        overrides[col_map[col]] = width
    return overrides


# ----------------------------------------------------------
#   ps command
# ----------------------------------------------------------

def _cmd_ps(args):
    mon = _mon_dir(getattr(args, "dir", None))

    only_running  = args.running and not args.completed
    only_completed = args.completed and not args.running
    show_running   = not only_completed
    show_completed = not only_running

    last_n    = 0 if args.all else max(0, args.last)
    wide      = getattr(args, "wide", False)
    no_header = getattr(args, "no_header", False)
    use_color = sys.stdout.isatty() and not getattr(args, "no_color", False)

    fmt_overrides = {}
    if getattr(args, "fmt", None):
        try:
            fmt_overrides = _parse_fmt(args.fmt)
        except ValueError as exc:
            print(f"jawm-monitor ps: --fmt: {exc}", file=sys.stderr)
            return 1

    if not os.path.isdir(mon):
        print(f"jawm-monitor: monitoring directory not found: {mon}")
        print("  Set JAWM_MONITORING_DIRECTORY or pass --dir to override.")
        return 1

    now = datetime.now()

    # --- classify running entries ---
    raw_running      = _load_running(mon) if show_running else []
    visible_running  = []
    unresolved_count = 0

    for e in raw_running:
        start_dt = _parse_dt(e.get("Run Start"))
        if start_dt is None:
            visible_running.append(e)
            continue
        elapsed_s = (now - start_dt).total_seconds()
        if elapsed_s > _UNRESOLVED_S:
            unresolved_count += 1
        elif elapsed_s > _STALE_S:
            e["_status"] = "STALE"
            visible_running.append(e)
        else:
            visible_running.append(e)

    completed_entries = _load_completed(mon, last_n) if show_completed else []
    all_entries       = visible_running + completed_entries

    if not all_entries and unresolved_count == 0:
        parts = []
        if show_running:
            parts.append("no running processes")
        if show_completed:
            parts.append("no completed processes")
        print(f"jawm-monitor: {' and '.join(parts)} found in {mon}")
        return 0

    # --- table ---
    headers = ["STATUS", "NAME",  "HASH",  "MANAGER", "ID",  "STARTED", "ELAPSED", "ENDED", "EXIT"]
    caps    = [10,        30,      12,      10,         15,    19,        12,        19,       6   ]
    if wide:
        headers.append("LOG PATH")
        caps.append(60)

    # Apply --fmt overrides (col index → new cap width)
    for col_idx, new_width in fmt_overrides.items():
        if col_idx < len(caps):
            caps[col_idx] = new_width

    rows  = _build_rows(all_entries, wide, now)
    sep   = "  "

    # dynamic column widths, capped
    col_w = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_w[i] = min(caps[i], max(col_w[i], len(str(cell))))

    if not no_header and rows:
        hdr = sep.join(h.ljust(col_w[i]) for i, h in enumerate(headers))
        print(_colorize(hdr, _C["DIM"], use_color))
        print(_colorize("-" * len(hdr), _C["DIM"], use_color))

    for row in rows:
        status = row[0]
        color  = _C.get(status, "") if use_color else ""
        cells  = [_trunc(str(row[i]), col_w[i]).ljust(col_w[i]) for i in range(len(row))]
        if color:
            line = f"{color}{cells[0]}{_C['RESET']}{sep}{sep.join(cells[1:])}"
        else:
            line = sep.join(cells)
        print(line)

    # --- footer ---
    if not no_header:
        parts = []
        if show_running:
            n_run   = sum(1 for e in visible_running if e["_status"] == "RUNNING")
            n_stale = sum(1 for e in visible_running if e["_status"] == "STALE")
            run_label = f"{n_run} running"
            if n_stale:
                run_label += f", {n_stale} stale (>48h)"
            parts.append(run_label)
        if show_completed:
            label = f"{len(completed_entries)} completed"
            if last_n > 0:
                label += f" (last {last_n})"
            parts.append(label)

        footer = f"  {mon}  |  {', '.join(parts)}"
        if unresolved_count:
            footer += f"  |  {unresolved_count} unresolved (>7d) — run 'jawm-monitor clean -u' to resolve"

        print()
        print(_colorize(footer, _C["DIM"], use_color))

    return 0


# ----------------------------------------------------------
#   clean helpers
# ----------------------------------------------------------

def _assert_inside(path, root):
    """
    Raise ValueError if *path* is not inside *root* after normalisation.

    This is a last-ditch containment guard: collectors always produce paths
    from os.listdir so they should already be safe, but this ensures no
    path can escape its expected directory even if the call chain changes.
    """
    real_path = os.path.realpath(os.path.abspath(path))
    real_root = os.path.realpath(os.path.abspath(root))
    if not real_path.startswith(real_root + os.sep) and real_path != real_root:
        raise ValueError(
            f"Safety check failed: {path!r} is not inside {root!r}\n"
            f"  resolved path: {real_path}\n"
            f"  expected root: {real_root}"
        )


def _check_mon_dir(mon):
    """
    Lightweight sanity check that *mon* looks like a jawm monitoring directory.
    It must have at least one of Running/ or Completed/ as a direct child.
    Raises ValueError if neither exists so callers can bail before touching anything.
    """
    has_running   = os.path.isdir(os.path.join(mon, "Running"))
    has_completed = os.path.isdir(os.path.join(mon, "Completed"))
    if not (has_running or has_completed):
        raise ValueError(
            f"{mon!r} does not look like a jawm monitoring directory "
            f"(expected a Running/ or Completed/ subdirectory)."
        )


def _parse_age(s):
    """
    Parse an age string into seconds.
    Accepts: '7d', '48h', '30' (bare integer → days).
    Returns float seconds, or raises ValueError on bad input.
    """
    s = s.strip().lower()
    try:
        if s.endswith("d"):
            return float(s[:-1]) * 86400
        if s.endswith("h"):
            return float(s[:-1]) * 3600
        return float(s) * 86400  # default unit: days
    except (ValueError, AttributeError):
        raise ValueError(f"Invalid age format: {s!r}. Use e.g. '7d', '48h', or '30' (days).")


def _confirm(prompt, force):
    """Ask for confirmation. Returns True if force=True or user types y/yes."""
    if force:
        return True
    try:
        ans = input(f"{prompt} [y/N] ").strip().lower()
        return ans in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _fmt_size(n_bytes):
    """Format a byte count as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TB"


def _path_size(p):
    """Return total size of a file or directory tree in bytes."""
    try:
        if os.path.isfile(p):
            return os.path.getsize(p)
        total = 0
        for dirpath, _, filenames in os.walk(p):
            for fname in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fname))
                except OSError:
                    pass
        return total
    except Exception:
        return 0


# ----------------------------------------------------------
#   clean — collectors (pure read, return what would be acted on)
# ----------------------------------------------------------

def _collect_unresolved(mon, threshold_s, now):
    """
    Find Running/ entries older than threshold_s.
    Returns list of (running_fpath, new_completed_fpath, data_dict).
    """
    results = []
    running_dir   = os.path.join(mon, "Running")
    completed_dir = os.path.join(mon, "Completed")
    if not os.path.isdir(running_dir):
        return results
    for e in _load_running(mon):
        start_dt = _parse_dt(e.get("Run Start"))
        if start_dt is None:
            continue
        if (now - start_dt).total_seconds() > threshold_s:
            # Derive manager and job-id from the *filename* (written by jawm,
            # not user-controlled content) to avoid path-traversal if a
            # monitoring file's content were ever crafted with "../" in it.
            src_fname = e["_fname"]                        # e.g. local.85628.txt
            mgr, jid  = _fname_parse_running(src_fname)   # parse from filename
            new_fname = f"{mgr}.{jid}.UNRESOLVED.txt"
            new_fpath = os.path.join(completed_dir, new_fname)
            results.append((e["_fpath"], new_fpath, e))
    return results


def _collect_running_to_remove(mon, older_than_s, keep_last, now):
    """
    Collect Running/ file paths to delete.
    older_than_s=None and keep_last=None → all entries.
    older_than_s → only entries older than threshold (by Run Start).
    keep_last    → keep the N most recently started, remove the rest.
    """
    entries = _load_running(mon)
    if not entries:
        return []

    if older_than_s is not None:
        def _is_old(e):
            dt = _parse_dt(e.get("Run Start"))
            if dt is None:
                return False
            return (now - dt).total_seconds() > older_than_s
        entries = [e for e in entries if _is_old(e)]

    if keep_last is not None and keep_last >= 0:
        # sort newest first, skip first keep_last, the rest are removed
        entries_by_newest = sorted(entries, key=lambda e: e.get("Run Start") or "", reverse=True)
        entries = entries_by_newest[keep_last:]

    return [e["_fpath"] for e in entries]


def _collect_completed_to_remove(mon, older_than_s, keep_last, now):
    """
    Collect Completed/ file paths to delete.
    older_than_s=None and keep_last=None → all entries.
    older_than_s → only entries older than threshold (by mtime).
    keep_last    → keep the N most recently completed, remove the rest.
    """
    completed_dir = os.path.join(mon, "Completed")
    if not os.path.isdir(completed_dir):
        return []

    files = []
    for fname in os.listdir(completed_dir):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(completed_dir, fname)
        mtime = os.path.getmtime(fpath)
        files.append((mtime, fpath))

    if not files:
        return []

    if older_than_s is not None:
        cutoff = now.timestamp() - older_than_s
        files = [(m, p) for m, p in files if m < cutoff]

    if keep_last is not None and keep_last >= 0:
        # sort newest first, skip first keep_last, the rest are removed
        files_newest = sorted(files, key=lambda x: x[0], reverse=True)
        files = files_newest[keep_last:]

    return [p for _, p in files]


def _collect_unresolved_running_to_remove(mon, threshold_s, now):
    """
    Find Running/ entries older than threshold_s for direct deletion (no move).
    Returns a list of file paths.
    Uses the same age logic as _collect_unresolved but skips the move step.
    """
    results = []
    if not os.path.isdir(os.path.join(mon, "Running")):
        return results
    for e in _load_running(mon):
        start_dt = _parse_dt(e.get("Run Start"))
        if start_dt is None:
            continue
        if (now - start_dt).total_seconds() > threshold_s:
            results.append(e["_fpath"])
    return results


def _collect_unresolved_completed_to_remove(mon, older_than_s, now):
    """
    Find Completed/ entries whose Exit Code is UNRESOLVED.
    older_than_s=None → all UNRESOLVED entries.
    older_than_s      → only entries whose Run Start is older than the threshold.
                        Falls back to mtime if Run Start is absent.
    Returns a list of file paths.
    """
    completed_dir = os.path.join(mon, "Completed")
    if not os.path.isdir(completed_dir):
        return []
    results = []
    for fname in os.listdir(completed_dir):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(completed_dir, fname)
        data  = _parse_file(fpath)
        if not data:
            continue
        ec = data.get("Exit Code", "").strip()
        if ec.upper() != "UNRESOLVED":
            continue
        if older_than_s is not None:
            # Prefer Run Start (reliable for UNRESOLVED); fall back to mtime.
            run_start = _parse_dt(data.get("Run Start"))
            if run_start is not None:
                age_s = (now - run_start).total_seconds()
            else:
                age_s = now.timestamp() - os.path.getmtime(fpath)
            if age_s <= older_than_s:
                continue   # not old enough — keep it
        results.append(fpath)
    return results


def _collect_git_to_remove(git_dir, older_than_s, keep_last, now):
    """
    Collect git cache entries (immediate children of git_dir) to delete.
    older_than_s=None and keep_last=None → all entries.
    older_than_s → entries not accessed in that many seconds (by mtime).
    keep_last    → keep the N most recently accessed, remove the rest.
    """
    if not os.path.isdir(git_dir):
        return []

    entries = []
    for name in os.listdir(git_dir):
        p = os.path.join(git_dir, name)
        mtime = os.path.getmtime(p)
        entries.append((mtime, p))

    if not entries:
        return []

    if older_than_s is not None:
        cutoff = now.timestamp() - older_than_s
        entries = [(m, p) for m, p in entries if m < cutoff]

    if keep_last is not None and keep_last >= 0:
        entries_newest = sorted(entries, key=lambda x: x[0], reverse=True)
        entries = entries_newest[keep_last:]

    return [p for _, p in entries]


# ----------------------------------------------------------
#   clean — executors
# ----------------------------------------------------------

def _do_resolve(items, dry_run, use_color):
    """Move Running entries to Completed/ as UNRESOLVED."""
    tag = _colorize("UNRESOLVED", _C["UNRESOLVED"], use_color)
    for running_fpath, completed_fpath, data in items:
        src_name  = os.path.basename(running_fpath)
        dest_name = os.path.basename(completed_fpath)
        if dry_run:
            print(f"  {src_name}  →  {dest_name}")
            continue
        try:
            os.makedirs(os.path.dirname(completed_fpath), exist_ok=True)
            with open(completed_fpath, "w") as fh:
                # Re-write all original fields; no Run End — the process never
                # finished cleanly so there is no meaningful end timestamp.
                for key in ("Job ID", "Job Name", "Job Hash", "Manager", "Path",
                            "Process Initiated", "Run Start"):
                    val = data.get(key, "")
                    if val:
                        fh.write(f"{key}: {val}\n")
                fh.write("Exit Code: UNRESOLVED\n")
            if os.path.exists(running_fpath):
                os.remove(running_fpath)
            print(f"  {src_name}  →  {dest_name}  [{tag}]")
        except Exception as exc:
            print(f"  {src_name}  ERROR: {exc}", file=sys.stderr)


def _do_remove_files(fpaths, dry_run, root_dir):
    """
    Delete a list of file paths.
    root_dir is used for a containment safety check on every path.
    """
    for fpath in fpaths:
        fname = os.path.basename(fpath)
        if dry_run:
            print(f"  {fname}")
            continue
        try:
            _assert_inside(fpath, root_dir)
            os.remove(fpath)
            print(f"  removed  {fname}")
        except ValueError as exc:
            print(f"  SKIPPED  {fname}: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"  ERROR removing {fname}: {exc}", file=sys.stderr)


def _do_remove_paths(paths, dry_run, root_dir):
    """
    Delete a list of file/directory paths (git cache entries).
    root_dir is used for a containment safety check on every path.
    Symlinks are removed as links only — never recursively deleted.
    """
    for p in paths:
        name = os.path.basename(p)
        size = _fmt_size(_path_size(p))
        if dry_run:
            print(f"  {name}  ({size})")
            continue
        try:
            _assert_inside(p, root_dir)
            if os.path.islink(p):
                # Remove the symlink itself, never follow it into external data.
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            print(f"  removed  {name}  ({size})")
        except ValueError as exc:
            print(f"  SKIPPED  {name}: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"  ERROR removing {name}: {exc}", file=sys.stderr)


# ----------------------------------------------------------
#   clean — summary (no args: show counts + help)
# ----------------------------------------------------------

def _clean_summary(mon, git_dir, use_color):
    now = datetime.now()

    # Running counts
    running_all = _load_running(mon) if os.path.isdir(mon) else []
    n_run_total = len(running_all)
    n_stale, n_unresolved = 0, 0
    for e in running_all:
        dt = _parse_dt(e.get("Run Start"))
        if dt is None:
            continue
        s = (now - dt).total_seconds()
        if s > _UNRESOLVED_S:
            n_unresolved += 1
        elif s > _STALE_S:
            n_stale += 1

    # Completed counts
    completed_dir = os.path.join(mon, "Completed")
    n_completed = len([f for f in os.listdir(completed_dir) if f.endswith(".txt")]) \
        if os.path.isdir(completed_dir) else 0

    # Git cache
    n_git = len(os.listdir(git_dir)) if os.path.isdir(git_dir) else 0
    git_size = _fmt_size(_path_size(git_dir)) if os.path.isdir(git_dir) else "0 B"

    dim = _C["DIM"] if use_color else ""
    rst = _C["RESET"] if use_color else ""

    print(f"{dim}jawm-monitor clean — nothing was changed  (pass flags to act){rst}")
    print()
    print(f"  Monitoring: {mon}")
    print(f"    Running:    {n_run_total} entries"
          + (f"  ({n_stale} stale >48h,  {n_unresolved} unresolved >7d)" if (n_stale or n_unresolved) else ""))
    print(f"    Completed:  {n_completed} entries")
    print()
    print(f"  Git cache:  {git_dir}")
    print(f"    Entries:    {n_git}  ({git_size})")
    print()
    print(f"  Available flags:")
    print(f"    -u, --unresolved          move running >7d to Completed/ as UNRESOLVED")
    print(f"    -U, --delete-unresolved   delete all UNRESOLVED from Running/ and Completed/")
    print(f"    --running                 remove running entries")
    print(f"    --completed               remove completed entries")
    print(f"    --git-cache               clean git cache entries")
    print(f"    --all                     resolve unresolved + remove all running + completed")
    print(f"    --older-than <age>        filter by age  (e.g. 7d, 48h, 30)")
    print(f"    --keep-last N             keep N most recent entries")
    print(f"    -n, --dry-run             preview without making changes")
    print(f"    -f, --force               skip confirmation prompt")
    print()
    print(f"  Examples:")
    print(f"    jawm-monitor clean -u                    # move hanging >7d → UNRESOLVED")
    print(f"    jawm-monitor clean -U                    # delete all UNRESOLVED entries")
    print(f"    jawm-monitor clean -U --older-than 30d   # delete UNRESOLVED older than 30 days")
    print(f"    jawm-monitor clean --completed --older-than 30d")
    print(f"    jawm-monitor clean --running --keep-last 10")
    print(f"    jawm-monitor clean --git-cache --keep-last 5")
    print(f"    jawm-monitor clean --all --dry-run")


# ----------------------------------------------------------
#   clean command
# ----------------------------------------------------------

def _cmd_clean(args):
    mon     = _mon_dir(getattr(args, "dir", None))
    git_dir = _DEFAULT_GIT_DIR
    now     = datetime.now()

    use_color = sys.stdout.isatty() and not getattr(args, "no_color", False)
    dry_run   = args.dry_run
    force     = args.force

    # Sanity-check the monitoring directory before touching anything.
    # Bail early if it doesn't look like a jawm monitoring directory so that
    # a mis-typed --dir can't accidentally delete unrelated .txt files.
    has_action_flags = any([
        args.unresolved, args.delete_unresolved,
        args.running, args.completed, args.git_cache, args.all,
        args.older_than, args.keep_last is not None,
    ])
    if has_action_flags and os.path.isdir(mon):
        try:
            _check_mon_dir(mon)
        except ValueError as exc:
            print(f"jawm-monitor clean: {exc}", file=sys.stderr)
            return 1

    # -u and -U are mutually exclusive (move vs delete — pick one)
    if args.unresolved and args.delete_unresolved:
        print("jawm-monitor clean: -u/--unresolved and -U/--delete-unresolved are mutually exclusive.", file=sys.stderr)
        return 1

    # Validate: --older-than and --keep-last are mutually exclusive
    if args.older_than and args.keep_last is not None:
        print("jawm-monitor clean: --older-than and --keep-last are mutually exclusive.", file=sys.stderr)
        return 1

    older_than_s = None
    if args.older_than:
        try:
            older_than_s = _parse_age(args.older_than)
        except ValueError as exc:
            print(f"jawm-monitor clean: {exc}", file=sys.stderr)
            return 1

    keep_last = args.keep_last  # int or None

    # Determine which actions are requested
    do_unresolved        = args.unresolved        or args.all
    do_delete_unresolved = args.delete_unresolved
    do_running           = args.running           or args.all
    do_completed         = args.completed         or args.all
    do_git               = args.git_cache

    # --older-than alone (no target) → apply to running + completed
    if older_than_s is not None and not any([do_unresolved, do_delete_unresolved,
                                             do_running, do_completed, do_git]):
        do_running   = True
        do_completed = True

    # --keep-last alone (no target) → error
    if keep_last is not None and not any([do_running, do_completed, do_git]):
        print("jawm-monitor clean: --keep-last requires a target (--running, --completed, or --git-cache).", file=sys.stderr)
        return 1

    has_action = any([do_unresolved, do_delete_unresolved, do_running, do_completed, do_git])
    if not has_action:
        _clean_summary(mon, git_dir, use_color)
        return 0

    # --- Collect what would be affected ---

    # 1. Unresolved move (-u): use --older-than as threshold if specified, else default 7d
    unresolved_items = []
    if do_unresolved:
        threshold = older_than_s if (args.unresolved and older_than_s) else _UNRESOLVED_S
        unresolved_items = _collect_unresolved(mon, threshold, now)

    # 2. Unresolved delete (-U): Running entries to delete + Completed UNRESOLVED entries
    #    --older-than filters both sides; no --keep-last (doesn't apply to UNRESOLVED).
    #    Deduplication: exclude any paths already covered by -u above (shouldn't overlap
    #    since -u and -U are mutually exclusive, but be defensive).
    unresolved_move_paths = {fp for fp, _, _ in unresolved_items}
    ur_running_delete   = []
    ur_completed_delete = []
    if do_delete_unresolved:
        threshold = older_than_s if older_than_s else _UNRESOLVED_S
        ur_running_delete = [
            p for p in _collect_unresolved_running_to_remove(mon, threshold, now)
            if p not in unresolved_move_paths
        ]
        ur_completed_delete = _collect_unresolved_completed_to_remove(mon, older_than_s, now)

    # 3. Running: for --all, remove all remaining; for --running, respect filters.
    #    Exclude entries already captured by -u (move) or -U (delete).
    running_files = []
    if do_running:
        ot = older_than_s if args.running else None   # --all ignores --older-than for running
        kl = keep_last    if args.running else None
        excluded = unresolved_move_paths | set(ur_running_delete)
        all_running_files = _collect_running_to_remove(mon, ot, kl, now)
        running_files = [f for f in all_running_files if f not in excluded]

    # 4. Completed: exclude entries already captured by -U to avoid double-listing.
    completed_files = []
    if do_completed:
        ot = older_than_s
        kl = keep_last if args.completed else None
        excluded_completed = set(ur_completed_delete)
        all_completed = _collect_completed_to_remove(mon, ot, kl, now)
        completed_files = [f for f in all_completed if f not in excluded_completed]

    # 5. Git cache
    git_paths = []
    if do_git:
        git_paths = _collect_git_to_remove(git_dir, older_than_s, keep_last, now)

    # --- Nothing to do ---
    total = (len(unresolved_items) + len(ur_running_delete) + len(ur_completed_delete)
             + len(running_files) + len(completed_files) + len(git_paths))
    if total == 0:
        print("jawm-monitor clean: nothing to clean.")
        return 0

    # --- Preview ---
    if unresolved_items:
        print(f"Resolve {len(unresolved_items)} running entr{'y' if len(unresolved_items)==1 else 'ies'} → UNRESOLVED:")
        for fp, cfp, _ in unresolved_items:
            print(f"  {os.path.basename(fp)}  →  {os.path.basename(cfp)}")
    if ur_running_delete or ur_completed_delete:
        n = len(ur_running_delete) + len(ur_completed_delete)
        print(f"Delete {n} UNRESOLVED entr{'y' if n==1 else 'ies'} "
              f"({len(ur_running_delete)} running,  {len(ur_completed_delete)} completed):")
        for fp in ur_running_delete:
            print(f"  [running]   {os.path.basename(fp)}")
        for fp in ur_completed_delete:
            print(f"  [completed] {os.path.basename(fp)}")
    if running_files:
        print(f"Remove {len(running_files)} running entr{'y' if len(running_files)==1 else 'ies'}:")
        for fp in running_files:
            print(f"  {os.path.basename(fp)}")
    if completed_files:
        print(f"Remove {len(completed_files)} completed entr{'y' if len(completed_files)==1 else 'ies'}:")
        for fp in completed_files:
            print(f"  {os.path.basename(fp)}")
    if git_paths:
        total_size = _fmt_size(sum(_path_size(p) for p in git_paths))
        print(f"Remove {len(git_paths)} git cache entr{'y' if len(git_paths)==1 else 'ies'}  ({total_size}):")
        for p in git_paths:
            print(f"  {os.path.basename(p)}")

    if dry_run:
        print("\n(dry run — no changes made)")
        return 0

    # --- Confirm ---
    print()
    if not _confirm(f"  Proceed with {total} operation(s)?", force):
        print("Aborted.")
        return 0
    print()

    # --- Execute ---
    if unresolved_items:
        print(f"Resolving {len(unresolved_items)} unresolved {'entry' if len(unresolved_items)==1 else 'entries'}:")
        _do_resolve(unresolved_items, dry_run=False, use_color=use_color)
    if ur_running_delete:
        print(f"Deleting {len(ur_running_delete)} UNRESOLVED running {'entry' if len(ur_running_delete)==1 else 'entries'}:")
        _do_remove_files(ur_running_delete, dry_run=False, root_dir=os.path.join(mon, "Running"))
    if ur_completed_delete:
        print(f"Deleting {len(ur_completed_delete)} UNRESOLVED completed {'entry' if len(ur_completed_delete)==1 else 'entries'}:")
        _do_remove_files(ur_completed_delete, dry_run=False, root_dir=os.path.join(mon, "Completed"))
    if running_files:
        print(f"Removing {len(running_files)} running {'entry' if len(running_files)==1 else 'entries'}:")
        _do_remove_files(running_files, dry_run=False, root_dir=os.path.join(mon, "Running"))
    if completed_files:
        print(f"Removing {len(completed_files)} completed {'entry' if len(completed_files)==1 else 'entries'}:")
        _do_remove_files(completed_files, dry_run=False, root_dir=os.path.join(mon, "Completed"))
    if git_paths:
        print(f"Removing {len(git_paths)} git cache {'entry' if len(git_paths)==1 else 'entries'}:")
        _do_remove_paths(git_paths, dry_run=False, root_dir=git_dir)

    print("\nDone.")
    return 0


# ----------------------------------------------------------
#   logs — directory helpers
# ----------------------------------------------------------

def _parse_proc_dir_name(dirname):
    """
    Parse '<name>_<YYYYMMDD>_<HHMMSS>_<hash>' → (name, 'YYYYMMDD_HHMMSS', hash).
    Returns None if dirname doesn't match the expected pattern.
    The name portion may itself contain underscores; parsing is anchored from the right.
    """
    parts = dirname.rsplit("_", 3)
    if len(parts) != 4:
        return None
    name, date, time_, hash_ = parts
    if (len(date) == 8 and date.isdigit() and
            len(time_) == 6 and time_.isdigit() and
            len(hash_) == 10 and hash_.isalnum()):
        return name, f"{date}_{time_}", hash_
    return None


def _read_exitcode_file(proc_dir, name):
    """Read <proc_dir>/<name>.exitcode → stripped string, or None if absent."""
    path = os.path.join(proc_dir, f"{name}.exitcode")
    try:
        with open(path) as fh:
            return fh.read().strip()
    except Exception:
        return None


def _proc_dir_status(exitcode):
    """Derive a display status string from an exit-code string (or None)."""
    if exitcode is None:
        return "RUNNING"
    return "OK" if exitcode == "0" else "FAILED"


def _load_proc_dirs(log_dir, last_n=0):
    """
    Scan log_dir for process log directories (name_YYYYMMDD_HHMMSS_hash).
    Returns a list of entry dicts sorted oldest-first.
    last_n=0 → all entries; last_n>0 → the most recent N (still oldest-first).
    Directory size is NOT computed here — use _path_size() on demand.
    """
    entries = []
    try:
        names = os.listdir(log_dir)
    except Exception:
        return []
    for dirname in names:
        dpath = os.path.join(log_dir, dirname)
        if not os.path.isdir(dpath):
            continue
        parsed = _parse_proc_dir_name(dirname)
        if parsed is None:
            continue
        name, ts_str, hash_ = parsed
        ec = _read_exitcode_file(dpath, name)
        entries.append({
            "name":     name,
            "hash":     hash_,
            "ts_str":   ts_str,
            "dt":       _parse_dt(ts_str),
            "status":   _proc_dir_status(ec),
            "exitcode": ec,
            "path":     dpath,
            "dirname":  dirname,
        })
    entries.sort(key=lambda e: e["ts_str"])
    if last_n > 0:
        entries = entries[-last_n:]   # most recent N, still oldest-first
    return entries


def _parse_error_log(log_dir):
    """
    Parse <log_dir>/error.log into a list of entry dicts, oldest-first.
    Each dict: {timestamp, process, hash, log_folder, error_type, message, raw}.
    Returns [] if error.log doesn't exist or can't be read.
    """
    error_log = os.path.join(log_dir, "error.log")
    if not os.path.isfile(error_log):
        return []
    try:
        with open(error_log) as fh:
            content = fh.read()
    except Exception:
        return []

    DASH80 = "-" * 80
    entries = []
    for block in content.split(DASH80):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        entry = {
            "raw": block, "process": "", "hash": "",
            "timestamp": "", "log_folder": "", "error_type": "", "message": "",
        }
        i = 0
        # Line 0: [2026-04-07 09:50:03] Process: align_sample1 (Hash: 1d25c67735)
        if i < len(lines):
            line = lines[i]
            if line.startswith("["):
                ts_end = line.find("]")
                if ts_end > 0:
                    entry["timestamp"] = line[1:ts_end]
                    rest = line[ts_end + 2:].strip()
                    if rest.startswith("Process:"):
                        rest = rest[8:].strip()
                        hmark = " (Hash: "
                        if hmark in rest:
                            entry["process"] = rest[:rest.index(hmark)]
                            entry["hash"]    = rest[rest.index(hmark) + len(hmark):].rstrip(")")
                        else:
                            entry["process"] = rest
            i += 1
        # Line 1: Log folder: /path/...
        if i < len(lines) and lines[i].startswith("Log folder:"):
            entry["log_folder"] = lines[i][11:].strip()
            i += 1
        # Rest: error message; first word before ':' is the error type prefix
        if i < len(lines):
            first = lines[i]
            if ": " in first:
                entry["error_type"] = first.split(":")[0].strip()
            entry["message"] = "\n".join(lines[i:])
        if entry["process"] or entry["message"]:
            entries.append(entry)
    return entries


def _list_run_files(log_dir):
    """
    Return list of (mtime_float, fpath) for files in <log_dir>/jawm_runs/,
    sorted oldest-first (ascending mtime).
    """
    runs_dir = os.path.join(log_dir, "jawm_runs")
    if not os.path.isdir(runs_dir):
        return []
    files = []
    for fname in os.listdir(runs_dir):
        fpath = os.path.join(runs_dir, fname)
        if os.path.isfile(fpath):
            files.append((os.path.getmtime(fpath), fpath))
    files.sort()
    return files


def _find_proc_dirs(log_dir, query):
    """
    Find process log dirs matching query (case-insensitive).
    - ≤10 alphanumeric chars → treated as a hash prefix; newest match first.
    - Otherwise              → exact process name match; all instances oldest-first.
    """
    all_entries = _load_proc_dirs(log_dir, last_n=0)
    q = query.lower().strip()
    is_hash_query = len(q) <= 10 and q.isalnum()
    if is_hash_query:
        matches = [e for e in all_entries if e["hash"].lower().startswith(q)]
        matches.sort(key=lambda e: e["ts_str"], reverse=True)
    else:
        matches = [e for e in all_entries if e["name"].lower() == q]
    return matches


# ----------------------------------------------------------
#   logs — command handlers
# ----------------------------------------------------------

def _cmd_logs_overview(log_dir, use_color):
    """Print a compact summary of the logs directory."""
    if not os.path.isdir(log_dir):
        print(f"jawm-monitor logs: directory not found: {os.path.abspath(log_dir)}")
        print("  Use -l/--log-dir to specify a different path.")
        return 1

    entries   = _load_proc_dirs(log_dir, last_n=0)
    n_ok      = sum(1 for e in entries if e["status"] == "OK")
    n_failed  = sum(1 for e in entries if e["status"] == "FAILED")
    n_running = sum(1 for e in entries if e["status"] == "RUNNING")
    errors    = _parse_error_log(log_dir)
    runs      = _list_run_files(log_dir)
    last_run  = datetime.fromtimestamp(runs[-1][0]) if runs else None

    dim = _C["DIM"] if use_color else ""
    rst = _C["RESET"] if use_color else ""

    print(f"Logs: {os.path.abspath(log_dir)}")
    print()

    runs_label = str(len(runs))
    if last_run:
        runs_label += f"   last: {last_run.strftime('%Y-%m-%d %H:%M')}"
    print(f"  Runs:       {runs_label}")

    proc_parts = []
    if n_ok:      proc_parts.append(_colorize(f"{n_ok} OK",         _C["OK"],      use_color))
    if n_failed:  proc_parts.append(_colorize(f"{n_failed} failed",  _C["FAILED"],  use_color))
    if n_running: proc_parts.append(_colorize(f"{n_running} running", _C["RUNNING"], use_color))
    proc_label = str(len(entries))
    if proc_parts:
        proc_label += f"   ({',  '.join(proc_parts)})"
    print(f"  Processes:  {proc_label}")

    err_label = str(len(errors))
    if errors:
        err_label += f"   → {_colorize('error.log', _C['FAILED'], use_color)}"
    print(f"  Errors:     {err_label}")

    print()
    print(f"{dim}  Flags: --runs  --run [-f]  --errors [N]  --ls [-n N]  --show <name|hash>{rst}")
    return 0


def _cmd_logs_runs(log_dir, last_n, no_header, use_color):
    """List run transcripts in jawm_runs/, oldest-first."""
    runs = _list_run_files(log_dir)
    if not runs:
        print(f"jawm-monitor logs: no run transcripts found in {log_dir}/jawm_runs/")
        return 0

    if last_n > 0:
        runs = runs[-last_n:]   # most recent N, displayed oldest-first (already sorted)

    headers = ["STARTED",  "MODULE",  "SIZE"]
    caps    = [19,          50,        10   ]
    sep     = "  "

    rows = []
    for mtime, fpath in runs:
        started = _fmt_dt(datetime.fromtimestamp(mtime))
        fname   = os.path.basename(fpath)
        base    = fname[:-4] if fname.endswith(".log") else fname
        # Strip trailing _YYYYMMDD_HHMMSS from module name if present
        parts   = base.rsplit("_", 2)
        module  = parts[0] if (len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit()) else base
        size    = _fmt_size(os.path.getsize(fpath))
        rows.append([started, module, size, fpath])   # fpath kept for footer, not displayed

    col_w = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row[:len(headers)]):
            col_w[i] = min(caps[i], max(col_w[i], len(str(cell))))

    if not no_header and rows:
        hdr = sep.join(h.ljust(col_w[i]) for i, h in enumerate(headers))
        print(_colorize(hdr, _C["DIM"], use_color))
        print(_colorize("-" * len(hdr), _C["DIM"], use_color))

    for row in rows:
        cells = [_trunc(str(row[i]), col_w[i]).ljust(col_w[i]) for i in range(len(headers))]
        print(sep.join(cells))

    if not no_header:
        n      = len(runs)
        footer = (f"  {os.path.join(os.path.abspath(log_dir), 'jawm_runs')}"
                  f"  |  {n} run{'s' if n != 1 else ''}")
        if last_n > 0:
            footer += f" (last {last_n})"
        print()
        print(_colorize(footer, _C["DIM"], use_color))
    return 0


def _tail_file(path, follow):
    """
    Print a file's full content, then optionally keep polling for new lines
    (like tail -f) until KeyboardInterrupt.
    """
    try:
        with open(path) as fh:
            sys.stdout.write(fh.read())
            sys.stdout.flush()
            if not follow:
                return
            while True:
                line = fh.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    time.sleep(0.1)
    except KeyboardInterrupt:
        print()   # clean newline after ^C
    except Exception as exc:
        print(f"jawm-monitor logs: error reading {path}: {exc}", file=sys.stderr)


def _cmd_logs_run(log_dir, follow):
    """Print (and optionally follow) the most recent run transcript."""
    runs = _list_run_files(log_dir)
    if not runs:
        print(f"jawm-monitor logs: no run transcripts found in {log_dir}/jawm_runs/")
        return 1
    _, fpath = runs[-1]   # most recent
    # Print the file path as a dim annotation on stderr so it doesn't pollute pipes
    print(f"# {fpath}", file=sys.stderr)
    _tail_file(fpath, follow)
    return 0


def _cmd_logs_errors(log_dir, last_n, use_color):
    """Print the last N entries from error.log."""
    errors = _parse_error_log(log_dir)
    if not errors:
        error_log = os.path.join(log_dir, "error.log")
        if not os.path.isfile(error_log):
            print(f"jawm-monitor logs: no error.log found in {log_dir}")
        else:
            print("jawm-monitor logs: error.log is empty — no errors recorded")
        return 0

    shown = errors[-last_n:] if last_n > 0 else errors
    dim   = _C["DIM"] if use_color else ""
    rst   = _C["RESET"] if use_color else ""

    for entry in shown:
        ts      = entry.get("timestamp", "?")
        proc    = entry.get("process", "?")
        hash_   = entry.get("hash", "")
        etype   = entry.get("error_type", "")
        message = entry.get("message") or entry.get("raw", "")
        folder  = entry.get("log_folder", "")

        hash_str  = f"  ({hash_})" if hash_ else ""
        etype_str = (f"  {_colorize(etype, _C['FAILED'], use_color)}" if etype else "")
        print(f"{_colorize(f'[{ts}]', _C['DIM'], use_color)}"
              f"  {proc}{hash_str}{etype_str}")
        if folder:
            print(f"  {dim}{folder}{rst}")
        for line in message.splitlines():
            print(f"  {line}")
        print()   # blank line between entries

    total   = len(errors)
    n_shown = len(shown)
    footer  = (f"  {os.path.join(os.path.abspath(log_dir), 'error.log')}"
               f"  |  showing {n_shown} of {total} error{'s' if total != 1 else ''}")
    print(_colorize(footer, _C["DIM"], use_color))
    return 0


def _cmd_logs_show(log_dir, query, use_color):
    """Drill into one or all matching process log directories."""
    matches = _find_proc_dirs(log_dir, query)
    if not matches:
        print(f"jawm-monitor logs: no process matching {query!r} in {log_dir}")
        return 1

    dim  = _C["DIM"] if use_color else ""
    rst  = _C["RESET"] if use_color else ""
    div  = _colorize("-" * 60, _C["DIM"], use_color)

    # For name queries we show all runs of that process (oldest-first).
    # For hash queries matches is newest-first; if somehow multiple, show all.
    for idx, e in enumerate(matches):
        if idx > 0:
            print(div)

        name   = e["name"]
        hash_  = e["hash"]
        dpath  = e["path"]
        status = e["status"]
        ec     = e["exitcode"]

        sc = _C.get(status, "")
        print(f"Process:  {name}   {_colorize(status, sc, use_color)}")
        print(f"  Hash:    {hash_}")
        print(f"  Started: {_fmt_dt(e['dt'])}")
        print(f"  Dir:     {dpath}")

        if ec is not None:
            ec_color = _C["OK"] if ec == "0" else _C["FAILED"]
            print(f"  Exit:    {_colorize(ec, ec_color, use_color)}")
            ec_file = os.path.join(dpath, f"{name}.exitcode")
            if os.path.isfile(ec_file) and e["dt"]:
                ec_mtime = datetime.fromtimestamp(os.path.getmtime(ec_file))
                elapsed  = _fmt_duration((ec_mtime - e["dt"]).total_seconds())
                print(f"  Ended:   {_fmt_dt(ec_mtime)}   elapsed: {elapsed}")

        # stderr tail
        error_file = os.path.join(dpath, f"{name}.error")
        if os.path.isfile(error_file):
            try:
                with open(error_file) as fh:
                    lines = fh.readlines()
                n_tail = 20
                tail   = lines[-n_tail:] if len(lines) > n_tail else lines
                trunc  = (f" (last {n_tail} of {len(lines)} lines)"
                          if len(lines) > n_tail else f" ({len(lines)} lines)")
                print()
                print(f"{dim}--- stderr{trunc} ---{rst}")
                for line in tail:
                    sys.stdout.write(line)
                if tail and not tail[-1].endswith("\n"):
                    print()
            except Exception:
                pass

    return 0


def _cmd_logs_ls(args, log_dir, use_color):
    """List process log directories, styled like jawm-monitor ps."""
    last_n    = 0 if getattr(args, "all", False) else max(0, getattr(args, "last", 20))
    no_header = getattr(args, "no_header", False)
    wide      = getattr(args, "wide", False)

    fmt_overrides = {}
    if getattr(args, "fmt", None):
        try:
            fmt_overrides = _parse_fmt(args.fmt, col_map=_LOG_LS_COL_INDEX)
        except ValueError as exc:
            print(f"jawm-monitor logs: --fmt: {exc}", file=sys.stderr)
            return 1

    if not os.path.isdir(log_dir):
        print(f"jawm-monitor logs: directory not found: {os.path.abspath(log_dir)}")
        print("  Use -l/--log-dir to specify a different path.")
        return 1

    entries = _load_proc_dirs(log_dir, last_n=last_n)
    if not entries:
        print(f"jawm-monitor logs: no process log directories found in {log_dir}")
        return 0

    now = datetime.now()

    headers = ["STATUS", "NAME", "HASH", "STARTED",  "ENDED",   "ELAPSED", "EXIT"]
    caps    = [8,         40,     10,     19,          19,         12,        6   ]
    if wide:
        headers.append("DIR")
        caps.append(60)

    for col_idx, new_width in fmt_overrides.items():
        if col_idx < len(caps):
            caps[col_idx] = new_width

    rows = []
    for e in entries:
        status   = e["status"]
        start_dt = e["dt"]
        ended    = "-"
        elapsed  = "-"

        if status == "RUNNING":
            if start_dt:
                elapsed = _fmt_duration((now - start_dt).total_seconds())
        else:
            ec_path = os.path.join(e["path"], f"{e['name']}.exitcode")
            if os.path.isfile(ec_path) and start_dt:
                ec_mtime = datetime.fromtimestamp(os.path.getmtime(ec_path))
                ended    = _fmt_dt(ec_mtime)
                elapsed  = _fmt_duration((ec_mtime - start_dt).total_seconds())

        row = [status, e["name"], e["hash"], _fmt_dt(start_dt), ended, elapsed,
               e["exitcode"] if e["exitcode"] is not None else "-"]
        if wide:
            row.append(e["path"])
        rows.append(row)

    sep   = "  "
    col_w = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_w[i] = min(caps[i], max(col_w[i], len(str(cell))))

    if not no_header and rows:
        hdr = sep.join(h.ljust(col_w[i]) for i, h in enumerate(headers))
        print(_colorize(hdr, _C["DIM"], use_color))
        print(_colorize("-" * len(hdr), _C["DIM"], use_color))

    for row in rows:
        status = row[0]
        color  = _C.get(status, "") if use_color else ""
        cells  = [_trunc(str(row[i]), col_w[i]).ljust(col_w[i]) for i in range(len(row))]
        if color:
            line = f"{color}{cells[0]}{_C['RESET']}{sep}{sep.join(cells[1:])}"
        else:
            line = sep.join(cells)
        print(line)

    if not no_header:
        n      = len(entries)
        footer = f"  {os.path.abspath(log_dir)}  |  {n} process{'es' if n != 1 else ''}"
        if last_n > 0:
            footer += f" (last {last_n})"
        print()
        print(_colorize(footer, _C["DIM"], use_color))
    return 0


def _cmd_logs(args):
    """Dispatcher for 'jawm-monitor logs' subcommand."""
    log_dir   = os.path.expanduser(getattr(args, "log_dir", None) or _DEFAULT_LOG_DIR)
    use_color = sys.stdout.isatty() and not getattr(args, "no_color", False)

    if getattr(args, "ls", False):
        return _cmd_logs_ls(args, log_dir, use_color)

    if getattr(args, "runs", False):
        last_n = max(0, getattr(args, "last", 0))   # 0 = show all runs by default
        return _cmd_logs_runs(log_dir, last_n,
                              no_header=getattr(args, "no_header", False),
                              use_color=use_color)

    if getattr(args, "run", False):
        return _cmd_logs_run(log_dir, follow=getattr(args, "follow", False))

    if getattr(args, "errors", None) is not None:
        return _cmd_logs_errors(log_dir, last_n=args.errors, use_color=use_color)

    if getattr(args, "show", None):
        return _cmd_logs_show(log_dir, query=args.show, use_color=use_color)

    # No flag → overview
    return _cmd_logs_overview(log_dir, use_color)


# ----------------------------------------------------------
#   Argument parser
# ----------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="jawm-monitor",
        description="jawm-monitor — inspect running and completed jawm processes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  jawm-monitor ps                  # running + last 20 completed\n"
            "  jawm-monitor ps -r               # only running\n"
            "  jawm-monitor ps -c               # only completed (last 20)\n"
            "  jawm-monitor ps -c -n 50         # last 50 completed\n"
            "  jawm-monitor ps -a               # running + all completed\n"
            "  jawm-monitor ps --wide           # include log path column\n"
            "  jawm-monitor ps -d /tmp/mon      # custom monitoring directory\n"
            "  jawm-monitor clean               # show counts + available options\n"
            "  jawm-monitor clean -u            # resolve hanging processes\n"
        ),
    )
    parser.add_argument("-V", "--version", action="version", version=f"jawm-monitor {_VERSION}")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ---- ps ----
    ps = sub.add_parser(
        "ps",
        help="List running and completed processes",
        description=(
            "List processes recorded in the jawm monitoring directory.\n\n"
            "By default shows all currently running processes followed by\n"
            "the 20 most recently completed processes.\n\n"
            "Age thresholds (running processes only):\n"
            "  > 48 h   → shown as STALE\n"
            "  > 7 days → hidden, counted in footer as unresolved"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "column names for --fmt: status, name, hash, manager, id, started, elapsed, ended, exit, path\n\n"
            "examples:\n"
            "  jawm-monitor ps                         running + last 20 completed\n"
            "  jawm-monitor ps -r                      only running\n"
            "  jawm-monitor ps -c -n 50                last 50 completed\n"
            "  jawm-monitor ps -a                      all completed\n"
            "  jawm-monitor ps --wide                  add log-path column\n"
            "  jawm-monitor ps --fmt name:60            widen the name column to 60 chars\n"
            "  jawm-monitor ps --fmt name:80,id:30     multiple column overrides\n"
        ),
    )
    _a = ps.add_argument
    _a("-r", "--running",   action="store_true", default=False, help="Show only running processes")
    _a("-c", "--completed", action="store_true", default=False, help="Show only completed processes")
    _a("-n", "--last",      type=int, default=20, metavar="N",
       help="Number of most recent completed entries to show (default: 20; ignored with -a)")
    _a("-a", "--all",       action="store_true", default=False,
       help="Show all completed entries (overrides -n/--last)")
    _a("-d", "--dir",       metavar="DIR",
       help=f"Monitoring directory (default: {_DEFAULT_MON_DIR})")
    _a("--wide",            action="store_true", default=False,
       help="Show an additional log-path column")
    _a("--fmt",             metavar="COL:WIDTH[,COL:WIDTH...]",
       help="Override column widths. Use 'col:width' or 'col=width' pairs separated by commas. "
            "Column names: status, name, hash, manager, id, started, elapsed, ended, exit, path. "
            "Example: --fmt name:80  or  --fmt name:60,id:30")
    _a("--no-header",       dest="no_header", action="store_true", default=False,
       help="Suppress column headers and footer")
    _a("--no-color",        dest="no_color",  action="store_true", default=False,
       help="Disable ANSI colour output")

    # ---- clean ----
    cl = sub.add_parser(
        "clean",
        help="Clean up monitoring and git cache entries",
        description=(
            "Clean stale or unwanted entries from the monitoring directory and git cache.\n\n"
            "With no flags: shows a summary of cleanable entries and lists all options.\n"
            "All destructive operations require confirmation unless --force is passed.\n"
            "Use --dry-run to preview any operation without making changes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "age format: '7d' = 7 days, '48h' = 48 hours, '30' = 30 days (bare int = days)\n\n"
            "examples:\n"
            "  jawm-monitor clean                           show summary, do nothing\n"
            "  jawm-monitor clean -u                        resolve running >7d → UNRESOLVED\n"
            "  jawm-monitor clean -u --older-than 2d        resolve running >2d → UNRESOLVED\n"
            "  jawm-monitor clean -U                        delete all UNRESOLVED (running + completed)\n"
            "  jawm-monitor clean -U --older-than 30d       delete UNRESOLVED older than 30 days\n"
            "  jawm-monitor clean --running                 remove all running entries\n"
            "  jawm-monitor clean --running --older-than 2d remove running entries older than 2 days\n"
            "  jawm-monitor clean --running --keep-last 5   keep 5 most recent running, remove rest\n"
            "  jawm-monitor clean --completed               remove all completed entries\n"
            "  jawm-monitor clean --completed --older-than 30d\n"
            "  jawm-monitor clean --completed --keep-last 100\n"
            "  jawm-monitor clean --git-cache               wipe entire git cache\n"
            "  jawm-monitor clean --git-cache --older-than 14d\n"
            "  jawm-monitor clean --git-cache --keep-last 5\n"
            "  jawm-monitor clean --all                     resolve + remove all running + completed\n"
            "  jawm-monitor clean --all --dry-run           preview --all without acting\n"
        ),
    )
    _b = cl.add_argument
    _b("-u", "--unresolved",        action="store_true", default=False,
       help="Move running entries older than 7d (or --older-than) to Completed/ as UNRESOLVED")
    _b("-U", "--delete-unresolved", dest="delete_unresolved", action="store_true", default=False,
       help="Delete all UNRESOLVED entries from both Running/ and Completed/. "
            "Respects --older-than to filter by age. Mutually exclusive with -u")
    _b("--running",                 action="store_true", default=False,
       help="Remove running entries (all, or filtered by --older-than / --keep-last)")
    _b("--completed",         action="store_true", default=False,
       help="Remove completed entries (all, or filtered by --older-than / --keep-last)")
    _b("--git-cache",         dest="git_cache", action="store_true", default=False,
       help="Clean git cache entries in ~/.jawm/git/ (all, or filtered by --older-than / --keep-last)")
    _b("--all",               action="store_true", default=False,
       help="Resolve unresolved + remove all running and completed entries")
    _b("--older-than",        metavar="AGE",
       help="Only act on entries older than AGE (e.g. 7d, 48h, 30). "
            "Mutually exclusive with --keep-last")
    _b("--keep-last",         dest="keep_last", type=int, metavar="N",
       help="Keep N most recent entries, remove the rest. "
            "Applies to --running, --completed, and --git-cache. "
            "Mutually exclusive with --older-than")
    _b("-n", "--dry-run",     dest="dry_run", action="store_true", default=False,
       help="Preview what would be affected without making any changes")
    _b("-f", "--force",       action="store_true", default=False,
       help="Skip the confirmation prompt")
    _b("-d", "--dir",         metavar="DIR",
       help=f"Monitoring directory (default: {_DEFAULT_MON_DIR})")
    _b("--no-color",          dest="no_color", action="store_true", default=False,
       help="Disable ANSI colour output")

    # ---- logs ----
    lg = sub.add_parser(
        "logs",
        help="Inspect the jawm logs directory",
        description=(
            "Inspect the jawm logs directory (default: ./logs).\n\n"
            "With no flags: prints a summary — process counts, error count, last run.\n\n"
            "Each flag activates a specific view; use one at a time.\n\n"
            "Log directory layout:\n"
            "  logs/\n"
            "  ├── error.log                     all failures, one entry per attempt\n"
            "  ├── jawm_runs/\n"
            "  │   └── <module>_<ts>.log         full CLI transcript per jawm run\n"
            "  └── <name>_<ts>_<hash>/           one directory per process instance\n"
            "      ├── <name>.output / .error     stdout / stderr\n"
            "      ├── <name>.exitcode            exit status\n"
            "      ├── <name>.script / .command   resolved script and launch command\n"
            "      └── stats.json                 CPU/mem usage (if --stats was used)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "column names for --fmt (with --ls):\n"
            "  status, name, hash, started, ended, elapsed, exit, dir\n\n"
            "examples:\n"
            "  jawm-monitor logs                         overview of ./logs\n"
            "  jawm-monitor logs -l /path/to/logs        use a custom log directory\n"
            "  jawm-monitor logs --runs                  list all run transcripts\n"
            "  jawm-monitor logs --runs -n 10            last 10 run transcripts\n"
            "  jawm-monitor logs --run                   print last run transcript\n"
            "  jawm-monitor logs --run -f                follow last run as it writes\n"
            "  jawm-monitor logs --errors                last 10 errors from error.log\n"
            "  jawm-monitor logs --errors 20             last 20 errors\n"
            "  jawm-monitor logs --ls                    list processes (last 20)\n"
            "  jawm-monitor logs --ls -n 50              last 50 processes\n"
            "  jawm-monitor logs --ls -a                 all processes\n"
            "  jawm-monitor logs --ls --fmt name:60      widen name column\n"
            "  jawm-monitor logs --ls --wide             add directory column\n"
            "  jawm-monitor logs --show gate_6           details for all gate_6 runs\n"
            "  jawm-monitor logs --show 1e1cd29m         details by hash prefix\n"
        ),
    )
    _c = lg.add_argument
    _c("-l", "--log-dir",  dest="log_dir", metavar="DIR",
       help=f"Logs directory to inspect (default: {_DEFAULT_LOG_DIR})")
    _c("--runs",           action="store_true", default=False,
       help="List run transcripts in jawm_runs/ (oldest-first; use -n to limit)")
    _c("--run",            action="store_true", default=False,
       help="Print the most recent run transcript to stdout")
    _c("-f", "--follow",   action="store_true", default=False,
       help="Follow the run transcript as new lines are written (use with --run)")
    _c("--errors",         nargs="?", const=10, type=int, metavar="N",
       help="Print the last N errors from error.log (default N=10 when flag is given without a value)")
    _c("--ls",             action="store_true", default=False,
       help="List process log directories in a table (like jawm-monitor ps)")
    _c("--show",           metavar="NAME_OR_HASH",
       help="Show full details for a process: exit code, stderr tail, stats. "
            "Accepts a process name (all runs shown) or a hash prefix")
    _c("-n", "--last",     type=int, default=20, metavar="N",
       help="Number of entries to show with --ls or --runs (default: 20)")
    _c("-a", "--all",      action="store_true", default=False,
       help="Show all entries — overrides -n/--last (applies to --ls)")
    _c("--fmt",            metavar="COL:WIDTH[,COL:WIDTH...]",
       help="Override column widths for --ls. Pairs are col:width or col=width. "
            "Columns: status, name, hash, started, ended, elapsed, exit, dir. "
            "Example: --fmt name:60  or  --fmt name:60,hash:12")
    _c("--wide",           action="store_true", default=False,
       help="Add a directory path column (with --ls)")
    _c("--no-header",      dest="no_header", action="store_true", default=False,
       help="Suppress column headers and footer")
    _c("--no-color",       dest="no_color", action="store_true", default=False,
       help="Disable ANSI colour output")

    return parser


# ----------------------------------------------------------
#   Entry point
# ----------------------------------------------------------

def main():
    parser = _build_parser()
    args   = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "ps":
        sys.exit(_cmd_ps(args) or 0)

    if args.command == "clean":
        sys.exit(_cmd_clean(args) or 0)

    if args.command == "logs":
        sys.exit(_cmd_logs(args) or 0)

    print(f"jawm-monitor: unknown command '{args.command}'", file=sys.stderr)
    parser.print_help(sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

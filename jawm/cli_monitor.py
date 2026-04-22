"""
jawm-monitor — inspect running and completed jawm processes.

Reads the monitoring directory (~/.jawm/monitoring/ by default) and prints a
tabular summary of process state without touching the per-process log directories.
"""

import argparse
import os
import shutil
import sys
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
            mgr = e.get("Manager", "")
            jid = e.get("Job ID", "")
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


def _do_remove_files(fpaths, dry_run):
    """Delete a list of file paths."""
    for fpath in fpaths:
        fname = os.path.basename(fpath)
        if dry_run:
            print(f"  {fname}")
            continue
        try:
            os.remove(fpath)
            print(f"  removed  {fname}")
        except Exception as exc:
            print(f"  ERROR removing {fname}: {exc}", file=sys.stderr)


def _do_remove_paths(paths, dry_run):
    """Delete a list of file/directory paths (git cache entries)."""
    for p in paths:
        name = os.path.basename(p)
        size = _fmt_size(_path_size(p))
        if dry_run:
            print(f"  {name}  ({size})")
            continue
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            print(f"  removed  {name}  ({size})")
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
    print(f"    jawm-monitor clean -u                    # resolve hanging >7d")
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
    do_unresolved = args.unresolved or args.all
    do_running    = args.running    or args.all
    do_completed  = args.completed  or args.all
    do_git        = args.git_cache

    # --older-than alone (no target) → apply to running + completed
    if older_than_s is not None and not any([do_unresolved, do_running, do_completed, do_git]):
        do_running   = True
        do_completed = True

    # --keep-last alone (no target) → error
    if keep_last is not None and not any([do_running, do_completed, do_git]):
        print("jawm-monitor clean: --keep-last requires a target (--running, --completed, or --git-cache).", file=sys.stderr)
        return 1

    has_action = any([do_unresolved, do_running, do_completed, do_git])
    if not has_action:
        _clean_summary(mon, git_dir, use_color)
        return 0

    # --- Collect what would be affected ---

    # 1. Unresolved: use --older-than as threshold if specified, else default 7d
    unresolved_items = []
    if do_unresolved:
        threshold = older_than_s if (args.unresolved and older_than_s) else _UNRESOLVED_S
        unresolved_items = _collect_unresolved(mon, threshold, now)

    # 2. Running: for --all, remove all remaining; for --running, respect filters
    running_files = []
    if do_running:
        ot = older_than_s if args.running else None   # --all ignores --older-than for running
        kl = keep_last    if args.running else None
        # exclude entries already captured in unresolved_items
        unresolved_paths = {fp for fp, _, _ in unresolved_items}
        all_running_files = _collect_running_to_remove(mon, ot, kl, now)
        running_files = [f for f in all_running_files if f not in unresolved_paths]

    # 3. Completed
    completed_files = []
    if do_completed:
        ot = older_than_s  # respected for both --completed and --all
        kl = keep_last if args.completed else None   # --all doesn't apply keep-last to completed
        completed_files = _collect_completed_to_remove(mon, ot, kl, now)

    # 4. Git cache
    git_paths = []
    if do_git:
        git_paths = _collect_git_to_remove(git_dir, older_than_s, keep_last, now)

    # --- Nothing to do ---
    total = len(unresolved_items) + len(running_files) + len(completed_files) + len(git_paths)
    if total == 0:
        print("jawm-monitor clean: nothing to clean.")
        return 0

    # --- Preview ---
    if unresolved_items:
        print(f"Resolve {len(unresolved_items)} running entr{'y' if len(unresolved_items)==1 else 'ies'} → UNRESOLVED:")
        for fp, cfp, _ in unresolved_items:
            print(f"  {os.path.basename(fp)}  →  {os.path.basename(cfp)}")
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
    if running_files:
        print(f"Removing {len(running_files)} running {'entry' if len(running_files)==1 else 'entries'}:")
        _do_remove_files(running_files, dry_run=False)
    if completed_files:
        print(f"Removing {len(completed_files)} completed {'entry' if len(completed_files)==1 else 'entries'}:")
        _do_remove_files(completed_files, dry_run=False)
    if git_paths:
        print(f"Removing {len(git_paths)} git cache {'entry' if len(git_paths)==1 else 'entries'}:")
        _do_remove_paths(git_paths, dry_run=False)

    print("\nDone.")
    return 0


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
            "examples:\n"
            "  jawm-monitor ps                 running + last 20 completed\n"
            "  jawm-monitor ps -r              only running\n"
            "  jawm-monitor ps -c -n 50        last 50 completed\n"
            "  jawm-monitor ps -a              all completed\n"
            "  jawm-monitor ps --wide          add log-path column\n"
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
    _b("-u", "--unresolved",  action="store_true", default=False,
       help="Move running entries older than 7d (or --older-than) to Completed/ as UNRESOLVED")
    _b("--running",           action="store_true", default=False,
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

    print(f"jawm-monitor: unknown command '{args.command}'", file=sys.stderr)
    parser.print_help(sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

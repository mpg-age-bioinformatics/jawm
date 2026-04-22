"""
jawm-monitor — inspect running and completed jawm processes.

Reads the monitoring directory (~/.jawm/monitoring/ by default) and prints a
tabular summary of process state without touching the per-process log directories.
"""

import argparse
import os
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

_STALE_S      = 48 * 3600        # 48 h  → show as STALE
_UNRESOLVED_S = 7  * 24 * 3600   # 7 days → hide, count in footer

_VALID_CMDS = {"ps"}

# ANSI colour codes (only applied when stdout is a tty)
_C = {
    "RUNNING":    "\033[33m",   # yellow
    "STALE":      "\033[35m",   # magenta
    "OK":         "\033[32m",   # green
    "FAILED":     "\033[31m",   # red
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
        entries.append(data)
    entries.sort(key=lambda e: e.get("Run Start") or "")
    return entries


def _load_completed(mon_dir, last_n):
    """
    Return a list of dicts for files in Completed/, sorted by mtime desc.
    last_n=0 means no limit.
    """
    completed_dir = os.path.join(mon_dir, "Completed")
    entries = []
    if not os.path.isdir(completed_dir):
        return entries

    files = []
    for fname in os.listdir(completed_dir):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(completed_dir, fname)
        files.append((os.path.getmtime(fpath), fpath, fname))

    files.sort(key=lambda x: x[0], reverse=True)
    if last_n > 0:
        files = files[:last_n]

    for mtime, fpath, fname in files:
        data = _parse_file(fpath)
        if not data:
            continue
        mgr, jid, ec_fname = _fname_parse_completed(fname)
        data.setdefault("Manager", mgr)
        data.setdefault("Job ID", jid)
        ec = data.get("Exit Code", ec_fname).strip()
        data["Exit Code"] = ec
        try:
            data["_status"] = "OK" if int(ec) == 0 else "FAILED"
        except Exception:
            data["_status"] = "DONE"
        data["_mtime"] = mtime
        entries.append(data)

    return entries


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
            elapsed  = _fmt_duration((now - start_dt).total_seconds()) if start_dt else "pending"
            ended    = "-"
            exit_code = "-"
        else:
            end_dt   = _parse_dt(e.get("Run End"))
            elapsed  = _fmt_duration((end_dt - start_dt).total_seconds()) if (start_dt and end_dt) else "-"
            ended    = _fmt_dt(end_dt)
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
    raw_running     = _load_running(mon) if show_running else []
    visible_running = []
    unresolved_count = 0

    for e in raw_running:
        start_dt = _parse_dt(e.get("Run Start"))
        if start_dt is None:
            # No start time recorded yet — treat as RUNNING / pending
            visible_running.append(e)
            continue
        elapsed_s = (now - start_dt).total_seconds()
        if elapsed_s > _UNRESOLVED_S:
            unresolved_count += 1          # hidden from table, counted in footer
        elif elapsed_s > _STALE_S:
            e["_status"] = "STALE"
            visible_running.append(e)
        else:
            visible_running.append(e)      # status already "RUNNING"

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
    caps    = [7,         30,      12,      10,         15,    19,        12,        19,       6   ]
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
            footer += f"  |  {unresolved_count} unresolved — run 'jawm-monitor clean -u' to clean"

        print()
        print(_colorize(footer, _C["DIM"], use_color))

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
    _add = ps.add_argument

    _add("-r", "--running",
         action="store_true", default=False,
         help="Show only running processes")
    _add("-c", "--completed",
         action="store_true", default=False,
         help="Show only completed processes")
    _add("-n", "--last",
         type=int, default=20, metavar="N",
         help="Number of most recent completed entries to show (default: 20; ignored with -a)")
    _add("-a", "--all",
         action="store_true", default=False,
         help="Show all completed entries (overrides -n/--last)")
    _add("-d", "--dir",
         metavar="DIR",
         help=f"Monitoring directory (default: {_DEFAULT_MON_DIR})")
    _add("--wide",
         action="store_true", default=False,
         help="Show an additional log-path column")
    _add("--no-header",
         dest="no_header", action="store_true", default=False,
         help="Suppress column headers and footer")
    _add("--no-color",
         dest="no_color", action="store_true", default=False,
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

    print(f"jawm-monitor: unknown command '{args.command}'", file=sys.stderr)
    parser.print_help(sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

# jawm-monitor

`jawm-monitor` is the companion CLI for inspecting jawm processes — both while they are running and after they complete. It reads the monitoring directory and the logs directory without modifying any process state or output files.

```bash
jawm-monitor COMMAND [flags]
```

Four commands are available:

| Command | What it does |
|---------|-------------|
| [`ps`](#ps) | List running and completed processes from the monitoring directory |
| [`logs`](#logs) | Inspect the logs directory — processes, errors, run transcripts |
| [`stats`](#stats) | Show resource usage statistics (CPU and memory) |
| [`clean`](#clean) | Remove stale monitoring entries and git cache data |

Run `jawm-monitor COMMAND --help` for the full flag reference for any command.

**Related Environment variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `JAWM_MONITORING_DIRECTORY` | `~/.jawm/monitoring` | Override the default monitoring directory for `ps` and `clean` |


---

## `ps`

List processes recorded in the jawm monitoring directory. Shows currently running processes together with recently completed ones.

```bash
jawm-monitor ps [flags]
```

### Synopsis

```
jawm-monitor ps [-r] [-c] [-n N] [-a] [-d DIR]
               [--wide] [--fmt COL:WIDTH[,...]]
               [--no-header] [--no-color]
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-r`, `--running` | `False` | Show only running processes |
| `-c`, `--completed` | `False` | Show only completed processes |
| `-n`, `--last` | `20` | Number of most recent completed entries to show. Ignored with `-a` |
| `-a`, `--all` | `False` | Show all completed entries (overrides `-n`) |
| `-d`, `--dir` | `~/.jawm/monitoring` | Monitoring directory |
| `--wide` | `False` | Add a log-path column |
| `--fmt` | — | Override column widths; see below |
| `--no-header` | `False` | Suppress column headers and footer line |
| `--no-color` | `False` | Disable ANSI colour output |

### Columns

| Column | Description |
|--------|-------------|
| `STATUS` | Current state of the process (see status values below) |
| `NAME` | Process name |
| `HASH` | 10-character process hash |
| `MANAGER` | Execution backend (`local`, `slurm`, `kubernetes`, …) |
| `ID` | Backend job or process ID |
| `STARTED` | Run start time (`YYYY-MM-DD HH:MM:SS`) |
| `ELAPSED` | Running time — live for active processes, final for completed ones |
| `ENDED` | Run end time (`-` for running processes) |
| `EXIT` | Exit code (`-` for running processes) |
| `PATH` | Log directory path — only shown with `--wide` |

### Status values

| Status | Colour | Meaning |
|--------|--------|---------|
| `RUNNING` | yellow | Process is currently active |
| `STALE` | magenta | Running entry not updated in more than 48 hours — likely orphaned |
| `OK` | green | Completed with exit code 0 |
| `FAILED` | red | Completed with a non-zero exit code |
| `UNRESOLVED` | grey | Was running but never reported completion — moved here by `clean -u` |

Processes that have been running for more than 7 days are hidden from the default view and counted in the footer. Use `jawm-monitor clean -u` to move them to Completed as UNRESOLVED.

### `--fmt` — column width overrides

Widen (or narrow) any column by passing `COL:WIDTH` pairs:

```bash
jawm-monitor ps --fmt name:60
jawm-monitor ps --fmt name:80,id:30
```

Accepted column names: `status`, `name`, `hash`, `manager`, `id`, `started`, `elapsed`, `ended`, `exit`, `path`.
Both `:` and `=` separators are accepted (`name:60` and `name=60` are equivalent).

### Examples

```bash
# Default — running processes + last 20 completed
jawm-monitor ps

# Only running processes
jawm-monitor ps -r

# Only completed, show last 50
jawm-monitor ps -c -n 50

# All completed entries
jawm-monitor ps -a

# Add log-path column
jawm-monitor ps --wide

# Widen the name column
jawm-monitor ps --fmt name:60

# Use a custom monitoring directory
jawm-monitor ps -d /scratch/project/.jawm/monitoring

# Machine-readable (no headers, no colour)
jawm-monitor ps --no-header --no-color
```

---

## `logs`

Inspect the jawm logs directory. Provides several focused views into the log directory structure via flags.

```bash
jawm-monitor logs [flags]
```

### Synopsis

```
jawm-monitor logs [-l DIR]
                  [--runs | --run [-f] | --errors [N] | --ls | --hash MODULE]
                  [--show NAME_OR_HASH [--error] [--output] [--script]
                   [--command] [--id] [--slurm] [--k8s] [--stats]]
                  [-n N] [-a] [--fmt COL:WIDTH[,...]] [--wide]
                  [--no-header] [--no-color]
```

### Log directory layout

```
logs/
├── error.log                        all process failures, one entry per attempt
├── jawm_hashes/
│   ├── <module>.hash                output hash for resume / test comparison
│   ├── <module>_input.history       history of input hashes
│   └── <module>_user_defined.history
├── jawm_runs/
│   └── <module>_<YYYYMMDD>_<HHMMSS>.log   full CLI transcript per jawm run
└── <name>_<YYYYMMDD>_<HHMMSS>_<hash>/     one directory per process instance
    ├── <name>.output                stdout
    ├── <name>.error                 stderr
    ├── <name>.exitcode              exit status
    ├── <name>.script                resolved script
    ├── <name>.command               launch command
    ├── <name>.id                    backend job / process ID
    ├── <name>.slurm                 Slurm job script  (Slurm processes only)
    ├── <name>.k8s.json              Kubernetes manifest  (K8s processes only)
    └── stats.json                   CPU / memory usage  (requires --stats)
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-l`, `--log-dir` | `./logs` | Logs directory to inspect |
| `--runs` | `False` | List run transcripts in `jawm_runs/` |
| `--run` | `False` | Print the most recent run transcript to stdout |
| `-f`, `--follow` | `False` | Follow the run transcript as it is written (use with `--run`) |
| `--errors` | — | Print the last N errors from `error.log`. Pass the flag alone for 10, or supply a number (`--errors 20`) |
| `--ls` | `False` | List process log directories in a table (like `ps`) |
| `--hash` | — | Print hash and history files for a module from `jawm_hashes/` |
| `--show` | — | Show details for a process — by name (all runs) or hash prefix (newest match) |
| `-n`, `--last` | `20` | Number of entries to show with `--ls` or `--runs` |
| `-a`, `--all` | `False` | Show all entries with `--ls` (overrides `-n`) |
| `--fmt` | — | Override column widths for `--ls`; see below |
| `--wide` | `False` | Add a directory path column (with `--ls`) |
| `--no-header` | `False` | Suppress column headers and footer |
| `--no-color` | `False` | Disable ANSI colour output |

### `--show` file flags

When `--show` is used, the following flags append specific files from the matching process directory. Multiple flags can be combined.

| Flag | File | Description |
|------|------|-------------|
| `--error` | `<name>.error` | Full stderr |
| `--output` | `<name>.output` | Full stdout |
| `--script` | `<name>.script` | Resolved script |
| `--command` | `<name>.command` | Launch command |
| `--id` | `<name>.id` | Backend job / process ID |
| `--slurm` | `<name>.slurm` | Slurm job script |
| `--k8s` | `<name>.k8s.json` | Kubernetes manifest (pretty-printed) |
| `--stats` | `stats.json` | CPU / memory stats (pretty-printed JSON) |

Without any file flag, `--show` prints a summary header and the last 20 lines of stderr.

### `--fmt` for `--ls`

Column names for `--ls`: `status`, `name`, `hash`, `started`, `ended`, `elapsed`, `exit`, `dir`.

```bash
jawm-monitor logs --ls --fmt name:60
jawm-monitor logs --ls --fmt name:60,hash:12
```

### Examples

```bash
# Overview — process counts, error count, last run timestamp
jawm-monitor logs

# Use a custom log directory
jawm-monitor logs -l /scratch/project/logs

# List run transcripts (all)
jawm-monitor logs --runs

# List last 10 run transcripts
jawm-monitor logs --runs -n 10

# Print the most recent run transcript
jawm-monitor logs --run

# Follow the current run as it writes (like tail -f)
jawm-monitor logs --run -f

# Last 10 errors from error.log
jawm-monitor logs --errors

# Last 20 errors
jawm-monitor logs --errors 20

# List process log directories (last 20)
jawm-monitor logs --ls

# List last 50 processes
jawm-monitor logs --ls -n 50

# All processes, with directory column
jawm-monitor logs --ls -a --wide

# Output hash and input history for a module
jawm-monitor logs --hash mymodule

# Summary and stderr tail for a process (by name — shows all runs)
jawm-monitor logs --show gate_6

# Summary for a specific run (by hash prefix — shows newest match)
jawm-monitor logs --show 1e1cd29m

# Full stderr for a process
jawm-monitor logs --show gate_6 --error

# Full stdout
jawm-monitor logs --show gate_6 --output

# Resolved script and launch command together
jawm-monitor logs --show gate_6 --script --command

# Slurm job script
jawm-monitor logs --show gate_6 --slurm

# Kubernetes manifest
jawm-monitor logs --show gate_6 --k8s

# Resource stats JSON
jawm-monitor logs --show gate_6 --stats
```

---

## `stats`

Show CPU and memory resource usage collected during jawm runs. Statistics are only available when jawm is invoked with `--stats`.

```bash
jawm-monitor stats [flags]
```

### Synopsis

```
jawm-monitor stats [-l DIR]
                   [--runs | --process | --show NAME_OR_HASH]
                   [--sort KEY] [--reverse] [--additional-fields]
                   [-n N] [--no-header] [--no-color]
```

### Data sources

Resource data is recorded in two places:

- **`:::SUMMARY:::` blocks** in run transcripts (`jawm_runs/*.log`) — aggregate stats across all processes in a run; used by the bare command and `--runs`
- **`stats.json`** in individual process log directories — per-process CPU and memory measurements; used by `--process` and `--show`

### Collection requirements

Stats collection is backend-specific. Each backend has its own dependency:

| Backend | Mechanism | Requirement |
|---------|-----------|-------------|
| `local` | `ps` | Available on all Linux and macOS systems |
| `slurm` | `sstat` | `sstat` must be in `PATH` on the submission host |
| `kubernetes` | `kubectl top` | [Kubernetes Metrics Server](https://github.com/kubernetes-sigs/metrics-server) must be installed on the cluster |

If a dependency is missing, jawm logs a one-time warning and skips stats collection for that backend. All other run behaviour is unaffected.

!!! note
    The Metrics Server is not installed by default on all clusters. Managed clusters (GKE, EKS, AKS) typically include it; local clusters (kind, minikube) require a one-time setup. See your cluster's documentation for installation instructions. For kind, the deployment also requires the `--kubelet-insecure-tls` flag due to self-signed kubelet certificates.

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-l`, `--log-dir` | `./logs` | Logs directory to inspect |
| `--runs` | `False` | Per-run stats table — one row per run that has a `:::SUMMARY:::` block |
| `--process` | `False` | Per-process stats table — one row per process with a `stats.json` |
| `--show` | — | Full stats detail for a process by name or hash prefix |
| `--sort` | see below | Sort key for `--runs` or `--process` |
| `--reverse` | `False` | Reverse the default sort direction |
| `--additional-fields` | `False` | Show extra fields (e.g. Slurm/K8s metrics) as extra columns in `--process`, or as a block in `--show` |
| `-n`, `--last` | all | Limit output to N entries |
| `--no-header` | `False` | Suppress column headers and footer |
| `--no-color` | `False` | Disable ANSI colour output |

### Sort keys

**`--runs`** — default `date` (newest first):

| Key | Sorts by |
|-----|---------|
| `date` | Run timestamp (newest first by default) |
| `module` | Module name (alphabetical) |
| `processes` | Number of processes |
| `cpu_avg` | Average CPU usage |
| `cpu_peak` | Peak CPU usage |
| `mem_avg` | Average memory usage |
| `mem_peak` | Peak memory usage |

**`--process`** — default `started` (oldest first):

| Key | Sorts by |
|-----|---------|
| `started` | Process start time (oldest first by default) |
| `name` | Process name (alphabetical) |
| `hash` | Process hash |
| `polls` | Number of stat poll samples |
| `cpu_avg` | Average CPU usage (highest first by default) |
| `cpu_peak` | Peak CPU usage (highest first by default) |
| `mem_avg` | Average memory usage (highest first by default) |
| `mem_peak` | Peak memory usage (highest first by default) |

All metric sort keys default to descending (highest first). `--reverse` flips the direction for any key.

### Memory units

All memory values are reported in decimal GB (1 GB = 1 000 000 000 bytes). The `--show` view additionally shows raw MiB values alongside GB for precision.

### Examples

```bash
# Summary of the last run (aggregate stats from the most recent run transcript)
jawm-monitor stats

# Use a custom log directory
jawm-monitor stats -l /scratch/project/logs

# Per-run stats table — all runs, newest first
jawm-monitor stats --runs

# Last 10 runs
jawm-monitor stats --runs -n 10

# Runs sorted by peak CPU usage
jawm-monitor stats --runs --sort cpu_peak

# Runs sorted by peak memory, lowest first
jawm-monitor stats --runs --sort mem_peak --reverse

# Per-process stats table (all processes, oldest first)
jawm-monitor stats --process

# Top 10 processes by peak CPU usage
jawm-monitor stats --process --sort cpu_peak -n 10

# Top 10 processes by peak memory usage
jawm-monitor stats --process --sort mem_peak -n 10

# Include extra backend-specific fields (Slurm / Kubernetes)
jawm-monitor stats --process --additional-fields

# Full stats detail for a process by name
jawm-monitor stats --show gate_6

# Full stats detail by hash prefix
jawm-monitor stats --show 1e1cd29m

# Full stats with additional fields
jawm-monitor stats --show gate_6 --additional-fields
```

---

## `clean`

Remove stale or unwanted entries from the monitoring directory and the git cache. With no flags, prints a summary of what is cleanable and lists available actions.

All destructive operations ask for confirmation before acting. Use `--dry-run` to preview any operation without making any changes, and `--force` to skip the confirmation prompt.

```bash
jawm-monitor clean [flags]
```

### Synopsis

```
jawm-monitor clean [-u] [-U]
                   [--running] [--completed] [--git-cache] [--all]
                   [--older-than AGE] [--keep-last N]
                   [-n] [-f] [-d DIR] [--no-color]
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-u`, `--unresolved` | `False` | Move running entries older than 7 days (or `--older-than`) to Completed as UNRESOLVED. Mutually exclusive with `-U` |
| `-U`, `--delete-unresolved` | `False` | Delete all UNRESOLVED entries from both Running and Completed. Respects `--older-than`. Mutually exclusive with `-u` |
| `--running` | `False` | Remove running entries (all, or filtered by `--older-than` / `--keep-last`) |
| `--completed` | `False` | Remove completed entries (all, or filtered by `--older-than` / `--keep-last`) |
| `--git-cache` | `False` | Clean entries in the git cache directory `~/.jawm/git/` |
| `--all` | `False` | Resolve unresolved (`-u`) + remove all running and completed entries |
| `--older-than` | — | Only act on entries older than AGE. Mutually exclusive with `--keep-last` |
| `--keep-last` | — | Keep the N most recent entries; remove the rest. Applies to `--running`, `--completed`, and `--git-cache`. Mutually exclusive with `--older-than` |
| `-n`, `--dry-run` | `False` | Preview what would be affected without making any changes |
| `-f`, `--force` | `False` | Skip the confirmation prompt |
| `-d`, `--dir` | `~/.jawm/monitoring` | Monitoring directory |
| `--no-color` | `False` | Disable ANSI colour output |

### Age format

`--older-than` accepts these formats:

| Format | Meaning |
|--------|---------|
| `7d` | 7 days |
| `48h` | 48 hours |
| `30` | 30 days (bare integer = days) |

### How `-u` and `-U` differ

- **`-u` / `--unresolved`** — moves running entries that have been in Running for longer than the threshold into Completed, marking them with `Exit Code: UNRESOLVED`. They remain visible in `ps` and can still be examined. This is the safe default for tidying abandoned runs.
- **`-U` / `--delete-unresolved`** — permanently deletes UNRESOLVED entries from both Running and Completed. Use this once you are done reviewing them.

### Examples

```bash
# Show a summary of what is cleanable — no changes made
jawm-monitor clean

# Move all running entries older than 7 days → UNRESOLVED
jawm-monitor clean -u

# Move running entries older than 2 days → UNRESOLVED
jawm-monitor clean -u --older-than 2d

# Preview the above without acting
jawm-monitor clean -u --older-than 2d --dry-run

# Delete all UNRESOLVED entries from Running and Completed
jawm-monitor clean -U

# Delete only UNRESOLVED entries older than 30 days
jawm-monitor clean -U --older-than 30d

# Remove all running entries
jawm-monitor clean --running

# Remove running entries older than 2 days
jawm-monitor clean --running --older-than 2d

# Keep the 5 most recent running entries, remove the rest
jawm-monitor clean --running --keep-last 5

# Remove all completed entries
jawm-monitor clean --completed

# Remove completed entries older than 30 days
jawm-monitor clean --completed --older-than 30d

# Keep the 100 most recent completed entries
jawm-monitor clean --completed --keep-last 100

# Clean the entire git cache
jawm-monitor clean --git-cache

# Remove git cache entries not accessed in 14 days
jawm-monitor clean --git-cache --older-than 14d

# Keep the 5 most recently used git cache entries
jawm-monitor clean --git-cache --keep-last 5

# Resolve unresolved + remove all running and completed in one step
jawm-monitor clean --all

# Preview --all without making changes
jawm-monitor clean --all --dry-run

# Run --all without prompting for confirmation
jawm-monitor clean --all --force

# Use a custom monitoring directory
jawm-monitor clean -d /scratch/project/.jawm/monitoring -u
```

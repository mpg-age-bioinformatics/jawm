# Log Structure

Every jawm run produces a predictable set of log files. Knowing where they live and what they contain is the foundation for debugging anything that goes wrong. This page is a reference map — it would give the idea where to look.

---

### Top-level layout

All logs live under a single base directory, controlled by `-l` / `--logs-directory` (default: `./logs`), or with `Process` parameter [logs_directory](../process/parameters.md#logs_directory):

```
logs/
├── <process_name>_<datetime>_<hash>/   # one directory per Process run
│   ├── <name>.output                   # stdout
│   ├── <name>.error                    # stderr
│   ├── <name>.exitcode                 # exit code
│   ├── <name>.script                   # the resolved script that was executed
│   ├── <name>.command                  # the exact shell command that launched the process
│   ├── <name>.id                       # PID (local) or job ID (Slurm/K8s)
│   ├── <name>.slurm                    # Slurm job script (Slurm only)
│   ├── <name>.k8s.json                 # Kubernetes manifest (K8s only)
│   └── stats.json                      # resource stats (when --stats is enabled)
│
├── error.log                           # aggregated error summary (all failed processes)
├── jawm_runs/
│   └── <module>_<timestamp>.log        # full CLI run transcript
└── jawm_hashes/
    ├── <module>.hash                   # output hash for jawm-test comparison
    ├── <module>_input.history          # input parameter history
    └── <module>_user_defined.history   # user-defined hash history (scope: hash)
```

---

### Per-process log directory

Each `Process` gets its own log directory named:

```
<logs_directory>/<process_name>_<datetime>_<hash>/
```

For example: `logs/bwa_align_20240315_142301_a3f9bc/`

The `<hash>` is a 10-character identifier partly derived from the Process parameters — the same hash used to reference the process in `depends_on`, `Process.wait()`, and the registry.

#### `<name>.output` — stdout

Everything the process writes to standard output. For bash scripts, this is any `echo` or command output. For Python scripts, this is `print()` output.

```bash
cat logs/bwa_align_20240315_142301_a3f9bc/bwa_align.output
```

#### `<name>.error` — stderr

Standard error output. Tool warnings, progress messages, and error messages from the script go here. This is the first place to look when a process fails.

```bash
cat logs/bwa_align_20240315_142301_a3f9bc/bwa_align.error
```

#### `<name>.exitcode` — exit code

A single number — the exit code of the process. `0` means success; anything else is a failure. This is what `Process.get_exitcode()`, `Process.is_successful()`, and `Process.has_failed()` read.

```bash
cat logs/bwa_align_20240315_142301_a3f9bc/bwa_align.exitcode
# 0
```

#### `<name>.script` — resolved script

The actual script that was executed, after all `{{variable}}` substitutions have been applied. This is invaluable for debugging — it shows exactly what ran, not what the template said should run.

```bash
cat logs/bwa_align_20240315_142301_a3f9bc/bwa_align.script
```

If `script_file` was used, the resolved content is copied here and a comment at the end shows the original file path.

#### `<name>.command` — launch command

The exact shell command used to launch the process — including any container wrapper (`apptainer exec ...`, `docker run ...`) or `before_script`/`after_script` wrapping. Useful when debugging container execution issues.

```bash
cat logs/bwa_align_20240315_142301_a3f9bc/bwa_align.command
```

#### `<name>.id` — process or job ID

For **local** execution: the OS process ID (PID).  
For **Slurm**: the Slurm job ID (as returned by `sbatch --parsable`).  
For **Kubernetes**: the pod name.

```bash
cat logs/bwa_align_20240315_142301_a3f9bc/bwa_align.id
# 84231
```

---

### Slurm-specific files

When `manager="slurm"`, an additional file is written:

#### `<name>.slurm` — Slurm job script

The full `#SBATCH` job script submitted to Slurm, including all directives, the container wrapper (if any), and `before_script`/`after_script` content. Use this to reproduce or inspect a job submission manually:

```bash
cat logs/bwa_align_20240315_142301_a3f9bc/bwa_align.slurm

# #!/bin/bash
# #SBATCH --job-name=bwa_align_a3f9bc
# #SBATCH --mem=32G
# #SBATCH --cpus-per-task=8
# ...
```

Stdout and stderr from the Slurm job are still written to `<name>.output` and `<name>.error` in the same log directory (jawm sets `--output` and `--error` automatically unless overridden in `manager_slurm`).

---

### Kubernetes-specific files

When `manager="kubernetes"`, an additional file is written:

#### `<name>.k8s.json` — Kubernetes Job manifest

The full Kubernetes Job manifest (JSON) that was submitted to the cluster. Contains the pod spec, container image, environment variables, volume mounts, and resource requests. Useful for inspecting exactly what was sent to the cluster:

```bash
cat logs/bwa_align_20240315_142301_a3f9bc/bwa_align.k8s.json
```

Pod stdout and stderr are captured by jawm and written back to `<name>.output` and `<name>.error` after the pod completes.

---

### `error.log` — aggregated error summary

The error summary file collects failure details from **all** failed processes in one place. Instead of hunting through individual process directories, you can open this single file to see every error across the entire run.

Default location: `<logs>/error.log`  
Configurable with the `error_summary_file` Process parameter.

Each entry looks like:

```
[2024-03-15 14:23:45] Process: bwa_align (Hash: a3f9bc)
Log folder: /path/to/logs/bwa_align_20240315_142301_a3f9bc
LocalAttempt: Process in Local failed.
--- stderr tail ---
[E::bwa_idx_load_file] fail to locate the index files
-----------------------------------------------------------------------------------
```

Entries are appended chronologically and separated by a line of dashes. If a process retries, each failed attempt is appended separately.

!!! tip
    The error summary file is the fastest way to understand what went wrong across a complex run. See [Errors & Debugging](errors.md) for how to use it effectively.

---

### `jawm_runs/` — CLI run transcript

When you run a module with the `jawm` command, a full transcript of everything printed to the terminal is written to:

```
<logs>/jawm_runs/<module>_<timestamp>.log
```

This file captures everything: Process-level log lines, jawm's own status messages, any Python output from the module, and final summary. It is identical to what you see in the terminal during the run.

```bash
cat logs/jawm_runs/mymodule_20240315_142301.log
```

This is particularly useful for post-mortem debugging when a run was unattended (e.g. in CI or a `screen` session), or when you want to share the full run context with someone else.

---

### `jawm_hashes/` — output hashes and history

After every `jawm` run, hash files are written here for reproducibility tracking:

| File | Description |
|------|-------------|
| `<module>.hash` | Composite hash of the run's output files — compared by `jawm-test` |
| `<module>_input.history` | Record of input parameters used in this run |
| `<module>_user_defined.history` | Written when `scope: hash` is defined in a YAML config |

These files are used by `jawm-test` to detect whether a module's outputs have changed between runs. See [Test a Module](../module/test.md) for details.

---

### Monitoring directory

jawm also maintains a lightweight monitoring directory that tracks which processes are currently running and which have completed. Default location: `~/.jawm/monitoring/`  
Configurable with the `monitoring_directory` Process parameter or `JAWM_MONITORING_DIRECTORY` environment variable.

```
~/.jawm/monitoring/
├── Running/
│   └── local.84231.txt     # one file per active process: <manager>.<id>.txt
└── Completed/
    └── local.84231.0.txt   # <manager>.<id>.<exitcode>.txt
```

Each file contains the job ID, process name, hash, manager, script path, start time, and (for completed) exit code. This directory is what `jawm-monitor` will use to provide live status views — it's designed to be readable by external tools without touching the per-process log directories.

!!! note
    Monitoring directory is mainly used for jawm tracking; this is not genreally user facing.

---

### `stats.json` — resource stats

When `--stats` is enabled (or `JAWM_RECORD_STAT=1`), a `stats.json` file is written inside each process log directory and updated periodically while the process runs:

```json
{
  "n": 42,
  "cpu_avg_pct": 387.5,
  "cpu_peak_pct": 792.3,
  "rss_avg_mib": 4821.2,
  "rss_peak_mib": 6144.0
}
```

CPU is reported as a percentage where 100% = one full core (so 800% = 8 cores fully utilised). See [Stats & Performance](stats.md) for how to read and use this.

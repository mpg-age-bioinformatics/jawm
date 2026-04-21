# Stats & Performance

jawm can record per-process resource usage — CPU and memory — while processes run. This is useful for understanding how much a workflow actually consumed, identifying memory-hungry steps, and right-sizing resource requests for Slurm or Kubernetes jobs.

Stats collection is **opt-in** and has no effect on workflow execution when disabled.

---

### Enabling stats collection

Pass `--stats` when running a module:

```bash
jawm mymodule.py --stats
```

Or set the environment variable before running:

```bash
export JAWM_RECORD_STAT=1
jawm mymodule.py
```

`JAWM_RECORD_STAT` accepts: `1`, `true`, `yes`, `on` (case-insensitive).

When enabled, jawm starts a background thread that periodically samples all active processes and writes results to a `stats.json` file inside each process's log directory.

---

### The `stats.json` file

Each active process gets a `stats.json` in its log directory, updated periodically while the process is running:

```
logs/align_sample1_20260407_095002_1d25c67735/stats.json
```

A typical file looks like:

```json
{
  "poll_count": 5,
  "cpu_sum_pct": 1842.3,
  "cpu_peak_pct": 412.7,
  "cpu_avg_pct": 368.5,
  "rss_sum_mib": 24105.0,
  "rss_peak_mib": 6144.0,
  "rss_avg_mib": 4821.0
}
```

#### Field reference

| Field | Description |
|-------|-------------|
| `poll_count` | Number of sampling polls completed |
| `cpu_avg_pct` | Average CPU usage across all polls |
| `cpu_peak_pct` | Highest single-poll CPU reading |
| `cpu_sum_pct` | Cumulative CPU sum (used to compute the average) |
| `rss_avg_mib` | Average resident memory (RSS) in MiB across all polls |
| `rss_peak_mib` | Highest single-poll RSS reading in MiB |
| `rss_sum_mib` | Cumulative RSS sum (used to compute the average) |

**CPU is reported as a percentage where 100% = one full core.** A value of `800%` means 8 cores were fully utilised at that moment. This convention matches `ps` and `sstat` output directly.

Memory is reported in **mebibytes (MiB)**: 1 MiB = 1024 × 1024 bytes. To convert to GB: divide by ~954 (or multiply by ~0.00105).

!!! note
    Depending on the manager, you may see additional internal fields. Additionally, `_`-prefixed fields are internal tracking values. They are written to the file but are not part of the user-facing summary.

--- 

**Why CPU is zero on the first Slurm poll:** Slurm stats use `sstat`, which reports cumulative CPU seconds. Computing a CPU percentage requires two samples to calculate a delta. On the first poll only a baseline is captured — CPU fields remain `0` until the second poll. RSS is available from the first poll since it is an instantaneous reading, not a delta.

---

### Extra Slurm fields via `JAWM_STATS_SLURM_FIELDS`

For Slurm jobs, you can request additional `sacct` fields to be captured at the end of the run. Set a comma-separated list of `sacct` field names:

```bash
export JAWM_STATS_SLURM_FIELDS=MaxRSS,CPUTime,MaxDiskRead,MaxDiskWrite
jawm mymodule.py --stats
```

After the run finishes, jawm calls `sacct` once per job and appends an `additional_fields` key to each Slurm process's `stats.json`:

```json
{
  "poll_count": 8,
  "cpu_avg_pct": 387.5,
  ...
  "additional_fields": {
    "MaxRSS": "6291456K",
    "CPUTime": "00:04:12",
    "MaxDiskRead": "2048M",
    "MaxDiskWrite": "512M"
  }
}
```

Field values are returned as strings exactly as `sacct` reports them. Only valid `sacct` field names are accepted — invalid names are logged as a warning and skipped.

!!! note
    `JAWM_STATS_SLURM_FIELDS` requires Slurm's `sacct` to be available. It has no effect for local or Kubernetes jobs.

---

### Polling interval

Stats are sampled periodically. The default interval is **30 seconds**, with a minimum of 5 seconds. Change it with:

```bash
export JAWM_STATS_INTERVAL=60   # poll every 60 seconds
```

For short processes (under a minute), the default 30-second interval may result in only one or zero polls — `poll_count` will be 0 or 1 and averages may be unreliable. Lower the interval if you need meaningful stats for fast processes.

---

### End-of-run summary

After every run with `--stats` enabled, jawm prints an aggregate summary to the CLI transcript (`logs/jawm_runs/<module>_<timestamp>.log`):

```
[stats] :::SUMMARY::: (CPU: ~100% = 1 full core; memory in GB decimal)
    Number of jawm Processes: 4
    Average CPU usage across jawm Processes: ~312.4%
    Peak CPU usage across jawm Processes: 792.3%
    Peak CPU jawm Process: bwa_align (log path: logs/bwa_align_20260407_142301_a3f9bc)
    Average memory (RSS) usage across jawm Processes: ~3.821 GB
    Peak memory (RSS) usage across jawm Processes: 6.442 GB
    Peak memory (RSS) jawm Process: sort_bam (log path: logs/sort_bam_20260407_143012_f1c8de)
```

Memory in the summary is converted to GB (decimal: 1 GB = 1,000,000,000 bytes) for readability. The per-process `stats.json` still stores values in MiB.

---

### How collection works

#### Local processes

jawm uses a single `ps` call to batch-sample all active local processes. For each process, it reads the current CPU% and RSS directly from the OS. These are instantaneous readings — CPU% reflects activity in the recent scheduling window, not a cumulative total.

#### Slurm processes

jawm calls `sstat --jobs=<jobids> --parsable2` to query Slurm's accounting for running jobs. CPU is derived from the delta in cumulative CPU seconds between polls (requires two samples); RSS comes from `sstat`'s `MaxRSS` field. The `sstat` tool must be available on the submission host. If `sstat` is not found, a warning is logged and Slurm CPU stats are skipped.

#### Kubernetes processes

Resource stats are not yet collected for Kubernetes processes. `stats.json` will not be written for K8s jobs.

---

### Tips

- **Right-sizing Slurm jobs:** Run your workflow once with `--stats` on representative data. The `rss_peak_mib` value in each process's `stats.json` tells you the actual peak memory — use it to set `--mem` in `manager_slurm` with a small safety margin.
- **Identifying bottlenecks:** The end-of-run summary shows which process used the most CPU and memory. Use this to prioritise where optimisation effort will have the most impact.
- **Stats for short processes:** If a process completes before the first poll, `stats.json` will either not exist or show `poll_count=0`. Lower `JAWM_STATS_INTERVAL` or accept that very short steps won't have reliable stats.
- **jawm-monitor integration:** `jawm-monitor` will include the feature to display live per-process stats from `stats.json` without needing to open individual files.

---

### See also

- [Log Structure](logs.md) — where `stats.json` lives within the log directory layout
- [jawm CLI reference](../cli/jawm.md) — `--stats` flag
- [jawm-monitor](../cli/jawm-monitor.md) — live process monitoring (from v1.0.0)

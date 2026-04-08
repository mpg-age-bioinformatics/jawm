# JAWM Configuration

jawm reads `JAWM_*` environment variables to control system-level behavior such as concurrency limits, polling intervals, timeouts, and backend tuning. These variables can be set in the shell or in a persistent config file.

---

## Config File

jawm automatically loads variables from a config file at startup. Only variables prefixed with `JAWM_` are read, and **existing environment variables are never overridden** — the config file provides defaults only.

### Default location

```text
~/.jawm/config
```

### Custom location

```bash
export JAWM_CONFIG_FILE=/path/to/jawm.conf
```

### File format

Simple `KEY=VALUE` syntax. Blank lines and lines starting with `#` are ignored.

```text
# ~/.jawm/config
JAWM_MAX_PROCESS=50
JAWM_EXPAND_PATH=true
JAWM_LOG_EMOJI=0
JAWM_WAIT_TIMEOUT=43200
```

_**Note**_: Shell features such as `export`, variable expansion (`$HOME`), or inline comments are not supported. Only `KEY=VALUE` pairs are recognized.

---

## Setting Variables in the Shell

Any `JAWM_*` variable can also be set directly in the shell, either persistently or per-command.

**Using `export`**

```bash
export JAWM_MAX_PROCESS=50
jawm workflow.py
```

The variable remains set for the entire shell session.

**Inline per-command**

```bash
JAWM_MAX_PROCESS=50 jawm workflow.py
```

The variable applies only to that single invocation and does not persist.

**Precedence**

Shell environment variables **always take precedence** over the config file. If `JAWM_MAX_PROCESS` is already set via `export`, the value in `~/.jawm/config` is ignored.

---

_**Variable Reference**_

## General Variables

---

### `JAWM_CONFIG_FILE`

- **Type:** `str` (path)
- **Default:** `~/.jawm/config`

Path to the jawm config file. Set this in the shell environment to use a custom config location.

```bash
export JAWM_CONFIG_FILE=/shared/team/jawm.conf
```

---

### `JAWM_LOG_EMOJI`

- **Type:** `bool`
- **Default:** `1` (enabled)
- **Values:** `1`, `true`, `yes`, `on` to enable; `0`, `false`, `no`, `off` to disable

Controls whether jawm prepends emoji indicators to log messages.

```text
JAWM_LOG_EMOJI=0
```

---

### `JAWM_MONITORING_DIRECTORY`

- **Type:** `str` (path)
- **Default:** `~/.jawm/monitoring`

Directory where jawm writes process monitoring state files. Can also be set via the `monitoring_directory` Process parameter.

```text
JAWM_MONITORING_DIRECTORY=/tmp/jawm_monitoring
```

---

### `JAWM_MODULES_PATH`

- **Type:** `str` (path)
- **Default:** `<caller_dir>/.submodules`

Root directory where jawm modules are cloned or searched. If the path is relative, it is resolved relative to the calling script's directory.

```text
JAWM_MODULES_PATH=/shared/jawm_modules
```

---

## Path Expansion

---

### `JAWM_EXPAND_PATH`

- **Type:** `bool`
- **Default:** `true`
- **Values:** `true`, `1`, `yes` to enable; `false`, `0`, `no` to disable

When enabled, jawm automatically expands relative paths starting with `./` or `../` to absolute paths. This is the default behavior.

```text
JAWM_EXPAND_PATH=false
```

---

### `JAWM_EXPAND_HOME`

- **Type:** `bool`
- **Default:** `false`
- **Values:** `true`, `1`, `yes` to enable; `false`, `0`, `no` to disable

When enabled, jawm expands `~` in path values to the user's home directory.

```text
JAWM_EXPAND_HOME=true
```

---

## Concurrency

---

### `JAWM_MAX_PROCESS`

- **Type:** `int`
- **Default:** not set (no limit)

Global limit on the number of concurrently running processes across all backends. When set, jawm will hold new process executions until an active slot is available.

```text
JAWM_MAX_PROCESS=50
```

---

### `JAWM_MAX_PROCESS_<MANAGER>`

- **Type:** `int`
- **Default:** not set (no limit)

Per-backend concurrency limit. Replace `<MANAGER>` with the uppercase backend name. Takes precedence over `JAWM_MAX_PROCESS` for that backend.

```text
JAWM_MAX_PROCESS_SLURM=100
JAWM_MAX_PROCESS_LOCAL=4
JAWM_MAX_PROCESS_KUBERNETES=20
```

---

### `JAWM_PROCESS_WAIT_POLL`

- **Type:** `float` (seconds)
- **Default:** `0.2`

Polling interval when waiting for a concurrency slot to become available.

```text
JAWM_PROCESS_WAIT_POLL=0.5
```

---

## Wait and Synchronization

---

### `JAWM_WAIT_TIMEOUT`

- **Type:** `int` (seconds)
- **Default:** `86400` (24 hours)

Maximum time `jawm.Process.wait()` will wait for a process to finish before timing out.

```text
JAWM_WAIT_TIMEOUT=43200
```

---

### `JAWM_WAIT_GRACE`

- **Type:** `float` (seconds)
- **Default:** `0.3`

Brief grace period before `jawm.Process.wait()` and `jawm.Process.kill_all()` scan the registry. Allows recently launched processes to register.

```text
JAWM_WAIT_GRACE=0.5
```

---

### `JAWM_WAIT_STABILIZE`

- **Type:** `int` (seconds)
- **Default:** `600` (10 minutes)

Maximum time `jawm.Process.wait()` will wait for the registry to stabilize in dynamic mode. Dynamic mode waits until no new processes are being added before proceeding.

```text
JAWM_WAIT_STABILIZE=300
```

---

### `JAWM_WAIT_CLI`

- **Type:** `bool`
- **Default:** `1` (enabled)
- **Values:** `1`, `true`, `yes`, `on` to enable; `0`, `false`, `no`, `off` to disable

Controls whether the `jawm` CLI automatically waits for all processes to finish at the end of a workflow run.

```text
JAWM_WAIT_CLI=0
```

---

## Execution Throttle

---

### `JAWM_EXECUTE_SERIAL_WAIT`

- **Type:** `bool`
- **Default:** `false`

Enables a small delay before each serial (non-parallel) process execution. Useful for avoiding burst submissions.

```text
JAWM_EXECUTE_SERIAL_WAIT=true
```

---

### `JAWM_EXECUTE_PARALLEL_WAIT`

- **Type:** `bool`
- **Default:** `true`

Enables a small delay before each parallel process execution. Enabled by default to space out concurrent submissions.

```text
JAWM_EXECUTE_PARALLEL_WAIT=false
```

---

### `JAWM_EXECUTE_WAIT`

- **Type:** `float` (seconds)
- **Default:** `0.1` (backend-specific: `0.3` for Slurm)

Base delay in seconds applied before execution when throttling is enabled.

```text
JAWM_EXECUTE_WAIT=0.5
```

---

### `JAWM_EXECUTE_WAIT_<MANAGER>`

- **Type:** `float` (seconds)
- **Default:** falls back to `JAWM_EXECUTE_WAIT`

Per-backend override for the execution throttle delay. Replace `<MANAGER>` with the uppercase backend name. Takes precedence over `JAWM_EXECUTE_WAIT`.

```text
JAWM_EXECUTE_WAIT_SLURM=0.5
JAWM_EXECUTE_WAIT_KUBERNETES=0.2
```

---

## Filesystem

---

### `JAWM_FS_SETTLE_TIMEOUT`

- **Type:** `float` (seconds)
- **Default:** `10`

Maximum time to wait for an output file to appear and stabilize after a process finishes. Useful on network filesystems (NFS, GPFS) where metadata may lag.

```text
JAWM_FS_SETTLE_TIMEOUT=30
```

---

### `JAWM_FS_SETTLE_POLL`

- **Type:** `float` (seconds)
- **Default:** `0.2`
- **Minimum:** `0.05`

Polling interval for filesystem settle checks.

```text
JAWM_FS_SETTLE_POLL=0.5
```

---

### `JAWM_PROCESS_FINISH_WAIT`

- **Type:** `float` (seconds)
- **Default:** `0.0`

Additional wait time after a process finishes, before jawm reads its output files. Applied on top of filesystem settle checks.

```text
JAWM_PROCESS_FINISH_WAIT=1.0
```

---

## Local Backend

---

### `JAWM_LOCAL_FINISH_WAIT`

- **Type:** `float` (seconds)
- **Default:** `0.0`

Additional wait time after a local process finishes. Functions like `JAWM_PROCESS_FINISH_WAIT` but specific to the local backend.

```text
JAWM_LOCAL_FINISH_WAIT=0.5
```

---

## Slurm Backend

---

### `JAWM_MAX_SLURM_JOBS`

- **Type:** `int`
- **Default:** not set (no limit)

Maximum number of concurrent Slurm jobs for the current user. When set, jawm queries `squeue` and holds submissions until the job count drops below this limit. Opt-in only.

```text
JAWM_MAX_SLURM_JOBS=500
```

---

### `JAWM_MAX_SLURM_JOBS_WAIT_POLL`

- **Type:** `float` (seconds)
- **Default:** `3.0`
- **Minimum:** `0.5`

Polling interval when waiting for Slurm job capacity.

```text
JAWM_MAX_SLURM_JOBS_WAIT_POLL=5.0
```

---

### `JAWM_MAX_SLURM_JOBS_SQUEUE_INTERVAL`

- **Type:** `float` (seconds)
- **Default:** `2.0`
- **Minimum:** `1.0`

Minimum interval between `squeue` calls. Prevents excessive querying of the Slurm scheduler.

```text
JAWM_MAX_SLURM_JOBS_SQUEUE_INTERVAL=5.0
```

---

### `JAWM_SLURM_TRANSIENT_RETRY`

- **Type:** `int`
- **Default:** `7`

Number of retry attempts when a transient Slurm error is detected during job submission (e.g., controller not responding).

```text
JAWM_SLURM_TRANSIENT_RETRY=10
```

---

### `JAWM_SLURM_TRANSIENT_WAIT`

- **Type:** `int` (seconds)
- **Default:** `5`

Wait time before the first retry after a transient Slurm submission error.

```text
JAWM_SLURM_TRANSIENT_WAIT=10
```

---

### `JAWM_SLURM_FINISH_WAIT`

- **Type:** `float` (seconds)
- **Default:** `1.5`

Additional wait time after a Slurm job reaches a final state, before jawm reads output files. Includes a filesystem stability check.

```text
JAWM_SLURM_FINISH_WAIT=3.0
```

---

## Kubernetes Backend

---

### `JAWM_K8S_AUTOMOUNT`

- **Type:** `bool`
- **Default:** `0` (disabled)
- **Values:** `1`, `true`, `yes`, `on` to enable

When enabled, jawm automatically generates hostPath volume mounts from process variables. Can also be enabled per-process via `manager_kubernetes={"automated_mount": True}`.

```text
JAWM_K8S_AUTOMOUNT=1
```

---

### `JAWM_K8S_LOG_OUTPUT_INTERVAL`

- **Type:** `int` (seconds)
- **Default:** `60`
- **Minimum:** `20`

Interval for periodic log pulls from the running Kubernetes pod to the local output file.

```text
JAWM_K8S_LOG_OUTPUT_INTERVAL=30
```

---

### `JAWM_K8S_POD_CREATE_TIMEOUT`

- **Type:** `int` (seconds)
- **Default:** `300` (5 minutes)

Maximum time to wait for a Kubernetes pod to be created. If exceeded, the process is treated as failed.

```text
JAWM_K8S_POD_CREATE_TIMEOUT=600
```

---

### `JAWM_K8S_POD_START_TIMEOUT`

- **Type:** `int` (seconds)
- **Default:** `1200` (20 minutes)

Maximum time to wait for a Kubernetes pod to start running after creation. Covers image pull and container initialization.

```text
JAWM_K8S_POD_START_TIMEOUT=1800
```

---

### `JAWM_K8S_LOG_TAIL_LINES`

- **Type:** `int`
- **Default:** `50`

Number of trailing log lines captured from a Kubernetes container when the process fails. Written to the stderr file.

```text
JAWM_K8S_LOG_TAIL_LINES=100
```

---

### `JAWM_KUBERNETES_FINISH_WAIT`

- **Type:** `float` (seconds)
- **Default:** `0.0`

Additional wait time after a Kubernetes job completes, before jawm reads output files.

```text
JAWM_KUBERNETES_FINISH_WAIT=2.0
```

---

## CLI and Statistics

---

### `JAWM_RECORD_STAT`

- **Type:** `bool`
- **Default:** `0` (disabled)
- **Values:** `1`, `true`, `yes`, `on` to enable

Enables runtime statistics collection. When enabled, jawm periodically records process states and writes `stats.json` to each process log directory.

```text
JAWM_RECORD_STAT=1
```

---

### `JAWM_STATS_INTERVAL`

- **Type:** `float` (seconds)
- **Default:** `30`
- **Minimum:** `5`

Interval between statistics collection cycles when `JAWM_RECORD_STAT` is enabled.

```text
JAWM_STATS_INTERVAL=60
```

---

### `JAWM_STATS_SLURM_FIELDS`

- **Type:** `str` (comma-separated)
- **Default:** empty (disabled)

Additional `sacct` fields to query and store in `stats.json` after Slurm processes complete. Only used when `JAWM_RECORD_STAT` is enabled.

```text
JAWM_STATS_SLURM_FIELDS=MaxRSS,Elapsed,TotalCPU
```

---

### `JAWM_GIT_CACHE`

- **Type:** `str` (path)
- **Default:** `~/.jawm/git`

Directory where jawm caches git-based module clones. Set to `.` to use `<cwd>/git`.

```text
JAWM_GIT_CACHE=/tmp/jawm_git_cache
```

---

## Remote YAML Configuration

---

### `JAWM_ALLOW_URL_CONFIG`

- **Type:** `bool`
- **Default:** `1` (enabled)
- **Values:** `1`, `true`, `yes`, `on` to enable; `0`, `false`, `no`, `off` to disable

Controls whether the CLI accepts remote URLs as YAML parameter files. Disable to restrict configuration to local files only.

```text
JAWM_ALLOW_URL_CONFIG=0
```

---

### `JAWM_URL_CACHE_DIR`

- **Type:** `str` (path)
- **Default:** `~/.jawm/remote_params`

Directory where downloaded remote YAML files are cached.

```text
JAWM_URL_CACHE_DIR=/tmp/jawm_url_cache
```

---

### `JAWM_URL_MAX_BYTES`

- **Type:** `int` (bytes)
- **Default:** `1048576` (1 MB)

Maximum allowed size for a remote YAML file download.

```text
JAWM_URL_MAX_BYTES=2097152
```

---

### `JAWM_URL_TIMEOUT`

- **Type:** `float` (seconds)
- **Default:** `10`

Timeout for downloading a remote YAML file.

```text
JAWM_URL_TIMEOUT=30
```

---

### `JAWM_URL_FORCE_REFRESH`

- **Type:** `bool`
- **Default:** `0` (disabled)
- **Values:** `1`, `true`, `yes`, `on` to enable

When enabled, jawm re-downloads remote YAML files even if a cached version exists.

```text
JAWM_URL_FORCE_REFRESH=1
```

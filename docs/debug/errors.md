# Errors Debugging

When a process fails, jawm gives you several layers of information to work with. Start with the broadest view — the aggregated error summary — and drill down from there. This page walks through every tool available, in the order you should reach for them.

---

### Step 1: Read the error summary file

The fastest first step after a failure is opening `error.log`. By default it lives at:

```
<logs>/error.log
```

Configurable via the [`error_summary_file`](../process/parameters.md#error_summary_file) Process parameter.

Every time a process fails — regardless of manager (local, Slurm, Kubernetes) — an entry is appended here. You do not need to know which process failed or where its log directory is. The summary file collects all failures in one place, in chronological order.

A typical entry looks like:

```
[2026-04-07 09:50:03] Process: align_sample1 (Hash: 1d25c67735)
Log folder: /path/to/logs/align_sample1_20260407_095002_1d25c67735
LocalError: Unhandled exception in monitoring for align_sample1: [Errno 2] No such file or directory: 'scripts/align.sh'
--------------------------------------------------------------------------------
```

Each entry contains:

| Field | What it tells you |
|-------|-------------------|
| Timestamp | When the failure was recorded |
| Process name | Which process failed |
| Hash | The 10-character process hash — use this to look up its log directory |
| Log folder | Full path to the per-process log directory |
| Error type prefix | The category of failure (see below) |
| Error message | What actually went wrong — often includes a stderr tail |

Entries are separated by a line of 80 dashes. If a process retried multiple times, each failed attempt gets its own entry.

```bash
cat logs/error.log
```

#### Error type prefixes

The label at the start of the error message identifies where in jawm the failure originated:

| Prefix | Meaning |
|--------|---------|
| `LocalError` | Unhandled exception in local execution or monitoring |
| `LocalAttempt` | Process failed in the local executor — one entry per attempt, plus a final summary |
| `DockerError` | Exception during Docker command execution |
| `ApptainerError` | Exception during Apptainer command execution |
| `SlurmError` | Slurm job submission failed, or job exited with non-zero status |
| `SlurmMonitoring` | `sacct` monitoring exhausted its retries (Slurm) |
| `K8sKubectl` | `kubectl apply` failed or returned a non-zero exit |
| `K8sStartup` | Kubernetes pod did not start within the configured timeout, or crashed at startup |
| `K8sAttempt` | Kubernetes job failed — one entry per attempt |
| `K8sError` | Unhandled exception in Kubernetes monitoring |
| `ExecuteError` | Process failed to launch or raised an unhandled exception at execute time |
| `ErrorYAML` | YAML parameter file could not be loaded or parsed |
| `ErrorScript` | Missing or invalid script content (neither `script` nor `script_file` was valid) |
| `InvalidValue` | Unsupported value (e.g. `manager`) |
| `ErrorWait` | Error detected during `Process.wait()` — disallowed exit code or an exception in the wait loop |
| `VarUpdate` | `update_vars()` call failed |
| `Killer` | Process was manually terminated via `Process.kill()` |

You can see multiple entries for the same Process with retries — one per failed attempt before the final give-up.

---

### Step 2: Read the per-process stderr file

The error summary includes a tail of stderr for most error types, but it is limited to a few lines. For the full error output from the process itself, read the `.error` file directly:

```bash
cat logs/align_sample1_20260407_095002_1d25c67735/align_sample1.error
```

This file contains everything the process wrote to standard error — tool warnings, traceback output, error messages from called programs. For most failures, this is the definitive answer to **_what the script actually complained about_**.

The corresponding stdout file is at `<name>.output` in the same directory:

```bash
cat logs/align_sample1_20260407_095002_1d25c67735/align_sample1.output
```

---

### Step 3: Check the exit code

The `.exitcode` file contains a single number — the exit code of the process:

```bash
cat logs/align_sample1_20260407_095002_1d25c67735/align_sample1.exitcode
# 1
```

`0` means success. Any other value is a failure. If the file is missing entirely, the process did not start (it was skipped via `when=False`, or it was blocked because an earlier process already failed).

---

### Inspecting processes programmatically

All the above files are also accessible via Process methods. These are useful when you want to check outcomes inside a workflow, add conditional logic, or write post-run summaries.

#### `get_exitcode()`

Returns the content of the `.exitcode` file as a string, or `None` if the file does not exist.

```python
code = my_process.get_exitcode()
print(code)   # "0", "1", "127", etc., or None if not started
```

#### `is_successful()` and `has_failed()`

Convenience wrappers around `get_exitcode()`:

```python
if my_process.is_successful():
    print("Process completed successfully")

if my_process.has_failed():
    print("Process failed — check stderr:")
    print(my_process.get_error())
```

`is_successful()` returns `True` iff the exit code is `"0"`.  
`has_failed()` returns `True` iff an exit code was recorded _and_ it is non-zero.  
Both return `False` (not `True`, not an error) if the process never started.

#### `get_error()`

Returns the full content of the `.error` file (stderr), or `None` if the file does not exist.

```python
stderr = my_process.get_error()
if stderr:
    print(stderr)
```

#### `get_output()`

Returns the full content of the `.output` file (stdout), or `None` if unavailable.

```python
stdout = my_process.get_output()
```

#### `get_script()`

Returns the resolved script — the actual content that was executed, after all `{{variable}}` substitutions. If the original process used `script_file`, the substituted content is copied into `.script` and the original file path is noted in a comment at the end.

This is particularly useful when you suspect a variable substitution produced an unexpected value:

```python
print(my_process.get_script())
# See exactly what ran, not what the template said should run
```

#### `get_command()`

Returns the exact shell command used to launch the process — including any container wrapper (`apptainer exec ...`, `docker run ...`) and `before_script`/`after_script` wrapping.

```python
print(my_process.get_command())
```

---

### Live output tailing during `Process.wait()`

To stream a process's output to the terminal in real time while waiting for it to finish, use the `tail` parameter of `Process.wait()`:

```python
# Tail stdout while waiting for a specific process
Process.wait(align.hash, tail=True)

# Tail stderr (useful for tools that write progress to stderr)
Process.wait(align.hash, tail="stderr")

# Tail both stdout and stderr
Process.wait(align.hash, tail="both")
```

The default `tail=None` does not stream output — only status log lines are printed. `tail=True` and `tail="stdout"` are equivalent.

This is useful for long-running processes where you want immediate feedback, or when debugging interactively and want to see tool output without manually opening the log files.

---

### Forcing a process to run despite earlier failures

By default, when any process fails, jawm sets a stop flag that prevents all subsequent processes from executing — avoiding wasted work on a run that is already broken.

Sometimes during debugging you want to run a specific downstream process anyway — for example to confirm whether a particular step would succeed given the right inputs. Set `always_run=True` to bypass the stop flag for that process:

```python
cleanup = jawm.Process(
    name="cleanup",
    always_run=True,
    script="""#!/bin/bash
    rm -rf /tmp/intermediate/
    """,
)
cleanup.execute()
```

The `always_run` flag does not affect whether a process waits for its `depends_on` dependencies — it only bypasses the global stop check. Use this with care: if a previous process failed because it did not produce required input files, a dependent process with `always_run=True` may fail for a different reason.

---

### See also

- [Log Structure](logs.md) — where every file lives and what it contains
- [Stats & Performance](stats.md) — CPU and memory tracking per process
- [`error_summary_file` parameter](../process/parameters.md#error_summary_file) — configure the error summary path per process
- [`Process.wait()` method](../process/methods.md#wait) — full parameter reference including `tail` options

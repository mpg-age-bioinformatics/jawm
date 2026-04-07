This page documents the class-level methods of `jawm.Process`.

Class-level methods are called on the `jawm.Process` class itself, not on a specific process instance. They operate on the workflow as a whole with the example use cases like setting shared configuration, waiting for processes to complete, terminating running processes, querying workflow state, and resetting runtime state.

```python
import jawm

jawm.Process.set_default(manager="local", retries=1)    # example

p1 = jawm.Process(name="step1", script="#!/bin/bash\necho step1")
p2 = jawm.Process(name="step2", script="#!/bin/bash\necho step2")

p1.execute()
p2.execute()

jawm.Process.wait()     # example
```

The available class-level methods can be grouped into the following categories:

- **Configuration** — `set_default()`, `set_override()`, `update()`
- **Synchronization** — `wait()`
- **Process control** — `kill()`, `kill_all()`
- **State reset** — `reset_stop()`, `reset_runtime()`
- **Status & inspection** — `list_active()`, `list_all()`, `list_monitoring_threads()`, `get_cls_values()`, `get_cls_var()`

For instance methods that operate on a specific process (such as `p.execute()` or `p.is_successful()`), see the [Methods](methods.md) page.

For class-level parameters (such as `jawm.Process.default_parameters` or `jawm.Process.registry`), see the [Class-Level Parameters](cls_parameters.md) page.

---

## `set_default()`

- **Signature**: `jawm.Process.set_default(**kwargs)`
- **Returns**: `None`

Set one or more default values at the class level for all `Process` instances.

These defaults are applied with the **lowest priority** in the configuration precedence — they are overridden by YAML configuration, Python arguments, CLI overrides, and `jawm.Process.override_parameters`.

`name` and reserved keys are filtered out and cannot be set as defaults.

`set_default()` only affects processes created **after** the call. To also update already-registered processes, use `jawm.Process.update()` instead.

**Example:**
```python
import jawm

jawm.Process.set_default(
    manager="local",
    logs_directory="logs",
    retries=2
)
```

After setting defaults, any new `Process` will use these values unless overridden:

```python
p = jawm.Process(
    name="example",
    script="""#!/bin/bash
echo "Hello"
"""
)
# p.manager is "local"
# p.logs_directory is "logs"
# p.retries is 2
```

**Example — container defaults:**
```python
jawm.Process.set_default(
    environment="docker",
    container="python:3.12",
    docker_run_as_user=True
)
```

---

## `set_override()`

- **Signature**: `jawm.Process.set_override(**kwargs)`
- **Returns**: `None`

Set one or more override values at the class level that take the **highest priority** for all `Process` instances.

These overrides win over YAML configuration, Python arguments, and CLI overrides.

`name` and reserved keys are filtered out and cannot be set as overrides.

`set_override()` only affects processes created **after** the call. To also update already-registered processes, use `jawm.Process.update()` instead.

**Example:**
```python
import jawm

jawm.Process.set_override(
    manager="slurm",
    manager_slurm={"--partition": "batch", "--cpus-per-task": "4"}
)
```

After setting overrides, all processes will use these values regardless of other configuration:

```python
p = jawm.Process(
    name="example",
    manager="local",  # will be ignored
    script="""#!/bin/bash
echo "Hello"
"""
)
# p.manager is "slurm" (override wins)
```

---

## `update()`

- **Signature**: `jawm.Process.update(override=True, **kwargs)`
- **Returns**: `None`

System-wide update of Process parameters that applies to both **future processes** and **already-registered (not yet executed) processes**.

This method provides more control than `set_default()` or `set_override()` alone, because it retroactively updates existing `Process` instances in the registry that have not started execution yet. Processes that have already started are not affected.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `override` | `bool` | `True` | If `True`, applies as a high-priority override. If `False`, applies as a low-priority default. |
| `**kwargs` | | | Any Process parameters to update. |

**Behavior with `override=True` (default):**

- Updates `jawm.Process.override_parameters` with a deep merge for dict-like parameters.
- Overwrites the parameter value on all not-yet-executed processes in the registry.

**Behavior with `override=False`:**

- Updates `jawm.Process.default_parameters` with a deep merge for dict-like parameters.
- Only fills in missing (unset) parameter values on existing processes — existing values are not overwritten.
- Removes any previously set `jawm.Process.override_parameters` entry for the same key.

**Example — override update (affects existing processes):**
```python
import jawm

p1 = jawm.Process(name="step1", script="#!/bin/bash\necho 1")
p2 = jawm.Process(name="step2", script="#!/bin/bash\necho 2")

# Both p1 and p2 (not yet executed) will get retries=3
jawm.Process.update(retries=3)
```

**Example — default update (fill missing only):**
```python
import jawm

p1 = jawm.Process(name="step1", script="#!/bin/bash\necho 1", retries=2)
p2 = jawm.Process(name="step2", script="#!/bin/bash\necho 2")

jawm.Process.update(override=False, retries=5)
# p1.retries remains 2 (already set)
# p2.retries becomes 5 (was unset)
```

**Example — deep merge for dict parameters:**
```python
jawm.Process.update(
    env={"THREADS": "8", "MODE": "production"}
)
# Existing env keys on processes are preserved; new keys are merged in
```

---

## `wait()`

- **Signature**: `jawm.Process.wait(process_list="all", allowed_exit="auto", tail=None, tail_poll=0.5, log=True, timeout=None, dynamic=False, abort="auto", exitcode=1, graceful=True)`
- **Returns**: `bool`

Wait until the specified processes are finished, optionally checking their exit codes.

This is the primary synchronization point in a jawm workflow. It blocks the calling thread until all specified processes have completed, and optionally verifies their exit codes.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `process_list` | `"all"`, `str`, `list[str]`, or `list[Process]` | `"all"` | Which process(es) to wait for. Accepts process names, hashes, Process instances, or `"all"` for every executed/finished process in the registry. |
| `allowed_exit` | `"auto"`, `"all"`, `int`, `str`, or `list` | `"auto"` | Allowed exit codes. `"auto"` allows exit code `0`, treating missing exit codes as acceptable when `process_list="all"` and as failures for specific processes. `"all"` accepts any exit code. |
| `tail` | `None`, `True`, `"stdout"`, `"stderr"`, or `"both"` | `None` | If set, stream live process output to the console while waiting. `True` is equivalent to `"stdout"`. |
| `tail_poll` | `float` | `0.5` | Polling interval in seconds for live tailing. |
| `log` | `bool` | `True` | Whether to log wait-related messages. |
| `timeout` | `int` or `None` | `None` | Maximum seconds to wait per process. `None` waits indefinitely, unless `JAWM_WAIT_TIMEOUT` environment variable is set. |
| `dynamic` | `bool` | `False` | Enable dynamic stabilization mode on the process registry. |
| `abort` | `bool`, `str`, or `"auto"` | `"auto"` | Action on failure. See abort behavior below. |
| `exitcode` | `int` | `1` | Exit code used when `abort="exit"`. |
| `graceful` | `bool` | `True` | If `True` and aborting, wait for all remaining active processes to finish before raising/exiting. |

**Returns:** `True` if all waited processes completed with allowed exit codes, `False` otherwise.

**Abort behavior:**

The `abort` parameter controls what happens when a process finishes with a disallowed exit code:

| Value | Behavior |
|---|---|
| `"auto"` (default) | No abort when `process_list="all"`. Raises `RuntimeError` when waiting for specific processes. |
| `True` or `"raise"` | Raises a `RuntimeError`. |
| `"exit"` | Calls `sys.exit()` with the specified `exitcode`. |
| `False` or `None` | No abort; returns `False` instead. |

When `graceful=True` (default), jawm waits for all remaining active processes to complete before raising or exiting. When `graceful=False`, the abort happens immediately after the failure is detected.

**Dynamic mode:**

When `dynamic=True`, `jawm.Process.wait()` does not take a single snapshot of the registry. Instead, it monitors the registry for stabilization — repeatedly polling until no new processes are being registered and all active ones have finished. This requires 3 consecutive stable polling cycles before confirming. This is useful for workflows that dynamically create processes during execution.

The maximum stabilization wait time is controlled by the `JAWM_WAIT_STABILIZE` environment variable (default: 600 seconds).

**Example — wait for all processes:**
```python
import jawm

p1 = jawm.Process(name="step1", script="#!/bin/bash\necho 1")
p2 = jawm.Process(name="step2", script="#!/bin/bash\necho 2")

p1.execute()
p2.execute()

jawm.Process.wait()
```

**Example — wait for specific processes:**
```python
jawm.Process.wait([p1.hash, p2.hash])
```

**Example — wait with live tailing:**
```python
jawm.Process.wait(tail="both")
```

**Example — wait with timeout:**
```python
jawm.Process.wait(timeout=300)  # 5 minutes per process
```

**Example — abort on failure:**
```python
# Raises RuntimeError on any non-zero exit
jawm.Process.wait([p1.hash], abort=True)
```

**Example — accept multiple exit codes:**
```python
jawm.Process.wait(allowed_exit=[0, 1])
```

**Example — exit the program on failure:**
```python
jawm.Process.wait(abort="exit", exitcode=2)
```

**Example — dynamic mode:**
```python
jawm.Process.wait(dynamic=True)
```

_**Note**_: The `JAWM_WAIT_TIMEOUT` environment variable can set a global default timeout (in seconds) for all `jawm.Process.wait()` calls where no explicit `timeout` is provided.

---

## `kill()`

- **Signature**: `jawm.Process.kill(identifier)`
- **Returns**: `bool`

Attempt to terminate a running process by its hash or name.

Looks up the process in `jawm.Process.registry` using the provided identifier. If found and currently running, terminates it using the appropriate method for its execution backend:

- **Local**: sends `SIGTERM` to the process PID.
- **Slurm**: verifies the job is active with `squeue`, then runs `scancel`.
- **Kubernetes**: deletes the Job and its pods via `kubectl`. If the process has not yet received a runtime ID, falls back to deleting by jawm labels.

On successful termination, jawm:

- Writes a `<name>.killer` file in the process log directory with termination details.
- Logs the termination to the error summary file.
- Marks the process as finished so that `jawm.Process.wait()` unblocks.
- Moves the monitoring status from Running to Completed.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `identifier` | `str` | Process name or hash. Using the hash is preferred for uniqueness. |

**Returns:** `True` if successfully killed, `False` otherwise (e.g. already finished, not found, or termination failed).

**Example:**
```python
import jawm

p = jawm.Process(name="long_running", script="#!/bin/bash\nsleep 3600")
p.execute()

jawm.Process.kill(p.hash)
```

**Example — kill by name:**
```python
jawm.Process.kill("long_running")
```

---

## `kill_all()`

- **Signature**: `jawm.Process.kill_all()`
- **Returns**: `dict`

Kill all currently running processes in the registry.

Iterates through all registered processes and terminates any that have started execution but not yet finished. For Slurm processes, performs additional cleanup by cancelling jobs matched by name pattern.

A brief grace period (controlled by `JAWM_WAIT_GRACE`, default 0.3 seconds) is applied before scanning, to allow recently started processes to register their runtime IDs.

**Returns:** A dictionary with three keys:

| Key | Type | Description |
|---|---|---|
| `"killed"` | `list[str]` | Processes successfully terminated (`"name\|hash"` format). |
| `"not_executed"` | `list[str]` | Processes that were registered but never started execution. |
| `"failed"` | `list[str]` | Processes where termination was attempted but failed. |

**Example:**
```python
import jawm

p1 = jawm.Process(name="step1", script="#!/bin/bash\nsleep 3600")
p2 = jawm.Process(name="step2", script="#!/bin/bash\nsleep 3600")

p1.execute()
p2.execute()

result = jawm.Process.kill_all()
print(f"Killed: {len(result['killed'])}")
print(f"Failed to kill: {len(result['failed'])}")
```

---

## `reset_stop()`

- **Signature**: `jawm.Process.reset_stop()`
- **Returns**: `None`

Clear the class-level `jawm.Process.stop_future_event` flag to allow processes to run again after a previous failure.

When a process fails, jawm sets `stop_future_event` to prevent subsequent processes from executing. `reset_stop()` clears this flag so new or pending processes can proceed.

_**Note**_: `reset_stop()` only clears the stop flag. It does not restart or re-execute any previously skipped processes.

**Example:**
```python
import jawm

# After a failure, reset the stop flag
jawm.Process.reset_stop()

# Processes can now execute again
p = jawm.Process(name="retry_step", script="#!/bin/bash\necho retry")
p.execute()
```

---

## `reset_runtime()`

- **Signature**: `jawm.Process.reset_runtime()`
- **Returns**: `None`

Reset the global runtime state of all `Process` instances.

This method performs three actions:

1. Clears the `jawm.Process.stop_future_event` flag.
2. Marks all lingering processes as finished so nothing waits on them indefinitely.
3. Clears the `jawm.Process.registry`.

This is primarily intended for **interactive environments** such as Jupyter notebooks where the Python interpreter persists across multiple workflow runs. It is safe to call between tests or repeated invocations within a single Python session.

_**Note**_: `reset_runtime()` only resets in-memory state. It does not delete log files or other artifacts from previous runs.

**Example:**
```python
import jawm

# After completing a workflow run in a notebook
jawm.Process.reset_runtime()

# Start a fresh workflow
p = jawm.Process(name="fresh_start", script="#!/bin/bash\necho fresh")
p.execute()
```

---

## `list_active()`

- **Signature**: `jawm.Process.list_active()`
- **Returns**: `list[dict]`

List all currently active (unfinished) processes in the registry.

Returns a list of dictionaries, each containing summary information about a process that has not yet finished.

**Returned fields:**

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Process name |
| `hash` | `str` | Process hash |
| `id` | `str` | Runtime ID (PID, Slurm job ID, or K8s job name), or `"NA"` |
| `manager` | `str` | Execution backend |
| `environment` | `str` | Execution environment |
| `log_path` | `str` | Path to the process log directory |
| `initiated_at` | `str` | Timestamp when the process was initialized |
| `execution_start` | `str` | Timestamp when execution started, or `"NA"` |

**Example:**
```python
import jawm

p1 = jawm.Process(name="step1", script="#!/bin/bash\nsleep 60")
p1.execute()

for proc_info in jawm.Process.list_active():
    print(f"{proc_info['name']} ({proc_info['manager']}) — started at {proc_info['execution_start']}")
```

---

## `list_all()`

- **Signature**: `jawm.Process.list_all()`
- **Returns**: `list[dict]`

List all registered processes, both running and finished.

Returns a list of dictionaries with detailed information about every unique process in the registry.

**Returned fields:**

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Process name |
| `hash` | `str` | Process hash |
| `id` | `str` | Runtime ID (PID, Slurm job ID, or K8s job name), or `"NA"` |
| `manager` | `str` | Execution backend |
| `environment` | `str` | Execution environment |
| `log_path` | `str` | Path to the process log directory |
| `initiated_at` | `str` | Timestamp when the process was initialized |
| `execution_start` | `str` | Timestamp when execution started, or `"NA"` |
| `execution_end` | `str` | Timestamp when execution ended, or `"NA"` |
| `finished` | `bool` | Whether the process has finished |
| `success` | `bool` or `"NA"` | Whether the process exited with code `0`, or `"NA"` if no exit code is available |

**Example:**
```python
import jawm

# ... run a workflow ...
jawm.Process.wait()

for proc_info in jawm.Process.list_all():
    status = "success" if proc_info["success"] is True else "failed"
    print(f"{proc_info['name']} — {status}")
```

---

## `list_monitoring_threads()`

- **Signature**: jawm.Process.list_monitoring_threads()
- **Returns**: `list[dict]`

List all processes with active background monitoring threads.

Each process execution spawns a background monitoring thread that tracks the running subprocess or job. This method returns information about processes whose monitoring threads are still alive, which is useful for debugging or verifying that all processes have fully completed.

**Returned fields:**

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Process name |
| `hash` | `str` | Process hash |
| `manager` | `str` | Execution backend |
| `started_at` | `str` | Timestamp when execution started |
| `finished` | `bool` | Whether the process has finished |
| `thread_alive` | `bool` | Always `True` in the returned list (only active threads are included) |

**Example:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\nsleep 60")
p.execute()

active_threads = jawm.Process.list_monitoring_threads()
print(f"{len(active_threads)} monitoring thread(s) still active")
```

---

## `get_cls_values()`

- **Signature**: `jawm.Process.get_cls_values()`
- **Returns**: `dict`

Return a dictionary describing the current class-level state of `jawm.Process`.

This is useful for inspection and debugging, especially to verify what defaults, overrides, or CLI injections are currently active.

**Returned fields:**

| Field | Type | Description |
|---|---|---|
| `default_parameters` | `dict` | Current class-level defaults |
| `override_parameters` | `dict` | Current class-level overrides |
| `_cli_global_overrides` | `dict` | CLI-injected global overrides (populated by `jawm` CLI) |
| `_cli_process_overrides` | `dict` | CLI-injected process-specific overrides (populated by `jawm` CLI) |
| `parameter_types` | `dict` | Expected parameter types |
| `reserved_keys` | `set` | Internal reserved key names |
| `supported_managers` | `set` | Supported execution backends |
| `stop_future_event` | `bool` | Whether the stop flag is currently set |

**Example:**
```python
import jawm

jawm.Process.set_default(manager="local", retries=2)

state = jawm.Process.get_cls_values()
print(state["default_parameters"])
# {"manager": "local", "retries": 2}

print(state["stop_future_event"])
# False
```

---

## `get_cls_var()`

- **Signature**: `jawm.Process.get_cls_var(key=None, default=None)`
- **Returns**: `any` or `dict`

Get a class-level global `var` value or the full merged global `var` dictionary.

This method resolves `var` values from all class-level configuration sources in precedence order:

```text
default_parameters < YAML global < CLI overrides < override_parameters
```

This is useful for accessing global workflow variables that are defined at the class level, independent of any specific process instance.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `key` | `str` or `None` | `None` | If a string, return the resolved value for that key. If `None`, return the full merged `var` dictionary. |
| `default` | `any` | `None` | Value returned when the specified key is not found. |

**Example — get all class-level vars:**
```python
import jawm

jawm.Process.set_default(var={"fruit": "Apple", "count": "3"})

all_vars = jawm.Process.get_cls_var()
print(all_vars)
# {"fruit": "Apple", "count": "3"}
```

**Example — get a specific var:**
```python
fruit = jawm.Process.get_cls_var("fruit")
print(fruit)
# "Apple"
```

**Example — get with a fallback default:**
```python
color = jawm.Process.get_cls_var("color", default="red")
print(color)
# "red"
```

---

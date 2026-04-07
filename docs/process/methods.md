This page documents the instance methods of `jawm.Process`.

Instance methods are called on a specific `Process` object after it has been created. They operate on that individual process — executing it, inspecting its status, reading its logs, or creating modified copies.

```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\necho hi")
p.execute()
p.get_values()
```

The available instance methods can be grouped into the following categories:

- **Execution & lifecycle** — `execute()`, `clone()`, `is_valid()`
- **Configuration updates** — `update_params()`, `update_vars()`
- **Log & artifact readers** — `get_output()`, `get_error()`, `get_exitcode()`, `get_command()`, `get_script()`, `get_slurm()`, `get_id()`
- **Status checks** — `is_finished()`, `is_successful()`, `has_failed()`
- **Inspection** — `get_values()`, `get_var()`

For class-level methods that operate on all processes (such as `jawm.Process.wait()` or `jawm.Process.kill()`), see the [class-level methods](cls_methods.md) page.

---

## `execute()`

- **Returns**: `None`

Launch the process execution.

This is the primary method to run a process. It handles the full execution lifecycle including conditional execution, dependency resolution, script generation, and launching through the configured backend (`local`, `slurm`, or `kubernetes`).

By default, `execute()` returns immediately and the process runs in the background. Use `jawm.Process.wait()` or `p.is_finished()` to check when it has completed. If `parallel=False` is set on the process, `execute()` blocks until the process finishes.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `depends_on` | `str`, `list[str]`, or `None` | `None` | Upstream process names or hashes to wait for before executing. If provided, overrides the instance's existing `depends_on` value for this execution. |

**Execution flow:**

1. Checks the `when` condition — if `False`, the process is skipped and marked as finished.
2. Checks `resume` — if enabled and a matching successful previous run exists, skips execution.
3. Checks `jawm.Process.stop_future_event` — if set and `always_run` is not `True`, skips execution.
4. Waits for all dependencies listed in `depends_on` to finish.
5. If `allow_skipped_deps=False`, verifies that all dependencies completed successfully.
6. Launches the process through the configured manager.
7. On failure, logs the error and sets `jawm.Process.stop_future_event`.

**Example — basic execution:**
```python
import jawm

p = jawm.Process(
    name="hello",
    script="""#!/bin/bash
echo "Hello from jawm"
"""
)

p.execute()
jawm.Process.wait()
```

**Example — with dependency override:**
```python
import jawm

p1 = jawm.Process(name="step1", script="#!/bin/bash\necho step1")
p2 = jawm.Process(name="step2", script="#!/bin/bash\necho step2")

p1.execute()
p2.execute(depends_on=[p1.hash])

jawm.Process.wait()
```

**Example — sequential (blocking) execution:**
```python
import jawm

p = jawm.Process(
    name="blocking_step",
    parallel=False,
    script="""#!/bin/bash
echo "This blocks until done"
"""
)

p.execute()  # returns only after the process finishes
```

---

## `clone()`

- **Returns**: `jawm.Process`

Create a new `Process` instance by copying the current one with optional modifications.

`clone()` deep-copies the current process configuration, applies any provided overrides, and returns a new `Process` instance. The original process is not modified.

This is useful for creating variations of a process, such as running the same script with different variables or on a different backend.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `str` or `None` | `None` | Name for the cloned process. Defaults to the original process's name. |
| `param_file` | `str`, `list[str]`, or `None` | `None` | YAML parameter file(s) for the clone. Defaults to the original's `param_file`. |
| `**overrides` | | | Any process parameters to override in the cloned instance. |

**Example — basic clone:**
```python
import jawm

p1 = jawm.Process(
    name="align_sample1",
    var={"sample": "S01", "mk.output": "results/S01"},
    script="#!/bin/bash\necho hi"
)

p2 = p1.clone(
    name="align_sample2",
    var={"sample": "S02", "mk.output": "results/S02"}
)

p1.execute()
p2.execute()
```

**Example — clone with parameter override:**
```python
p_local = jawm.Process(
    name="analysis",
    manager="local",
    script_file="scripts/run.sh"
)

p_slurm = p_local.clone(
    name="analysis_slurm",
    manager="slurm",
    manager_slurm={"--partition": "batch", "--cpus-per-task": "8"}
)
```

_**Note**_: `clone()` preserves any modifications made to the original process after initialization (e.g. via `p.var["key"] = "value"`), not just the values provided at construction time.

---

## `is_valid()`

- **Returns**: `bool`

Validate the Process configuration.

Checks the process for common configuration issues such as missing required fields, unknown parameters, type mismatches, missing script files, invalid shebang lines, and unresolved placeholder variables.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `mode` | `str` | `"strict"` | Validation mode. `"basic"` fails only on errors. `"strict"` fails on both errors and warnings. |

**Checks performed:**

- `name` is present and is a string
- Either `script` or `script_file` is provided
- `manager` is a supported value
- `script_file` exists on disk (if provided)
- Script starts with a valid shebang line (`#!`)
- All `{{placeholder}}` variables in the script are defined in `var` or `var_file`
- Parameter types match expected types from `jawm.Process.parameter_types`
- No unrecognized parameter names

**Example:**
```python
import jawm

p = jawm.Process(
    name="example",
    script="""#!/bin/bash
echo "{{greeting}}"
""",
    var={"greeting": "Hello"}
)

if p.is_valid():
    p.execute()
else:
    print("Process configuration has issues")
```

**Example — basic mode (ignoring warnings):**
```python
p.is_valid(mode="basic")
```

---

## `update_params()`

- **Returns**: `None`

Update the Process instance's parameters from new YAML file(s) or directory.

Loads parameters from the provided YAML file(s) and merges them into the current process configuration. Existing values are overridden by the new values. Dict-like parameters (such as `var`, `env`, `manager_slurm`) are deep-merged.

The `param_file` reference is stored on the instance for traceability, and the cached base script is invalidated if script-related parameters changed.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `param_file` | `str` or `list[str]` | `None` | Path to a YAML file, multiple files, or a directory containing YAML files. |

**Example:**
```python
import jawm

p = jawm.Process(
    name="analysis",
    script_file="scripts/run.sh"
)

p.update_params("parameters/slurm.yaml")
p.execute()
```

**Example — multiple files:**
```python
p.update_params(["parameters/base.yaml", "parameters/override.yaml"])
```

---

## `update_vars()`

- **Returns**: `None`

Update the Process instance's variable placeholders from file(s) or directory.

Loads variables from the provided file(s) and merges them into the current `var` dictionary. New values take precedence over existing ones. Short aliases for `mk.*` and `map.*` keys are added automatically.

The `var_file` reference is stored on the instance for traceability, and the cached base script is invalidated so the updated variables are applied on the next execution.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `var_file` | `str` or `list[str]` | | Path to a YAML file, multiple files, or a directory containing variable files. |

**Example:**
```python
import jawm

p = jawm.Process(
    name="analysis",
    var={"sample": "S01"},
    script_file="scripts/run.sh"
)

# Load additional variables from file
p.update_vars("variables/extra_vars.yaml")
p.execute()
```

---

## `get_id()`

- **Returns**: `str` or `None`

Return the runtime identifier of the process.

Reads the content of the `.id` file from the process log directory. Depending on the execution backend, this is the local PID, Slurm job ID, or Kubernetes job name.

Since the `.id` file is written asynchronously after the process starts, this method retries for up to `max_wait` seconds.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_wait` | `int` or `float` | `3` | Maximum time in seconds to wait for the `.id` file to appear. |
| `interval` | `float` | `0.5` | Polling interval in seconds between retries. |

**Returns:** The runtime ID as a string, or `None` if unavailable within the wait period.

**Example:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\nsleep 60")
p.execute()
jawm.Process.wait([p.hash])

pid = p.get_id()
print(f"Process running with ID: {pid}")
```

---

## `get_output()`

- **Returns**: `str` or `None`

Return the content of the process standard output (`.output`) file.

Reads the full content of the `<name>.output` file from the process log directory.

**Returns:** The stdout content as a string, or `None` if the file does not exist or is not yet available.

**Example:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\necho hello")
p.execute()
jawm.Process.wait([p.hash])

print(p.get_output())
# "hello\n"
```

---

## `get_error()`

- **Returns**: `str` or `None`

Return the content of the process standard error (`.error`) file.

Reads the full content of the `<name>.error` file from the process log directory.

**Returns:** The stderr content as a string, or `None` if the file does not exist or is not yet available.

**Example:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\necho 'error message' >&2")
p.execute()
jawm.Process.wait([p.hash])

print(p.get_error())
# "error message\n"
```

---

## `get_exitcode()`

- **Returns**: `str` or `None`

Return the exit code of the process.

Reads the content of the `<name>.exitcode` file from the process log directory.

**Returns:** The exit code as a string (e.g. `"0"`, `"1"`), or `None` if the process has not yet finished or the file is not available.

_**Note**_: The return value is a string, not an integer. A successful process returns `"0"` or a string starting with `"0:"`.

**Example:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\nexit 0")
p.execute()
jawm.Process.wait([p.hash])

print(p.get_exitcode())
# "0"
```

---

## `get_command()`

- **Returns**: `str` or `None`

Return the launch command used to execute the process.

Reads the content of the `<name>.command` file from the process log directory. This contains the full command that jawm used to launch the process, including any container wrapping or manager-specific arguments.

**Returns:** The command as a string, or `None` if the file does not exist or is not yet available.

**Example:**
```python
import jawm

p = jawm.Process(
    name="step1",
    environment="docker",
    container="python:3.12",
    script="#!/usr/bin/env python3\nprint('hello')"
)
p.execute()
jawm.Process.wait([p.hash])

print(p.get_command())
```

---

## `get_script()`

- **Returns**: `str` or `None`

Return the generated script content for the process.

Reads the content of the `<name>.script` file from the process log directory. This is the final script after placeholder substitution and any modifications applied by jawm.

**Returns:** The script content as a string, or `None` if the file does not exist or is not yet available.

**Example:**
```python
import jawm

p = jawm.Process(
    name="step1",
    var={"greeting": "Hello"},
    script="""#!/bin/bash
echo "{{greeting}} from jawm"
"""
)
p.execute()
jawm.Process.wait([p.hash])

print(p.get_script())
# #!/bin/bash
# echo "Hello from jawm"
```

---

## `get_slurm()`

- **Returns**: `str` or `None`

Return the generated Slurm submission script for the process.

Reads the content of the `<name>.slurm` file from the process log directory. This file is only created when the process is executed with `manager="slurm"`.

**Returns:** The Slurm script content as a string, or `None` if the file does not exist (e.g. when using a non-Slurm manager).

**Example:**
```python
import jawm

p = jawm.Process(
    name="step1",
    manager="slurm",
    manager_slurm={"--partition": "batch", "--cpus-per-task": "4"},
    script="#!/bin/bash\necho hello"
)
p.execute()
jawm.Process.wait([p.hash])

print(p.get_slurm())
# #!/bin/bash
# #SBATCH --job-name=step1_...
# #SBATCH --partition=batch
# #SBATCH --cpus-per-task=4
# ...
```

---

## `is_finished()`

- **Returns**: `bool`

Check whether the process has finished execution.

Returns `True` if the process has completed (regardless of success or failure), or was skipped. Returns `False` if the process is still running or has not yet started.

**Example:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\nsleep 10")
p.execute()

print(p.is_finished())  # False (still running)

jawm.Process.wait([p.hash])
print(p.is_finished())  # True
```

---

## `is_successful()`

- **Returns**: `bool`

Check whether the process completed successfully.

Returns `True` only if the process has finished and its exit code is `0`. Returns `False` if the process is still running, was skipped without an exit code, or finished with a non-zero exit code.

**Example:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\nexit 0")
p.execute()
jawm.Process.wait([p.hash])

print(p.is_successful())  # True
```

**Example — checking after failure:**
```python
p = jawm.Process(name="failing", script="#!/bin/bash\nexit 1")
p.execute()
jawm.Process.wait([p.hash], allowed_exit="all")

print(p.is_successful())  # False
```

---

## `has_failed()`

- **Returns**: `bool`

Check whether the process finished with a non-zero exit code.

Returns `True` only if the process has finished and its exit code is not `0`. Returns `False` if the process is still running, was skipped without an exit code, or completed successfully.

_**Note**_: `has_failed()` and `is_successful()` are not always exact opposites. A process that was skipped or is still running returns `False` for both.

**Example:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\nexit 1")
p.execute()
jawm.Process.wait([p.hash], allowed_exit="all")

print(p.has_failed())    # True
print(p.is_successful()) # False
```

---

## `get_values()`

- **Returns**: `dict`

Return a dictionary of the current values of all parameters and reserved keys on the Process instance.

This includes both user-provided parameters (from `jawm.Process.parameter_types`) and internal runtime attributes (from `jawm.Process.reserved_keys`), providing a complete snapshot of the process state.

**Example:**
```python
import jawm

p = jawm.Process(
    name="step1",
    manager="local",
    retries=2,
    script="#!/bin/bash\necho hi"
)

values = p.get_values()
print(values["name"])       # "step1"
print(values["manager"])    # "local"
print(values["retries"])    # 2
print(values["hash"])       # "cb6bc9hopa" (generated)
print(values["log_path"])   # "/path/to/logs/step1_..."
```

---

## `get_var()`

- **Returns**: `any`

Return a single variable value from the process `var` dictionary.

Looks up the given key in the process's `var` dictionary and returns the value. If the key is not found, returns `default`.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `key` | `str` | | The variable name to look up. |
| `default` | `any` | `None` | Value to return if the key is not found. |

**Example:**
```python
import jawm

p = jawm.Process(
    name="step1",
    var={"sample": "S01", "mk.output": "results/S01"},
    script="#!/bin/bash\necho {{sample}}"
)

print(p.get_var("sample"))          # "S01"
print(p.get_var("mk.output"))      # "results/S01"
print(p.get_var("output"))          # "results/S01" (short alias)
print(p.get_var("missing", "N/A"))  # "N/A"
```

---

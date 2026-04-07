This page documents the class-level parameters of `jawm.Process`.

Unlike [instance parameters](parameters.md) which apply to a specific `Process` object, class-level parameters belong to the `jawm.Process` class itself and affect all processes in a workflow.

These are accessed through the class directly, for example `jawm.Process.default_parameters` or `jawm.Process.registry`.

Some of these parameters are intended for direct use in workflows, while others are managed internally by jawm and typically do not require user intervention. Each entry below indicates whether it is user-facing or internal.

---

## `default_parameters`

- **Category**: `class parameter`
- **Type**: `dict`
- **Default**: `{}`
- **Usage**: user-facing (through `jawm.Process.set_default()`)

Class-level fallback parameters applied with the **lowest priority** in the configuration precedence.

`jawm.Process.default_parameters` provides baseline values for all `Process` instances. Any value defined here can be overridden by YAML configuration, Python arguments, CLI overrides, or `override_parameters`.

This is useful for setting shared defaults across all processes in a workflow, such as a common `logs_directory`, `manager`, or `retries` value.

_**Note**_: Users should not modify `jawm.Process.default_parameters` directly. Use `jawm.Process.set_default()` instead, which handles filtering of reserved keys and updates the dictionary safely.

**Example — setting defaults with `set_default()`:**
```python
import jawm

jawm.Process.set_default(
    manager="local",
    logs_directory="logs",
    retries=1
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
# p.manager will be "local"
# p.logs_directory will be "logs"
# p.retries will be 1
```

**Overriding a default for a specific process:**
```python
p = jawm.Process(
    name="example",
    script="""#!/bin/bash
echo "Hello"
""",
    retries=3  # overrides the default of 1
)
```

---

## `override_parameters`

- **Category**: `class parameter`
- **Type**: `dict`
- **Default**: `{}`
- **Usage**: user-facing (through `jawm.Process.set_override()`)

Class-level parameters applied with the **highest priority** in the configuration precedence.

`jawm.Process.override_parameters` forces specific values for all `Process` instances, overriding YAML configuration, Python arguments, and CLI overrides. Only reserved keys and `name` are excluded.

This is useful when you need to enforce a specific configuration regardless of what individual processes or YAML files define.

_**Note**_: Users should not modify `jawm.Process.override_parameters` directly. Use `jawm.Process.set_override()` instead, which handles filtering of reserved keys and updates the dictionary safely.

**Example — setting overrides with `set_override()`:**
```python
import jawm

jawm.Process.set_override(
    manager="slurm",
    environment="apptainer"
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
# p.manager will be "slurm" (override wins)
```

---

## `stop_future_event`

- **Category**: `class parameter`
- **Type**: `threading.Event`
- **Usage**: managed internally (use `jawm.Process.reset_stop()` to clear)

A shared stop flag that is triggered when a process fails.

When a process fails during execution, jawm sets `jawm.Process.stop_future_event`. Before launching, each process checks this flag and skips execution if it is set (unless `always_run=True` is configured on that process).

This provides a fail-fast mechanism for workflows: if one process fails, downstream processes that have not yet started are automatically skipped.

_**Note**_: `jawm.Process.stop_future_event` is set and checked internally by jawm during process execution. Users do not need to set it manually. To clear it after a failure and allow processes to run again, use `jawm.Process.reset_stop()`.

**Example — checking the stop flag:**
```python
import jawm

jawm.Process.stop_future_event.is_set()  # False by default
```

**Example — clearing the stop flag after a failure:**
```python
jawm.Process.reset_stop()
```

**Example — a process that runs despite the stop flag:**
```python
p = jawm.Process(
    name="cleanup",
    always_run=True,
    script="""#!/bin/bash
echo "This runs even if other processes failed"
"""
)
```

---

## `registry`

- **Category**: `class parameter`
- **Type**: `dict`
- **Default**: `{}`
- **Usage**: managed internally (read-only access for users)

A class-level dictionary that stores all `Process` instances, indexed by both `name` and `hash`.

When a `Process` is created, jawm automatically registers it in `jawm.Process.registry` under both its `name` and its generated `hash`. This allows jawm to look up processes by either identifier for dependency resolution, waiting, killing, and status queries.

_**Note**_: `jawm.Process.registry` is managed internally by jawm. Users do not need to modify it. It can be read for inspection, and `jawm.Process.reset_runtime()` can be used to clear it between workflow runs in interactive environments.

**Example — looking up a process:**
```python
import jawm

p = jawm.Process(name="step1", script="#!/bin/bash\necho hi")

# Look up by name
jawm.Process.registry["step1"]

# Look up by hash
jawm.Process.registry[p.hash]
```

**Example — listing all registered processes ():**
```python
for proc in set(jawm.Process.registry.values()):
    print(proc.name, proc.hash)
```

_**Note**_: Since each process is registered under both its `name` and `hash`, iterating over `jawm.Process.registry.items()` will yield two entries per process. To get unique processes, iterate over `set(jawm.Process.registry.values())`.

---

## `parameter_types`

- **Category**: `class parameter`
- **Type**: `dict`
- **Usage**: internal (can be read for reference)

A dictionary that defines the expected type for each recognized Process parameter.

jawm uses `jawm.Process.parameter_types` internally during validation to check that parameter values match their expected types. Each key is a parameter name and the value is the expected Python type (or a tuple of types when multiple types are accepted).

_**Note**_: This parameter is handled internally by jawm for validation purposes. Users do not need to modify it, but it can be useful as a reference to see what parameters are available and what types they expect.

**Example — inspecting parameter types:**
```python
import jawm

print(jawm.Process.parameter_types["manager"])
# <class 'str'>

print(jawm.Process.parameter_types["retries"])
# <class 'int'>

print(jawm.Process.parameter_types["param_file"])
# (<class 'str'>, <class 'list'>)
```

---

## `reserved_keys`

- **Category**: `class parameter`
- **Type**: `set`
- **Usage**: internal (can be read for reference)

A set of internal key names reserved by jawm for runtime bookkeeping.

jawm uses `jawm.Process.reserved_keys` internally to protect runtime attributes from being overwritten by user configuration. Reserved keys are excluded from `jawm.Process.set_default()`, `jawm.Process.set_override()`, `jawm.Process.update()`, process cloning, and YAML parameter merging.

These include internal attributes such as `hash`, `log_path`, `finished_event`, `runtime_id`, `execution_start_at`, and others that jawm manages automatically during the process lifecycle.

_**Note**_: This parameter is handled internally by jawm. Users do not need to modify it, but it can be useful to check whether a given key name is reserved.

**Example — inspecting reserved keys:**
```python
import jawm

print(jawm.Process.reserved_keys)
# {"scope", "params", "hash", "date_time", "log_path", ...}
```

---

## `supported_managers`

- **Category**: `class parameter`
- **Type**: `set`
- **Default**: `{"local", "slurm", "kubernetes"}`
- **Usage**: internal (can be read for reference)

The set of execution backends supported by jawm.

jawm uses `jawm.Process.supported_managers` internally to validate the `manager` parameter when a process is configured. If a `manager` value is not in `supported_managers`, jawm may raise a validation warning or error depending on the validation mode.

_**Note**_: This parameter is handled internally by jawm. Users do not need to modify it, but it can be read to check which execution backends are available.

**Example — inspecting supported managers:**
```python
import jawm

print(jawm.Process.supported_managers)
# {"local", "slurm", "kubernetes"}
```

---

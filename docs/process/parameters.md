This page documents parameters associated with `jawm.Process` instance.

There are two types of parameters in jawm Processs:

- **Process instance parameters** — applied to a specific `Process` object when it is created.
- **Class-level parameters** — applied to the `jawm.Process` class itself and affect all processes in the workflow.

Instance parameters can be provided in multiple ways:

- directly in Python when creating a `Process`
- through YAML configuration files
- through CLI overrides

---

## `name`

- **Category**: `parameter`
- **Type**: `str`
- **Required**: `True`

Name of the process.

This is the user provided primary identifier of a `Process` and is used throughout jawm to identify and track process executions, as well as logging, dependency handling, run directory naming, and generated files.

_**Note**_: Unique process name is preferred for easier identification and to avoid conflicts. Each process must have a `name`. 

**Example:**
```python
name="my_process"
```

While creating a `jawm.Process`, `name` needs to be defined in the Python code. In YAML, `name` is required to define other parameters in `- scope: process`.

**YAML Example:**
```yaml
name: "my_process"
```

---

## `hash`

- **Category**: `parameter`
- **Type**: `str` *(read-only)*

A generated 10-character identifier used to track executions: the first 6 characters come from a SHA-256 of the current parameters; the last 4 are random (lowercase letters/digits) to avoid collisions. Generated at Process initialization; not user-supplied.

_**Note**_: `hash` is an internal/reserved key and should not be set manually.

**Example log usage:**
```text
hello_world|cb6bc9hopa
```

`hash` of each instance can be used in multiple important places such as `depends_on`, `Process.wait()`

**Example `depends_on` usage:**
```python
p1 = jamw.Process(name="p1", ...)
p2 = jawm.Process(name="p2", depends_on=[p1.hash], ...)
# or use inside `execute` to have the same depends_on outcome
# p2.execute(p1.hash)
```

**Example `jawm.Process.wait()` usage:**
```python
p1 = jamw.Process(name="p1", ...)
p2 = jawm.Process(name="p2", ...)
p1.execute()
jawm.Process.wait([p1.hash])        # to wait until p1 execution is finished
p2.execute()
```

---

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

## `param_file`

- **Category**: `parameter`
- **Type**: `str` or `list[str]`

Path to a YAML parameter file, multiple YAML parameter files, or a directory containing YAML files.

`param_file` is used to load process configuration from YAML. These files can define both global parameters and process-specific parameters using `scope: global` and `scope: process`.

When multiple files are provided, they are loaded and merged in order. A directory can also be provided, in which case jawm loads YAML files from that directory.

_**Note**_: `param_file` can be set in Python, but it is especially important when passed through the CLI using `-p`, because that changes precedence behavior and gives YAML higher priority than normal Python instance arguments.

**Example:**
```python
param_file="parameters/params.yaml"
```

**Multiple files Example:**
```python
param_file=["parameters/base.yaml", "parameters/override.yaml"]
```

**Directory Example:**
```python
param_file="parameters"
```

**CLI Example:**
```bash
jawm module.py -p parameters/params.yaml
```

**CLI Example with multiple files:**
```bash
jawm module.py -p parameters/base.yaml parameters/override.yaml
```

---

## `script`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `#!/bin/bash`

Inline script content to be executed by the `Process`.

If `script` is provided, jawm uses it as the main script content for the process. The script requires start with a valid shebang line such as `#!/bin/bash` or `#!/usr/bin/env python3`.

_**Note**_: The **script requires to start with a valid shebang line** such as `#!/bin/bash` or `#!/usr/bin/env python3`.

**Example:**
```python
script="""#!/usr/bin/env python3
for fruit in ["Apple", "Banana", "Ananas"]:
    print(f"Fruit: {fruit}")
"""
```

**YAML Example:**
```yaml
script: |
  #!/usr/bin/env python3
  for fruit in ["Apple", "Banana", "Ananas"]:
      print(f"Fruit: {fruit}")
```

**Common shebang examples:**

```bash
#!/bin/bash
```

```bash
#!/usr/bin/env bash
```

```python
#!/usr/bin/env python3
```

```r
#!/usr/bin/env Rscript
```

```bash
#!/usr/bin/env sh
```

The shebang defines which interpreter should execute the script. Using `/usr/bin/env` is generally preferred because it resolves the interpreter from the system `PATH`, making scripts more portable across environments.

---
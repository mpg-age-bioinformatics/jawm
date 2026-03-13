# Process Configuration

A `Process` can be configured using several mechanisms:

1. **YAML configuration files**
2. **Python keyword arguments**
3. **Explicit Python arguments**
4. **CLI overrides**
5. **Class default parameters**

These configuration layers are merged with a defined **precedence order**.

---

# Parameter Precedence

jawm supports flexible configuration through multiple layers.  
When parameters are defined in multiple places, **higher-precedence values override lower-precedence ones**.

### Standard precedence (low to high)

```text
default_parameters
< YAML global
< YAML process
< kwargs
< python_args
< (CLI -p) YAML global
< (CLI -p) YAML process
< cli injected override (--global)
< cli injected override (--process)
< override_parameters
```

This allows workflows to be configured in a structured way while still supporting runtime overrides.

---

# Internal Precedence Logic

The parameter precedence changes slightly depending on whether a YAML parameter file is provided through the CLI using `-p`.

## Normal Usage

When no CLI parameter file override is used:

```text
default_parameters
< YAML global
< YAML process
< kwargs
< explicit_args
< cli injected override (--global)
< cli injected override (--process)
< override_parameters
```

In this mode, **Python arguments override YAML parameters**.

Internally, the precedence layers are applied as:

---

## CLI-driven Usage

When a parameter file is supplied through the CLI with `-p`, jawm assumes the workflow is **configuration-driven**, so **YAML overrides Python arguments**.

```text
default_parameters
< kwargs
< explicit_args
< YAML global
< YAML process
< cli injected override (--global)
< cli injected override (--process)
< override_parameters
```

---

# Ways to Configure a Process

## 1. Python Arguments

The most common method is to provide parameters directly:

```python
import jawm

p = jawm.Process(
    name="example",
    script="""#!/bin/bash
echo "Hello"
""",
    manager="local",
    logs_directory="custom_path"
)
```

---

## 2. YAML Configuration

Processes can also read configuration from YAML files.

Example of a global YAML block:

```yaml
- scope: global
  manager: local
  logs_directory: custom_path
```

Global scoped parameters would be applied to all the Processes.

Example of a process-specific YAML block:

```yaml
- scope: process
  name: "example*"
  manager: local
  logs_directory: custom_path
```

While defining `- scope: process`, `name` is required as it chooses Process by name. `name` accepts wildcard and list values, so the parameters can be applied in specific Processes.
Process specific paramters would overwrite global parameters.

---

## 3. CLI Overrides

Parameters can also be overridden directly from the CLI.

Example:

```bash
jawm run workflow.py --process.example.manager=local
```

Global override example:

```bash
jawm run workflow.py --global.retry=3
```

---
# Runtime Configuration

jawm provides multiple complementary configuration mechanisms that control how workflows behave at runtime — without modifying the workflow code itself.

---

### YAML Parameter Files

YAML parameter files define **process-level configuration** such as execution backend, container image, resource requests, environment variables, and any other Process parameter.

YAML files are typically passed via the CLI:

```bash
jawm workflow.py -p params.yaml
```

Or loaded directly in Python using [param_file parameter](../process/parameters.md/#param_file)

#### Scopes

A jawm YAML file is a list of entries, each with a `scope` that determines how it is applied:

**`global`**

Parameters applied to **all** processes in the workflow.

```yaml
- scope: global
  manager: local
  logs_directory: ./logs
```

**`process`**

Parameters applied to **specific processes** by name. The `name` field is required and supports wildcards and lists, so a single block can target multiple processes.

```yaml
- scope: process
  name: "align_*"
  manager: slurm
```

Process-scoped parameters override global-scoped parameters. You can learn more about [Process configuration & predence here](../process/conf_precedence.md)

**`hash`**

A special scope used by the CLI to define a **content hash policy** for the workflow run. It specifies which files to hash, optional filters, and an optional reference hash for validation.

```yaml
- scope: hash
  include:
    - main.py
    - scripts/**/*.sh
  allowed_extensions: [py, sh]
  exclude_dirs: [__pycache__]
```

This scope is only relevant when running via the `jawm` CLI.

**`includes`**

Any YAML entry can use `includes` to **import entries from other YAML files**. Include paths are resolved relative to the file that contains the directive. jawm detects and prevents circular includes.

```yaml
- includes: shared/base_config.yaml
- includes:
    - slurm_defaults.yaml
    - docker_settings.yaml

- scope: process
  name: "my_step"
  cpus: 16
```

This allows reusable, modular configuration across workflows.

See [YAML Config](yaml.md) for full syntax and examples.

---

### JAWM Environment Variables

`JAWM_*` environment variables control **system-level behavior** such as concurrency limits, polling intervals, timeouts, logging preferences, and backend-specific tuning.

These variables are not typically set in workflow code. Instead, they are configured in the shell environment or in the `~/.jawm/config` file:

```bash
# Shell
export JAWM_MAX_PROCESS=50

# Or in ~/.jawm/config
JAWM_MAX_PROCESS=50
JAWM_LOG_EMOJI=0
```

See [JAWM Config](config.md) for the full variable reference.

---

### How They Relate

| Aspect | YAML Parameter Files | JAWM Environment Variables |
|---|---|---|
| **What they configure** | Process parameters (manager, image, resources, etc.) | System behavior (concurrency, timeouts, polling, etc.) |
| **Scope** | Per-process or global (within a workflow) | Global (across all workflows) |
| **Where they live** | `.yaml` files, passed via `-p` or `parameters_file` | Shell environment or `~/.jawm/config` |
| **Precedence role** | Part of the 8-level [parameter precedence](../process/conf_precedence.md) chain | Read directly by jawm internals at runtime |

Both mechanisms are optional. jawm works out of the box with sensible defaults.

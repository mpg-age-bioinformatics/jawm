# Your First Process

In jawm, a workflow is built from one or more **Process** objects.  
Each `Process` represents a single executable step such as running a script, commands, or containerized task.

This section walks through creating and running your first simple process.

---

## Minimal Example

Create a Python file, for example `hello.py`:

```python
import jawm

p = jawm.Process(
    name="hello_world",
    script="""#!/bin/bash
echo "Hello from jawm"
"""
)

p.execute()
```

You can run it as a python script or with `jawm` cli command (which provides more features and controls):

```bash
python hello.py
```

or

```bash
jawm hello.py
```

You should see logs (example below) printed in the terminal and a log directory (`logs`) created for the process.

```bash
[2026-03-24 15:08:37] - INFO - hello_world|cb6bc9nhv8 :: Launching process hello_world using Local executor.
[2026-03-24 15:08:37] - INFO - hello_world|cb6bc9nhv8 :: Log folder for process hello_world: /jawm/logs/hello_world_20260324_150837_cb6bc9nhv8
[2026-03-24 15:08:37] - INFO - hello_world|cb6bc9nhv8 :: Preparing base script for process hello_world
[2026-03-24 15:08:37] - INFO - hello_world|cb6bc9nhv8 :: Process hello_world started with PID: 41145
[2026-03-24 15:08:37] - INFO - hello_world|cb6bc9nhv8 :: Process hello_world (PID: 41145) is still running...
[2026-03-24 15:08:42] - INFO - hello_world|cb6bc9nhv8 :: Process hello_world completed with exit code: 0
```

---

## What Happens Under the Hood

When you call:

```python
p.execute()
```

jawm performs primarily the following steps:

1. Resolves parameters and configuration
2. Prepares the execution environment
3. Generates the execution script
4. Launches the process using the selected backend (default: `local`)
5. Stores logs and execution artifacts

---

## Process Logs

After execution, jawm creates a log directory under:

```text
<project_directory>/logs/
```

Each run generates a unique folder:

```text
hello_world_<timestamp>_<hash>
```

Inside this folder, you will find files and artifacts such as:

```text
hello_world.script
hello_world.command
hello_world.output
hello_world.error
hello_world.id
hello_world.exitcode
```

These files help you debug, inspect, and reproduce the process execution.

---

## Using Python Instead of Bash

You can also write Python scripts directly:

```python
import jawm

p = jawm.Process(
    name="python_example",
    script="""#!/usr/bin/env python3
print("Hello from Python inside jawm")
"""
)

p.execute()
```

jawm will detect the interpreter from the shebang line.

---

## Adding Variables

You can make your process dynamic using `var`:

```python
import jawm

p = jawm.Process(
    name="variable_example",
    var={"name": "jawm"},
    script="""#!/usr/bin/env python3
print("Hello {{name}}")
"""
)

p.execute()
```

This will print:

```text
Hello jawm
```

---

## Running via jawm CLI

Instead of running your script with Python, it is recommended to use the jawm CLI:

```bash
jawm hello.py
```

This enables additional features such as:

- parameter overrides
- logging of the CLI run
- workflow-level controls

---
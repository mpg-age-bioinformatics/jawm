# JAWM Process: How-To Guide

This document provides guidance on using diffeent features and internal behavior of the `Process` class in the JAWM workflow manager.

---

### 🔧 How to Set Global Monitoring Directory

**Description:**  
A global JAWM monitoring directory can be set using the `JAWM_MONITORING_DIRECTORY` environment variable.

**Note:**  
This directory stores tracking info of different jobs (Job ID, log location, current state, etc.). It is useful for visualization or external job monitoring tools.

**Example:**

```bash
# Set via shell (add to ~/.bashrc or ~/.zshrc for persistence)
export JAWM_MONITORING_DIRECTORY="/path/monitoring"
```

```python
# Set in Python script before importing or using JAWM
import os
os.environ["JAWM_MONITORING_DIRECTORY"] = "/path/monitoring"
```

---

### 📦 How to Get Process Values

**Description:**  
Any value set or resolved inside a `Process` class instance can be accessed directly.

**Example:**

```python
# After Process is created:
print(process_hw.name)
print(process_hw.hash)
print(process_hw.log_path)
```

---

### 📄 How to Use Global Values in YAML

**Description:**  
You can define default values for all processes using the `scope: global` section in the YAML file.

**Note:**  
These values can be overridden by process-specific values or inline arguments in Python.

**YAML Example:**

```yaml
- scope: global
  retries: 3
  monitoring_directory: "monitoring"
  logs_directory: "logs_slurm"
  manager: "slurm"
  manager_slurm: {"partition": "cluster", "mem": "2GB"}
```

---

### 🧩 How to Use Process-Specific Values in YAML

**Description:**  
You can define values for a specific process using `scope: process` and the matching `name`.

**Note:**  
These override any global values for that specific process.

**YAML Example:**

```yaml
- scope: process
  name: "process_name"
  environment: "apptainer"
  container: "/images/python.sif"
```

---

### ⚖️ Parameter Priority in Process

**Description:**  
Values for a process have different priority levels based on how they are passed.

**Note:**  
**Priority order (lowest to highest):**
1. Global YAML values (`scope: global`)
2. Process-specific YAML values (`scope: process`)
3. Inline keyword arguments in Python

This structure allows flexible configuration with sensible defaults and overrides.

**Example:**

```yaml
# parameters.yaml
- scope: global
  retries: 1

- scope: process
  name: "my_task"
  retries: 2
```

```python
proc = Process(
    name="my_task",
    param_file="parameters.yaml",
    retries=3
)
# Final retries = 3 (highest priority: inline argument)
```

---

### 🛠️ How to Set Logging Level

**Description:**  
Set logging level across all processes using `set_log_level`.

**Note:**  
Use `INFO` for typical usage (default). Levels like `DEBUG` or `ERROR` are also supported.

**Default:** `INFO`

**Example:**

```python
from jawm import Process
Process.set_log_level("INFO")
```

---

### 🧹 How to Reset stop_future_event

**Description:**  
The `stop_future_event` is a class-level flag to signal that a failure occurred, and future processes should be skipped.

**Note:**  
Use `.clear()` to allow running new processes after one fails. Useful in Jupyter notebooks or retries.

**Example:**

```python
from jawm import Process
Process.stop_future_event.clear()
```

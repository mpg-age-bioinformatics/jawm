"""
jawm - Just Another Workflow Manager

Why jawm?
---------
jawm is a lightweight, flexible, and Python-native workflow manager designed to
orchestrate reproducible, dependency-aware processes in both local and HPC environments.

✔ Python-based — fully written in Python, easy to extend and embed in any project.  
✔ Framework-agnostic — no external runtime or framework dependency.  
✔ Storage-agnostic — works seamlessly with local or mounted storage (NFS, object, etc.).  
✔ Notebook-ready — designed with data scientists in mind for interactive use.

Core Features
-------------
- Define processes with conditional execution and dependency chains.
- Support for local, Slurm, Docker, and Apptainer execution.
- Retry logic, error handling, and custom environment variables.
- Integrated monitoring and logging for observability and debugging.
- YAML-based parameterization for easy config reuse.

Public Interface
----------------
- `Process`: Define and run a step in your workflow.
- `jhelp()`: Get help for any parameter, example, or usage how-to.

Quickstart Example (inline script):
-----------------------------------
>>> from jawm import Process
>>> process_hw = Process(
...     name="hello_world",
...     script=\"\"\"#!/bin/bash
echo 'Hello World!'
\"\"\"
... )
>>> process_hw.execute()

Alternative (YAML-based config):
--------------------------------
process_hw = Process(name="hello_world", param_file="parameters/example.yaml")`
process_hw.execute()

Documentation:
--------------
Use `jhelp()` or visit https://github.com/mpg-age-bioinformatics/jawm for details.
"""

from .process import Process
from .docs import jhelp
from . import utils
import logging
logging.getLogger("jawm").addHandler(logging.NullHandler())

__all__ = ["Process", "jhelp", "utils"]

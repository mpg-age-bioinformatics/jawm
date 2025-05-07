# ---
# jupyter:
#   jupytext:
#     cell_markers: '{{{,}}}'
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.6
#   kernelspec:
#     display_name: Python 3.12.6
#     language: python
#     name: py3.12.6
# ---

# {{{
import os
os.environ['JAWM_MONITORING_DIRECTORY'] = 'monitoring'

# For development
# sys.path.append(os.path.abspath(os.path.join(os.path.abspath(os.getcwd()), '..')))

from jawm import Process
# }}}

### Hello World example
process_hw = Process(
    name="hello_world",
    script="""#!/bin/bash
echo 'Starting process...'
# sleep 15
echo 'Hello, World!' > output.txt
cat output.txt
"""
)

process_hw.execute()

print(f"Process Name: {process_hw.name}")
print(f"Log Path: {process_hw.log_path}")

### Python example
process_python = Process(
    name="python_example",
    script="""#!/usr/bin/env python3
print("Hello from Python")
print("2 + 2 =", 2 + 2)
""",
    retries=3
)

process_python.execute()

print(f"Log Path: {process_python.log_path}")

## R example
process_r = Process(
    name="r_example",
    script="""#!/usr/bin/env Rscript
cat("Hello from R\n")
print(2 + 2)
"""
)

process_r.execute()

print(f"Log Path: {process_r.log_path}")

# Run with script parameters
process_file = Process(
    name="python_file",
    script_file="scripts/hello.py",
    script_parameters={
        "APPNAME": "JAWM",
        "BYEMSG": "GOOD BYE!",
        "FRUITLIST": "['Apple', 'Banana', 'Orange']"
    }
)

process_file.execute()

print(f"Log Path: {process_file.log_path}")

# Run with script and parameters file
process_params = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc"
)

process_params.execute()

print(f"Log Path: {process_params.log_path}")

process_skip = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc",
    when=False
)

process_skip.execute()

# Run from paramters
process_c = Process(name="process_C", param_file=["parameters/metal.yaml", "parameters/metal2.yaml"])

process_c.execute()

print(f"Log Path: {process_c.log_path}")

# Run python with yaml parameter
process_py1 = Process(name="process_py1", param_file="parameters/python_example.yaml")
process_py2 = Process(name="process_py2", param_file="parameters/python_example.yaml")

process_py1.execute()

process_py2.execute()

print(f"Log Path for {process_py1.name}: {process_py1.log_path}")
print(f"Log Path for {process_py2.name}: {process_py2.log_path}")

# {{{
# Run with dependency
process_c = Process(name="process_C", param_file=["parameters/metal.yaml", "parameters/metal.yaml"])
process_c.execute()

process_a = Process(name="process_A", param_file="parameters/metal.yaml")
process_a.execute()

process_b = Process(name="process_B", param_file="parameters/metal.yaml")
process_b.execute()
# }}}

print(f"Log Path for {process_a.name}: {process_a.log_path}")
print(f"Log Path for {process_b.name}: {process_b.log_path}")
print(f"Log Path for {process_c.name}: {process_c.log_path}")

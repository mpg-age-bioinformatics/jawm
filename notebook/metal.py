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
#     display_name: Python 3.10.8
#     language: python
#     name: py3.10.8
# ---

# {{{
import sys
import os
import logging
import time
from jawm import Process

logging.basicConfig(level=logging.INFO)
os.environ['JAWM_MONITORING_DIRECTORY'] = 'monitoring'
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

output = process_hw.execute()

print(f"Process/Job ID: {output}")
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

output = process_python.execute()

print(f"Process/Job ID: {output}")
print(f"Log Path: {process_python.log_path}")

## R example
process_r = Process(
    name="r_example",
    script="""#!/usr/bin/env Rscript
cat("Hello from R\n")
print(2 + 2)
"""
)

output = process_r.execute()

print(f"Process/Job ID: {output}")
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

output = process_file.execute()

print(f"Process/Job ID: {output}")
print(f"Log Path: {process_file.log_path}")

# Run with script and parameters file
process_params = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc"
)

output = process_params.execute()

print(f"Process/Job ID: {output}")
print(f"Log Path: {process_params.log_path}")

process_skip = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc",
    when=False
)

output = process_skip.execute()

# Run from paramters
process_c = Process(name="process_C", param_file=["parameters/metal.yaml", "parameters/metal2.yaml"])

output = process_c.execute()

print(f"Process/Job ID: {output}")
print(f"Log Path: {process_c.log_path}")

# {{{
# Run with dependency
process_c = Process(name="process_C", param_file=["parameters/metal.yaml", "parameters/metal.yaml"])
output_c = process_c.execute()

process_a = Process(name="process_A", param_file="parameters/metal.yaml")
output_a = process_a.execute()

process_b = Process(name="process_B", param_file="parameters/metal.yaml")
output_b = process_b.execute()
# }}}

print(f"Process/Job ID: {output_a}")
print(f"Log Path: {process_a.log_path}")
print(f"Process/Job ID: {output_b}")
print(f"Log Path: {process_b.log_path}")
print(f"Process/Job ID: {output_c}")
print(f"Log Path: {process_c.log_path}")



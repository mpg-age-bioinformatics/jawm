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
echo 'Hello World from Slurm!' > output.txt
cat output.txt
""",
    manager="slurm",
    manager_slurm={"partition":"dedicated"},
    logs_directory="logs_slurm"
)

# Get any paramters
process_hw.logs_directory

output = process_hw.execute()

print(f"Process/Job ID: {output}")
print(f"Log Path: {process_hw.log_path}")

### Hello World failed example
process_hw = Process(
    name="hello_world",
    script="""#!/bin/bash
echo 'Hello World Failed!' > output.txt
echoooooo 'ENding process...'
""",
    manager="slurm",
    manager_slurm={"partition":"dedicated", "mem":"1GB"},
    logs_directory="logs_slurm"
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
    retries=3,
    manager="slurm",
    manager_slurm={"partition":"dedicated", "mem":"1GB"},
    logs_directory="logs_slurm"
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
""",
    retries=3,
    manager="slurm",
    manager_slurm={"partition":"cluster", "mem":"2GB"},
    logs_directory="logs_slurm"
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
    },
    retries=3,
    manager="slurm",
    manager_slurm={"partition":"cluster", "mem":"2GB"},
    logs_directory="logs_slurm"
)

# Check the provided params
process_file.params

output = process_file.execute()

print(f"Process/Job ID: {output}")
print(f"Log Path: {process_file.log_path}")

# Run with script and parameters file
process_params = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc",
    manager="slurm",
    manager_slurm={"partition":"cluster", "mem":"2GB"},
    logs_directory="logs_slurm"
)

output = process_params.execute()

print(f"Process/Job ID: {output}")
print(f"Log Path: {process_params.log_path}")

process_skip = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc",
    when=False,
    manager="slurm",
    manager_slurm={"partition":"cluster", "mem":"2GB"},
    logs_directory="logs_slurm"
)

output = process_skip.execute()

print(f"Process/Job ID: {output}")

# Run from paramters
process_c = Process(name="process_C", param_file=["parameters/slurm.yaml", "parameters/slurm2.yaml"])

output = process_c.execute()

print(f"Process/Job ID: {output}")
print(f"Log Path: {process_c.log_path}")

# {{{
# Run with dependency
process_c = Process(name="process_C", param_file=["parameters/slurm.yaml", "parameters/slurm2.yaml"])
output_c = process_c.execute()

process_a = Process(name="process_A", param_file="parameters/slurm.yaml")
output_a = process_a.execute()

process_b = Process(name="process_B", param_file="parameters/slurm.yaml")
output_b = process_b.execute()
# }}}

print(f"Process/Job ID: {output_a}")
print(f"Log Path: {process_a.log_path}")
print(f"Process/Job ID: {output_b}")
print(f"Log Path: {process_b.log_path}")
print(f"Process/Job ID: {output_c}")
print(f"Log Path: {process_c.log_path}")

# Run with apptainer container
process_apptainer = Process(
    name="slurm_apptainer",
    script="""#!/bin/bash
echo $HOSTNAME
echo $MY_VAR
""",
    environment='apptainer',
    container="/nexus/posix0/MAGE-flaski/service/images/python.sif",
    # environment_apptainer={
    #     "bind": ["/path/abc/:/abc/", "/path/def/:/def/"],
    #     "home": "/path/home"
    # },
    env={
        "MY_VAR": "APP_Value",
        "ANOTHER_VAR": "ANOTHER_VAR"
    },
    manager="slurm",
    manager_slurm={"partition":"dedicated", "mem":"4G"},
    logs_directory="logs_slurm"
)

output = process_apptainer.execute()

print(f"Process/Job ID: {process_apptainer}")
print(f"Log Path: {process_apptainer.log_path}")

# Run with singularity container from parameter file
singularity_params = Process(name="singularity_params", param_file=["parameters/slurm.yaml", "parameters/slurm2.yaml"])
output = singularity_params.execute()

print(f"Process/Job ID: {singularity_params}")
print(f"Log Path: {singularity_params.log_path}")



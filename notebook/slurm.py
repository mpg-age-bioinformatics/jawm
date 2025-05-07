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
# import sys
# sys.path.append(os.path.abspath(os.path.join(os.path.abspath(os.getcwd()), '..')))

from jawm import Process
# }}}

### Hello World example
process_hw = Process(
    name="hello_world",
    script="""#!/bin/bash
echo 'Starting process...'
echo 'Hello World from Slurm!' > output_slurm.txt
cat output_slurm.txt
""",
    manager="slurm",
    manager_slurm={"partition":"dedicated"},
    logs_directory="logs_slurm"
)

# Get any paramters
process_hw.logs_directory

process_hw.execute()

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

process_hw.execute()

print(f"Log Path: {process_hw.log_path}")

# Reset stop_future_event to execute in the same script neglecting the last error
Process.stop_future_event.clear()

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

process_python.execute()

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

process_r.execute()

print(f"Log Path: {process_r.log_path}")
print(f"Error Summary Log: {process_r.error_summary_file}")

# process_r failed due to the absence of R in the system
# Error can be checked easily from the `error_summary_file` or `log_path`
# Got error "Error: /usr/bin/env: ‘Rscript’: No such file or directory"
Process.stop_future_event.clear()

## R example
process_r_apptainer = Process(
    name="r_example",
    script="""#!/usr/bin/env Rscript
cat("Hello from R\n")
print(2 + 2)
""",
    retries=3,
    manager="slurm",
    manager_slurm={"partition":"cluster", "mem":"2GB"},
    logs_directory="logs_slurm",
    environment='apptainer',
    container="/nexus/posix0/MAGE-flaski/service/images/posit-latest.sif",    
)

process_r_apptainer.execute()

print(f"Log Path: {process_r_apptainer.log_path}")

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

process_file.execute()

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

process_params.execute()

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

process_skip.execute()

print(f"Log Path: {process_skip.log_path}")

# Run from paramters
process_c = Process(name="process_C", param_file=["parameters/slurm.yaml", "parameters/slurm2.yaml"])

process_c.execute()

print(f"Log Path: {process_c.log_path}")

# {{{
# Run with dependency
process_c = Process(name="process_C", param_file=["parameters/slurm.yaml", "parameters/slurm2.yaml"])
process_c.execute()

process_a = Process(name="process_A", param_file="parameters/slurm.yaml")
process_a.execute()

process_b = Process(name="process_B", param_file="parameters/slurm.yaml")
process_b.execute()
# }}}

print(f"Log Path of {process_a.name}: {process_a.log_path}")
print(f"Log Path of {process_b.name}: {process_b.log_path}")
print(f"Log Path of {process_c.name}: {process_c.log_path}")

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

process_apptainer.execute()

print(f"Log Path: {process_apptainer.log_path}")

# Run with singularity container from parameter file
singularity_params = Process(name="singularity_params", param_file=["parameters/slurm.yaml", "parameters/slurm2.yaml"])
singularity_params.execute()

print(f"Log Path: {singularity_params.log_path}")

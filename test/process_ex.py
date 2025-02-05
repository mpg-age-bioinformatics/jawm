# Add the parent directory (project root) to sys.path for development/testing purpose
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Start of the test script
from jawm import Process
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)

# ### Hello World example
# process_hw = Process(
#     name="hello_world",
#     script="""#!/bin/bash
# echo 'Starting process...'
# # sleep 15
# echo 'Hello, World!' > output.txt
# cat output.txt
# """,
#     retries=3
#     # memory="4 GB",
#     # time=60,
#     # retries=1,
#     # before_script="echo 'Preparing environment...'",
#     # after_script="echo 'Cleanup complete.'",
#     # when=True
# )

# output = process_hw.execute()
# print("Process Output:", output)

# ### Bash example
# # process_bash = Process(
# #     name="bash_example",
# #     script="""
# #         echo "Hello from Bash"
# #         echo "Current date: $(date)"
# #     """,
# #     interpreter="/bin/bash"
# # )

# # output = process_bash.execute()
# # print("Bash Output:", output)

# time.sleep(1)
# ### Python example
# process_python = Process(
#     name="python_example",
#     script="""#!/usr/bin/env python3
# print("Hello from Python")
# print("2 + 2 =", 2 + 2)
# """,
#     interpreter="python3"
# )

# output = process_python.execute()
# print("Python Output:", output)

# ### R example
# # process_r = Process(
# #     name="r_example",
# #     script="""
# # cat("Hello from R\n")
# # print(2 + 2)
# # """,
# #     interpreter="Rscript"
# # )

# # output = process_r.execute()
# # print("R Output:", output)

# time.sleep(1)
# # Run with slurm
# process_python = Process(
#     name="python_example",
#     script="""#!/usr/bin/env python3
# import time
# print("Hello from Python")
# print("2 + 3 =", 2 + 3)
# print("start sleeping!")
# time.sleep(5)
# print("python script ends!")
# """,
#     manager="slurm",
#     manager_slurm={"partition":"dedicated"}
# )

# output = process_python.execute()
# print("Python Output:", output)


# time.sleep(1)
# # Run with slurm and script
# process_python = Process(
#     name="python_file",
#     script_file="scripts/hello.py",
#     script_parameters={
#         "APPNAME": "JAWM",
#         "BYEMSG": "GOOD BYE!",
#         "FRUITLIST": "['Apple', 'Banana', 'Orange']"
#     },
#     manager="slurm",
#     manager_slurm={"partition":"dedicated"}
# )

# output = process_python.execute()
# print("Python Output:", output)


# time.sleep(1)
# # Run with slurm, script and parameters file
# process_python = Process(
#     name="python_file_params",
#     script_file="scripts/hello.py",
#     script_parameters_file="scripts/hello.rc",
#     manager="slurm",
#     manager_slurm={"partition":"dedicated"}
# )

# output = process_python.execute()
# print("Python Output:", output)


# time.sleep(1)
# # Run with apptainer container
# process_python = Process(
#     name="slurm_apptainer",
#     script="""#!/bin/bash
# echo $HOSTNAME
# echo $MY_VAR
# env
# """,
#     environment='apptainer',
#     container="/nexus/posix0/MAGE-flaski/service/hpc/home/hamin/python.sif",
#     # environment_apptainer={
#     #     "bind": ["/path/abc/:/abc/", "/path/def/:/def/"],
#     #     "home": "/path/home"
#     # },
#     env={
#         "MY_VAR": "APP_Value",
#         "ANOTHER_VAR": "ANOTHER_VAR"
#     },
#     manager="slurm",
#     manager_slurm={"partition":"dedicated"}
# )

# output = process_python.execute()
# print("Python Output:", output)

def ret_false():
    return False

time.sleep(1)
# Run with apptainer container
process_python = Process(
    name="env",
    manager="slurm",
    manager_slurm={"partition":"dedicated"},
    script="""#!/bin/bash
echo $MY_VAR
echo $SECVAL
env
""",
    env={
        "MY_VAR": "value",
        "SECVAL": "Second_Value"
    },
    environment='apptainer',
    container="/nexus/posix0/MAGE-flaski/service/hpc/home/hamin/python.sif",
)

output = process_python.execute()
print("Python Output:", output)


# Process A (dependency)
process_a = Process(
    name="process_A",
    script="""#!/bin/bash
echo 'Process A running'
sleep 10
""",
    retries=1,
    # when=ret_false()
)
process_a.execute()

# Process C (dependency)
process_c= Process(
    name="process_C",
    script="""#!/bin/bash
echo 'Process C running'
sleep 15
""",
    retries=1
)
process_c.execute()

# Process B depends on process_A and process_C
process_b = Process(
    name="process_B",
    script="""#!/bin/bash
echo 'Process B running after A, C finishes'
sleep 5
""",
    depends_on=["process_A", "process_C"]  # or use a list: depends_on=["process_A"]
)
process_b.execute()
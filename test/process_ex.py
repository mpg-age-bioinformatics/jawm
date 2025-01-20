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

### Hello World example
process_hw = Process(
    name="hello_world",
    script="""#!/bin/bash
echo 'Starting process...'
# sleep 15
echo 'Hello, World!' > output.txt
cat output.txt
""",
    retries=3
    # memory="4 GB",
    # time=60,
    # retries=1,
    # before_script="echo 'Preparing environment...'",
    # after_script="echo 'Cleanup complete.'",
    # when=True
)

output = process_hw.execute()
print("Process Output:", output)

### Bash example
# process_bash = Process(
#     name="bash_example",
#     script="""
#         echo "Hello from Bash"
#         echo "Current date: $(date)"
#     """,
#     interpreter="/bin/bash"
# )

# output = process_bash.execute()
# print("Bash Output:", output)

time.sleep(1)
### Python example
process_python = Process(
    name="python_example",
    script="""#!/usr/bin/env python3
print("Hello from Python")
print("2 + 2 =", 2 + 2)
""",
    interpreter="python3"
)

output = process_python.execute()
print("Python Output:", output)

### R example
# process_r = Process(
#     name="r_example",
#     script="""
# cat("Hello from R\n")
# print(2 + 2)
# """,
#     interpreter="Rscript"
# )

# output = process_r.execute()
# print("R Output:", output)

time.sleep(1)
# Run with slurm
process_python = Process(
    name="python_example",
    script="""#!/usr/bin/env python3
import time
print("Hello from Python")
print("2 + 3 =", 2 + 3)
print("start sleeping!")
time.sleep(15)
print("python script ends!")
""",
    manager="slurm",
    manager_slurm={"partition":"dedicated"}
)

output = process_python.execute()
print("Python Output:", output)


time.sleep(1)
# Run with slurm and script
process_python = Process(
    name="python_file",
    script_file="scripts/hello.py",
    manager="slurm",
    manager_slurm={"partition":"dedicated"}
)

output = process_python.execute()
print("Python Output:", output)

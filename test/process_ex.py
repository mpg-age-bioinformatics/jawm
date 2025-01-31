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

time.sleep(1)
# Run with apptainer container
process_python = Process(
    name="container",
    script="""#!/bin/bash
echo "Hello World!"
env
""",
    environment='docker',
    container="python:slim",
    # environment_apptainer={
    #     "bind": ["/path/abc/:/abc/", "/path/def/:/def/"],
    #     "home": "/path/home"
    # },
    # env={
    #     "MY_VAR": "APP_Value",
    #     "ANOTHER_VAR": "ANOTHER_VAR"
    # }
)

output = process_python.execute()
print("Python Output:", output)

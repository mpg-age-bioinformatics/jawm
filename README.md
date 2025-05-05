# JAWM
Just Another Workflow Manager


## Why

- Python based
- Code fully independent of framework
- Local and external storage agnostic
- Notebook ready and data scientist friendly

## Installation
```
pip install git+ssh://git@github.com/mpg-age-bioinformatics/JAWM.git --user
```

## HelloWorld
- Import the `Process` class
```
from jawm import Process
```

- Write the Process
```python
process_hw = Process(
    name="hello_world",
    script="""#!/bin/bash
echo 'Starting process...'
echo 'Hello World!' > output.txt
cat output.txt
"""
)
```

- Execute the Process
```
process_hw.execute()
```

This Process would run the bash script locally with the default paramters (check the available [paramters](docs/process_parameters.md)) and would generate logs with basic info:
```
[2025-05-05 08:47:46] INFO:: [hello_world|5c58] Executing process hello_world locally.
[2025-05-05 08:47:46] INFO:: [hello_world|5c58] Log folder for process hello_world: /JAWM/notebook/logs/hello_world_20250505_084736_5c58
[2025-05-05 08:47:46] INFO:: [hello_world|5c58] Preparing base script for process hello_world
[2025-05-05 08:47:46] INFO:: [hello_world|5c58] Process hello_world started with PID: 3820937
[2025-05-05 08:47:46] INFO:: [hello_world|5c58] Process hello_world (PID: 3820937) is still running...
[2025-05-05 08:47:51] INFO:: [hello_world|5c58] Process hello_world completed with exit code: 0
```

Alternatively, with parameter YAML file the Process can be initiated with `Process(name="hello_world", param_file="parameters/example.yaml")`

YAML Example:
```yaml
- scope: process
  name: "hello_world"
  script: |
    #!/bin/bash
    echo 'Starting process...'
    echo 'Hello World!' > output.txt
    cat output.txt
```



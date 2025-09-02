# jawm
Just Another Workflow Manager


## Why?

- Python based
- Code fully independent of framework
- Local and external storage agnostic
- Notebook ready and data scientist friendly

## Installation
```
pip install git+ssh://git@github.com/mpg-age-bioinformatics/jawm.git --user
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

This Process would run the bash script locally with the default parameters (check the available [parameters](docs/process_parameters.md)) and would generate logs with basic info:
```
[2025-08-14 08:11:53] - INFO - hello_world|003af14gxp :: Executing process hello_world locally.
[2025-08-14 08:11:53] - INFO - hello_world|003af14gxp :: Log folder for process hello_world: /jawm/notebook/logs/hello_world_20250814_081143_003af14gxp
[2025-08-14 08:11:53] - INFO - hello_world|003af14gxp :: Preparing base script for process hello_world
[2025-08-14 08:11:53] - INFO - hello_world|003af14gxp :: Process hello_world started with PID: 1385124
[2025-08-14 08:11:53] - INFO - hello_world|003af14gxp :: Process hello_world (PID: 1385124) is still running...
[2025-08-14 08:11:58] - INFO - hello_world|003af14gxp :: Process hello_world completed with exit code: 0
```

jawm logs follow this pattern by default: `[YYYY-MM-DD HH:MM:SS] - LEVEL - process_name|hash :: log_message`

Alternatively, with parameter YAML file the Process can be initiated and executed with:
```python
process_hw = Process(name="hello_world", param_file="parameters/example.yaml")`
process_hw.execute()
```

YAML Example (`parameters/example.yaml`):
```yaml
- scope: process
  name: "hello_world"
  script: |
    #!/bin/bash
    echo 'Starting process...'
    echo 'Hello World!' > output.txt
    cat output.txt
```

## FastQC Example
Follwing is another basic example of a single FastQC call, which is executed inside an Apptainer container using Slurm.

```python
fastqc_apptainer = Process(
    name="fastqc_apptainer",
    script="""#!/bin/bash
mkdir output
fastqc -o output/ input/reads.fastq
""",
    container="/images/fastqc.sif",
    environment="apptainer",
    manager="slurm"
)
```

This Process can be executed with `fastqc_apptainer.execute()`

With a parameter YAML file, the same process can be initiated and executed with:
```python
fastqc_apptainer = Process(name="fastqc_apptainer", param_file="parameters/fastqc_apptainer.yaml")`
fastqc_apptainer.execute()
```

YAML Example (`parameters/fastqc_apptainer.yaml`):
```yaml
- scope: process
  name: "fastqc_apptainer"
  script: |
    #!/bin/bash
    mkdir output
    fastqc -o output/ input/reads.fastq
  container: "/images/fastqc.sif"
  environment: "apptainer"
  manager: "slurm"
```

## Parameters
You can find details about the avaliable [Process parameters here](docs/process_parameters.md).

It can be also checked with the `jhelp` function (e.g. get documentation of `logs_directory` parameter).
```
from jawm import jhelp
jhelp("Process", "logs_directory")
```

Try `jhelp()`, in order to get the summary of available parameters, examples and how to use.

## HowTo
You can find details about different [Process howto here](docs/process_howto.md).

It can be also checked with the `jhelp` function (e.g. get documentation of `howto_yaml_global_value`).
```
from jawm import jhelp
jhelp("Process", "howto_yaml_global_value")
```

Try `jhelp()`, in order to get the summary of available parameters, examples and how to use.

## Examples
You can find some [basic examples of Process use here](docs/process_examples.md).

It can be also checked with the `jhelp` function (e.g. get documentation of `example_hello_world`).
```
from jawm import jhelp
jhelp("Process", "example_hello_world")
```

Try `jhelp()`, in order to get the summary of available parameters, examples and how to use.

## Projected Development Timeline
- 08.05.25 :: First draft for a one Fastqc call
- 01.06.25 :: First draft for a pipeline development

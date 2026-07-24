# Jupyter Notebook

jawm was build to be data science friendly and work out of a notebook.

As allways, you will need to import jawm:

```python
# Cell 1
import jawm
```

Define your processes:

```python
# Cell 2

# Define our process
fastqc=jawm.Process(

  # Process name
  name="fastqc",

  # Script to be run when process is executed
  script="""#!/bin/bash
fastqc {{extra_args}} -t {{cpus}} -o {{fastqc_output}} {{f}}
""",

  # Description of the variables
  desc={
    "extra_args":"Any fastqc argument with its respective value.",
    "cpus":"Number of cpus to be used.",
    "fastqc_output":"Output dir.",
    "f":"Input fastq file."
  },

  # Set the variables
  var={
    "extra_args":"",
    "cpus":1,
    "mk.fastqc_output":"./fastqc_output",
    "map.f":"my_test_file_1.fastq.gz"
  },

  # Image and respective environment
  container="mpgagebioinformatics/fastqc:0.11.9", # defaults to docker://mpgagebioinformatics/fastqc:0.11.9
  environment="docker", # docker or apptainer
  environment_docker={"--platform":"linux/amd64"}

)
```

And execute your process:

```python
# Cell 3
fastqc.execute()
```

    [2026-07-24 10:23:05] - INFO - fastqc|598d160k2h :: Launching process fastqc using Local executor.
    [2026-07-24 10:23:05] - INFO - fastqc|598d160k2h :: Log folder for process fastqc: /Users/jboucas/jawm_fastqc_notebook/logs/fastqc_20260724_102303_598d160k2h
    [2026-07-24 10:23:05] - INFO - fastqc|598d160k2h :: Preparing base script for process fastqc
    [2026-07-24 10:23:05] - INFO - fastqc|598d160k2h :: Executing process fastqc with docker container mpgagebioinformatics/fastqc:0.11.9
    [2026-07-24 10:23:05] - INFO - fastqc|598d160k2h :: Process fastqc started with PID: 35373
    [2026-07-24 10:23:05] - INFO - fastqc|598d160k2h :: Process fastqc (PID: 35373) is still running...
    [2026-07-24 10:24:00] - INFO - fastqc|598d160k2h :: Process fastqc completed with exit code: 0

On failure jawm might complain that it can not run new processes as one process already failed, for which you can `jawm.Process.reset_runtime()`.
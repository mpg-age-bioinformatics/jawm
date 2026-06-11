# FastQC

In this example we will stepwise build a production-grade FastQC jawm module.

Before starting let's take a look at FastQC's synopsis:
```bash
fastqc [-o output dir] [--(no)extract] [-f fastq|bam|sam]
           [-c contaminant file] seqfile1 .. seqfileN
```

We will start by defaulting our use case to:
```bash
fastqc -o output dir seqfile1
```

Now let's create a folder for our module and our python file:
```bash
mkdir jawm_fastqc
touch jawm_fastqc/fastqc.py
```

Download test data:
```bash
mkdir test_data
for i in {1..3}; do
  curl -L -o "./test_data/my_test_file_${i}.fastq.gz" "https://ndownloader.figshare.com/files/57999445"
done
```
---

## Process definition



We will start by importing jawm and defining the fastqc process:

```python
import jawm
import sys

# define our fastqc process
fastqc=jawm.Process(

  # Process name
  name="fastqc",

  # Script to be run when process is executed
  script="""#!/bin/bash
fastqc -o {{fastqc_output}} {{f}}
""",

  # Description of the variables
  desc={
    "fastqc_output": "Output dir.",
    "f": "Input fastq file."
  }

)

# Execute process when script is executed
fastqc.execute()

# Wait for all processes to complete
jawm.Process.wait()

sys.exit(0)
```

Detailed description of the Process arguments can be found under [Process > Parameters](../process/parameters.md).

Provided we have fastqc available in the path, we can now use the command line to run our script:

```bash
jawm ./jawm_fastqc \
  --process.fastqc.var.fastqc_output=./demo_output \
  --process.fastqc.var.f=./test_data/my_test_file_1.fastq.gz
```

As we try to build a more multipurpose reproducible module we want to:

- increase the number of arguments including adding any possible argument:

    `{{extra_args}} -t {{cpus}}`

- use a container system to run a Docker image:

    `container="mpgagebioinformatics/fastqc:0.11.9"`

- set the default arguments for SLURM-based execution:

    ```
    manager_slurm={
      "--mem":"20GB",
      "-t":"1:00:00",
      "-c":"4"
    }
    ```

Leading to the following changes:

```python
import jawm
import sys

# define our fastqc process
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

  # Default variable values
  var={
    "extra_args":"",
    "cpus":1
  },

  # image and respective environment
  container="mpgagebioinformatics/fastqc:0.11.9", # defaults to docker://mpgagebioinformatics/fastqc:0.11.9
  environment="docker", # docker or apptainer, defaults to docker

  # slurm default arguments
  manager_slurm={
    "--mem":"20GB",
    "-t":"1:00:00",
    "-c":"4"
  }

)

# Execute process when script is executed
fastqc.execute()

# Wait for all processes to complete
jawm.Process.wait()

sys.exit(0)
```

We will now run it once more making use of our container. We will also need to map our input file to the container by using `map` in `--process.fastqc.var.map.f` and our output folder with `mk` in `--process.fastqc.var.mk.fastqc_output` to make sure the folder is created in case it does not exist:

```bash
jawm ./jawm_fastqc \
  --process.fastqc.var.mk.fastqc_output=./demo_output \
  --process.fastqc.var.map.f=./test_data/my_test_file_1.fastq.gz
```

To make sure we do not run this process in case of the output having already been generated we will make use of the `when` argument to
make sure we only run the process if the output file does not already exist:

```python
import jawm
import sys
import os

# define our fastqc process
fastqc=jawm.Process(

  # Logical statement to be validated prior to execution
  when=lambda p: not os.path.isfile(
                        os.path.join(
                          p.var["fastqc_output"],
                          os.path.basename( str(p.var["f"]).lstrip().split(" ")[0].split( ".fastq.gz"  )[0].split( ".fq.gz"  )[0] )+"_fastqc.html"
                        )
                      ),

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

  # Default variable values
  var={
    "extra_args":"",
    "cpus":1
  },

  # image and respective environment
  container="mpgagebioinformatics/fastqc:0.11.9", # defaults to docker://mpgagebioinformatics/fastqc:0.11.9
  environment="docker", # docker or apptainer

  # slurm default arguments
  manager_slurm={
    "--mem":"20GB",
    "-t":"1:00:00",
    "-c":"4"
  }

)

# Execute process when script is executed
fastqc.execute()

# Wait for all processes to complete
jawm.Process.wait()

sys.exit(0)
```

Test it and check that it is now not running:
```bash
jawm ./jawm_fastqc \
  --process.fastqc.var.mk.fastqc_output=./demo_output \
  --process.fastqc.var.map.f=./test_data/my_test_file_1.fastq.gz
```

While this module now works well for one file, we might want to expand it to run over all the files in the test_data folder.


```python
import jawm
import sys
import os

# define our fastqc process
fastqc=jawm.Process(

  # Logical statement to be validated prior to execution
  when=lambda p: not os.path.isfile(
                        os.path.join(
                          p.var["fastqc_output"],
                          os.path.basename( str(p.var["f"]).lstrip().split(" ")[0].split( ".fastq.gz"  )[0].split( ".fq.gz"  )[0] )+"_fastqc.html"
                        )
                      ),

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

  # Default variable values
  var={
    "extra_args":"",
    "cpus":1
  },

  # image and respective environment
  container="mpgagebioinformatics/fastqc:0.11.9", # defaults to docker://mpgagebioinformatics/fastqc:0.11.9
  environment="docker", # docker or apptainer

  # slurm default arguments
  manager_slurm={
    "--mem":"20GB",
    "-t":"1:00:00",
    "-c":"4"
  }

)

# list all the fastq files in the input folder
fastq_files = [
    os.path.join( fastqc.var["input_folder"], f )
    for f in os.listdir( fastqc.var["input_folder"] )
    if f.endswith((".fastq.gz", ".fq.gz"))
]

for f in fastq_files :
  # for each fastq file clone the fastqc process
  fastqc_=fastqc.clone()
  # attribute the input file
  fastqc_.var["map.f"]=f
  # execute the process
  fastqc_.execute()

# Wait for all processes to complete
jawm.Process.wait()

sys.exit(0)
```

```bash
jawm ./jawm_fastqc \
  --process.fastqc.var.mk.fastqc_output=./demo_output \
  --process.fastqc.var.map.input_folder=./test_data
```

---

## Parameters file

For good working practices let's create a folder where we store our parameters files.
```
mkdir jawm_fastqc/yaml
touch jawm_fastqc/yaml/demo.yaml
```
Let's populate our `demo.yaml` with the parameters we were using in the command line:
```yaml
- scope: process
  name: "fastqc"
  var:
    mk.fastqc_output: ./demo_output
    map.f: ./test_data/my_test_file_1.fastq.gz
```

Let us now create different parameters files for different running environments starting with
running it on a <u>local</u> computer making use of <u>docker</u> and due to CPU limitations making sure
that processes <u>run sequentially</u>:

```yaml
# docker.yaml
- scope: global
  parallel: false # run processes sequentially
  environment: "docker"
  docker_run_as_user: true # do this if you want/need to run docker without root

- scope: process
  name: "fastqc"
  var:
    mk.fastqc_output: ./demo_output
    map.f: ./test_data/my_test_file_1.fastq.gz
```
Here we made use of the `scope: global` to pass definitions to all processes. We added `environment: "docker"` for
demonstration purposes but it is not required given that if you attribute an image to the `container` parameter as we did
above during process definition, jawm will default to `environment: "docker"`.

Now an example of an <u>Apptainer/SLURM</u> parameters file:
```yaml
# hpc.yaml
- scope: global
  environment: "apptainer"

  # add arguments to the apptainer call
  environment_apptainer: { "-B":"/nexus:/nexus" }

  # if needed (nfs mounts ?), disable mk. and map. volume mapping in containers
  automated_mount: False

  # use this if you need to for example add apptainer
  # to your path before the script is called
  before_script: "module load apptainer"

  # add more slurm arguments
  manager_slurm: { "-p":"cluster,dedicated" }

- scope: process
  name: "fastqc"
  manager: slurm
  var:
    cpus: 4
    mk.fastqc_output: ./demo_output
    map.f: ./test_data/my_test_file_1.fastq.gz
```
We here overwrote the number of threads passed to fastqc - `cpus: 4` - to match the number of
cpus set for SLURM jobs in our process definition `manager_slurm={ "-c":"4" }`.

When working with containers and nfs volumes it can sometimes be useful to disable the automated mounting of volumes that
is triggered by variables with `mk.<variable>` and `map.<variable>`. This can be achieved with `automated_mount: False`.

---

## Workflows


---

## CI/CD tests

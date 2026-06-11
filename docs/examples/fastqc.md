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
  environment="docker", # docker or apptainer, defaults to docker

  # slurm default arguments
  manager_slurm={
    "--mem":"20GB",
    "-t":"1:00:00",
    "-c":"4"
  }

)

# handle single file calls
if "f" in fastqc.var:
  # clone the fastqc process
  fastqc_=fastqc.clone()
  # execute the process
  fastqc_.execute()

# handle folder calls
if "input_folder" in fastqc.var :
 
  # list all the fastq files in the input folder
  fastq_files = [
      os.path.join( fastqc.var["input_folder"], f )
      for f in os.listdir( fastqc.var["input_folder"] )
      if f.endswith( (".fastq.gz", ".fq.gz") )
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

Workflows allow you build command line callable tasks or group of tasks. 
While workflows usage can be better understood for more complex tools (eg. kallisto where genome indexing processes might be called 
independently of mapping processes) or [multi-module](multimodule.md) usage, we will here give a short example for demo purposes 
which we can further use downstream for our CI/CD tests.

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

if __name__ == "__main__":

  from jawm.utils import workflow

  # parse the command line jawm call
  # if no workflow was called, workflows will default to 'main' 
  workflows, var, args, unknown_args = jawm.utils.parse_arguments(["main","fastqc","test"])

  # check which workflow was called from the command line
  if workflow( ["main","fastqc","test"], workflows ) :

    # handle single file calls
    if "f" in fastqc.var:
      # clone the fastqc process
      fastqc_=fastqc.clone()
      # execute the process
      fastqc_.execute()

    # handle folder calls
    if "input_folder" in fastqc.var :
    
      # list all the fastq files in the input folder
      fastq_files = [
          os.path.join( fastqc.var["input_folder"], f )
          for f in os.listdir( fastqc.var["input_folder"] )
          if f.endswith( (".fastq.gz", ".fq.gz") )
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

  # when running the test workflow we do also unzip the output file
  if workflow( ["test"], workflows ) :

    from pathlib import Path
    from zipfile import ZipFile

    # unzip the output file
    zip_path=os.path.join( fastqc.var["fastqc_output"], os.path.basename( str( fastqc.var["f"] ).lstrip().split(" ")[0].split( ".fastq.gz"  )[0].split( ".fq.gz"  )[0] )+"_fastqc.zip" )

    zip_path = Path(zip_path)
    destination = zip_path.parent
    destination.mkdir(parents=True, exist_ok=True)

    with ZipFile(zip_path, "r") as zip_ref:
      for member in zip_ref.infolist():
        target_path = destination / member.filename
        if not target_path.resolve().is_relative_to(destination.resolve()):
          raise ValueError(f"Unsafe zip entry: {member.filename}")
      zip_ref.extractall(destination)

    print("Test completed")
    sys.stdout.flush()

sys.exit(0)
```

We can now call our test workflow with:

```bash
jawm ./jawm_fastqc test \
  --process.fastqc.var.mk.fastqc_output=./demo_output \
  --process.fastqc.var.map.f=./test_data/my_test_file_1.fastq.gz
```

--- 

## Logs

---

## CI/CD tests

jawm was build with Coninuous Integration & Continuous Deployment in mind.

For this we start by creating a test folder as well as all the required files:

```bash
mkdir ./jawm_fastqc/test

# test related yaml files will be kept here
mkdir ./jawm_fastqc/test/yaml

# test associated yaml file
touch ./jawm_fastqc/test/test.yaml

# defines the tests to be run
touch ./jawm_fastqc/test/tests.txt

# source of raw input data
touch ./jawm_fastqc/test/data.txt
```

Let's start by populating our `test.yaml` file:

```yaml
# ./jawm_fastqc/test/test.yaml
- scope: process
  name: fastqc
  parallel: False
  var:
    mk.fastqc_output: "./test/test-output"
    map.f: "./test/test-input/my_test_file_1.fastq.gz"

# files to be used for SHA-256 hash generation     
- scope: hash
  include: ./test/test-output/my_test_file_1_fastqc/fastqc_data.txt
  # overwrite any existing hash in the logs folder
  overwrite: true
```

The `tests.txt` file will contain one line per command line call that will be tested:
```txt
#jawm_file.py;workflow;parameters.file1.yaml,parameters.file2.yaml;"Test name";test_hash
fastqc.py;test;./test/yaml/fastqc.yaml;"Main workflow test";8081eb3945c0631419ed3125da729d926b092ca6ea76329e3a21c50efb4689c6
```

--- 


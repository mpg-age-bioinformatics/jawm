# FastQC

In this example we will stepwise build a production-grade FastQC jawm module.

Before starting let's take a look at FastQC's synopsis:
```bash
fastqc [-o output dir] [--(no)extract] [-f fastq|bam|sam]
           [-c contaminant file] seqfile1 .. seqfileN
```

We will start by defaulting our use case to:
```bash
fastqc -o output_dir seqfile1
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

- use a container image to run FastQC:

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
    fastqc_.var["map.f"] = f
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

For good working practices let's create a folder where we store our parameter files.
```bash
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

Workflows allow you to build command line callable tasks or groups of tasks. 
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
        fastqc_.var["map.f"] = f
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

By default jawm creates logs in the current working directory. You can change this with `-l </path/to/my/logs/>`. Below is an example of the logs folder for our previous run:

```bash
logs/
├── fastqc_20260612_093249_e4c18enh5s
│   ├── fastqc.command
│   ├── fastqc.error
│   ├── fastqc.exitcode
│   ├── fastqc.id
│   ├── fastqc.output
│   └── fastqc.script
├── jawm_hashes
│   └── fastqc_input.history
└── jawm_runs
    └── jawm_fastqc_20260612_093249.log

4 directories, 8 files
```

In the logs folder you will find

1. **fastqc_20260612_093249_e4c18enh5s**: One folder for each executed jawm process in the form `<process_name>_<date>_<time>_<short_hash>`. The `hash` is generated based on the process definition and all
its associated values, e.g. values passed to a process from the command line or through YAML files.
This folder contains all the relevant files regarding an executed process. These files can be extremely useful during debugging. Each file is prefixed with the process name.

    ***fastqc.script***: the script generated from the `Process` definition `script` argument after replacement of variables.

    ```bash
    #!/bin/bash
    fastqc -t 1 \
      -o /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/demo_output \
      /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/test_data/my_test_file_1.fastq.gz
    ```

    ***fastqc.command***: the command that calls the script.

    ```bash
    docker run --rm -v /nexus:/nexus -u 60504:17600 mpgagebioinformatics/fastqc:0.11.9 /bin/bash -c /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/logs/fastqc_20260612_093249_e4c18enh5s/fastqc.script
    ```

    ***fastqc.output***: standard output

    ```
    Analysis complete for my_test_file_1.fastq.gz
    ```

    ***fastqc.error***: standard error

    ```
    Started analysis of my_test_file_1.fastq.gz
    Approx 5% complete for my_test_file_1.fastq.gz
    Approx 10% complete for my_test_file_1.fastq.gz
    Approx 15% complete for my_test_file_1.fastq.gz
    Approx 20% complete for my_test_file_1.fastq.gz
    Approx 25% complete for my_test_file_1.fastq.gz
    Approx 30% complete for my_test_file_1.fastq.gz
    Approx 35% complete for my_test_file_1.fastq.gz
    Approx 40% complete for my_test_file_1.fastq.gz
    Approx 45% complete for my_test_file_1.fastq.gz
    Approx 50% complete for my_test_file_1.fastq.gz
    Approx 55% complete for my_test_file_1.fastq.gz
    Approx 60% complete for my_test_file_1.fastq.gz
    Approx 65% complete for my_test_file_1.fastq.gz
    Approx 70% complete for my_test_file_1.fastq.gz
    Approx 75% complete for my_test_file_1.fastq.gz
    Approx 80% complete for my_test_file_1.fastq.gz
    Approx 85% complete for my_test_file_1.fastq.gz
    Approx 90% complete for my_test_file_1.fastq.gz
    Approx 95% complete for my_test_file_1.fastq.gz
    Approx 100% complete for my_test_file_1.fastq.gz
    ```

    ***fastqc.exitcode***: script exit code
    ```
    0
    ```

    ***fastqc.id***: jawm's internal job id
    
    ```
    120424
    ```

2. **jawm_runs**: A folder containing the log for each run. Each of these files logs the same stdout and stderr you see on your screen when running jawm. Each file has the form `jawm_<executed_python_file_name>_<date>_<time>.log`.

    ```bash
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: Initiating jawm module script from jawm command
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: Logging terminal output to: /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/logs/jawm_runs/jawm_fastqc_20260612_093249.log
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: Override param_file set to: /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/build.nexus.yaml
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: [sys] jawm: 0.1.0
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: [sys] Python: 3.10.12
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: [sys] OS: Linux-5.15.0-177-generic-x86_64-with-glibc2.35
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: [sys] Machine/Arch: x86_64
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: [sys] Docker: Docker version 25.0.5, build 5dc9bcc
    [2026-06-12 09:32:49] - INFO - jawm.cli|jawm_fastqc :: Running jawm module: /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/jawm_fastqc/fastqc.py
    [2026-06-12 09:32:49] - INFO - fastqc|e4c18enh5s :: Launching process fastqc using Local executor.
    [2026-06-12 09:32:49] - INFO - fastqc|e4c18enh5s :: Log folder for process fastqc: /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/logs/fastqc_20260612_093249_e4c18enh5s
    [2026-06-12 09:32:49] - INFO - fastqc|e4c18enh5s :: Preparing base script for process fastqc
    [2026-06-12 09:32:49] - INFO - fastqc|e4c18enh5s :: mk.* created directory /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/demo_output
    [2026-06-12 09:32:49] - INFO - fastqc|e4c18enh5s :: Executing process fastqc with docker container mpgagebioinformatics/fastqc:0.11.9
    [2026-06-12 09:32:49] - INFO - fastqc|e4c18enh5s :: Process fastqc started with PID: 120424
    [2026-06-12 09:32:49] - INFO - fastqc|e4c18enh5s :: Process fastqc (PID: 120424) is still running...
    [2026-06-12 09:33:09] - INFO - fastqc|e4c18enh5s :: Process fastqc completed with exit code: 0
    [2026-06-12 09:33:09] - INFO - fastqc|e4c18enh5s :: Process.wait → fastqc [e4c18enh5s] already completed
    [2026-06-12 09:33:09] - INFO - jawm.Process|WAIT :: Wait completed for 1 process(es).
    Test completed
    [2026-06-12 09:33:09] - INFO - jawm.cli|jawm_fastqc :: Module ended with exitcode (0); Initiating post run procedures.
    [2026-06-12 09:33:11] - INFO - jawm.cli|jawm_fastqc :: Ending jawm module script from jawm command
    ```
    
    Please take time to notice how the information in this log file for the fastqc process matches the information on the log for the respective process and how it points you to the respective process log folder.

3. **jawm_hashes**: A folder containing hashes, `jawm_hashes`. By default this folder is populated with one file of the form `<python_file_name>_input.history`. It's content has the form:

    ```
    <date>T<time>     <hash>        <run log file>       <input file>
    ```

    eg.

    ```
    2026-06-12T09:32:49     7917a4d3132ce4a712102651a73d5255406383502173e8f3224fb00f54e34b15        /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/logs/jawm_runs/jawm_fastqc_20260612_093249.log       /nexus/posix0/MAGE-flaski/service/posit/home/jboucas/build.nexus.yaml,/nexus/posix0/MAGE-flaski/service/posit/home/jboucas/tutorial_demo/jawm_fastqc/fastqc.py
    ```

    The `hash` is generated on the basis of the hashes of all run processes. More information can be found under [jawm_hashes](../debug/logs.md).
    Please visit [Log Structure](../debug/logs.md) and [Errors Debugging](../debug/errors.md) for more information.

---

## Version control

jawm looks for a `.git` folder in your module's directory to report on the current used version and how it differs from the remote. Thus, for version control all you need to do is to initialize the repo in your local folder and push it to the remote:
```bash
cd ./jawm_fastqc
git init
git add .
git commit -m "Initial commit"
git remote add origin git@github.com:username/my-project.git
git branch -M main
git push -u origin main
cd ..
```
For instructions on how to run your module directly from a remote repository, check [Run a remote module](../get_started/run_module.md#run-a-remote-module).

---

## CI/CD tests

jawm was built with Continuous Integration & Continuous Deployment in mind.

For this we start by creating a test folder as well as all the required files:

```bash
mkdir ./jawm_fastqc/test

# test related yaml files will be kept here
mkdir ./jawm_fastqc/test/yaml

# test associated yaml file
touch ./jawm_fastqc/test/yaml/test.yaml

# defines the tests to be run
touch ./jawm_fastqc/test/tests.txt

# source of raw input data
touch ./jawm_fastqc/test/data.txt
```

Let's now populate our `test.yaml` file:

```yaml
# ./jawm_fastqc/test/yaml/test.yaml
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
fastqc.py;test;./test/yaml/test.yaml;"Main workflow test";
```

with `"Test name"` being an arbitrary name given by you to the test. `test_hash` can be left empty for now and will be filled by the SHA-256 hash generated from the file(s) you added in:
```yaml
# files to be used for SHA-256 hash generation     
- scope: hash
  include: ./test/test-output/my_test_file_1_fastqc/fastqc_data.txt
  # overwrite any existing hash in the logs folder
  overwrite: true
```
If you need to input data for your tests you can make them available online and add them for download to the `data.txt` file:
```bash
13fb536154e7cf36a394d9b09ff99b7a  my_test_file_1.fastq.gz  https://ndownloader.figshare.com/files/57999445
```
which has the form:
```txt
<md5sum value>  <file name>  <download link>
```

You can now test your pipeline:
```
cd jawm_fastqc
jawm-test 
```

You will now see the `tests.txt` file populated with the respective output hash:
```bash
#jawm_file.py;workflow;parameters.file1.yaml,parameters.file2.yaml;"Test name";test_hash
fastqc.py;test;./test/yaml/test.yaml;"Main workflow test";903c31655306e9af2c208b47f520e07c0aa8ad106fd1e934ad6ff5ceee614d07
```

Check the output of `jawm-test --help` to learn how to test your module against different Python versions as well as different jawm versions.

You can now automate your module's testing by making use of GitHub actions.

```yaml
# ./.github/workflows/test.yaml
name: Test

on:
  workflow_dispatch:
  push:
    # test on every push to the main branch
    branches: ["main"]
  schedule:
      # test every Monday at app. 6 AM Berlin time.
      - cron: "30 4 * * 1"

jobs:
  build:
    # the build test uses jawm's default testing workflow 
    uses: mpg-age-bioinformatics/jawm/.github/workflows/modules.yaml@main
```

After pushing these changes you should be able to see the testing taking place under the "Actions" tab in your GitHub repo.

--- 
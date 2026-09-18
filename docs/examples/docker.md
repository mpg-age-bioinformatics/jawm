# Run FastQC Using the jawm Docker Image

This example runs jawm from its Docker image and uses jawm to start the containerized [FastQC workflow](fastqc.md). You only need Docker on the host machine; neither jawm nor FastQC needs to be installed directly on it.

The containers are arranged as follows:

```text
Host Docker daemon
├── mpgagebioinformatics/jawm:latest
│   └── jawm prepares and launches the process
└── mpgagebioinformatics/fastqc:0.11.9
    └── FastQC processes the input file
```

jawm uses the host Docker daemon through its socket. With this, jawm container has the Docker command-line client, while the Docker daemon runs on the host.

## Requirements

- Docker is installed and running.
- The host can download images from Docker Hub and the example data from Figshare.
- The jawm image can be trusted with access to the Docker socket.

Mounting the Docker socket gives the jawm container control over the host Docker daemon. Use this only with trusted images and workflows.

## 1. Prepare the Input

Create a clean working directory and download the example FASTQ file:

```bash
mkdir -p "$PWD/fastqc-docker-test/raw_data"
cd "$PWD/fastqc-docker-test"

curl -L \
  -o ./raw_data/my_test_file_1.fastq.gz \
  https://ndownloader.figshare.com/files/57999445
```

Everything produced by the example will remain in this directory after the jawm container exits.

## 2. Check Docker Access (optional)

Pull the jawm image and verify that it can communicate with the host Docker daemon:

```bash
docker pull mpgagebioinformatics/jawm:latest

docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  mpgagebioinformatics/jawm:latest \
  docker ps
```

The commands in this example use `mpgagebioinformatics/jawm:latest`. You can use `mpgagebioinformatics/jawm:stable` for the current stable release, or `mpgagebioinformatics/jawm:<tag>` to select a specific release.

If `docker ps` returns normally, the jawm container can start the FastQC container.

## 3. Run FastQC

Run the FastQC workflow:

```bash
docker run --rm -it \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD:$PWD" \
  -w "$PWD" \
  mpgagebioinformatics/jawm:latest \
  jawm jawm_fastqc test \
    --process.fastqc.var.mk.fastqc_output=./fastqc_output \
    --process.fastqc.var.map.f=./raw_data/my_test_file_1.fastq.gz
```

This runs the latest workflow version. To reproduce the revision tested in this example, use `jawm jawm_fastqc@6c73866 test`. To use a tagged release, use `jawm jawm_fastqc@<tag> test`.

The options passed to Docker have distinct purposes:

| Option | Purpose |
|---|---|
| `-v /var/run/docker.sock:/var/run/docker.sock` | Allows jawm to ask the host Docker daemon to run FastQC. |
| `-v "$PWD:$PWD"` | Makes the working directory available at the same absolute path inside the jawm container. |
| `-w "$PWD"` | Runs jawm from that shared working directory. |
| `--rm` | Removes the temporary jawm container after it exits. The mounted results remain on the laptop. |

Keeping the same absolute path is important. jawm passes the input, output and generated-script paths to the host Docker daemon, which must be able to find those paths when it starts the FastQC container.

The jawm command uses:

- `jawm_fastqc` to retrieve the latest workflow version;
- `test` to run the module's test workflow;
- `mk.fastqc_output` to create and map the output directory;
- `map.f` to map the FASTQ input into the FastQC container.

jawm downloads `mpgagebioinformatics/fastqc:0.11.9` automatically if that image is not already present.

## 4. Check the Results

List the generated FastQC results:

```bash
find fastqc_output -maxdepth 2 -type f
```

The output includes the FastQC HTML report, ZIP archive and extracted result files:

```text
fastqc_output/my_test_file_1_fastqc.html
fastqc_output/my_test_file_1_fastqc.zip
fastqc_output/my_test_file_1_fastqc/fastqc_data.txt
fastqc_output/my_test_file_1_fastqc/fastqc_report.html
fastqc_output/my_test_file_1_fastqc/summary.txt
```

List the jawm execution records:

```bash
find logs -maxdepth 2 -type f
```

Inspect the exact nested Docker command and its exit code:

```bash
cat logs/fastqc_*/fastqc.command
cat logs/fastqc_*/fastqc.exitcode
```

A successful run records exit code `0`. The process directory also retains the generated script, standard output, standard error and process identifier. See [Debugging logs](../debug/logs.md) for details about these files.

## Run a Local Workflow

The same mount pattern works with a workflow already present in the current directory:

```bash
docker run --rm -it \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD:$PWD" \
  -w "$PWD" \
  mpgagebioinformatics/jawm:latest \
  jawm ./workflow.py
```

Any Docker-based process defined by `workflow.py` is launched through the host Docker daemon, while its outputs and jawm logs remain in the mounted working directory.

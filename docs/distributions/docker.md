# Docker Image

The official jawm Docker image provides jawm and its command-line tools in a ready-to-use environment. It is available from [Docker Hub](https://hub.docker.com/r/mpgagebioinformatics/jawm) for AMD64 and ARM64 systems.

The image includes:

- jawm with its full optional dependencies;
- Python;
- common command-line utilities, including Bash, Git, curl, tar, gzip and unzip;
- the Docker command-line client.

The image does not run its own Docker daemon. To launch Docker-based processes from jawm, connect it to the host Docker daemon as described below.

## Image Tags

Choose the tag that matches how you want to use the image:

| Tag | Purpose |
|---|---|
| `latest` | Most recent image built from the main branch after the smoke tests pass. |
| `stable` | Most recent published release. |
| `<version>` | A specific release, such as `1.0.0`. |

Pull the latest development image:

```bash
docker pull mpgagebioinformatics/jawm:latest
```

Pull the current stable release:

```bash
docker pull mpgagebioinformatics/jawm:stable
```

For a specific release, replace the value of `JAWM_VERSION` with an available version tag:

```bash
JAWM_VERSION=1.0.0
docker pull "mpgagebioinformatics/jawm:${JAWM_VERSION}"
```

## Basic Usage

Running the image without a command displays the jawm help:

```bash
docker run --rm mpgagebioinformatics/jawm:latest
```

Check the installed jawm version:

```bash
docker run --rm \
  mpgagebioinformatics/jawm:latest \
  jawm --version
```

Open an interactive Bash shell:

```bash
docker run --rm -it \
  mpgagebioinformatics/jawm:latest \
  bash
```

Other included commands can be called in the same way:

```bash
docker run --rm \
  mpgagebioinformatics/jawm:latest \
  python --version
```

## Run a Workflow

Mount the current directory at `/workspace` to make local workflows, input files, outputs and logs available to the container:

```bash
docker run --rm -it \
  -v "$PWD:/workspace" \
  mpgagebioinformatics/jawm:latest \
  jawm ./workflow.py
```

The image uses `/workspace` as its default working directory. Any results written there remain in the current host directory after the temporary container exits.

Remote modules work in the same way:

```bash
docker run --rm -it \
  -v "$PWD:/workspace" \
  mpgagebioinformatics/jawm:latest \
  jawm jawm_demo
```

jawm retrieves the module, runs it from the mounted working directory and retains its outputs and logs on the host.

## Run Docker-Based Processes

The Docker client inside the jawm image can communicate with the host Docker daemon through its Unix socket. This allows a process configured with `environment="docker"` to launch its own container:

```bash
docker run --rm -it \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD:$PWD" \
  -w "$PWD" \
  mpgagebioinformatics/jawm:latest \
  jawm ./workflow.py
```

This is Docker-outside-of-Docker: the jawm container and the process container are siblings managed by the host Docker daemon.

```text
Host Docker daemon
├── jawm container
└── process container
```

The working directory is mounted at the same absolute path inside the jawm container because the host Docker daemon must be able to resolve every path that jawm passes to the process container. A different container-only path, such as `/workspace`, may not exist from the host daemon's perspective.

For a complete tested workflow, see [Run FastQC Using the jawm Docker Image](../examples/docker.md).

## Docker Socket Security

Mounting `/var/run/docker.sock` gives the jawm container control over the host Docker daemon. A process with access to this socket can start privileged containers, mount host paths and modify Docker resources.

Only mount the socket when Docker-backed processes are required, and only use it with trusted images and workflows. The socket is not needed when jawm runs ordinary local commands entirely inside its own container.

## Persistent jawm Cache

With `--rm`, the container's internal Git cache is removed when the container exits. Workflow outputs and logs in the mounted working directory are unaffected.

To retain the internal jawm cache between runs, mount a named volume at `/root/.jawm`:

```bash
docker volume create jawm-cache

docker run --rm -it \
  -v "$PWD:/workspace" \
  -v jawm-cache:/root/.jawm \
  mpgagebioinformatics/jawm:latest \
  jawm jawm_demo
```

## Inspect the Image Definition

The Dockerfile used to build the image is included for inspection and documentation:

```bash
docker run --rm \
  mpgagebioinformatics/jawm:latest \
  cat /usr/share/doc/jawm/Dockerfile
```

The source Dockerfile is also available in the repository under `resources/docker/Dockerfile`.

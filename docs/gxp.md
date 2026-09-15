# GxP

jawm is designed to support traceability, reproducibility, and evidence retention in GxP workflows. These technical features do not by themselves make a workflow or deployment GxP-compliant. The user using jawm remains responsible for validation, approved procedures, access control, review, retention, and any required electronic signatures.

## Execution records

Each `Process` receives a log folder under `logs/` (or the directory selected with `-l` / `logs_directory`), named `<process_name>_<YYYYMMDD>_<HHMMSS>_<identifier>` where the `identifier` encodes the process parameters from defaults, Python arguments, YAML configuration and applicable overrides, including command-line overrides. For example:

```text
fastqc_20260623_123454_e4c18e6bw1
│      │        │      └── e4c18e (parameter hash) + 6bw1 (random suffix)
│      │        └── 12:34:54
│      └── 2026-06-23
└── process name
```

The timestamp is the local date and time when the `Process` instance is created. The 10-character identifier is generated at that point as follows:

1. jawm merges the process parameters from defaults, Python arguments, YAML configuration and applicable overrides, including command-line overrides. It excludes `resume`, `when` and `desc`, applies any explicit hash selectors, sorts the remaining top-level parameter items, and feeds their Python `repr(...)` representation, encoded as bytes, into SHA-256. Normalized selector policies and successfully requested file-content digests also contribute to the hash. The remaining parameters include inline `script` text, supplied variables, container settings and path strings.
2. It also feeds in content digests for referenced `script_file`, `param_file` and `var_file` values. These digests cover byte sizes and SHA-256 content hashes; names are omitted by default. Directory selection is non-recursive: `param_file` includes `.yaml` / `.yml` files, while `var_file` includes `.yaml`, `.yml`, `.rc`, `.env` and `.conf` files. Explicitly selected files are included regardless of extension.
3. It takes the first **six hexadecimal characters** of the resulting SHA-256 digest and appends **four random lowercase letters or digits**. In this example, `e4c18e` is the parameter-derived prefix and `6bw1` is the random suffix.

Repeated runs with the same hash inputs normally share the six-character prefix but receive a new random suffix. The prefix is calculated before script placeholders are expanded; it is not a checksum of the final `.script` file or of every input/output file. Path changes can affect it, and Python objects such as callables can have representations that vary between runs. If a referenced-file digest cannot be calculated, that digest is omitted; if parameter-hash generation itself fails, jawm falls back to a fully random 10-character identifier. Use the file hashes described under [Inputs / Outputs](#inputs-outputs) to track data content; the short folder identifier alone does not establish content identity.

For processes that must run under different filesystem layouts, `hash_exclude` can omit explicitly selected machine-specific values from the parameter-derived prefix. `hash_include` can replace a selected file path with its content digest, causing a later run to receive a different prefix when that input file changes while remaining stable when identical content is relocated. These controls do not change the actual process configuration, variable substitution, or generated scripts and commands. They support a portable and auditable process identity without replacing the full file-content hashes under `scope: hash`.

Resume matching uses the process name and six-character parameter-hash prefix and only reuses a successfully completed run. `hash_include` is recalculated when a new `Process` is created; the hash and log folder do not change between retry attempts of the same instance.

A typical completed FastQC process folder contains:

```text
logs/fastqc_20260623_123454_e4c18e6bw1/
├── fastqc.script
├── fastqc.command
├── fastqc.output
├── fastqc.error
├── fastqc.exitcode
└── fastqc.id
```

| File | Contents |
| --- | --- |
| `fastqc.script` | The generated script after variable substitution. When `script_file` is used, it contains the resolved script and a comment identifying the original file path. |
| `fastqc.command` | The launch or submission command, including container or script wrappers where applicable. |
| `fastqc.output` | Captured standard output. |
| `fastqc.error` | Captured standard error, including tool progress messages and warnings as well as errors. |
| `fastqc.exitcode` | The recorded exit status, such as `0` for success; Slurm can retain a value such as `7:0`. |
| `fastqc.id` | The local operating-system process ID, Slurm job ID or Kubernetes Job name. |

Depending on the executor and options, the process folder can also contain a Slurm submission script (`fastqc.slurm`), a Kubernetes manifest (`fastqc.k8s.json`) and apply response (`fastqc.kubectl_apply.log`), or resource measurements (`stats.json`). Scientific results, such as FastQC reports, remain in the output directories specified by the script.

When a retry actually occurs, existing records from the failed attempt are copied on a best-effort basis to `attempts/attempt-<number>/` before the next attempt starts. Ordinary runs create no `attempts/` directory, and the final attempt remains in the top-level files. These copies preserve jawm-owned execution records, not scientific outputs or external scheduler records; see [Retry attempt records](debug/logs.md#retry-attempt-records).

At the surrounding `logs/` level, `jawm_runs/` stores CLI run transcripts, and `jawm_hashes/` stores run hash history and any configured `scope: hash` baselines and manifests. See [Log Structure](debug/logs.md) for the complete layout.

## Inputs / Outputs

Use `scope: hash` to record the identity of selected inputs, outputs, workflow files, and downloaded reference data. At the end of the workflow, jawm calculates a full SHA-256 content hash and records the combined value, its history, and a per-file diagnostic manifest.

```yaml
- scope: hash
  include:
    - ./fastqc_output/my_test_file_1_fastqc/fastqc_data.txt
    - <path_to_raw_data>/*.fastq.gz
  consider_name: false
  overwrite: false
```

With the default `consider_name: false`, identical file content can be relocated without changing the combined hash. Set it to `true` when relative names and paths are part of the expected identity. `overwrite: false` keeps the first stored value as the comparison baseline. A `reference` value can enforce an approved SHA-256 hash; a mismatch or missing included path makes the CLI exit with code `73`. See [`scope: hash`](config/yaml.md#scope-hash) for the complete policy.

## Reference data

Remote data fetched inside a script is not automatically content-hashed. Save regulated reference data to a managed file, record its source URL or accession and release/version, and include the downloaded file under `scope: hash`. If a later process must rerun when that file changes, also select its process parameter with `hash_include`. Where retrieval time matters, record it explicitly in the workflow output or run transcript.

## Versioned workflows

Use versioned workflows and pin remote modules to an immutable commit or an approved release:
```
jawm jawm_fastqc@6c73866 test \
  -p ./fastqc.yaml \
  -l ./logs
```

Changes to the staged version get reported in the log file:

```text
[2026-07-29 12:31:58] - INFO - jawm.cli|fastqc :: [git] Found git stamp commit: 6c738660
[2026-07-29 12:31:58] - WARNING - jawm.cli|fastqc :: [git] Local directory modified since export of commit 6c738660
```

For example, this warning appears if a file in the locally exported workflow is edited after export. jawm compares file modification times with the `.commit` stamp and logs the first eight characters of the recorded commit. This is a timestamp-based check: it does not list changed files or verify their contents against Git, and the warning does not stop execution.

## Environment log

When a workflow is run through the `jawm` CLI, its transcript contains an environment report, for example:

```text
[2026-07-29 12:31:58] - INFO - jawm.cli|fastqc :: [git] Found git stamp commit: 6c73866
[2026-07-29 12:31:58] - INFO - jawm.cli|fastqc :: [sys] jawm: 0.1.0
[2026-07-29 12:31:58] - INFO - jawm.cli|fastqc :: [sys] Python: 3.10.12
[2026-07-29 12:31:58] - INFO - jawm.cli|fastqc :: [sys] OS: Linux-5.15.0-177-generic-x86_64-with-glibc2.35
[2026-07-29 12:31:58] - INFO - jawm.cli|fastqc :: [sys] Machine/Arch: x86_64
[2026-07-29 12:31:58] - INFO - jawm.cli|fastqc :: [sys] Docker: Docker version 25.0.5, build 5dc9bcc
[2026-07-29 12:31:58] - INFO - jawm.cli|fastqc :: Running jawm module: /path/to/jawm_fastqc/fastqc.py
```

From this part of the log, the user can recover:

- the workflow commit: `6c73866`
- the JAWM release: `0.1.0`
- the Python release: `3.10.12`
- the operating system and architecture
- the execution tool used for the container
- the resolved workflow module path

We recommend running each workflow in a dedicated Python environment, such as a `venv` or Conda environment, to keep its dependencies separate from other projects. Record the Python version and pin the versions of jawm and its dependencies in a requirements file or environment lock file. Keep this file under version control alongside the workflow so the environment can be recreated for later runs.

The process hash is not a readable snapshot of the effective configuration. Retain every parameter and variable file passed with `-p` and `-v`, the exact CLI invocation and overrides, and the applicable environment or dependency lock file. Timestamps use the host clock, so regulated deployments should maintain synchronized clocks and record the applicable timezone.

## Container-based Process executions

Developers should ensure that every data analysis process uses a container and explicitly configures the relevant `jawm.Process` arguments. This keeps the analysis tools and their dependencies in a defined software environment that can be reused across runs.

For local and Slurm execution, `environment` selects the container runtime: `environment="docker"` uses Docker, while `environment="apptainer"` uses Apptainer (`"singularity"` is also accepted). The `container` argument identifies the image to run, such as `container="mpgagebioinformatics/fastqc:0.11.9"` for Docker or `container="/containers/fastqc-0.11.9.sif"` for Apptainer. Both arguments must be set to enable container execution: `environment` defaults to `"local"`, and requesting a container runtime without supplying `container` makes jawm fall back to local execution.

jawm resolves the process script and constructs the corresponding `docker run` or `apptainer exec` command, including configured mounts and environment variables, to execute that script inside the selected image. The generated script and launch command are recorded in the process log folder. The `manager` argument separately selects where the job is launched. With `manager="kubernetes"`, `container` specifies the Kubernetes Job's image directly; `environment` does not select a Docker or Apptainer wrapper for that job, and the generated Job manifest records the container configuration.

For reproducible runs, use a fixed image identity: pin registry images by digest (`image@sha256:<digest>`) or retain and hash the exact Apptainer `.sif` file. A version tag is useful for readability but can be reassigned to different image contents. Keep the container configuration under version control with the workflow, and avoid installing unpinned dependencies during execution. Combine the fixed software environment with versioned workflow code, hashed inputs and reference data, recorded parameters, and fixed random seeds where applicable to make analysis results reproducible.

## Validation and testing

`validation="strict"` can detect common process configuration problems before execution, and `jawm-test` can compare selected output hashes with approved regression references across configured environments. These are useful verification controls, but they do not replace documented computerized-system validation, change control, user training, or review procedures required by the organization.

## Archiving

After a workflow run such as:

```bash
jawm jawm_fastqc@6c73866 test \
  -p ./fastqc.yaml \
  -l ./logs
```

keep **both `jawm_fastqc/` and `logs/`**, together with every parameter and variable file used for the run, the exact invocation and overrides, and the environment lock file. The workflow folder preserves the staged workflow code and its version stamp; the logs preserve execution scripts, commands, statuses, histories and any failed-attempt copies made before retries. Keep the complete folders, including hidden files and any `attempts/` subdirectories.

Once the workflow and all child processes have finished, create a separate ZIP file for each folder and copy the configuration into a new archive directory:

```bash
archive_dir=$(mktemp -d "./fastqc-archive.XXXXXX")
zip -r "$archive_dir/jawm_fastqc.zip" jawm_fastqc/
zip -r "$archive_dir/logs.zip" logs/
cp fastqc.yaml "$archive_dir/fastqc.yaml"

# Check that both ZIP files can be read without errors.
unzip -t "$archive_dir/jawm_fastqc.zip"
unzip -t "$archive_dir/logs.zip"
```

Use a separate archive for each run so later executions cannot replace earlier evidence. Retain any input data, reference data and scientific outputs stored outside these folders as well, or record their locations in the managed archive.

You can keep the two ZIP files and configuration together in a Git repository. For example, initialise the new archive directory as a repository and commit the archived evidence:

```bash
git init "$archive_dir"
git -C "$archive_dir" add jawm_fastqc.zip logs.zip fastqc.yaml
git -C "$archive_dir" commit -m "Archive FastQC workflow 6c73866, logs and configuration"
```

Alternatively, retain the ZIP files and configuration in archive storage and generate SHA-256 checksums. For example, `shasum -a 256 jawm_fastqc.zip logs.zip fastqc.yaml > SHA256SUMS`, run inside the archive directory, creates a checksum list that can later be checked with `shasum -a 256 -c SHA256SUMS`.

Keep the checksum list alongside the retained files and preserve a trusted copy separately or in version control. ZIP files, checksums, and a normal Git repository can detect or track changes but do not by themselves provide immutable retention, access control, electronic signatures, or user attribution. Apply the organization's approved retention period, backup, access, review, and immutable-storage controls. Because commands, manifests, stdout, and stderr may contain sensitive values, protect the complete archive accordingly.

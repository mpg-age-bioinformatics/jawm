# Reproducing the JAWM FastQC Example

Reproducing an analysis requires two separate checks:

1. **Execution provenance:** use the same Python, JAWM, workflow commit, parameters, dependencies, container, input data, and execution backend.
2. **Result validation:** compare the content of the new outputs with a hash accepted from the original run.

This example uses the [`jawm_fastqc`](https://github.com/mpg-age-bioinformatics/jawm_fastqc) module. Its test workflow downloads one FASTQ file, runs FastQC in a container, extracts the FastQC report, and uses `scope: hash` to calculate a SHA-256 hash of `fastqc_data.txt`.

## Example Layout

Start in a new analysis directory:

```bash
mkdir fastqc-reproducibility
cd fastqc-reproducibility
mkdir provenance
```

The completed example will have this layout:

```text
fastqc-reproducibility/
├── .env_jawm/
├── jawm_fastqc/
│   ├── fastqc.py
│   ├── test/
│   │   ├── data.txt
│   │   ├── test-input/
│   │   ├── test-output/
│   │   ├── tests.txt
│   │   └── yaml/test.yaml
│   └── yaml/
├── provenance/
└── reproduced-logs/
```

## 1. Create a Python Environment and Install JAWM

A virtual environment isolates JAWM and its Python dependencies from system packages:

```bash
python3.11 -m venv --without-pip .env_jawm
curl -fsSLO https://bootstrap.pypa.io/get-pip.py
.env_jawm/bin/python get-pip.py
source .env_jawm/bin/activate
pip --version
pip install --upgrade pip setuptools wheel
```

The `python3.11` command is an example. Record and later reuse the same Python patch release when possible.

Install JAWM from a release tag:

```bash
pip install \
  "jawm[full] @ git+https://github.com/mpg-age-bioinformatics/jawm.git@0.1.0"
```

For stronger reproducibility, install JAWM from a full 40-character commit:

```bash
pip install \
  "jawm[full] @ git+https://github.com/mpg-age-bioinformatics/jawm.git@739c2fc561559bd8e254061fd9822811ffb3725b"
```

Replace the example commit with the JAWM commit that you intend to use. Confirm that the new environment is active:

```bash
command -v python
command -v jawm
python --version
jawm --version
```

## 2. Obtain and Pin the FastQC Workflow

Clone the workflow repository:

```bash
git clone \
  https://github.com/mpg-age-bioinformatics/jawm_fastqc.git
```

Record the full commit before running the analysis:

```bash
git -C jawm_fastqc rev-parse HEAD \
  > provenance/workflow.commit

git -C jawm_fastqc remote get-url origin \
  > provenance/workflow.repository

git -C jawm_fastqc status --porcelain \
  > provenance/workflow.status
```

An empty `provenance/workflow.status` means that the checkout has no uncommitted changes. A reproducibility record should contain a full commit SHA and a clean status.

If reproducing a previously recorded run, check out its exact commit:

```bash
workflow_commit="$(cat provenance/workflow.commit)"

git -C jawm_fastqc checkout --detach "$workflow_commit"
git -C jawm_fastqc rev-parse HEAD
git -C jawm_fastqc status --porcelain
```

The reported `HEAD` must equal the recorded commit, and the status command should print nothing.

Use a full commit rather than a moving branch such as `main`.

## 3. Download and Verify the Test Input

The workflow repository contains `test/data.txt`:

```text
13fb536154e7cf36a394d9b09ff99b7a  my_test_file_1.fastq.gz  https://ndownloader.figshare.com/files/57999445
```

Each non-comment line has three whitespace-separated fields:

```text
<MD5 checksum>  <file name>  <download URL>
```

The 32-character value in this file is an **MD5 input checksum**. It is different from the SHA-256 output hash generated later by JAWM.

Download the data from inside the module:

```bash
cd jawm_fastqc
jawm-test --runner download
```

The short form is equivalent:

```bash
jawm-test -r download
```

`jawm-test` reads `test/data.txt`, downloads the file to:

```text
test/test-input/my_test_file_1.fastq.gz
```

It then verifies the downloaded file with `md5sum` on Linux or `md5` on macOS. A checksum mismatch stops the download command with exit code `1`.

Run the download command again whenever the input needs to be verified. Existing files are not downloaded again, but their MD5 checksums are still checked:

```bash
jawm-test --runner download
```

Return to the parent analysis directory when inspecting provenance files:

```bash
cd ..
```

## 4. Understand the FastQC Workflow and Parameters

The process is defined in `jawm_fastqc/fastqc.py`. Its important reproducibility settings include:

- process name: `fastqc`
- container: `mpgagebioinformatics/fastqc:0.11.9`
- default environment: Docker
- command template: `fastqc {{extra_args}} -t {{cpus}} -o {{fastqc_output}} {{f}}`

The test configuration is `jawm_fastqc/test/yaml/test.yaml`:

```yaml
- scope: process
  name: fastqc
  parallel: false
  var:
    mk.fastqc_output: "./test/test-output"
    map.f: "./test/test-input/my_test_file_1.fastq.gz"

- scope: hash
  include: ./test/test-output/my_test_file_1_fastqc/fastqc_data.txt
  overwrite: true
```

The `test` workflow runs FastQC and extracts:

```text
test/test-output/my_test_file_1_fastqc/fastqc_data.txt
```

The `scope: hash` block is evaluated after all processes finish. JAWM therefore hashes the completed report rather than the workflow source or an intermediate file.

The container tag is recorded in the rendered launch command, but tags can be changed in a registry. For a long-lived reproducibility record, use or record an immutable container digest in addition to the tag.

## 5. Run the Original Analysis

Run the test workflow from the module directory:

```bash
cd jawm_fastqc

jawm fastqc.py test \
  -p ./test/yaml/test.yaml \
  -l ./test/logs
```

Save the exact invocation as part of the provenance record:

```bash
cp ./test/yaml/test.yaml \
  ../provenance/test.original.yaml
```

The run creates:

```text
test/logs/
├── fastqc_<datetime>_<hash>/
│   ├── fastqc.command
│   ├── fastqc.error
│   ├── fastqc.exitcode
│   ├── fastqc.id
│   ├── fastqc.output
│   └── fastqc.script
├── jawm_hashes/
│   ├── fastqc.hash
│   ├── fastqc_hash_manifest.json
│   ├── fastqc_input.history
│   └── fastqc_user_defined.history
└── jawm_runs/
    └── fastqc_<timestamp>.log
```

Check that the FastQC process succeeded:

```bash
find ./test/logs -name fastqc.exitcode -print \
  | sort \
  | while IFS= read -r exitcode_file; do
  printf "%s: " "$exitcode_file"
  cat "$exitcode_file"
  printf "\n"
done
```

Every exit-code file for the accepted run should contain `0`.

## 6. Collect Provenance from the Logs

Find the most recent CLI transcript:

```bash
run_log="$(ls -1t ./test/logs/jawm_runs/fastqc_*.log | head -1)"
echo "$run_log"
```

The `[sys]` lines record the JAWM version, Python version, operating system, architecture, and detected Docker, Apptainer, Slurm, or Kubernetes client versions:

```bash
grep '\[sys\]' "$run_log"
```

The `[git]` lines report the workflow commit in abbreviated form and whether its checkout had uncommitted changes:

```bash
grep '\[git\]' "$run_log"
```

The transcript only displays an abbreviated workflow commit. Keep the full value already recorded in `provenance/workflow.commit`.

Each process log adds more detail:

| File | Reproducibility information |
| --- | --- |
| `fastqc.script` | Fully rendered FastQC script after variable substitution. |
| `fastqc.command` | Exact launch command, including the Docker invocation and image tag. |
| `fastqc.output` | Standard output from FastQC. |
| `fastqc.error` | Standard error and diagnostics. |
| `fastqc.exitcode` | Final exit code. |
| `fastqc.id` | Runtime process identifier. |

Inspect the rendered script and command from the latest process:

```bash
process_log="$(ls -1dt ./test/logs/fastqc_*_* | head -1)"

cat "$process_log/fastqc.script"
cat "$process_log/fastqc.command"
cat "$process_log/fastqc.output"
cat "$process_log/fastqc.error"
```

The process-directory identifier and `fastqc.id` help track an execution, but neither is a checksum of its scientific result.

Copy the full workflow commit, logs, and accepted configuration to durable storage.

## 7. Save the Python and JAWM Installation

While the original virtual environment is active, record its interpreter and packages:

```bash
cd ..

python --version \
  > provenance/python.version 2>&1

python -c 'import sys; print(sys.executable); print(sys.version)' \
  > provenance/python.details

jawm --version \
  > provenance/jawm.version

pip freeze --all \
  > provenance/requirements.freeze.txt

pip show jawm \
  > provenance/jawm.package.txt
```

If JAWM was installed from Git, `requirements.freeze.txt` will normally contain its direct URL and resolved commit. Check it:

```bash
grep -Ei '^(jawm|.*jawm.*@)' \
  provenance/requirements.freeze.txt
```

A JAWM package version alone may not uniquely identify a development commit. If JAWM was installed from a local checkout, record that checkout separately:

```bash
git -C /path/to/jawm rev-parse HEAD \
  > provenance/jawm.commit

git -C /path/to/jawm status --porcelain \
  > provenance/jawm.status

git -C /path/to/jawm remote get-url origin \
  > provenance/jawm.repository
```

For an exact restoration, `jawm.commit` should contain a full SHA and `jawm.status` should be empty.

Also preserve:

- `jawm_fastqc/test/data.txt`
- `jawm_fastqc/test/yaml/test.yaml`
- `jawm_fastqc/test/tests.txt`
- the complete `jawm_fastqc/test/logs/` directory
- input and reference-data checksums
- container image digests
- relevant environment variables, locale, timezone, CPU count, and Docker settings

## 8. Accept the Original Output Hash

The original configuration uses:

```yaml
overwrite: true
```

This is convenient while generating a new test baseline, but it allows each run to replace that baseline. After reviewing the original FastQC result, copy its SHA-256 hash into the provenance directory:

```bash
cp jawm_fastqc/test/logs/jawm_hashes/fastqc.hash \
  provenance/fastqc-output.sha256

cp jawm_fastqc/test/logs/jawm_hashes/fastqc_hash_manifest.json \
  provenance/fastqc-output-manifest.json
```

The current module test records the expected hash in `test/tests.txt` as well:

```text
#jawm_file.py;workflow;parameters.file1.yaml,parameters.file2.yaml;"Test name";test_hash
fastqc.py;test;./test/yaml/test.yaml;"Main workflow test";903c31655306e9af2c208b47f520e07c0aa8ad106fd1e934ad6ff5ceee614d07
```

That value is the expected SHA-256 result for the selected `fastqc_data.txt` content. Review a newly generated baseline before committing or archiving it; accepting an incorrect output hash makes later incorrect results appear reproducible.

The files under `test/logs/jawm_hashes/` have different purposes:

- `fastqc.hash` is the stored baseline for the selected output.
- `fastqc_user_defined.history` records the newly calculated output hash for every run.
- `fastqc_hash_manifest.json` records the hash of each included file for mismatch diagnosis.
- `fastqc_input.history` is JAWM’s automatic run signature. It helps trace runs, but it is not a replacement for the explicit FastQC output hash.

## 9. Reinstall the Environment

To reproduce the analysis later, start from the same Python patch release and create a new environment:

```bash
python3.11 -m venv --without-pip .env_jawm_reproduced
curl -fsSLO https://bootstrap.pypa.io/get-pip.py
.env_jawm_reproduced/bin/python get-pip.py
source .env_jawm_reproduced/bin/activate
pip --version
pip install --upgrade pip setuptools wheel
pip install -r provenance/requirements.freeze.txt
```

Review `requirements.freeze.txt` first. Local paths, editable installations, and unpinned URLs are not portable. Replace the JAWM entry with its recorded full Git commit if necessary:

```text
jawm[full] @ git+https://github.com/mpg-age-bioinformatics/jawm.git@739c2fc561559bd8e254061fd9822811ffb3725b
```

Compare the restored package declarations with the original:

```bash
pip freeze --all \
  > provenance/requirements.reproduced.txt

diff -u \
  provenance/requirements.freeze.txt \
  provenance/requirements.reproduced.txt
```

No diff confirms the same declared Python packages. It does not guarantee identical operating-system libraries, container content, or hardware behavior.

## 10. Restore the Exact Workflow and Input

Clone the saved repository and check out the recorded commit:

```bash
workflow_repository="$(cat provenance/workflow.repository)"
workflow_commit="$(cat provenance/workflow.commit)"

git clone "$workflow_repository" jawm_fastqc-reproduced
git -C jawm_fastqc-reproduced checkout --detach "$workflow_commit"
git -C jawm_fastqc-reproduced rev-parse HEAD
git -C jawm_fastqc-reproduced status --porcelain
```

Download and verify the same input:

```bash
cd jawm_fastqc-reproduced
jawm-test --runner download
cd ..
```

Because `test/data.txt` belongs to the pinned workflow commit, this uses the recorded URL, filename, and expected MD5 checksum.

## 11. Validate the Rerun with `scope: hash`

Copy the original test configuration and add the accepted output hash directly to its `scope: hash` block as `reference`:

```bash
cp provenance/test.original.yaml \
  jawm_fastqc-reproduced/test/yaml/reproduce.yaml
```

Edit `jawm_fastqc-reproduced/test/yaml/reproduce.yaml` so its hash block is:

```yaml
- scope: hash
  include: ./test/test-output/my_test_file_1_fastqc/fastqc_data.txt
  recursive: true
  overwrite: false
  reference: ../provenance/fastqc-output.sha256
```

The reference path is resolved from the directory in which `jawm` is invoked. The example runs from `jawm_fastqc-reproduced/`, so `../provenance/fastqc-output.sha256` points to the original accepted hash.

Here, `scope: hash` defines both sides of the validation: `include` selects the reproduced output, and `reference` supplies the accepted SHA-256 value. `overwrite: false` prevents later runs from replacing JAWM's local `.hash` record; it does not alter the external reference file.

Ensure the reproduced output directory is empty:

```bash
test ! -e jawm_fastqc-reproduced/test/test-output
```

This matters because `fastqc.py` has a `when` condition that can skip FastQC when an output already exists.

Run the exact workflow commit with the restored environment and input:

```bash
cd jawm_fastqc-reproduced

jawm fastqc.py test \
  -p ./test/yaml/reproduce.yaml \
  -l ../reproduced-logs
```

On success, the transcript contains:

```text
[hash] Generated user-defined hash matched reference
```

If the result differs, JAWM exits with code `73` and reports:

```text
[hash] Generated user-defined hash does NOT match reference
```

Inspect the hash messages:

```bash
grep '\[hash\]' ../reproduced-logs/jawm_runs/*.log
```

Inspect the original and reproduced per-file manifests when diagnosing a mismatch:

```bash
python -m json.tool \
  ../provenance/fastqc-output-manifest.json

python -m json.tool \
  ../reproduced-logs/jawm_hashes/fastqc_hash_manifest.json
```

Manifest keys are absolute file paths, so they will differ when the restored workflow is in a different directory. Compare the SHA-256 value for `fastqc_data.txt`, not its parent path. When a baseline manifest comes from the same path, JAWM can also label files as `CHANGED`, `NEW`, or `REMOVED` in the transcript.

The newly calculated hash, history, and manifest are still written under `reproduced-logs/jawm_hashes/`. No file needs to be copied into that directory before the run. The `reference` field inside `scope: hash` is the authoritative comparison and makes a mismatch produce a nonzero exit status.

## Optional: Validate with `jawm-test`

The module already has a committed expected hash in `test/tests.txt`. From the restored workflow directory, `jawm-test` can download the data, run the declared test, and compare the generated output hash with that expected value:

```bash
cd jawm_fastqc-reproduced
rm -rf ./test/test-output
jawm-test
```

This is convenient for module development and CI. The explicit `reference` workflow above is useful when validating against a hash preserved with a particular analysis rather than the hash currently committed in the module’s `tests.txt`.

## Reproducibility Checklist

Before claiming that the rerun reproduced the original FastQC analysis, verify:

- the Python version, operating system, and architecture match the original transcript
- JAWM is installed from the recorded full commit or immutable release
- `jawm_fastqc` is at the recorded full commit and has no local modifications
- `test/data.txt` is unchanged and the input passes its MD5 check
- the parameter YAML and Python package declarations match
- the FastQC container version or, preferably, image digest matches
- `fastqc.exitcode` contains `0`
- the `scope: hash` result matches `provenance/fastqc-output.sha256`

For more detail, see [FastQC](fastqc.md), [Log Structure](../debug/logs.md), [YAML Config](../config/yaml.md), [Run a Module](../module/run.md), and [`jawm-test`](../cli/jawm-test.md).

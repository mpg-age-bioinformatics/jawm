# Test a Module

Every published module is expected to have a `test` sub-workflow (not a strict requirement) — a lightweight entry point that verifies the module is correctly wired, without needing real production data. On top of that, `jawm-test` provides hash-based regression testing that can run locally or in CI.

This page covers both: writing good test sub-workflows, and using `jawm-test` to make them reproducible.

---

### The `test` sub-workflow

By convention, every jawm module exposes a `test` workflow that:

- Requires **no real input data** — either generates synthetic data or uses a tiny bundled fixture
- Completes quickly
- Confirms the full code path runs without errors (tools are on PATH, scripts are correct, containers pull, etc.)

```python
if jawm.utils.workflow(select=workflows, workflows=["test"]):

    smoke = jawm.Process(
        name="test_smoke",
        script="""#!/bin/bash
set -euo pipefail

# Verify tools are available
bwa 2>&1 | grep -q "Program: bwa" || { echo "bwa not found"; exit 1; }
samtools --version | head -1

# Run a minimal alignment on synthetic data
echo ">ref\nACGTACGTACGT" > /tmp/test_ref.fa
bwa index /tmp/test_ref.fa 2>/dev/null
echo "@r1\nACGTACGT\n+\nIIIIIIII" > /tmp/test_reads.fq
bwa mem /tmp/test_ref.fa /tmp/test_reads.fq > /tmp/test_out.sam
echo "Smoke test passed"
""",
    )
    smoke.execute()

jawm.Process.wait([smoke.hash])
```

The `test` workflow should be included in `main` — users who run `jawm mymodule.py` without specifying a workflow get `main`, which runs everything including tests. This is the convention:

```python
# main runs everything, including test
if jawm.utils.workflow(select=workflows, workflows=["main", "align"]):
    ...

if jawm.utils.workflow(select=workflows, workflows=["main", "qc"]):
    ...

if jawm.utils.workflow(select=workflows, workflows=["main", "test"]):
    ...
```

Running just the test:

```bash
jawm mymodule.py test
```

---

### Setting up `jawm-test`

`jawm-test` provides structured, repeatable testing. After each run it reads the output hash that `jawm` writes to `logs/jawm_hashes/<module>.hash` and compares it against a stored reference in `test/tests.txt`. If the hashes match, the test passes. If they differ, the test fails — signalling that the module's output has changed.

The scaffold from `jawm-dev init` already creates both files. Here's how to populate them.

#### `test/tests.txt`

Semicolon-separated, one test per line. The first line is a header and is preserved as-is.

```
# module ; workflow ; params ; "name" ; hash
mymodule.py ; test  ;                        ; "smoke test"         ;
mymodule.py ; align ; yaml/docker.yaml       ; "alignment"          ;
mymodule.py ; main  ; yaml/docker.yaml       ; "full pipeline"      ;
```

Leave the hash field empty on first run — `jawm-test --override` fills it in automatically.

| Field | Description |
|-------|-------------|
| `module` | Path to the module file |
| `workflow` | Sub-workflow name |
| `params` | Arguments after `-p` — can include `-v` and other flags |
| `"name"` | Human-readable label (keep the quotes) |
| `hash` | Expected output hash; empty = capture on first run |

#### `test/data.txt`

If your tests need input files, list them here. On each run, `jawm-test` downloads missing files, verifies their MD5, and auto-extracts archives.

```
d41d8cd98f00b204e9800998ecf8427e  test/data/sample_R1.fq.gz  https://example.com/data/sample_R1.fq.gz
a87ff679a2f3e71d9181a67b7542122c  test/data/ref.tar.gz       https://example.com/data/ref.tar.gz
```

| Field | Description |
|-------|-------------|
| `md5sum` | Expected MD5 of the downloaded file |
| `filename` | Local path to save to |
| `url` | Download URL |

Archives are handled automatically:
- `.tar.gz` / `.tgz` → extracted
- `.fastq.gz` → left compressed
- other `.gz` → decompressed with `gunzip`

---

### Running tests

```bash
# First run — capture reference hashes
jawm-test --override

# Regular run — compare against stored hashes
jawm-test

# Continue past failures to see all results
jawm-test --ignore

# Download test data only (useful in CI pre-steps)
jawm-test --runner download
```

After `--override`, open `test/tests.txt` and verify the hashes look reasonable before committing them. The hash is your reference — committing a bad hash means future runs will pass against incorrect output.

---

### What the hash covers

After each `jawm` run, the CLI collects output files and writes a composite hash to:

```
logs/jawm_hashes/<module_name>.hash
```

Which files are included in the hash is controlled by `scope: hash` entries in your YAML parameter files:

```yaml
- scope: hash
  include:
    - "results/**"
    - "aligned/*.bam"
  exclude_dirs:
    - "logs"
  recursive: true
```

Without a `scope: hash` entry, jawm hashes a default set of output files. Being explicit about what to hash makes your tests stable — you avoid false failures from log files, timestamps, or intermediate files changing between runs.

---

### Testing with Docker or Apptainer

Most published modules run their `test` workflow inside a container. Pass the environment YAML when running:

```bash
# Test with Docker
jawm-test -y yaml/docker.yaml

# Test with Apptainer
jawm-test -y yaml/apptainer.yaml
```

The `-y` flag appends extra YAML files to every `jawm` call in the test run. This is the same as passing `-p yaml/docker.yaml` to each test manually, but done automatically for all tests in one go.

---

### CI integration

The `jawm-dev init` scaffold includes a ready-made `.github/workflows/test.yaml`. The core pattern is:

```yaml
- name: Run tests
  run: jawm-test --runner github -y yaml/docker.yaml
```

With `--runner github`, `jawm-test` reads `GITHUB_REF_NAME` and `GITHUB_REF_TYPE` from the Actions environment to determine the module version being tested. It writes `CODE_TAG` and `VERSION_TAG` to `$GITHUB_ENV` so downstream steps can reference them.

For manually dispatched runs where you want to test both the current commit and the latest release tag:

```yaml
- name: Run tests (dispatched)
  if: github.event_name == 'workflow_dispatch'
  run: jawm-test --runner github --dispatch -y yaml/docker.yaml
```

---

### Cross-version testing

`jawm-test` can run the same tests across multiple Python versions and multiple jawm versions. This is useful before publishing a new module version to confirm it works in the environments your users have.

```bash
# Test against Python 3.10 and 3.11, with jawm v1.2.0 and v1.3.0
jawm-test \
  -p 3.10.14 3.11.9 \
  -j v1.2.0 v1.3.0 \
  --jawm_repo github.com/mpg-age-bioinformatics/jawm.git \
  -y yaml/docker.yaml
```

`jawm-test` bootstraps pyenv if it is not installed, creates isolated virtualenvs named `py<python>-jawm.<jawm>`, and runs the full test matrix. Each combination is tested independently.

To skip a Python version that fails to install on your platform:

```bash
jawm-test -p 3.10.14 3.11.9 --skip_python_versions 3.10.14
```

---

### Updating hashes after intentional changes

When you change a module's logic and the output legitimately changes, update the stored hashes:

```bash
jawm-test --override
```

Then review the diff in `test/tests.txt` before committing — the hash change is your record that the output changed intentionally.

If you want to see which tests would fail before committing to an override:

```bash
jawm-test --ignore   # runs everything, reports mismatches, keeps stored hashes
```

---

### Tips for good tests

- **Keep the `test` workflow fast.** If it takes more than a minute it won't be run regularly. Use tiny synthetic inputs.
- **Test the actual code path.** A test that just runs `echo "ok"` verifies nothing. Run real tools on real (tiny) data.
- **Be explicit about what to hash.** A `scope: hash` YAML that targets your actual outputs gives you stable, meaningful assertions.
- **Commit both the test data checksums and the reference hashes.** Both live in `test/` and should be version-controlled alongside your module code.
- **Include `test` in `main`.** Anyone who runs `jawm mymodule.py` without arguments should get the test as part of the full pipeline run — this is the convention that makes modules trustworthy.

---

### See also

- [jawm-test reference](../cli/jawm-test.md) — full flag reference, file format details, CI integration
- [Develop a Module](develop.md) — writing the module, including setting up the `test` sub-workflow
- [jawm-dev lsvar](../cli/jawm-dev.md#lsvar) — finding variables in your module scripts

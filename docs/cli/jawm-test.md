# jawm-test

`jawm-test` is a bash-based advanced test runner for jawm modules. It runs the workflows you define in a tests file, compares the output hashes against stored reference values, and reports pass or fail. It is designed to work both locally during development and in CI (GitHub Actions).

```bash
jawm-test [options]
```

By default it uses your local `jawm` installation and system Python. Optionally it can manage multiple Python versions via pyenv and install specific jawm versions, making it useful for cross-version compatibility testing.

---

### How it works

1. **Download test data** (if `test/data.txt` exists) — files are fetched with `curl`, MD5-verified, and archives are auto-extracted
2. **Set up Python environments** — if you request non-system Python versions, pyenv is bootstrapped and virtualenvs are created
3. **Install jawm** — one or more jawm versions can be installed into each environment
4. **Determine module versions** — auto-detected from the current checkout, or explicit via `-m`
5. **Run each test** — for every Python × jawm × module version combination, runs `jawm <module> <workflow> -l <logs> -p <params>`
6. **Compare hashes** — reads the generated hash from `test/logs/jawm_hashes/<module>.hash` and compares it to the stored value in `tests.txt`
7. **Update or fail** — on mismatch, fails by default; with `--override`, updates the stored hash

---

### Prerequisites

`jawm-test` may requires the following tools to be available on `PATH` (based on the commands):

- `curl` — for downloading test data
- `tar`, `gunzip` — for extracting archives
- `git` — for checking out module versions and resolving tags
- `md5sum` (Linux) or `md5` (macOS) — for checksum verification
- `pyenv` — only needed if requesting non-`system` Python versions (bootstrapped automatically if missing)

---

### Quick start

```bash
# Run all tests (system Python, local jawm)
jawm-test

# First run — no stored hashes yet, capture them
jawm-test --override

# Keep going past failures (useful for seeing all failures at once)
jawm-test --ignore

# Download test data only, then exit
jawm-test --runner download
```

---

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-r`, `--runner` | `local` | Runner mode: `local`, `github`, or `download` |
| `-o`, `--override` | `false` | Overwrite stored hashes when a mismatch is detected |
| `--no-override` | — | Explicitly keep stored hashes (default behaviour) |
| `-i`, `--ignore` | `false` | Continue past failures and hash mismatches instead of exiting |
| `-y`, `--yaml` | — | Extra YAML files appended to every `jawm` call after `-p` |
| `-m`, `--module_versions` | auto | Explicit module versions/tags to test (skips auto-detection) |
| `-p`, `--python_versions` | `system` | Python version(s) to use. Non-`system` values are managed via pyenv |
| `--skip_python_versions` | — | Remove specific versions from the `-p` list |
| `-j`, `--jawm_versions` | `local` | jawm version(s) to install. Use `local` for the current installation |
| `--jawm_repo` | `github.com/mpg-age-bioinformatics/jawm.git` | Local path or Git repo to install jawm from |
| `-t`, `--tests_file` | `./test/tests.txt` | Path to the tests definition file |
| `--downloads_file` | `./test/data.txt` | Path to the test data downloads file |
| `-d`, `--dispatch` | `false` | Treat the run as dispatched (affects module tag selection) |
| `-h`, `--help` | — | Show help and exit |

#### `-r` / `--runner`

Controls how `jawm-test` operates:

- **`local`** (default) — runs from the current checkout. Module version is `"current"` by default; if `--dispatch` is set and a git tag exists, the latest tag is also tested.
- **`github`** — reads `GITHUB_REF_NAME` and `GITHUB_REF_TYPE` from the GitHub Actions environment to name versions. Writes `CODE_TAG` and `VERSION_TAG` to `$GITHUB_ENV`.
- **`download`** — downloads and verifies test data from `data.txt`, then exits without running any tests. Useful for pre-populating test data in CI.

#### `-o` / `--override`

When a test runs successfully but the generated hash differs from the stored one, `--override` updates `tests.txt` in place with the new hash. Use this after intentional changes to a module's output.

Without `--override`, a mismatch is treated as a test failure and exits with code `1`.

#### `-i` / `--ignore`

Continues running all tests even when a jawm run fails or a hash mismatches. Stored hashes are not updated unless `--override` is also set. Useful for seeing all failures in one pass rather than stopping at the first one.

#### `-y` / `--yaml`

Appends extra YAML files to every `jawm` invocation during testing. Useful for injecting environment-specific config (e.g. a Docker or Slurm YAML) on top of whatever params are defined in `tests.txt`.

```bash
jawm-test -y yaml/docker.yaml
jawm-test -y yaml/base.yaml yaml/override.yaml
```

#### `-p` / `--python_versions` and `-j` / `--jawm_versions`

For cross-version testing. Any Python version other than `"system"` is managed via pyenv — jawm-test bootstraps pyenv if it is not already installed, installs the requested Python versions, and creates virtualenvs named `py<python>-jawm.<jawm>`.

```bash
# Test against Python 3.10 and 3.11, with two jawm versions
jawm-test -p 3.10.14 3.11.9 -j v1.2.0 v1.3.0 \
  --jawm_repo github.com/mpg-age-bioinformatics/jawm.git
```

For local jawm installs from a directory:

```bash
jawm-test --jawm_repo ./jawm -p system
```

If `--jawm_repo` points to a local directory, `jawm-test` forces `--jawm_versions local` automatically.

---

### File formats

#### `test/tests.txt`

Defines the tests to run. Semicolon-separated, one test per line. The first line is treated as a header and preserved as-is.

```
# module ; workflow ; params ; "name" ; hash
mymodule.py ; test  ;                         ; "smoke test"     ;
mymodule.py ; main  ; yaml/docker.yaml        ; "full run"       ; abc123def456...
mymodule.py ; align ; yaml/docker.yaml -v vars.yaml ; "alignment" ; 789abc012def...
```

| Field | Description |
|-------|-------------|
| `module` | Path to the module file (e.g. `mymodule.py`) |
| `workflow` | Sub-workflow name to run (e.g. `main`, `test`, `align`) |
| `params` | Arguments passed after `-p` — may include additional flags like `-v` |
| `"name"` | Human-readable test name (kept in quotes) |
| `hash` | Expected output hash. Leave empty on the first run — `jawm-test` fills it in |

Lines starting with `#` and blank lines are ignored.

#### `test/data.txt`

Lists test input files that need to be downloaded before tests run. Space-separated, one file per line.

```
d41d8cd98f00b204e9800998ecf8427e  test/data/sample.fq.gz     https://example.com/sample.fq.gz
a87ff679a2f3e71d9181a67b7542122c  test/data/reference.tar.gz https://example.com/ref.tar.gz
```

| Field | Description |
|-------|-------------|
| `md5sum` | Expected MD5 checksum of the file |
| `filename` | Local path to save the file to |
| `url` | URL to download from |

Files are downloaded with `curl -L`. Archives are handled automatically:

- `.tar.gz` / `.tgz` → extracted with `tar -xzf`
- `.fastq.gz` → left compressed
- other `.gz` → decompressed with `gunzip`

If the file already exists locally, download is skipped but the MD5 is still verified. A checksum mismatch exits with code `1`.

---

### Where hashes come from

After each `jawm` run, the CLI writes a hash of the output files to:

```
<logs>/jawm_hashes/<module_name>.hash
```

`jawm-test` reads this file and compares it against the hash stored in `tests.txt`. This means the hash reflects the actual outputs produced by the module — not just whether the run succeeded, but whether the results are bit-for-bit reproducible.

The hash computation is controlled by `scope: hash` entries in your YAML parameter files — you can configure which files and directories are included. See the [Utils reference](../utils.md#hash_content) for details.

---

### Using jawm-test in CI

`jawm-test` is designed to drop into a GitHub Actions workflow. The `jawm_demo` template provides a ready-made `.github/workflows/test.yaml`. The key pattern is:

```yaml
- name: Run tests
  run: jawm-test --runner github -y yaml/docker.yaml
```

With `--runner github`, `jawm-test` reads `GITHUB_REF_NAME` and `GITHUB_REF_TYPE` to name the module version being tested and writes `CODE_TAG` / `VERSION_TAG` to `$GITHUB_ENV` for downstream steps.

For dispatched workflows (manual triggers), pass `--dispatch` to test both the current commit and the latest tag:

```yaml
- name: Run tests (dispatched)
  if: github.event_name == 'workflow_dispatch'
  run: jawm-test --runner github --dispatch -y yaml/docker.yaml
```

---

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All tests passed |
| `1` | One or more tests failed, hash mismatch, download error, or invalid arguments |

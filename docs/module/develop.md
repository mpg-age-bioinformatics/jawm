# Develop a Module

This page walks through how to write a jawm module from scratch — from the initial scaffold all the way to testing and publishing, with examples of ways to do that.

There is **no strict skeleton** you must follow. A jawm module is just a Python file that creates `Process` objects. The patterns shown here — `parse_arguments()`, `workflow()` gates, a `test/` directory — are conventions that make modules easy for others to run and test, but you're free to structure your code however works best for your project.

---

### Quick start with `jawm-dev init`

The fastest way to get started is the scaffolding command:

```bash
jawm-dev init myproject
```

This downloads the [`jawm_demo`](https://github.com/mpg-age-bioinformatics/jawm_demo) template, renames files and references to match your project name, initialises a Git repository, and (if credentials are available) creates a private remote on GitHub, GitLab, or Gitea.

```
jawm_myproject/
├── myproject.py                # main module file
├── submodules/
│   └── jawm_myproject_submodule/
│       └── myproject_submodule.py
├── scripts/                    # optional external scripts
├── yaml/                       # parameter YAMLs
├── test/
│   ├── tests.txt               # test definitions for jawm-test
│   └── data.txt                # test data checksums
└── .github/workflows/          # CI workflow
```

You can customise the Git server, user, and repository prefix:

```bash
# Local-only (no remote)
jawm-dev init myproject --server local

# GitLab with a custom org
jawm-dev init myproject --server gitlab.com --user my-org

# Custom prefix (default is jawm_)
jawm-dev init myproject --prefix wf_
```

The scaffold is just a starting point — feel free to rearrange, remove, or add whatever you need. There's nothing in jawm that requires this layout.

---

### A minimal module

At its simplest, a module is a Python file that creates one or more `Process` objects and calls `.execute()` on them:

```python
# align.py — a perfectly valid jawm module
import jawm

bwa = jawm.Process(
    name="bwa_mem",
    script="""#!/bin/bash
set -euo pipefail
bwa mem -t 8 {{genome}} {{reads_1}} {{reads_2}} \
  | samtools sort -o {{output_bam}}
""",
    var={
        "genome": "/data/ref/hg38.fa",
        "reads_1": "/data/reads/sample_R1.fq.gz",
        "reads_2": "/data/reads/sample_R2.fq.gz",
        "output_bam": "aligned.bam",
    },
)

bwa.execute()
jawm.Process.wait([bwa.hash])
```

That's it. You can run this with `jawm align.py`. Everything below adds convenience, structure, and testability on top of this foundation.

---

### The `parse_arguments()` / `workflow()` pattern

Most published modules use a two-function pattern from `jawm.utils` that gives the module a proper CLI and lets users choose which sub-workflows to run.

#### `parse_arguments()`

Call this once at the top of your module to set up the CLI:

```python
import jawm

workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    available_workflows=["main", "align", "qc", "test"],
    description="RNA-seq alignment and QC module.",
)
```

`parse_arguments()` returns four values:

| Value          | What it is                                                                 |
|----------------|---------------------------------------------------------------------------|
| `workflows`    | List of workflow names the user selected (e.g. `["align", "qc"]`)         |
| `var`          | Dictionary of variables merged from `-p` and `-v` files plus `--global.var.*` CLI overrides |
| `args`         | The full `argparse.Namespace` (includes `parameters`, `variables`, `logs_directory`, `resume`, etc.) |
| `unknown_args` | Any arguments argparse didn't recognise — useful for forwarding to sub-modules |

The built-in CLI flags (`-p`, `-v`, `-l`, `-r`, `-n`, `--git-cache`) are automatically wired up. You can also add your own custom flags (see [Custom CLI flags](#custom-cli-flags) below).

#### `workflow()`

Use `workflow()` as a gate before each group of Processes:

```python
if jawm.utils.workflow(select=workflows, workflows=["main", "align"]):
    # Processes here run only when the user picks "main" or "align"
    ...

if jawm.utils.workflow(select=workflows, workflows=["main", "qc"]):
    # These run for "main" or "qc"
    ...
```

This pattern means running `jawm mymodule.py main` executes everything, while `jawm mymodule.py align` runs only the alignment block.

---

### Using `script` vs `script_file`

jawm gives you two ways to provide a script to a `Process`:

- **`script`** — inline script content (the actual code to execute):

    ```python
    p = jawm.Process(
        name="hello",
        script="""#!/bin/bash
    echo "Hello, world!"
    """,
    )
    ```

- **`script_file`** — path to an external script file:

    ```python
    p = jawm.Process(
        name="hello",
        script_file="scripts/hello.sh",
    )
    ```

Both are equally valid. Inline `script` keeps everything in one place and is great for shorter scripts or when you want the module to be self-contained. `script_file` is handy when scripts are long or shared across multiple Processes.

!!! tip
    Throughout this guide, most examples use inline `script` to keep things self-contained. In your own modules, use whichever approach — or mix both — suits your project best.

---

### Using `var` for parameterisation

The `var` dictionary (or `var_file`) substitutes `{{placeholders}}` in your script at runtime:

```python
align = jawm.Process(
    name="bwa_align",
    script="""#!/bin/bash
set -euo pipefail
bwa mem -t {{threads}} {{genome}} {{reads_1}} {{reads_2}} \
  | samtools sort -@ {{threads}} -o {{output_bam}}
""",
    var={
        "threads": "8",
        "genome": "/data/ref/hg38.fa",
        "reads_1": "",   # to be provided via -v or YAML
        "reads_2": "",
        "output_bam": "aligned.bam",
    },
    desc={
        "threads": "Number of CPU threads",
        "genome": "Path to reference genome",
        "reads_1": "Forward reads (FASTQ)",
        "reads_2": "Reverse reads (FASTQ)",
        "output_bam": "Output BAM path",
    },
)
```

Variables can be overridden at multiple levels — YAML files (`-p`, `-v`), CLI overrides (`--global.var.threads=16` or `--process.bwa_align.var.threads=16`), or by the parent workflow setting `var` directly. Empty string `""` values act as required placeholders that the user must supply.

---

### Putting it together — a complete example

Here's a full module that aligns reads and runs QC, with a test sub-workflow:

```python
# rnaseq.py
import jawm

workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    available_workflows=["main", "align", "qc", "test"],
    description="RNA-seq alignment and quality control.",
)

# ── Alignment ──────────────────────────────────────
if jawm.utils.workflow(select=workflows, workflows=["main", "align"]):

    align = jawm.Process(
        name="star_align",
        script="""#!/bin/bash
set -euo pipefail

STAR --runMode alignReads \
     --genomeDir {{genome_dir}} \
     --readFilesIn {{reads_1}} {{reads_2}} \
     --readFilesCommand zcat \
     --runThreadN {{threads}} \
     --outSAMtype BAM SortedByCoordinate \
     --outFileNamePrefix {{output_prefix}}

samtools index {{output_prefix}}Aligned.sortedByCoord.out.bam
""",
        var={
            "genome_dir": "",
            "reads_1": "",
            "reads_2": "",
            "threads": "8",
            "output_prefix": "star_out/",
        },
        desc={
            "genome_dir": "STAR genome index directory",
            "reads_1": "Forward reads",
            "reads_2": "Reverse reads",
            "threads": "CPU threads for STAR",
            "output_prefix": "Output prefix for STAR",
        },
    )
    align.execute()

# ── QC ─────────────────────────────────────────────
if jawm.utils.workflow(select=workflows, workflows=["main", "qc"]):

    fastqc = jawm.Process(
        name="fastqc",
        script="""#!/bin/bash
set -euo pipefail
mkdir -p {{output_dir}}
fastqc -t {{threads}} -o {{output_dir}} {{reads_1}} {{reads_2}}
""",
        var={
            "reads_1": "",
            "reads_2": "",
            "threads": "4",
            "output_dir": "fastqc_results/",
        },
    )
    fastqc.execute()

# ── Test ───────────────────────────────────────────
if jawm.utils.workflow(select=workflows, workflows=["test"]):

    test_proc = jawm.Process(
        name="test_echo",
        script="""#!/bin/bash
set -euo pipefail
echo "Running smoke test"
echo "Module is wired correctly"
""",
    )
    test_proc.execute()

jawm.Process.wait("all")
```

Run it:

```bash
# Everything
jawm rnaseq.py main -v vars.yaml

# Just alignment
jawm rnaseq.py align -v vars.yaml

# Smoke test (no data needed)
jawm rnaseq.py test
```

---

### Process dependencies

When one Process depends on the output of another, use `depends_on`:

```python
download = jawm.Process(
    name="download_refs",
    script="""#!/bin/bash
set -euo pipefail
wget -q -O {{genome_fa}} {{genome_url}}
samtools faidx {{genome_fa}}
""",
    var={
        "genome_url": "https://example.com/hg38.fa",
        "genome_fa": "ref/hg38.fa",
    },
)
download.execute()

index = jawm.Process(
    name="bwa_index",
    script="""#!/bin/bash
set -euo pipefail
bwa index {{genome_fa}}
""",
    var={"genome_fa": "ref/hg38.fa"},
    depends_on=["download_refs"],
)
index.execute()

align = jawm.Process(
    name="align_reads",
    script="""#!/bin/bash
set -euo pipefail
bwa mem -t {{threads}} {{genome_fa}} {{reads_1}} {{reads_2}} \
  | samtools sort -o {{output_bam}}
samtools index {{output_bam}}
""",
    var={
        "genome_fa": "ref/hg38.fa",
        "reads_1": "",
        "reads_2": "",
        "threads": "8",
        "output_bam": "aligned.bam",
    },
    depends_on=["bwa_index"],
)
align.execute()

jawm.Process.wait("all")
```

All three Processes start executing immediately (each in its own thread), but `bwa_index` waits for `download_refs` to finish, and `align_reads` waits for `bwa_index`. jawm handles the synchronisation automatically.

You can also depend on multiple Processes:

```python
merge = jawm.Process(
    name="merge_bams",
    script="""#!/bin/bash
set -euo pipefail
samtools merge {{merged_bam}} {{bam_1}} {{bam_2}}
""",
    var={"merged_bam": "merged.bam", "bam_1": "a.bam", "bam_2": "b.bam"},
    depends_on=["align_sample_a", "align_sample_b"],
)
```

---

### Sub-modules

For larger projects, you can split your module into sub-modules — separate Python files that each define their own Processes. The main module file loads them with `jawm.utils.load_modules()`:

```python
# myproject.py (main module)
import jawm

workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    available_workflows=["main", "align", "qc", "test"],
    description="My multi-step pipeline.",
)

# Load sub-modules from local directories
jawm.utils.load_modules(
    ["submodules/jawm_myproject_submodule"],
    modules_root=".",
)

# Now call into the loaded sub-module
from jawm_myproject_submodule import myproject_submodule

if jawm.utils.workflow(select=workflows, workflows=["main", "align"]):
    myproject_submodule.run_alignment(var=var, args=args)
```

Sub-modules can also be remote Git repositories — see [Load Modules in Workflow](load.md) for the full details on `load_modules()`.

---

### Custom CLI flags

You can extend the CLI with module-specific flags using the `extra_args` parameter:

```python
workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    available_workflows=["main", "test"],
    description="Alignment module with aligner choice.",
    extra_args={
        "--aligner": "Aligner to use: bwa or bowtie2 (default: bwa)",
    },
)

aligner = args.aligner or "bwa"

if jawm.utils.workflow(select=workflows, workflows=["main"]):

    if aligner == "bwa":
        script_content = """#!/bin/bash
set -euo pipefail
bwa mem -t {{threads}} {{genome}} {{reads_1}} {{reads_2}} \
  | samtools sort -o {{output_bam}}
"""
    else:
        script_content = """#!/bin/bash
set -euo pipefail
bowtie2 -p {{threads}} -x {{genome}} \
  -1 {{reads_1}} -2 {{reads_2}} \
  | samtools sort -o {{output_bam}}
"""

    align = jawm.Process(
        name="align",
        script=script_content,
        var={
            "threads": "8",
            "genome": "",
            "reads_1": "",
            "reads_2": "",
            "output_bam": "aligned.bam",
        },
    )
    align.execute()

jawm.Process.wait("all")
```

Run with:

```bash
jawm mymodule.py main --aligner bowtie2 -v vars.yaml
```

Custom flags appear alongside the built-in ones in `--help`.

---

### Dynamic script content

Since `script` is just a Python string, you can build it dynamically:

```python
samples = ["sample_A", "sample_B", "sample_C"]

for sample in samples:
    p = jawm.Process(
        name=f"fastqc_{sample}",
        script=f"""#!/bin/bash
set -euo pipefail
fastqc -o qc_results/ data/{sample}_R1.fq.gz data/{sample}_R2.fq.gz
""",
    )
    p.execute()

jawm.Process.wait("all")
```

Or use `script_file` with dynamic variable injection:

```python
for sample in samples:
    p = jawm.Process(
        name=f"align_{sample}",
        script_file="scripts/align.sh",
        var={"sample_name": sample, "threads": "8"},
    )
    p.execute()
```

Both approaches work well. Inline scripts give you full Python string formatting power; `script_file` keeps shell code in `.sh` files where your editor can syntax-highlight it.

---

### Directory layout conventions

There's no enforced layout, but this structure works well for modules that others will consume:

```
jawm_myproject/
├── myproject.py            # module entry point
├── scripts/                # external script files (if using script_file)
│   └── align.sh
├── yaml/                   # default parameter / variable YAMLs
│   ├── params.yaml
│   └── docker.yaml
├── submodules/             # sub-module directories (if any)
│   └── jawm_myproject_submodule/
│       └── myproject_submodule.py
├── test/
│   ├── tests.txt           # jawm-test definitions
│   └── data.txt            # test data checksums
└── README.md
```

Adapt it to your needs — the only thing jawm cares about is a Python file with `Process` definitions.

---

### Testing with `jawm-test`

jawm ships with a `jawm-test` utility for structured, hash-based testing. It runs workflows defined in `test/tests.txt` and compares output hashes against stored reference values.

#### `test/tests.txt` format

Each line defines one test:

```
# module ; workflow ; extra params ; "test name" ; expected hash
myproject.py ; test ; ; "smoke test" ; abc123def456
myproject.py ; align ; -v test/test_vars.yaml ; "alignment test" ; 789abc012def
```

Fields are semicolon-separated:

| Field         | Description                                          |
|---------------|------------------------------------------------------|
| module        | Path to the module file                              |
| workflow      | Sub-workflow name to run                             |
| extra params  | Additional CLI flags (e.g. `-v test/vars.yaml`)      |
| test name     | Human-readable name (in quotes)                       |
| expected hash | Reference hash to compare against (empty on first run) |

#### `test/data.txt` format

If your tests need input data, list files with their MD5 checksums:

```
d41d8cd98f00b204e9800998ecf8427e  test/data/sample.fq.gz  https://example.com/sample.fq.gz
```

`jawm-test` downloads missing files, verifies checksums, and auto-extracts `.tar.gz`/`.tgz`/`.gz` archives.

#### Running tests

```bash
# Run all tests
jawm-test

# Override hashes on first run or after intentional changes
jawm-test --override

# Continue past failures
jawm-test --ignore

# Download test data only
jawm-test --runner download
```

---

### Inspecting variables with `jawm-dev lsvar`

`jawm-dev lsvar` reads a module file and extracts all `{{variable}}` references from `Process` script blocks, outputting them as YAML. It also warns about variables used in scripts but missing from `desc`, and notes variables defined in `desc` but unused in scripts.

```bash
$ jawm-dev lsvar myproject.py
- scope: process
  name: "star_align"
  var:
    genome_dir: ""
    output_prefix: ""
    reads_1: ""
    reads_2: ""
    threads: ""
- scope: process
  name: "fastqc"
  var:
    output_dir: ""
    reads_1: ""
    reads_2: ""
    threads: ""
```

This is useful for generating initial `var` dictionaries, checking for typos in placeholder names, and documenting which variables each Process expects.

---

### Publishing

Once your module is ready to share:

1. **Tag a release** — use semantic versioning (e.g. `v1.0.0`). Tags let consumers pin to a specific version with `@v1.0.0` or use `@latest-tag`.
2. **Push to Git** — any Git host works (GitHub, GitLab, Gitea, self-hosted).
3. **Naming convention** — prefix your repository with `jawm_` (e.g. `jawm_rnaseq`). This is a community convention, not a requirement — it makes modules discoverable on the Git server.

Consumers can then run your module directly:

```bash
# By repository name (uses default server/user)
jawm jawm_rnaseq main -v vars.yaml

# By full Git URL
jawm git@github.com:your-org/jawm_rnaseq.git main -v vars.yaml

# Pinned to a tag
jawm jawm_rnaseq@v1.0.0 main -v vars.yaml
```

Or load it from within another workflow:

```python
jawm.utils.load_modules(["jawm_rnaseq@latest-tag"])
```

See [Run a Module](run.md) and [Load Modules in Workflow](load.md) for the full details.

# Reproducing a FastQC Run with a Shared Log Directory

This example runs the `jawm_fastqc` workflow twice:

1. `run_1` creates the original FastQC result and reference hash.
2. `run_2` runs the same workflow again and validates its result against the hash created by `run_1`.

Both runs use the same JAWM log directory:

```text
fastqc-reproducibility/
├── run_1/
├── run_2/
└── logs/
```

The shared `logs/` directory connects the two runs. `run_1` creates:

```text
logs/jawm_hashes/fastqc.hash
```

and `run_2` uses that file as its `scope: hash` reference.

## 1. Create `run_1`

Create the main example directory and clone `jawm_fastqc` directly into `run_1`:

```bash
mkdir fastqc-reproducibility
cd fastqc-reproducibility

git clone \
  https://github.com/mpg-age-bioinformatics/jawm_fastqc.git \
  ./run_1
```

The directory now contains:

```text
fastqc-reproducibility/
└── run_1/
    ├── fastqc.py
    ├── test/
    └── yaml/
```

## 2. Download the Test Data for `run_1`

Enter `run_1` and download the test FASTQ:

```bash
cd ./run_1
jawm-test --runner download
```

`jawm-test` reads:

```text
test/data.txt
```

downloads:

```text
test/test-input/my_test_file_1.fastq.gz
```

and verifies its MD5 checksum.

## 3. Run FastQC in `run_1`

Run the test workflow and place its logs in the shared `../logs` directory:

```bash
jawm fastqc.py test \
  -p ./test/yaml/test.yaml \
  -l ../logs
```

The first run creates its result under:

```text
run_1/test/test-output/
```

and its logs under:

```text
logs/
├── fastqc_<datetime>_<hash>/
├── jawm_hashes/
│   ├── fastqc.hash
│   ├── fastqc_hash_manifest.json
│   ├── fastqc_input.history
│   └── fastqc_user_defined.history
└── jawm_runs/
```

Check the reference hash created by `run_1`:

```bash
cat ../logs/jawm_hashes/fastqc.hash
```

Return to the main example directory:

```bash
cd ..
```

The layout is now:

```text
fastqc-reproducibility/
├── run_1/
└── logs/
```

## 4. Create `run_2`

Find the `run_1` transcript in the shared log directory:

```bash
run_1_log="$(
  find ./logs/jawm_runs \
    -maxdepth 1 \
    -type f \
    -name 'fastqc_*.log' \
    -print \
    | sort \
    | tail -1
)"

echo "$run_1_log"
```

The transcript contains a line similar to:

```text
[git] Git repository HEAD commit: 6c738660
```

Extract the workflow commit from that line:

```bash
run_1_commit="$(
  grep '\[git\] Git repository HEAD commit:' "$run_1_log" \
    | tail -1 \
    | sed -E 's/.*HEAD commit: ([0-9a-fA-F]+).*/\1/'
)"

echo "$run_1_commit"
test -n "$run_1_commit"
```

Clone the repository again and ask Git to check out the commit recorded in the log:

```bash
git clone \
  https://github.com/mpg-age-bioinformatics/jawm_fastqc.git \
  ./run_2

git -C ./run_2 checkout --detach "$run_1_commit"
```

The transcript records an abbreviated commit SHA. Git accepts an abbreviated SHA when it identifies exactly one commit; the checkout fails if it cannot be resolved or is ambiguous.

Display the full commit selected in `run_2` and confirm that it starts with the logged value:

```bash
run_2_commit="$(git -C ./run_2 rev-parse HEAD)"
echo "$run_2_commit"

case "$run_2_commit" in
  "$run_1_commit"*)
    echo "run_2 is using the commit recorded in the run_1 log"
    ;;
  *)
    echo "run_2 commit does not match the run_1 log" >&2
    exit 1
    ;;
esac
```

`run_2` is now a clean checkout of the workflow commit reported by `run_1`, without the generated inputs, outputs, or logs from the first run.

The layout is now:

```text
fastqc-reproducibility/
├── run_1/
├── run_2/
└── logs/
```

## 5. Download the Test Data for `run_2`

```bash
cd ./run_2
jawm-test --runner download
```

This downloads and verifies a separate copy of the test FASTQ under:

```text
run_2/test/test-input/my_test_file_1.fastq.gz
```

## 6. Configure `run_2` to Use the Shared Hash

Open `test/yaml/test.yaml`. In its `scope: hash` section, change:

```yaml
overwrite: true
```

to:

```yaml
overwrite: false
```

Changing `overwrite` from `true` to `false` keeps the hash created by `run_1` unchanged.

Because JAWM is called from `run_2`, `../logs` points to the shared log directory.

## 7. Run FastQC in `run_2`

Run the second workflow and point it to the same shared log directory:

```bash
jawm fastqc.py test \
  -p ./test/yaml/reproduce.yaml \
  -l ../logs
```

The second run creates its result under:

```text
run_2/test/test-output/
```

Its process logs and transcript are added to the existing shared directory:

```text
logs/
├── fastqc_<run_1_datetime>_<hash>/
├── fastqc_<run_2_datetime>_<hash>/
├── jawm_hashes/
└── jawm_runs/
```

The process directories and transcripts have timestamps and identifiers, so the files from the two runs remain separate. The hash histories are appended with entries from both runs.

## 8. Check Whether `run_2` Reproduced `run_1`

If the output from `run_2` matches the hash created by `run_1`, JAWM prints:

```text
[hash] STATUS: MATCHED
[hash] Generated user-defined hash matched reference
```

The command completes successfully.

If the output is different, JAWM prints:

```text
[hash] STATUS: MISMATCHED
[hash] Generated user-defined hash does NOT match reference
```

and exits with code `73`.

Display the hash messages from both runs:

```bash
grep '\[hash\]' ../logs/jawm_runs/fastqc_*.log
```

Display the reference hash:

```bash
cat ../logs/jawm_hashes/fastqc.hash
```

Display the hash history:

```bash
cat ../logs/jawm_hashes/fastqc_user_defined.history
```

The history should contain one entry for `run_1` and another for `run_2`. When the reproduction succeeds, both entries contain the same SHA-256 hash.

## 9. Check Both Process Exit Codes

List the FastQC exit-code files in ascending path order:

```bash
find ../logs -name fastqc.exitcode -print \
  | sort \
  | while IFS= read -r exitcode_file; do
  printf "%s: " "$exitcode_file"
  cat "$exitcode_file"
  printf "\n"
done
```

Each successful FastQC process should have exit code `0`.

## Summary

Both JAWM calls use the same `-l` value:

```bash
# From run_1
jawm fastqc.py test \
  -p ./test/yaml/test.yaml \
  -l ../logs

# From run_2
jawm fastqc.py test \
  -p ./test/yaml/reproduce.yaml \
  -l ../logs
```

The shared log directory provides the reference:

```text
run_1
  ├── runs FastQC
  └── writes logs/jawm_hashes/fastqc.hash

run_2
  ├── runs FastQC again
  └── validates against logs/jawm_hashes/fastqc.hash
```

The essential rule is:

```yaml
overwrite: false
reference: ../logs/jawm_hashes/fastqc.hash
```

This preserves the `run_1` hash while allowing the shared histories and transcripts to record both runs.

For more detail, see [Log Structure](../debug/logs.md), [YAML Config](../config/yaml.md), and [FastQC](fastqc.md).

**Review evidence index — 8 September 2026**

[assessment.md](assessment.md) is the current GLP/GCP readiness assessment. Its latest update covers the regression-runner fix at commit `de53c274c8e1bb3b3b13b902bb7488151cea2714`. One of the six original observed findings is resolved for the locally tested path; five remain open.

| Record | Purpose |
|---|---|
| [assessment.initial.md](assessment.initial.md) | Unchanged initial assessment of `9e519079af55d5124e26f59445bd1985e9c7417e`. Its statements describe the original review, not the fix. Local source links open the current checkout; use the original commit to inspect historical source. |
| [evidence/observations.json](evidence/observations.json) and sibling `.log` files | Original six probe groups, including the original false-pass result. Retained unchanged. Temporary work-area paths identify the original execution location, not a durable archive. |
| [probes.py](probes.py) | Unchanged diagnostic script used for both reviews. It records observed behavior; its own exit of 0 does not mean the integrity controls passed. |
| [evidence/post-fix-de53c27/observations.json](evidence/post-fix-de53c27/observations.json) and sibling `.log` files | Fresh execution of the original probes against the fixed source. For `jawm_test_stale_hash`, changed output now exits 1 and `test_runner_reads_old_hash` is false. |
| [evidence/post-fix-de53c27/runner_tests.txt](evidence/post-fix-de53c27/runner_tests.txt) | Captured output of the eight focused runner regression tests. |
| [evidence/post-fix-de53c27/verification.json](evidence/post-fix-de53c27/verification.json) | Verification commands and process exit codes, exact source commit, UTC start/end, runtime environment and source-file SHA-256 values. |
| [sha256.initial.json](sha256.initial.json) | Unchanged original inventory. Its `assessment.md` digest now corresponds to `assessment.initial.md`; the other paths retain their original meaning. |
| [sha256.json](sha256.json) | Current inventory of all files in this review folder except itself, including the preserved initial records and new evidence. |

The fix creates a fresh `test/logs/run.XXXXXX/` directory for every runner invocation. Consequently, the original probe's `cli_mismatch_reported` field is now false: it checks the CLI's old `STATUS: MISMATCHED` message. The runner independently compares the fresh result with `tests.txt`, reports the mismatch and exits 1. That field changing to false is therefore expected, not a failed verification.

Verification is local and synthetic. The full base test suite, live Git/backend suites, remote CI results and deployed GLP/GCP controls were not verified. `--ignore` still deliberately permits an overall successful exit after a failed test; it is not a suitable acceptance gate without a separate reviewed disposition of failures.

The root `.gitignore` excludes `review`. These files are local review artifacts and are not included in normal commits or clones. The checksums provide an integrity inventory, not authenticated signatures or protected storage. Preserve the folder in the chosen controlled record system if it is to be retained as formal evidence.

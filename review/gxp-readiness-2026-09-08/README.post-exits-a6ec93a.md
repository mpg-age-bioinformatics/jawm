**Review evidence index — 8 September 2026**

[assessment.md](assessment.md) is the current GLP/GCP readiness assessment, reassessed at `a6ec93a2bba5ca54944a6d495fce5315e9154826`. Three of the six original observed findings are resolved locally; three remain open. This is not a compliance score or deployment approval.

| Record | Purpose |
|---|---|
| [assessment.initial.md](assessment.initial.md) | Unchanged initial assessment of `9e51907`. |
| [assessment.post-runner-de53c27.md](assessment.post-runner-de53c27.md), [earlier index](README.post-runner-de53c27.md) | Preserved assessment/index after the first fix; their one-resolved/five-open status is historical. |
| [original observations](evidence/observations.json) and sibling `.log` files | Original six probe groups; retained unchanged. |
| [first-fix observations](evidence/post-fix-de53c27/observations.json) and sibling evidence | Runner fix verification at `de53c27`, retained unchanged. |
| [current observations](evidence/post-fix-a6ec93a/observations.json) and sibling `.log` files | Fresh execution of all six original diagnostic groups at the current HEAD. |
| [runner tests](evidence/post-fix-a6ec93a/runner_tests.txt), [CLI exit tests](evidence/post-fix-a6ec93a/cli_exit_tests.txt) | Eight and sixteen passing focused tests respectively. |
| [current verification metadata](evidence/post-fix-a6ec93a/verification.json) | Exact commit, commands, process exits, UTC times, environment and selected source SHA-256 values. |
| [prior base-suite transcript](evidence/prior-base-suite/passed.txt), [initial failed attempt](evidence/prior-base-suite/initial-failed.txt), [provenance](evidence/prior-base-suite/provenance.json) | Earlier implementation-session evidence: final summary 57 passed, 0 failed with unavailable backends skipped. Predates the merge; not a fresh full-suite verification of this HEAD. Initial fixture-state failure retained for traceability. |
| [probes.py](probes.py) | Unchanged diagnostic script. Its own exit 0 means observations were collected, not that integrity controls passed. |
| [original inventory](sha256.initial.json), [post-runner inventory](sha256.post-runner-de53c27.json) | Preserved inventories. Their `assessment.md` entries correspond to the respective archived assessments. The post-runner `README.md` entry corresponds to the archived index. |
| [current inventory](sha256.json) | SHA-256 of every file in this review folder except this inventory itself. |

| Original probe | Initial result | Current result |
|---|---|---|
| Changed runner output | CLI runner exit 0 from old hash | Exit 1 from current invocation hash |
| Reference mismatch after workflow `sys.exit(0)` | Exit 0 | Exit 73 |
| Child exit 7 without explicit checking wait | CLI exit 0 | CLI exit 1 |
| Resume after changed input/deleted output | Successful skip; stale/missing output | Unchanged; open |
| Two-attempt stdout retention | Only second attempt retained | Unchanged; open |
| Aggregate `AB+C` versus `A+BC` | Equal digest | Unchanged; open |

The runner now creates a fresh `test/logs/run.XXXXXX/` directory for each invocation. The probe's `cli_mismatch_reported` field is therefore false: it searches for the CLI's old `STATUS: MISMATCHED` message. The runner independently compares the fresh result with `tests.txt` and correctly exits 1.

Verification is local and synthetic. Live Git/backend suites, remote CI results and deployed GLP/GCP controls remain unverified. `--ignore` deliberately permits successful runner exit after a failed test; `--override` and empty expected hashes accept new baselines. `JAWM_WAIT_CLI=0` disables the CLI's automatic child-outcome check. These settings need controlled use when relying on the repaired controls.

Historical local source links open the current checkout; inspect the named historical commit for the original source. Temporary work-area paths record execution locations, not durable archives. The prior inventory was verified before this reassessment, and historical records were preserved.

The root `.gitignore` excludes `review`. These files are local artifacts, absent from normal commits/clones. Checksums are an integrity inventory, not signatures or protected storage. Preserve this folder in the chosen controlled record system if retained as formal evidence.

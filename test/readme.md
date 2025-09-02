# `jawm` Base Tests with `base_test,py`

This script (`base_test.py`) can validate the core functionalities of **jawm (Just Another Workflow Manager)** across multiple execution backends: **local**, **Slurm**, and **Kubernetes**.

Git action on every commit runs and validate for the local backend. Utilizing the `jawm` command, the base tests can be executed with different **manager**.

## `local` Execution

From `cd test`, simply run the following:
```
jawm base_test.py
```

## `slurm` Execution
Run with:
```
jawm base_test.py -p parameters/slurm.yaml
```
`parameters/slurm.yaml` contains only the basic parameters. You can update the `yaml` based on the system, if required.

## `kubernetes` Execution
Run with:
```
jawm base_test.py -p parameters/k8.yaml
```
`parameters/k8.yaml` contains only the basic parameters. You can update the `yaml` based on the system, if required.

## Outcome
If all test cases passed, there would be a summary similar to the followings.
```
===== TEST SUMMARY =====
✅ Passed: 20
❌ Failed: 0
🎉 All tests passed!
```

## Cleanup

By default, the `base_test.py` cleans up the created directories/files at the end (default empty logs folder may still be there).  Can comment out the `Cleanup created directories` portion to keep the logs.

# CLI Tools Overview

jawm ships four command-line tools, each with a distinct role — from running workflows to scaffolding new modules to structured testing:

| Command | Role | Who uses it |
|---------|------|-------------|
| [`jawm`](jawm.md) | Run a workflow module (local or remote) | Everyone |
| [`jawm-dev`](jawm-dev.md) | Developer utilities — scaffold and inspect modules | Module authors |
| [`jawm-test`](jawm-test.md) | Structured test runner with hash verification | Module authors, CI |
| [`jawm-monitor`](jawm-monitor.md) | Live process and job monitoring _(coming soon)_ | Everyone |

---

### `jawm` — the primary command

`jawm` is the main entry point and the command you will use most. It runs a jawm module — a Python file that defines one or more named workflows — either from a local path or directly from a remote Git repository.

```bash
jawm <module> [workflow] [flags]
```

`<module>` can be a local file, a directory, a repository name, a full Git URL, or any of those with a `@ref` suffix to pin to a specific branch, tag, or commit. jawm resolves the module, clones it if needed, injects parameters and variables, and executes the workflow — all in one step.

Everything else — `jawm-dev`, `jawm-test`, `jawm-monitor` — is built around making `jawm` workflows easier to write, verify, and observe. See [`jawm`](jawm.md) for the full reference.

---

### Which tool do I need?

- **Running a workflow** — use `jawm`
- **Starting a new module from scratch** — use `jawm-dev init`
- **Checking what variables a module expects** — use `jawm-dev lsvar`
- **Verifying a module still produces correct output** — use `jawm-test`
- **Watching jobs run or reviewing past runs** — use `jawm-monitor` _(coming soon)_

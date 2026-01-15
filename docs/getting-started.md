# Theme test: code blocks, callouts, and layout

This page is meant to compare how different MkDocs themes render common documentation patterns.

---

## 1) Plain code block (Python)

```python
from jawm import Process

p = Process(
    name="hello_world",
    script="""#!/bin/bash
echo "Hello from jawm"
"""
)

p.execute()
```

---

## 2) Command line block (bash)

```bash
pip install jawm
jawm --help
mkdocs serve
```

---

## 3) YAML example

```yaml
global:
  logs_directory: ./logs
  manager: local

process:
  hello_world:
    script: |
      #!/bin/bash
      echo "Hello YAML!"
```

---

## 4) Inline code + file paths

Use the `Process` class and set `manager="slurm"` for HPC runs.  
Logs are written under `./logs/<process>_<timestamp>_<hash>/` by default.

---

## 5) Notes / warnings (admonitions)

!!! note
    This is a note. Use it for small tips or clarifications.

!!! warning
    This is a warning. Use it for things that can break a run.

!!! tip
    This is a tip. Use it for best practices.

---

## 6) A small table

| Feature | Local | Slurm | Kubernetes |
|--------:|:-----:|:-----:|:----------:|
| Dependencies | ✅ | ✅ | ✅ |
| Containers | ✅ | ✅ | ✅ |
| Stats collection | ✅ | ✅ | ⚠️ depends |

---

## 7) Long lines and wrapping

This is a deliberately long line to see how themes handle readability and wrapping on wide screens:

`/very/long/path/with/many/segments/that/should/not/look/terrible/on/a/large/display/and/should/wrap/nicely/if/needed`

---

## 8) “Recipe” style: step-by-step

1. Create a workflow module `workflow.py`
2. Define processes
3. Call `execute()`
4. Inspect logs in `./logs`

---

## 9) Code block that should feel “CLI friendly”

```bash
# run a workflow module
python workflow.py

# inspect logs
ls -lah logs/
```
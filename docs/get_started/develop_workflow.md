# Developing a Workflow

In jawm, a workflow is simply a Python module that defines one or more `Process` objects and executes them.

There is no separate DSL or framework layer — you write normal Python code and use `jawm.Process` to describe each step.

---

### A basic workflow

You can define multiple steps (with `jawm.Process`) in a workflow:

```python
import jawm

p1 = jawm.Process(
    name="step1",
    script="""#!/bin/bash
echo "Step 1"
"""
)

p2 = jawm.Process(
    name="step2",
    script="""#!/bin/bash
echo "Step 2"
"""
)

p1.execute()
p2.execute()
```

This will execute `step1` and `step2`.


**Running the workflow**

Once your workflow file is ready, you can run it using `jawm my_workflow.py`.

---

### Bootstrap a new workflow project

`jawm` also provides the `jawm-dev` helper CLI to quickly bootstrap a new workflow project from the demo template.

```bash
jawm-dev init my_first_wf -s local
```

This creates a new workflow project directory based on the `jawm_demo` template, using the default `jawm_` prefix.

For example, the command above creates:

```text
jawm_my_first_wf/
```

You can then test the generated workflow:

```bash
cd jawm_my_first_wf
jawm my_first_wf.py -p ./yaml/docker.yaml
```

**Note:** the demo workflow uses Docker, so Docker must be installed and accessible for this test run to work.

The `jawm-dev init` command can also target remote Git hosting when needed, but using `-s local` is the simplest way to start developing your first workflow locally.

Followings are the basic functionalities of bootstrap a new workflow project with `jawm-dev init`:

```bash
positional arguments:
  name                  Base module name (without prefix). Example: 'demo' → repo 'jawm_demo', file 'demo.py'.

options:
  -h, --help            show this help message and exit
  -s SERVER, --server SERVER
                        Git server host or URL (use 'local' to skip remote). Default: github.com
  -u USER, --user USER  Git username/organization for remote. Default: mpg-age-bioinformatics
  -p MODULE_PREFIX, --prefix MODULE_PREFIX, --module-prefix MODULE_PREFIX
                        Repository directory prefix. Default: jawm_
```

---


### Next steps

- Explore [**Process parameters**](process/parameters.md) to customize execution behavior
- Learn about [**configuration and precedence**](process/conf_precedence.md)
- Try running workflows on different backends

---
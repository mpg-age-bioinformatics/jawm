# Running a Workflow

Once jawm is installed, a workflow can be run either from a local Python module or directly from a shared remote workflow module.

---

### Run a local workflow module

A simple way to get started is to clone a demo workflow repository and run one of its modules.

```bash
# clone the demo module
git clone git@github.com:mpg-age-bioinformatics/jawm_demo.git

# run a simple workflow from the jawm demo
cd jawm_demo
jawm simple.py
```

You can also run the same workflow using python:

```bash
python simple.py
```


In addition to the command line, `jawm` workflows can also be launched directly from Python using `jawm.cli.run()`.

**Example with a local workflow file:**
```python
import jawm

rc = jawm.cli.run(["simple.py"])
print(rc)
```

This is equivalent to:

```bash
jawm simple.py
```

**Note:** This `simple.py` from [jawm_demo](https://github.com/mpg-age-bioinformatics/jawm_demo) uses a Docker environment, so Docker must be installed and accessible for it to run successfully.

---

### Run a remote workflow module

`jawm` can run shared workflow modules directly from remote Git repositories without requiring you to clone them manually.

For example, using the [jawm_git_test](https://github.com/mpg-age-bioinformatics/jawm_git_test) repository:

By default, `jawm` resolves repositories from `github.com/mpg-age-bioinformatics/`

So you can run the repository simply by its name:

```bash
jawm jawm_git_test
```

This runs the default workflow entrypoint (`main.py`) from the repository.

You can also specify versions or branches:

```bash
jawm jawm_git_test@v1.0.0
jawm jawm_git_test@latest-tag
```

And target a specific workflow file inside the repository:

```bash
jawm jawm_git_test@main//examples/demo.py
```

This allows you to run workflows from subdirectories, such as `examples/demo.py`.

You can also provide the full repository path explicitly or with :

```bash
jawm github.com/mpg-age-bioinformatics/jawm_git_test
```

---

### Available shared workflows

Available shared workflow modules from us can be found [here (GitHub.com)](https://github.com/mpg-age-bioinformatics?q=jawm_&type=all&language=&sort=).

These modules can be used as ready-made workflows, or imported into your own workflow modules when needed.

---

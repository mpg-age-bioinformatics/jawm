# jawm

*just another workflow manager*

[![Documentation](https://img.shields.io/badge/docs-jawm-blue?style=for-the-badge)](https://bioinformatics.age.mpg.de/jawm/)

`jawm` is a lightweight, Python-native workflow manager for building reproducible, dependency-aware workflows across different execution environments.

It is designed for researchers, data scientists, and engineers who want the flexibility of Python without committing to a heavyweight workflow framework, a custom DSL, or an external orchestration service.

## Why?

- Python based and python-like
- Continuous smooth learning curve
- Workflow code fully independent of framework
- Notebook ready and data scientist friendly
- Local and external storage agnostic
- Executors: local, Slurm, Kubernetes
- Containers: Docker, Apptainer
- Reusable local and remote workflow modules
- Traceable execution records

## Installation
```
pip install "git+https://github.com/mpg-age-bioinformatics/jawm.git"
```
Or install with optional dependencies (e.g. `pandas`, `openpyxl`):
```
pip install "jawm[full] @ git+https://github.com/mpg-age-bioinformatics/jawm.git"
```

*Note*: Installing with jawm[full] may fail on some systems because it pulls in `pandas`, which can require native compilation if no prebuilt wheel is available. Additionally, you can add `--upgrade-strategy only-if-needed` to avoid unnecessary dependency upgrades, and `--user` if you don’t have permission to write to site-packages. If you run into installation issues, try upgrading packaging tools first: `python -m pip install -U pip setuptools wheel`.

## Quick example

```python
import jawm

p = jawm.Process(
    name="hello_world",
    script="""#!/bin/bash
echo "Hello from jawm"
""",
)

p.execute()
```

Save the example as `hello.py` and run it with:

```bash
jawm hello.py
```

jawm executes the process locally by default and records its generated script, output, exit code, and runtime metadata under `./logs`.

## Demo module

Clone the public demo module and run its simple workflow:

```bash
git clone https://github.com/mpg-age-bioinformatics/jawm_demo.git
cd jawm_demo
jawm simple.py
```

The workflow file can also be run directly with `python simple.py`.

You can also let jawm retrieve and run the public module without cloning it manually:

```bash
jawm jawm_demo//simple.py
```

Take a look at [jawm_demo](https://github.com/mpg-age-bioinformatics/jawm_demo) for more demos of jawm workflows.

## Developing your first jawm workflow

You can develop your first jawm workflow by:
```
jawm-dev init my_first_wf -s local
```

Test it (requires Docker):
```
cd jawm_my_first_wf
jawm my_first_wf.py -p ./yaml/docker.yaml
```

## Resources

[Read the Docs](https://bioinformatics.age.mpg.de/jawm/) for more information on how to create workflows with jawm.

Availabe workflows can be found [here (GitHub.com)](https://github.com/mpg-age-bioinformatics?q=jawm_&type=all&language=&sort=).

## Status

`jawm` is under active development.  
The API is stabilizing, but some features and interfaces may evolve before a stable release.

[![Version](https://img.shields.io/github/v/tag/mpg-age-bioinformatics/jawm?label=version&sort=semver)](https://github.com/mpg-age-bioinformatics/jawm/tags)

## Credits

The Bioinformatics Core Facility of the Max Planck Institute for Biology of Ageing, Cologne, Germany.

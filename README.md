# jawm
just another workflow manager

## Why?

- Python based and python-like
- Continuous smooth learning curve
- Workflow code fully independent of framework
- Notebook ready and data scientist friendly
- Local and external storage agnostic
- Executors: local, Slurm, Kubernetes
- Containers: Docker, Apptainer

## Installation
```
pip install git+ssh://git@github.com/mpg-age-bioinformatics/jawm.git
```

## Running jawm

```
# clone the demo module
git clone git@github.com:mpg-age-bioinformatics/jawm_demo.git

# simple workflow
cd jawm_demo
python simple.py

# simple workflow with using the jawm executable
jawm simple.py
```

Take a look at the [jawm_demo](https://github.com/mpg-age-bioinformatics/jawm_demo) for more demos of jawm workflows.

## Developing your first jawm workfow

You can develop your first jawm workflow by:
```
jawm-dev init my_first_wf -s local
```

Test it (requires docker):
```
cd jawm_my_first_wf
jawm my_first_wf.py -p ./yaml/docker.yaml
```

[Read the Docs](https://github.com/mpg-age-bioinformatics/jawm) for more information on how to create workflows with jawm.

Availabe workflows can be found [here (GitHub.com)](https://github.com/mpg-age-bioinformatics?q=jawm_&type=all&language=&sort=).
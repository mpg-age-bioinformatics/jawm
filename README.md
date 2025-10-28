# jawm
just another workflow manager

## Why?

- Python based and python-like
- Continuous smooth learning curve
- Code fully independent of framework
- Notebook ready and data scientist friendly
- Local and external storage agnostic
- Executors: local, Slurm, Kubernetes
- Containers: Docker, Apptainer

## Installation
```
pip install git+ssh://git@github.com/mpg-age-bioinformatics/jawm.git
```

## Running jawm

Start your first jawm workflow:
```
jawm-dev init my_first_wf -s local
```

Test it (requires docker):
```
cd jawm_my_first_wf
jawm my_first_wf -p ./yaml/docker.yaml
```

Check out the contents of 
```
my_first_wf.py
```
to see how jawm works.

The workflow you just generated is based [jawm_demo](https://github.com/mpg-age-bioinformatics/jawm_demo) - check it out more examples on creating workflows with jawm (eg. within jupyter notebooks ).

Availabe workflows can be found [here (GitHub.com)](https://github.com/mpg-age-bioinformatics?q=jawm_&type=all&language=&sort=).
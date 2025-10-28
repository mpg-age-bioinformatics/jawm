# jawm
just another workflow manager

## Why?

- Python based and python-like
- Continuous smooth learning curve
- Code fully independent of framework
- Local and external storage agnostic
- Notebook ready and data scientist friendly

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

Availabe workflows can be found [here (GitHub.com)](https://github.com/mpg-age-bioinformatics?q=jawm_&type=all&language=&sort=).
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

## Developing and testing

Start your first jawm workflow:
```
jawm-dev init my_first_wf -s local
```

Test it (requires docker):
```
cd my_first_wf
jawm-test
```

Check out the contents of 
```
my_first_wf.py
```
to see how jawm works.

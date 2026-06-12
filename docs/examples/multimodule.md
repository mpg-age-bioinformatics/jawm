# Multi-module workflows

jawm is modular allwoing you to use modules across different workflows.

In this example we will learn how to create a workflow that uses 3 publicly available modules, [jawm_genomes](https://github.com/mpg-age-bioinformatics/jawm_genomes) and [jawm_kallisto](https://github.com/mpg-age-bioinformatics/jawm_kallisto). 
We will also add some level of automation which can be practical for complex workflows. For a more complex example please visit 
[github.com/mpg-age-bioinformatics/jawm_rnaseq](https://github.com/mpg-age-bioinformatics/jawm_rnaseq).

The main relevant function for multi-module workflows is [`jawm.utils.load_modules`](../utils.md/#load_modules) here used as:

```python
load_modules([
    "submodules",
    "jawm_genomes@697ce30",
    "jawm_kallisto@ceaba6c",
] )
```

This will import all Processes and functions defined in the respective modules.

We will call this module "multi" and start by generating the required files and folders:

```bash
NAME="multi"

mkdir -p jawm_${NAME} \
  jawm_multi/submodules \ 
  jawm_${NAME}/yaml \
  jawm_${NAME}/test \
  jawm_${NAME}/test/yaml \
  jawm_${NAME}/.github/workflows

touch jawm_${NAME}/${NAME}.py \
  jawm_${NAME}/yaml/docker.yaml \
  jawm_${NAME}/test/tests.txt \
  jawm_${NAME}/test/data.txt \
  jawm_${NAME}/test/yaml/test.yaml \
  jawm_${NAME}/.gitignore \
  jawm_${NAME}/.github/workflows/test.yaml
```

The folder `jawm_multi/submodules` should contain any helper functions or processes you might want to build for this multi-module workflow. This is specially important when having long workflows and wanting to keep your main python file (here `multi.py`) as clean and workflow oriented as possible:

```bash
jawm_multi/submodules/_multi.py
```

We now start creating our workflow:

```python
# jawm_multi/multi.py
import jawm
import logging
logger = logging.getLogger("jawm_multi")

if __name__ == "__main__":

  from jawm.utils import workflow, load_modules, get_image, id_files

  # load external modules
  load_modules([
      "submodules",
      "jawm_genomes@697ce30",
      "jawm_kallisto@ceaba6c",
  ] )

  # read arguments
  workflows, var, args, unknown_args= jawm.utils.parse_arguments( ["main","multi","test"] )

  if workflow( ["main","multi","test" ], workflows ) :

    ##################
    # kallisto index #
    ##################

    # seq type: primary_assembly vs. toplevel (preference for primary_assembly )
    if "seq_type" not in var :
        seq_type=genomes.check_primary_assembly_exists( var['organism'], var['release'] )
        jawm.Process.update( var={ "seq_type" : seq_type } )
        var["seq_type"]=seq_type

    # download references
    genomes.download_gtf.var["filename"] = genomes.download_gtf.var["organism"] + "." + str( genomes.download_gtf.var["release"] ) + ".gtf.gz"
    genomes.download_gtf.var["mk.output_folder"] = os.path.join( var["genomes_folder"], var["organism"], var["release"] )
    genomes.download_gtf.execute()

    genomes.download_dna.var["filename"] = genomes.download_dna.var["organism"] + "." + str(genomes.download_dna.var["release"]) + "." + genomes.download_dna.var["seq_type"] + ".dna.fa.gz"
    genomes.download_dna.var["mk.output_folder"] = os.path.join( var["genomes_folder"], var["organism"], var["release"] )
    genomes.download_dna.execute()

    gtf_file=os.path.join( 
        genomes.download_gtf.var["mk.output_folder"],
        f'{var["organism"]}.{var["release"]}.no.rRNA.gtf' 
        )

    kallisto_dic={ 
        "mk.kallisto_index":os.path.join( genomes.download_gtf.var["mk.output_folder"], "kallisto_index" ),
        "mk.kallisto_output":os.path.join( var["project_folder"], "kallisto_output" ),
        "gtf_file": gtf_file,
        "fasta_file":os.path.join( 
            genomes.download_gtf.var["mk.output_folder"], 
            f'{var["organism"]}.{var["release"]}.{var["seq_type"]}.dna.fa' 
            )
    }

    jawm.Process.update( var=kallisto_dic )
    
    # generate indexes
    kallisto.get_genome.execute( [ genomes.download_gtf.hash, genomes.download_dna.hash ] )
    kallisto.writecdna.execute( kallisto.get_genome.hash )
    kallisto.indexer.execute( kallisto.writecdna.hash )

    #################
    # list raw data #
    #################

    jawm.Process.wait( kallisto.indexer.hash )

    # list read1 and read2 files
    read1_files = list(Path( fastqc.fastqc.var["raw_data"] ).glob(f'*{fastqc.fastqc.var["read1_suffix"]}'))
    read1_files=[ str(s) for s in read1_files if not str(s).startswith("tmp.") ]
    read2_files = [ str(s).split( var["read1_suffix"] )[0] +var["read2_suffix"] for s in read1_files  ]
    read2_files = [ s for s in read2_files if Path(s).is_file() ]

    ####################
    # kallisto mapping #
    ####################

    # check if it is unstranded, 1st strand, or 2nd strand mapping
    kallisto.unstranded_mapping.var["read_1"]=os.path.basename(read1_files[0])
    kallisto.unstranded_mapping.execute( kallisto.indexer.hash )
    
    kallisto.gene_model.execute( kallisto.get_genome.hash )
    
    kallisto.infer_experiment.var["read_1"]=os.path.basename( read1_files[0] )
    kallisto.infer_experiment.execute( [ kallisto.gene_model.hash, kallisto.unstranded_mapping.hash ] )

    kallisto.strand_checker.execute( kallisto.infer_experiment.hash )

    jawm.Process.wait( kallisto.strand_checker.hash )

    # running mapping jobs
    flagstat_jobs=[]
    mapping_jobs=[]
    for read1 in read1_files:

      # clone the processes required for each file
      mapping_=kallisto.mapping.clone()
      flagstat_=kallisto.flagstat.clone()

      mapping_.var["read_1"]=os.path.basename( read1 )
      mapping_.execute( kallisto.strand_checker.hash )
      mapping_jobs.append( mapping_.hash )

      flagstat_.var["read_1"]=os.path.basename( read1 )
      flagstat_.execute( mapping_.hash ) 

      flagstat_jobs.append( flagstat_.hash )

    jawm.Process.wait( mapping_jobs )

  if workflow( ["main","multi","test" ], workflows ) :

    logger.info("Test completed.")

exit(0)
```

Populate `.gitignore` and initiate repo:

```bash
cat > jawm_${NAME}/myfile.txt <<EOF
__pycache__
logs
test-input
test-output
.ipynb_checkpoints
__init__.py
.submodules
*.txt.tmp
EOF

cd ./jawm_${NAME}
git init
git add .
git commit -m "Initial commit"
```

We have added `.submodules` to our `.gitignore` as this is where cloned modules live.

For this example we will need to download 6 RNAseq samples, 2 groups, triplicates, for which we populate the 
`data.txt` file and download the respective data:

```
cat > test/data.txt <<EOF
9c2b62a5b940a2cb9942f7413ce75f22  N2_treated.Rep_1.READ_1.fastq.gz  https://ndownloader.figshare.com/files/58690402
b502103f640be7f10b32b0754355e130  N2_treated.Rep_2.READ_1.fastq.gz  https://ndownloader.figshare.com/files/58690396
0d5aa56947877744b4409a032a03b953  N2_treated.Rep_3.READ_1.fastq.gz  https://ndownloader.figshare.com/files/58690390  
4f8e2a955b9d1f15506e6143cb13c6ca  N2.Rep_1.READ_1.fastq.gz  https://ndownloader.figshare.com/files/58690420
b1cc365dc6b967e42cf5296a2c741442  N2.Rep_2.READ_1.fastq.gz  https://ndownloader.figshare.com/files/58690414
a6518ef73e3dbcb37f8a59fe705077f2  N2.Rep_3.READ_1.fastq.gz  https://ndownloader.figshare.com/files/58690408
EOF

jawm-test -r download
```

Populate the `docker.yaml` file:

```yaml
# jawm_multi/yaml/docker.yaml


```

Try the workflow with: 

```
jawm -p yaml/docker.yaml
```
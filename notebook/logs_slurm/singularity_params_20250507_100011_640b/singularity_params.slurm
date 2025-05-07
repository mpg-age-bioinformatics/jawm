#!/bin/bash
#SBATCH --partition=cluster
#SBATCH --mem=2GB

apptainer exec --env MY_VAR=APP_Value --env ANOTHER_VAR=ANOTHER_VAR /nexus/posix0/MAGE-flaski/service/images/python.sif /nexus/posix0/MAGE-flaski/service/posit/home/hamin/JAWM/notebook/logs_slurm/singularity_params_20250507_100011_640b/singularity_params.script

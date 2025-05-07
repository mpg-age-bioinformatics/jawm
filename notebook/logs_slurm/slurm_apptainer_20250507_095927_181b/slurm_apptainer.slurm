#!/bin/bash
#SBATCH --partition=dedicated
#SBATCH --mem=4G

apptainer exec --env MY_VAR=APP_Value --env ANOTHER_VAR=ANOTHER_VAR /nexus/posix0/MAGE-flaski/service/images/python.sif /nexus/posix0/MAGE-flaski/service/posit/home/hamin/JAWM/notebook/logs_slurm/slurm_apptainer_20250507_095927_181b/slurm_apptainer.script

#!/bin/bash
#SBATCH --partition=dedicated
#SBATCH --mem=dedicated

apptainer exec --env MY_VAR=APP_Value --env ANOTHER_VAR=ANOTHER_VAR /nexus/posix0/MAGE-flaski/service/images/python.sif /nexus/posix0/MAGE-flaski/service/posit/home/hamin/JAWM/notebook/logs/slurm_apptainer_20250218_144535_slurm_87/slurm_apptainer.script

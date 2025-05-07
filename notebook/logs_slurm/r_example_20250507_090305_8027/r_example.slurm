#!/bin/bash
#SBATCH --partition=cluster
#SBATCH --mem=2GB

apptainer exec /nexus/posix0/MAGE-flaski/service/images/posit-latest.sif /nexus/posix0/MAGE-flaski/service/posit/home/hamin/JAWM/notebook/logs_slurm/r_example_20250507_090305_8027/r_example.script

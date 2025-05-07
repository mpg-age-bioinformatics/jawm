# ---
# jupyter:
#   jupytext:
#     cell_markers: '{{{,}}}'
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.16.6
#   kernelspec:
#     display_name: Python 3.12.6
#     language: python
#     name: py3.12.6
# ---

# {{{
import os
os.environ['JAWM_MONITORING_DIRECTORY'] = 'monitoring'

# For development
# import sys
# sys.path.append(os.path.abspath(os.path.join(os.path.abspath(os.getcwd()), '../..')))

from jawm import Process
# }}}

fastqc_apptainer = Process(name="fastqc_apptainer", param_file="parameters/fastqc.yaml")
fastqc_apptainer.execute()

# {{{
# Inline Process Example

# fastqc_apptainer = Process(
#     name="fastqc_apptainer",
#     script="""#!/bin/bash
# # mkdir output
# fastqc -o output/ input/reads.fastq
# """,
#     container="/nexus/posix0/MAGE-flaski/service/images/fastqc-0.11.9.sif",
#     environment="apptainer",
#     manager="slurm"
# )

# fastqc_apptainer.execute()
# }}}

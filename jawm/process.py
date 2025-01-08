import subprocess
import threading
import os
import sys
import logging
import tempfile
import time
from datetime import datetime

class Process:
    """
    A class to define and execute processes with support for multiple managers,
    pre/post scripts, retries, and resource configurations.
    """
    def __init__(self, name, script, **kwargs):
        """
        Initialize the Process object.

        :param name: Name of the process.
        :param script: The main script or command to execute.
        :param kwargs: Additional parameters to configure the process.
        """
        # Primary parameters
        self.name = name
        self.script = script

        # Directory parameters
        self.project_directory = kwargs.get("project_directory", os.path.dirname(os.path.abspath(sys.argv[0])))
        os.makedirs(self.project_directory, exist_ok=True)
        self.logs_directory = kwargs.get("logs_directory", os.path.join(self.project_directory, "logs"))
        os.makedirs(self.logs_directory, exist_ok=True)
        self.parameters_directory = kwargs.get("parameters_directory", os.path.join(self.project_directory, "parameters"))

        # Management parameters
        self.manager = kwargs.get("manager", "metal")
        self.env = kwargs.get("env", os.environ.copy())
        self.inputs = kwargs.get("inputs", {})
        self.outputs = kwargs.get("outputs", {})
        self.retries = kwargs.get("retries", 0)
        self.container = kwargs.get("container", None)
        self.use_scratch = kwargs.get("scratch", False)
        self.error_strategy = kwargs.get("error_strategy", "retry")
        self.when = kwargs.get("when", True)
        self.before_script = kwargs.get("before_script", None)
        self.after_script = kwargs.get("after_script", None)
        self.logger = logging.getLogger(name)

        # Local execution configurations
        self.manager_local = kwargs.get("manager_local", {})

        # Slurm execution configurations
        self.manager_slurm = kwargs.get("manager_slurm", {})

        # Metadata
        self.date_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_path = os.path.join(self.logs_directory, f"{self.name}_{self.date_time}_{self.manager}")
        os.makedirs(self.log_path, exist_ok=True)

    def _generate_sbatch_command(self):
        """
        Generate an sbatch command dynamically based on user-provided SLURM properties.
        :return: The sbatch command as a list.
        """
        sbatch_command = ["sbatch"]

        # Add user-provided SLURM options dynamically
        for key, value in self.manager_slurm.items():
            sbatch_command.extend([f"--{key}", str(value)])

        # Add defaults for output and error only if not provided by the user
        if "output" not in self.manager_slurm:
            sbatch_command.extend(["--output", os.path.join(self.log_path, f"{self.name}.output")])
        if "error" not in self.manager_slurm:
            sbatch_command.extend(["--error", os.path.join(self.log_path, f"{self.name}.error")])

        return sbatch_command

    def _generate_slurm_script(self):
        """
    Generate a Slurm job script that executes the provided script as an executable file.
    :return: Path to the Slurm script.
    """
        self.logger.info(f"Generating Slurm job script for process: {self.name}")

        # Write the user's script to a standalone file
        original_script_path = os.path.join(self.log_path, f"{self.name}.script")
        with open(original_script_path, "w") as original_script_file:
            original_script_file.write(self.script)

        # Ensure the script is executable
        os.chmod(original_script_path, 0o755)

        # Define the Slurm script file name
        slurm_script_path = os.path.join(self.log_path, f"{self.name}.slurm")

        # Create the Slurm job script
        with open(slurm_script_path, "w") as slurm_script_file:
            slurm_script_file.write("#!/bin/bash\n")  # Slurm script shebang
            
            # Add SLURM options dynamically
            for key, value in self.manager_slurm.items():
                slurm_script_file.write(f"#SBATCH --{key}={value}\n")

            # Call the executable script
            slurm_script_file.write(f"\n{original_script_path}\n")

        return slurm_script_path

    def _execute_metal(self):
        """
        Execute the process locally with resource constraints.
        :return: The output of the executed script.
        """
        self.logger.info(f"Executing process {self.name} locally")
        try:
            # Define the path for the script/log files
            script_path = os.path.join(self.log_path, f"{self.name}.script")
            stdout_path = os.path.join(self.log_path, f"{self.name}.output")
            stderr_path = os.path.join(self.log_path, f"{self.name}.error")
            exitcode_path = os.path.join(self.log_path, f"{self.name}.exitcode")

            # Write the script content to the file
            with open(script_path, "w") as script_file:
                script_file.write(self.script)
            
            # Make the script executable
            os.chmod(script_path, 0o755)
            
            # Open the output and error files
            with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
                # Execute the script directly
                result = subprocess.Popen(
                    [script_path],
                    env=self.env,
                    # timeout=self.manager_local.get("time"),  # Apply timeout if specified
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True
                )
            process_id = result.pid
            self.logger.info(f"Process {self.name} started with PID: {process_id}")

            def monitor_process():
                """
                Monitor/log the process in a background thread.
                """
                elapsed_time = 0
                while result.poll() is None:
                    # log every 3mins of waiting for the process to be finished
                    if elapsed_time % 180 == 0:
                        self.logger.info(f"Process {self.name} (PID: {process_id}) is still running...")
                    elapsed_time += 3
                    time.sleep(3)  # Sleep for a while before checking again

                # Once finished, get the return code
                exitcode = result.returncode
                self.logger.info(f"Process {self.name} completed with exit code: {exitcode}")
                with open(exitcode_path, "w") as exitcode_file:
                    exitcode_file.write(str(exitcode))

                # Retries if fails
                if exitcode != 0:
                    with open(stderr_path, "r") as stderr_file:
                        error_message = stderr_file.read().strip()
                    self.logger.error(f"Process {self.name} failed with error: {error_message}")
                    if self.retries > 0:
                        self.logger.info(f"Retrying process {self.name}, {self.retries} retries left.")
                        self.retries -= 1
                        return self._execute_metal()
                    # raise RuntimeError(f"Process {self.name} failed with error: {error_message}")
                    self.logger.error(f"Process {self.name} failed with error: {error_message}")

            # Start monitoring in a background thread
            monitor_thread = threading.Thread(target=monitor_process, daemon=False)
            monitor_thread.start()

            # Return the output
            return process_id

        finally:
            pass
            # Cleanup the temporary script file
            # if os.path.exists(temp_script_path):
            #     os.remove(temp_script_path)

    def _execute_slurm(self):
        """
        Execute the process as a Slurm job.
        :return: Slurm job ID.
        """
        self.logger.info(f"Executing process {self.name} in Slurm")

        # Generate log folder for this slurm job
        # log_folder = f"{self.name}_{self.date_time}_slurm"
        # log_path = os.path.join(self.logs_directory, log_folder)
        # os.makedirs(log_path, exist_ok=True)
        self.logger.info(f"Log folder for process {self.name}: {self.log_path}")

        # Generate the Slurm job script
        slurm_script_path = self._generate_slurm_script()

        # Generate the sbatch command
        sbatch_command = self._generate_sbatch_command()
        sbatch_command.append(slurm_script_path)

        self.logger.info(f"Submitting process {self.name} with command: {' '.join(sbatch_command)}")

        try:
            # Submit the job script to Slurm
            result = subprocess.run(
                sbatch_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Check the result of submission
            if result.returncode == 0:
                job_id = result.stdout.strip().split()[-1]
                self.logger.info(f"Process {self.name} submitted as Slurm job {job_id}.")
                return job_id
            else:
                self.logger.error(f"Failed to submit process {self.name} to Slurm: {result.stderr}")
                raise RuntimeError(f"Slurm submission failed for process {self.name}")

        finally:
            pass
            # Cleanup the Slurm script
            # if os.path.exists(slurm_script_path):
            #     os.remove(slurm_script_path)

    def execute(self):
        """
        Execute the process based on the specified manager (local or slurm).
        """
        if self.manager == "metal":
            return self._execute_metal()
        elif self.manager == "slurm":
            return self._execute_slurm()
        else:
            raise ValueError(f"Unsupported manager: {self.manager}")

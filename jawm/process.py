import subprocess
import os
import logging
import tempfile

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
        self.name = name
        self.script = script
        self.manager = kwargs.get("manager", "local")
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
            sbatch_command.extend(["--output", f"{self.name}.out"])
        if "error" not in self.manager_slurm:
            sbatch_command.extend(["--error", f"{self.name}.err"])

        return sbatch_command

    def _generate_slurm_script(self):
        """
    Generate a Slurm job script that executes the provided script as an executable file.
    :return: Path to the Slurm script.
    """
        self.logger.info(f"Generating Slurm job script for process: {self.name}")

        # Write the user's script to a standalone file
        user_script_path = os.path.abspath(f"{self.name}_script")
        with open(user_script_path, "w") as user_script_file:
            user_script_file.write(self.script)

        # Ensure the script is executable
        os.chmod(user_script_path, 0o755)

        # Create the Slurm job script
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".slurm") as slurm_script:
            slurm_script.write("#!/bin/bash\n")  # Slurm script shebang
            
            # Add SLURM options dynamically
            for key, value in self.manager_slurm.items():
                slurm_script.write(f"#SBATCH --{key}={value}\n")

            # Call the executable script
            slurm_script.write(f"\n{user_script_path}\n")

        return slurm_script.name

    def _execute_locally(self):
        """
        Execute the process locally with resource constraints.
        :return: The output of the executed script.
        """
        self.logger.info(f"Executing process {self.name} locally")
        try:
            # Write the script to a temporary file
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_script:
                temp_script.write(self.script)
                temp_script_path = temp_script.name
            
            # Make the script executable
            os.chmod(temp_script_path, 0o755)
            
            # Execute the script directly
            result = subprocess.run(
                [temp_script_path],
                env=self.env,
                timeout=self.manager_local.get("time"),  # Apply timeout if specified
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Check execution result
            if result.returncode == 0:
                self.logger.info(f"Process {self.name} completed successfully.")
            else:
                self.logger.error(f"Process {self.name} failed with error: {result.stderr}")
                if self.retries > 0:
                    self.logger.info(f"Retrying process {self.name}, {self.retries} retries left.")
                    self.retries -= 1
                    return self._execute_locally()
                raise RuntimeError(f"Process {self.name} failed with error: {result.stderr}")

            # Return the output
            return result.stdout

        finally:
            # Cleanup the temporary script file
            if os.path.exists(temp_script_path):
                os.remove(temp_script_path)

    def _execute_slurm(self):
        """
        Execute the process as a Slurm job.
        :return: Slurm job ID.
        """
        self.logger.info(f"Executing process {self.name} in Slurm")

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
            # Cleanup the Slurm script
            if os.path.exists(slurm_script_path):
                os.remove(slurm_script_path)

    def execute(self):
        """
        Execute the process based on the specified manager (local or slurm).
        """
        if self.manager == "local":
            return self._execute_locally()
        elif self.manager == "slurm":
            return self._execute_slurm()
        else:
            raise ValueError(f"Unsupported manager: {self.manager}")

import subprocess
import threading
import os
import sys
import logging
import tempfile
import time
import random
import yaml
from datetime import datetime

class Process:
    # Global registry to map process names to process instances.
    registry = {}

    """
    A class to define and execute processes with support for multiple managers,
    pre/post scripts, retries, and resource configurations.
    """
    def __init__(self, name, param_file=None, **kwargs):
        """
        Initialize the Process object.

        :param name (required): Name of the process.
        :param param_file: YAML format file(s) that includes different parameters
        :param kwargs: Additional parameters to configure the process.
        """
        # Load YAML parameters if provided
        yaml_params = self.parse_yaml_config(param_file) if param_file else {"global": {}, "process": {}}

        # Retrieve configurations: Process-specific first, fallback to global
        process_params = yaml_params["process"].get(name, {})
        global_params = yaml_params["global"]

        # Merge in priority order: global < process < kwargs
        self.params = {**global_params, **process_params, **kwargs}

        # Primary parameters
        self.name = name

        # Register the process and get depends_on parameter
        Process.registry[self.name] = self
        self.depends_on = self.params.get("depends_on", [])
        if isinstance(self.depends_on, str):
            self.depends_on = [self.depends_on]

        self.script = self.params.get("script", "#!/bin/bash")
        self.script_file = self.params.get("script_file", None)
        self.script_type = "script" if self.script != "#!/bin/bash" else "file" if self.script_file is not None else "script"
        self.script_parameters = self.params.get("script_parameters", None)
        self.script_parameters_file = self.params.get("script_parameters_file", None)

        # Directory parameters
        # self.project_directory = self.params.get("project_directory", os.path.dirname(os.path.abspath(sys.argv[0])))
        # self.project_directory = self.params.get("project_directory", os.getcwd())
        self.project_directory = os.path.abspath(self.params.get("project_directory", "."))
        os.makedirs(self.project_directory, exist_ok=True)
        self.logs_directory = os.path.abspath(self.params.get("logs_directory", os.path.join(self.project_directory, "logs")))
        os.makedirs(self.logs_directory, exist_ok=True)
        self.parameters_directory = self.params.get("parameters_directory", os.path.join(self.project_directory, "parameters"))

        # Setup monitoring directory
        self.monitoring_directory = self.params.get("monitoring_directory", os.environ.get("JAWM_MONITORING_DIRECTORY", None))
        try:
            os.makedirs(self.monitoring_directory, exist_ok=True) if self.monitoring_directory is not None else None
            self.running_directory, self.completed_directory = (os.path.join(self.monitoring_directory, 'Running'), os.path.join(self.monitoring_directory, 'Completed')) if self.monitoring_directory else (None, None)
            if self.monitoring_directory: os.makedirs(self.running_directory, exist_ok=True); os.makedirs(self.completed_directory, exist_ok=True)
        except Exception as e:
            self.logger.warning(f"Monitoring directory issue: {str(e)}")
            self.monitoring_directory = None

        # Management parameters
        self.manager = self.params.get("manager", "metal")
        # self.source_env = os.environ.copy()
        self.env = self.params.get("env", {})
        self.combined_env = {**os.environ.copy(), **self.env}
        self.inputs = self.params.get("inputs", {})
        self.outputs = self.params.get("outputs", {})
        self.retries = self.params.get("retries", 0)
        self.use_scratch = self.params.get("scratch", False)
        self.error_strategy = self.params.get("error_strategy", "retry")
        self.when = self.params.get("when", True)
        self.before_script = self.params.get("before_script", None)
        self.after_script = self.params.get("after_script", None)
        self.logger = logging.getLogger(name)

        # Local execution configurations
        self.manager_local = self.params.get("manager_local", {})

        # Slurm execution configurations
        self.manager_slurm = self.params.get("manager_slurm", {})

        # Execution environment configurations
        self.environment = self.params.get("environment", "local")
        self.container = self.params.get("container", None)
        self.environment_apptainer = self.params.get("environment_apptainer", {})
        self.environment_docker = self.params.get("environment_docker", {})
        self.environment = {"apptainer": "apptainer", "singularity": "apptainer", "docker": "docker"}.get(self.environment, "local") if self.container is not None else "local"

        # Metadata
        self.date_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.hash = f"{random.randint(0, 255):02x}"
        self.log_path = os.path.join(self.logs_directory, f"{self.name}_{self.date_time}_{self.manager}_{self.hash}")
        os.makedirs(self.log_path, exist_ok=True)

        # For reuse and track (doesn't come from the user parameters directly)
        self.base_script_path = None

        # A threading event that signals when this process has finished.
        self.finished_event = threading.Event()

    def parse_yaml_config(self, param_file):
        """
        Parses one or multiple YAML files and merges configurations.

        :param param_file: A string (single file) or a list of YAML file paths.
        :return: Dictionary with merged global and process-specific parameters.
        """
        yaml_params = {"global": {}, "process": {}}

        # Ensure param_file is a list
        if isinstance(param_file, str):
            param_file = [param_file]

        for yaml_file in param_file:
            try:
                with open(yaml_file, "r") as file:
                    yaml_data = yaml.safe_load(file) or []
            except Exception as e:
                raise ValueError(f"Failed to load YAML file {yaml_file}: {str(e)}")

            for entry in yaml_data:
                scope = entry.get("scope")
                name = entry.get("name", None)

                if scope == "global":
                    yaml_params["global"].update(entry)  # Merge into global scope
                elif scope == "process" and name:
                    if name not in yaml_params["process"]:
                        yaml_params["process"][name] = entry
                    else:
                        yaml_params["process"][name].update(entry)  # Merge process-specific configs

        return yaml_params

    def _script_placeholders(self, script_content):
        """
        Replace placeholders in the script content with provided parameters.
        :param script_content: The content of the script file.
        :return: The updated script content with placeholders replaced.
        """
        parameters = self.script_parameters or {}
        
        # Load additional parameters from file if provided
        if self.script_parameters_file:
            with open(self.script_parameters_file, "r") as param_file:
                file_parameters = {}
                for line in param_file:
                    # Skip empty lines or lines without an '='
                    if line.strip() and "=" in line:
                        # Split into key and value, removing unnecessary spaces
                        key, value = map(str.strip, line.strip().split("=", 1))
                        
                        # Remove surrounding quotes from the value if present
                        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                            value = value[1:-1]

                        file_parameters[key] = value
                parameters.update(file_parameters)

        # Replace placeholders in the script
        for key, value in parameters.items():
            placeholder = f"{{{{{key}}}}}"  # e.g., {{param_name}}
            script_content = script_content.replace(placeholder, str(value))

        return script_content
    
    def _generate_base_script(self):
        """
        Generate the script file for execution, replacing any placeholders with provided parameters.
        :return: The path to the script file.
        """
        if self.base_script_path is not None:
            # If the base script path is already set, return it directly
            return self.base_script_path

        self.logger.info(f"Preparing base script for process {self.name}")

        self.base_script_path = os.path.join(self.log_path, f"{self.name}.script")

        script_content = ""

        if self.script_type == "script":
            # If an inline script is provided, use it as the base content
            script_content = self.script
        elif self.script_type == "file" and self.script_file:
            # If a script file is provided, read its content
            with open(self.script_file, "r") as original_script:
                script_content = original_script.read()
            self.logger.info(f"Original script for process {self.script_file}")
        else:
            raise ValueError("Invalid script type or missing script content.")

        # Replace placeholders with provided parameters
        script_content = self._script_placeholders(script_content)

        # Write the updated script to the base script file
        with open(self.base_script_path, "w") as script_file:
            script_file.write(script_content)

        # Append original file path as a comment if applicable
        if self.script_type == "file" and self.script_file:
            with open(self.base_script_path, "a") as script_file:
                script_file.write(f"\n##### Original script file: {os.path.abspath(self.script_file)}\n")

        # Make the script executable
        os.chmod(self.base_script_path, 0o755)

        return self.base_script_path


    def _generate_slurm_script(self):
        """
        Generate a Slurm job script that executes the provided script as an executable file.
        :return: Path to the Slurm script.
        """
        self.logger.info(f"Generating Slurm job script for process: {self.name}")

        # Prepare base script and get the path
        base_script_path = self._generate_base_script()

        # Define the Slurm script file name
        slurm_script_path = os.path.join(self.log_path, f"{self.name}.slurm")

        if self.environment == "apptainer":
            slurm_script_command = (" ".join(self._build_apptainer_command(base_script_path)))
        elif self.environment == "docker":
            slurm_script_command = (" ".join(self._build_docker_command(base_script_path)))
        else:
            slurm_script_command = base_script_path

        # Create the Slurm job script
        with open(slurm_script_path, "w") as slurm_script_file:
            slurm_script_file.write("#!/bin/bash\n")  # Slurm script shebang
            
            # Add SLURM options dynamically
            for key, value in self.manager_slurm.items():
                slurm_script_file.write(f"#SBATCH --{key}={value}\n")

            # Call the executable script
            slurm_script_file.write(f"\n{slurm_script_command}\n")

        return slurm_script_path

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
        
    def _build_apptainer_command(self, script_path):
        """
        Build the Apptainer command dynamically based on user configurations.
        :param script_path: The path to the script to execute inside the container.
        :return: The Apptainer command as a list.
        """
        # Base command
        apptainer_command = ["apptainer", "exec"]

        # Apply user-defined Apptainer options dynamically
        for option, value in self.environment_apptainer.items():
            if isinstance(value, list):
                # Handle options that require multiple values (e.g., --bind)
                for v in value:
                    apptainer_command.extend([f"--{option}", str(v)])
            elif isinstance(value, bool):
                # Handle flags (e.g., --no-home)
                if value:  # Only include the flag if True
                    apptainer_command.append(f"--{option}")
            else:
                # Handle regular key-value options
                apptainer_command.extend([f"--{option}", str(value)])

        # Add environment variables
        if self.env:
            # apptainer_command.extend(["--env", f"{','.join(f'{k}="{v}"' for k, v in self.env.items())}"])
            for key, val in self.env.items():
                # apptainer_command.extend(["--env", f'{key}="{val}"'])
                apptainer_command.extend(["--env", f'{key}="{val}"' if " " in val else f"{key}={val}"])

        # Add container and script
        apptainer_command.extend([self.container, script_path])

        return apptainer_command
 
    def _build_docker_command(self, script_path):
        """
        Build the Docker command dynamically based on user configurations.
        
        :param script_path: The path to the script to execute inside the container.
        :return: The Docker command as a list.
        """
        # Base command
        docker_command = ["docker", "run", "--rm"]

        # Apply user-defined Docker options dynamically
        for option, value in self.environment_docker.items():
            if isinstance(value, list):
                # Handle options that require multiple values (e.g., --volume)
                for v in value:
                    docker_command.extend([f"--{option}", str(v)])
            elif isinstance(value, bool):
                # Handle flags (e.g., --privileged)
                if value:  # Only include the flag if True
                    docker_command.append(f"--{option}")
            else:
                # Handle regular key-value options
                docker_command.extend([f"--{option}", str(value)])

        # Add environment variables
        if self.env:
            for key, val in self.env.items():
                docker_command.extend(["-e", f'{key}="{val}"' if " " in val else f"{key}={val}"])

        # Mount working directory if necessary
        # docker_command.extend(["-v", f"{self.project_directory}:{self.project_directory}"])

        # Set working directory inside the container
        # docker_command.extend(["-w", self.project_directory])

        # Add container image and script to execute
        docker_command.extend([self.container, "/bin/bash", "-c", script_path])

        return docker_command

    def _monitoring_running_file(self, job_id, script_path):
        """
        Creates a file <self.manager>.<job_id>.txt in the running directory.
        """
        if self.running_directory:
            try:
                running_file_path = os.path.join(self.running_directory, f"{self.manager}.{job_id}.txt")
                with open(running_file_path, "w") as file:
                    file.write(f"Job ID: {job_id}\n")
                    file.write(f"Job Name: {self.name}\n")
                    file.write(f"Path: {script_path}")
            except Exception as e:
                self.logger.warning(f"Failed to create running file for {self.name} in Monitoring: {str(e)}")

    def _monitoring_completed_file(self, job_id, script_path, exit_code):
        """
        Moves the process from Running to Completed by deleting the running file
        and creating a new file in the Completed directory.
        """
        if self.running_directory and self.completed_directory:
            try:
                running_file_path = os.path.join(self.running_directory, f"{self.manager}.{job_id}.txt")
                completed_file_path = os.path.join(self.completed_directory, f"{self.manager}.{job_id}.{exit_code}.txt")

                # Remove the running file if it exists
                if os.path.exists(running_file_path):
                    os.remove(running_file_path)

                # Create the completed file
                with open(completed_file_path, "w") as file:
                    file.write(f"Job ID: {job_id}\n")
                    file.write(f"Job Name: {self.name}\n")
                    file.write(f"Path: {script_path}\n")
                    file.write(f"Exit Code: {exit_code}")

            except Exception as e:
                self.logger.warning(f"Failed to create completed file for {self.name} in Monitoring: {str(e)}")

    def _execute_metal(self):
        """
        Execute the process locally with resource constraints.
        :return: The output of the executed script.
        """
        self.logger.info(f"Executing process {self.name} locally")
        try:
            # Define the path for the script/log files
            base_script_path = self._generate_base_script()
            stdout_path = os.path.join(self.log_path, f"{self.name}.output")
            stderr_path = os.path.join(self.log_path, f"{self.name}.error")
            exitcode_path = os.path.join(self.log_path, f"{self.name}.exitcode")
            id_path = os.path.join(self.log_path, f"{self.name}.id")
            command_path = os.path.join(self.log_path, f"{self.name}.command")
            
            # Open the output and error files
            with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
                # Execute the script directly
                if self.environment == "apptainer":
                    self.logger.info(f"Executing process {self.name} with apptainer container {self.container}")
                    command = self._build_apptainer_command(base_script_path)
                    with open(command_path, "w") as command_path_file:
                        command_path_file.write(" ".join(command))
                    result = subprocess.Popen(
                        command,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        text=True
                    )
                elif self.environment == "docker":
                    self.logger.info(f"Executing process {self.name} with docker container {self.container}")
                    command = self._build_docker_command(base_script_path)
                    with open(command_path, "w") as command_path_file:
                        command_path_file.write(" ".join(command))
                    result = subprocess.Popen(
                        command,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        text=True
                    )
                else:
                    with open(command_path, "w") as command_path_file:
                        command_path_file.write(base_script_path)
                    result = subprocess.Popen(
                        [base_script_path],
                        env=self.combined_env,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        text=True
                    )
            process_id = result.pid
            self.logger.info(f"Process {self.name} started with PID: {process_id}")

            # Create monitoring file in Running directory
            self._monitoring_running_file(process_id, base_script_path)

            def monitor_process():
                """
                Monitor/log the process in a background thread.
                """
                elapsed_time = 0
                # start_time = time.time()
                # max_monitor_time = 5 * 24 * 3600

                while result.poll() is None:
                    # if time.time() - start_time > max_monitor_time:
                    #     self.logger.error(f"Process {self.name} exceeded maximum monitoring time. Killing process.")
                    #     result.terminate()
                    #     break
                    # log every 3mins of waiting for the process to be finished
                    if elapsed_time % 180 == 0:
                        self.logger.info(f"Process {self.name} (PID: {process_id}) is still running...")
                    elapsed_time += 5
                    time.sleep(5)  # Sleep for a while before checking again

                # Once finished, get the return code
                exitcode = result.returncode
                self.logger.info(f"Process {self.name} completed with exit code: {exitcode}")
                with open(exitcode_path, "w") as exitcode_file:
                    exitcode_file.write(str(exitcode))
                with open(id_path, "w") as id_file:
                    id_file.write(str(process_id))

                # Retries if fails
                if exitcode != 0:
                    with open(stderr_path, "r") as stderr_file:
                        error_message = stderr_file.read().strip()
                    self.logger.error(f"Process {self.name} failed with error: {error_message}")
                    if self.retries > 0:
                        self.logger.info(f"Retrying process {self.name}, {self.retries} retries left.")
                        self.retries -= 1
                        return self._execute_metal()
                    self.logger.error(f"Process {self.name} failed with error: {error_message}")
                    raise RuntimeError(f"Process {self.name} failed with error: {error_message}")
                
                # Create monitoring file in Completed directory
                self._monitoring_completed_file(process_id, base_script_path, exitcode)
                
                # Mark process as finished.
                self.finished_event.set()

            # Start monitoring in a background thread
            monitor_thread = threading.Thread(target=monitor_process, daemon=False)
            monitor_thread.start()

            # Return the output
            return process_id

        finally:
            # Ensure finished_event is set, even in case of failure
            self.finished_event.set()

    def _execute_slurm(self):
        """
        Execute the process as a Slurm job.
        :return: Slurm job ID.
        """
        self.logger.info(f"Executing process {self.name} in Slurm")
        self.logger.info(f"Log folder for process {self.name}: {self.log_path}")
        exitcode_path = os.path.join(self.log_path, f"{self.name}.exitcode")
        id_path = os.path.join(self.log_path, f"{self.name}.id")
        command_path = os.path.join(self.log_path, f"{self.name}.command")

        # Generate the Slurm job script
        slurm_script_path = self._generate_slurm_script()

        # Generate the sbatch command
        sbatch_command = self._generate_sbatch_command()
        sbatch_command.append(slurm_script_path)

        self.logger.info(f"Submitting process {self.name} with command: {' '.join(sbatch_command)}")
        with open(command_path, "w") as command_path_file:
            command_path_file.write(" ".join(sbatch_command))

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
                with open(id_path, "w") as id_file:
                    id_file.write(str(job_id))
                # Create monitoring file in Running directory
                self._monitoring_running_file(job_id, slurm_script_path)
            else:
                self.logger.error(f"Failed to submit process {self.name} to Slurm: {result.stderr}")
                raise RuntimeError(f"Slurm submission failed for process {self.name}")

            def monitor_slurm_job():
                """
                Monitor the Slurm job in the background and capture its exit code.
                """
                elapsed_time = 0
                retry_fail = 0
                max_fail = 10
                # start_time = time.time()
                # max_monitor_time = 5 * 24 * 3600

                while True:
                    # if time.time() - start_time > max_monitor_time:
                    #     self.logger.error(f"Slurm job {job_id} exceeded maximum monitoring time")
                    #     break
                    # Query the job's status and exit code using sacct
                    job_info = subprocess.run(
                        ["sacct", "-j", job_id, "--format=JobID,State,ExitCode", "-n"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )

                    # Handle failure on slurm job querieng
                    if job_info.returncode != 0:
                        if retry_fail >= max_fail:
                            self.logger.error(f"Max retries ({max_fail}) for quering job with sacct tool reached for id {job_id}. Please make sure, sacct tool is working. Monitoring stopped!")
                            break
                        self.logger.warning(f"Failed to query job {job_id} status: {job_info.stderr}")
                        time.sleep(min(10 * (2 ** retry_fail), 300))
                        retry_fail += 1
                        continue  # Retry querying

                    # Parse the job state and exit code
                    output = job_info.stdout.strip()
                    if output:
                        _, state, exit_code = output.split()[:3]
                        # log every 3mins of waiting for the process to be finished
                        if elapsed_time % 180 == 0:
                            self.logger.info(f"Job {job_id} state: {state}, exit code: {exit_code}")
                        if state in {"COMPLETED", "FAILED", "CANCELLED"}:
                            self.logger.info(f"Job {job_id} completed with exit code: {exit_code}")
                            # Create monitoring file in Completed directory
                            self._monitoring_completed_file(job_id, slurm_script_path, exit_code)
                            # log the exit code
                            with open(exitcode_path, "w") as exitcode_file:
                                exitcode_file.write(str(exit_code))
                                break
                            

                    time.sleep(10)  # Check status every 10 seconds
                    elapsed_time += 10

                # Mark process as finished.
                self.finished_event.set()

            # Start monitoring in a background thread
            monitor_thread = threading.Thread(target=monitor_slurm_job, daemon=False)
            monitor_thread.start()

            return job_id

        finally:
            # Ensure finished_event is set, even in case of failure
            self.finished_event.set()

    def execute(self):
        """
        Execute the process based on the specified manager (local or slurm).
        """
        # Skip if the condition does not fulfilled
        if not self.when:
            self.logger.info(f"Process {self.name} skipped as execution condition did not fulfilled!")
            self.finished_event.set()
            return

        # Wait for dependencies to complete.
        for dep in self.depends_on:
            dep_proc = Process.registry.get(dep)
            if dep_proc is None:
                self.logger.warning(f"Dependency {dep} not found in registry, skipping wait.")
            else:
                self.logger.info(f"Waiting for dependency process {dep} to finish before executing {self.name}.")
                dep_proc.finished_event.wait()

        if self.manager == "metal":
            return self._execute_metal()
        elif self.manager == "slurm":
            return self._execute_slurm()
        else:
            raise ValueError(f"Unsupported manager: {self.manager}")

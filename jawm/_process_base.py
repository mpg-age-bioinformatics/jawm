import os
import yaml
import re
from functools import reduce
from datetime import datetime

# Setup method registration for dynamic injection into the main Process class
from ._method_lib import register_method

__methods__ = []
register = register_method(__methods__)


@register
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
            self._log_error_summary(f"Failed to load YAML file {yaml_file}: {str(e)}")
            Process.stop_future_event.set()
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


@register
def _log_error_summary(self, error_message):
    """
    Log errors to a central error summary file for easy tracking.
    """
    with open(self.error_summary_file, "a") as error_log:
        error_log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Process: {self.name} (Hash: {self.hash})\n")
        error_log.write(f"  Error: {error_message}\n")
        error_log.write("-" * 80 + "\n")  # Separator for readability


@register
def _script_placeholders(self, script_content):
    """
    Replace placeholders in the script content with parameters or object attribute values.
    Supports flat {{KEY}} and object attributes like {{JAWM.Process.logs_directory}} → self.logs_directory.
    If the provided parameter values is not found, then {{VAR}} would replaced by empty string.
    This can fail a scipt if not used properly. user needs to be cautios with the use of {{VAR}} in the script.
    :param script_content: The content of the script file.
    :return: The updated script content with placeholders replaced.
    """

    parameters = self.script_parameters or {}

    # Load additional parameters from file if provided
    if self.script_parameters_file:
        with open(self.script_parameters_file, "r") as param_file:
            for line in param_file:
                if line.strip() and "=" in line:
                    key, value = map(str.strip, line.strip().split("=", 1))
                    if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                        value = value[1:-1]
                    parameters[key] = value

    # Resolve nested attribute like JAWM.Process.logs_directory → self.logs_directory
    def resolve_placeholder(key):
        if key in parameters:
            return str(parameters[key])

        prefix = "JAWM.Process."
        if key.startswith(prefix):
            attr_path = key[len(prefix):]  # get 'logs_directory'
            try:
                # Support nested attributes, e.g., a.b.c
                value = reduce(getattr, attr_path.split("."), self)
                return "" if value is None else str(value)
            except AttributeError:
                return ""  # or keep placeholder if preferred: return f"{{{{{key}}}}}"

        return f"{{{{{key}}}}}"  # if not matched, return as-is

    # Regex pattern to find all {{...}} placeholders
    pattern = re.compile(r"\{\{([^}]+)\}\}")

    return pattern.sub(lambda match: resolve_placeholder(match.group(1).strip()), script_content)


@register
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
        self._log_error_summary("Invalid script type or missing script content.")
        Process.stop_future_event.set()
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


@register
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


@register
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


@register
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


@register
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


@register
def _apply_retry_parameters(self, attempt_i):
    """
    Apply retry-specific parameters before a retry attempt.
    :param attempt_i: The current attempt index (1-based).
    """
    retry_params = self.retry_overrides.get(attempt_i, {})
    if not retry_params:
        return

    self.logger.info(f"Applying retry parameters for retry attempt {attempt_i}: {retry_params}")

    for key, value in retry_params.items():
        # Handle existing fields to update
        if hasattr(self, key):
            current_val = getattr(self, key)
            if isinstance(current_val, dict) and isinstance(value, dict):
                current_val.update(value)
                setattr(self, key, current_val)
            else:
                setattr(self, key, value)
        else:
            # If it's a new attribute, just assign
            setattr(self, key, value)


@register
def get_id(self):
    """
    Returns the runtime job ID (PID for metal, Job ID for Slurm) if available.
    Returns None if the job hasn't started or the ID file doesn't exist.
    """
    id_file_path = os.path.join(self.log_path, f"{self.name}.id")
    if os.path.exists(id_file_path):
        with open(id_file_path, "r") as f:
            job_id = f.read().strip()
        return job_id
    return None
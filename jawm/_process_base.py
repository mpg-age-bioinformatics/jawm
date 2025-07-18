import os
import yaml
import re
import time
import fnmatch
import shlex
from functools import reduce
from datetime import datetime

# Setup method registration for dynamic injection into the main Process class
from ._method_lib import register_method

__methods__ = []
register = register_method(__methods__)


@register
def _parse_yaml_config(self, param_file):
    """
    Parses one or multiple YAML files or a directory containing YAMLs and merges configurations.

    :param param_file: A string (single file or directory) or a list of YAML file paths.
    :return: Dictionary with merged global and process-specific parameters.
    """
    yaml_params = {"global": {}, "process": {}}

    # Ensure param_file is a list
    if isinstance(param_file, str):
        if os.path.isdir(param_file):
            # Use all .yaml/.yml files in the directory
            param_file = sorted([
                os.path.join(param_file, f)
                for f in os.listdir(param_file)
                if f.endswith((".yaml", ".yml"))
            ])
        else:
            param_file = [param_file]
    elif isinstance(param_file, list):
        # Only expand individual files; directories not allowed in list
        param_file = [p for p in param_file if os.path.isfile(p)]

    for yaml_file in param_file:
        try:
            with open(yaml_file, "r") as file:
                yaml_data = yaml.safe_load(file) or []
        except Exception as e:
            # It may not log in error summary if self.error_summary_file is not yet there
            self._log_error_summary(f"Failed to load YAML file {yaml_file}: {str(e)}")
            self.__class__.stop_future_event.set()
            raise ValueError(f"Failed to load YAML file {yaml_file}: {str(e)}")

        if isinstance(yaml_data, dict):
            yaml_data = [yaml_data]

        for entry in yaml_data:
            if not isinstance(entry, dict):
                continue

            scope = entry.get("scope")
            name = entry.get("name", None)

            # Merge into global scope
            if scope == "global":
                yaml_params["global"].update(entry)
            # Merge Process specific config with wildcard enabled
            elif scope == "process" and name and self.name: 
                if fnmatch.fnmatch(self.name, name):
                    if self.name not in yaml_params["process"]:
                        yaml_params["process"][self.name] = entry.copy()
                    else:
                        yaml_params["process"][self.name].update(entry)

    return yaml_params


@register
def _log_error_summary(self, error_message, type_text="Error"):
    """
    Log errors to a central error summary file for easy tracking.
    """
    if not getattr(self, "error_summary_file", None):
        return
    if not error_message:
        error_message = "Empty error message, possibly the Process was killed!"
    with open(self.error_summary_file, "a") as error_log:
        error_log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Process: {self.name} (Hash: {self.hash})\n")
        error_log.write(f"  {type_text}: {error_message}\n")
        error_log.write("-" * 80 + "\n")  # Separator for readability


@register
def _script_placeholders(self, script_content):
    """
    Replace placeholders in the script content with parameters or object attribute values.
    Supports flat {{KEY}} and object attributes like {{JAWM.Process.logs_directory}} → self.logs_directory.
    If the provided parameter values is not found, then {{JAWM.Process.*}} would replaced by empty string.
    {{VAR}} would stay the same in case of missing placeholder value.
    This can fail a scipt if not used properly. user needs to be cautios with the use of {{VAR}} in the script.
    :param script_content: The content of the script file.
    :return: The updated script content with placeholders replaced.
    """

    parameters = self.script_variables or {}

    # Load additional parameters from file if provided
    if self.script_variables_file:
        file_ext = os.path.splitext(self.script_variables_file)[1].lower()

        try:
            with open(self.script_variables_file, "r") as param_file:
                if file_ext in [".yaml", ".yml"]:
                    parsed_yaml = yaml.safe_load(param_file)
                    if isinstance(parsed_yaml, dict):
                        parameters.update(parsed_yaml)

                    elif isinstance(parsed_yaml, list):
                        for entry in parsed_yaml:
                            if not isinstance(entry, dict):
                                continue

                            scope = entry.get("scope")
                            name = entry.get("name", None)

                            if scope == "global" and "script_variables" in entry:
                                if isinstance(entry["script_variables"], dict):
                                    parameters.update(entry["script_variables"])

                            elif scope == "process" and name and self.name:
                                if fnmatch.fnmatch(self.name, name):
                                    if isinstance(entry.get("script_variables"), dict):
                                        parameters.update(entry["script_variables"])

                    else:
                        self.logger.warning(f"{self.script_variables_file} contains no usable script_variables.")

                else:
                    for line in param_file:
                        if line.strip() and "=" in line:
                            key, value = map(str.strip, line.strip().split("=", 1))
                            if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                                value = value[1:-1]
                            parameters[key] = value
        except Exception as e:
            self.logger.warning(f"Failed to load script_variables_file '{self.script_variables_file}': {e}")

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
                self.logger.warning(f"Unresolved JAWM.Process variables in Process script (replaced by empty string): {key}")
                return ""  # or keep placeholder if preferred: return f"{{{{{key}}}}}"

        self.logger.warning(f"Unresolved placeholder variables in Process script (kept as-is): {key}")
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
def _generate_command_wrapper(self, main_command):
    """
    Compose full bash command with before_script && main_command && after_script.
    :param main_command: Base command
    :return: Comand wrapped with before or after script command
    """
    parts = []
    if self.before_script:
        parts.append(self.before_script.strip())
    parts.append(" ".join(main_command))
    if self.after_script:
        parts.append(self.after_script.strip())
    return " && ".join(parts)


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
                apptainer_command.extend([option, str(v)])
        elif isinstance(value, bool):
            # Handle flags (e.g., --no-home)
            if value:  # Only include the flag if True
                apptainer_command.append(option)
        else:
            # Handle regular key-value options
            apptainer_command.extend([option, str(value)])

    # Add environment variables
    if self.env:
        # apptainer_command.extend(["--env", f"{','.join(f'{k}="{v}"' for k, v in self.env.items())}"])
        for key, val in self.env.items():
            # apptainer_command.extend(["--env", f'{key}="{val}"'])
            apptainer_command.extend(["--env", f'{key}="{val}"' if " " in val else f"{key}={val}"])

    # Add container and script
    if self.container_before_script or self.container_after_script:
        command_parts = []
        if self.container_before_script:
            command_parts.append(self.container_before_script.strip())
        command_parts.append(script_path)
        if self.container_after_script:
            command_parts.append(self.container_after_script.strip())

        wrapped_command = shlex.quote(" && ".join(command_parts))
        apptainer_command.extend([self.container, "/bin/bash", "-c", wrapped_command])
    else:
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
                docker_command.extend([option, str(v)])
        elif isinstance(value, bool):
            # Handle flags (e.g., --privileged)
            if value:  # Only include the flag if True
                docker_command.append(option)
        else:
            # Handle regular key-value options
            docker_command.extend([option, str(value)])

    # Add environment variables
    if self.env:
        for key, val in self.env.items():
            docker_command.extend(["-e", f'{key}="{val}"' if " " in val else f"{key}={val}"])

    # Add container image and script to execute
    if self.container_before_script or self.container_after_script:
        command_parts = []
        if self.container_before_script:
            command_parts.append(self.container_before_script.strip())
        command_parts.append(script_path)
        if self.container_after_script:
            command_parts.append(self.container_after_script.strip())

        wrapped_command = shlex.quote(" && ".join(command_parts))
        docker_command.extend([self.container, "/bin/bash", "-c", wrapped_command])
    else:
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
                file.write(f"Job Hash: {self.hash}\n")
                file.write(f"Path: {script_path}\n")
                file.write(f"Process Initiated: {self.date_time}\n")
                file.write(f"Run Start: {getattr(self, 'execution_start_at', 'NA')}")
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
                file.write(f"Job Hash: {self.hash}\n")
                file.write(f"Path: {script_path}\n")
                file.write(f"Process Initiated: {self.date_time}\n")
                file.write(f"Run Start: {getattr(self, 'execution_start_at', 'NA')}\n")
                file.write(f"Run End: {datetime.now().strftime('%Y%m%d_%H%M%S')}\n")
                file.write(f"Exit Code: {exit_code}")
        except Exception as e:
            self.logger.warning(f"Failed to create completed file for {self.name} in Monitoring: {str(e)}")


@register
def _apply_retry_parameters(self, attempt_i):
    """
    Apply override parameters defined for a specific retry attempt.
    Supports formats like "+2", "+20%" for resource keys, and auto-adjusts
    Slurm time strings like "00:01:00" using seconds or percentage.
    
    :param attempt_i: The current attempt index (1-based).
    """
    retry_params = self.retry_overrides.get(attempt_i, {})
    if not retry_params:
        return

    self.logger.info(f"Applying retry parameters for retry attempt {attempt_i}: {retry_params}")

    def _adjust_time(time_str, delta):
        """
        Adjust a time string in HH:MM:SS format using absolute (value as second) or percentage-based delta.
        """
        try:
            h, m, s = map(int, time_str.split(":"))
            base_seconds = h * 3600 + m * 60 + s
            if isinstance(delta, str) and delta.endswith("%"):
                new_seconds = base_seconds * (1 + float(delta.strip('%')) / 100)
            else:
                new_seconds = base_seconds + int(delta)
            hrs, rem = divmod(int(new_seconds), 3600)
            mins, secs = divmod(rem, 60)
            return f"{hrs:02}:{mins:02}:{secs:02}"
        except:
            return time_str

    def _apply_relative(val, delta):
        """
        Adjust numeric or time values with absolute or percentage deltas.
        Supports formats like "+2", "+20%", and HH:MM:SS time strings.
        """
        val = str(val)
        
        if re.match(r"^\d{1,2}:\d{2}:\d{2}$", val):
            return _adjust_time(val, delta)

        m = re.match(r"^(\d+(?:\.\d+)?)([a-zA-Z]*)$", val)
        if not m:
            return val
        num, unit = float(m.group(1)), m.group(2)

        try:
            if isinstance(delta, str) and delta.endswith("%") and delta[:-1].lstrip("+-").replace('.', '', 1).isdigit():
                new_val = round(num * (1 + float(delta.strip('%')) / 100), 2)
            elif isinstance(delta, str) and delta.lstrip("+-").replace('.', '', 1).isdigit():
                new_val = round(num + float(delta), 2)
            else:
                return delta
            return f"{int(new_val) if new_val.is_integer() else new_val}{unit}"
        except:
            return val

    for key, value in retry_params.items():
        if hasattr(self, key):
            cur = getattr(self, key)
            if isinstance(cur, dict) and isinstance(value, dict):
                for k, v in value.items():
                    cur[k] = _apply_relative(cur[k], v) if k in cur else v
                setattr(self, key, cur)
            else:
                setattr(self, key, _apply_relative(cur, value))
        else:
            setattr(self, key, value)


@register
def _read_log_file(self, filename):
    """
    Internal helper to read a log file's content, stripping trailing whitespace.
    Returns None if the file does not exist.
    """
    file_path = os.path.join(self.log_path, filename)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return f.read().strip()
    return None


@register
def get_id(self, max_wait=3, interval=0.5):
    """Return the content of the process .id file (PID or Slurm job ID), or None if unavailable (default, retrying up to: max_wait=3, interval=0.5)."""
    for _ in range(int(max_wait / interval)):
        if (val := self._read_log_file(f"{self.name}.id")):
            return val
        time.sleep(interval)
    return None


@register
def get_output(self):
    """Return the content of the process .output file, or None if unavailable."""
    return self._read_log_file(f"{self.name}.output")


@register
def get_error(self):
    """Return the content of the process .error file, or None if unavailable."""
    return self._read_log_file(f"{self.name}.error")


@register
def get_exitcode(self):
    """Return the content of the process .exitcode file, or None if unavailable."""
    return self._read_log_file(f"{self.name}.exitcode")


@register
def get_command(self):
    """Return the content of the process .command file, or None if unavailable."""
    return self._read_log_file(f"{self.name}.command")


@register
def get_script(self):
    """Return the content of the process .script file, or None if unavailable."""
    return self._read_log_file(f"{self.name}.script")


@register
def get_slurm(self):
    """Return the content of the process .slurm file containing slurm commands, or None if unavailable."""
    return self._read_log_file(f"{self.name}.slurm")


@register
def is_finished(self):
    """Return True or False based on whether the Process has finished or not"""
    return self.finished_event.is_set()
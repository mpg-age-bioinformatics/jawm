import os
import yaml
import re
import fnmatch
import shlex
import hashlib
import time
from functools import reduce
from datetime import datetime
from urllib.parse import urlparse

# Setup method registration for dynamic injection into the main Process class
from ._method_lib import register_method
from ._utils import _expand_relpaths_in_value

__methods__ = []
register = register_method(__methods__)


# ----------------------------------------------------------
#   Process instance specific internal methods
# ---------------------------------------------------------

@register
def _prepare_base_dirs(self):
    """
    Prepare/create necessary file and folder, should be called in execution
    """
    os.makedirs(self.project_directory, exist_ok=True)
    os.makedirs(self.logs_directory, exist_ok=True)
    try:
        os.makedirs(self.monitoring_directory, exist_ok=True) if self.monitoring_directory is not None else None
        self.running_directory, self.completed_directory = (os.path.join(self.monitoring_directory, 'Running'), os.path.join(self.monitoring_directory, 'Completed')) if self.monitoring_directory else (None, None)
        if self.monitoring_directory: os.makedirs(self.running_directory, exist_ok=True); os.makedirs(self.completed_directory, exist_ok=True)
    except Exception as e:
        self.logger.warning(f"Monitoring directory issue: {str(e)}")
        self.monitoring_directory = None
    os.makedirs(self.log_path, exist_ok=True)


@register
def _generate_hash_params(self):
    """
    Generate a 6-char SHA256 prefix from:
      - sorted self.params (so path strings also affect it),
      - content hash of script_file (file only),
      - content hash of param_file / var_file (files or directories),
        filtering directory contents by allowed extensions.

    Returns
    -------
    str
        6-character hexadecimal hash prefix.
    """
    from ._utils import hash_content

    # Hash the parameters themselves (stable ordering)
    h = hashlib.sha256()
    ignored_params = {"resume", "when", "desc"}
    filtered_params = {k: v for k, v in (self.params or {}).items() if k not in ignored_params}
    base_items = sorted(filtered_params.items())
    h.update(repr(base_items).encode())

    # Add content digests for referenced files/dirs
    # script_file (single file path)
    try:
        sf = self.params.get("script_file", None)
        if sf:
            digest = hash_content(sf, recursive=False)
            h.update(digest.encode())
    except Exception:
        pass

    # param_file (file or directory; restrict to YAML when directory)
    try:
        pf = self.params.get("param_file", None)
        if pf:
            digest = hash_content(pf, allowed_extensions=["yaml", "yml"], recursive=False)
            h.update(digest.encode())
    except Exception:
        pass

    # var_file (file/list/dir; restrict to YAML/RC/ENV/CONF when directory)
    try:
        vf = self.params.get("var_file", None)
        if vf:
            digest = hash_content(vf, allowed_extensions=["yaml", "yml", "rc", "env", "conf"], recursive=False)
            h.update(digest.encode())
    except Exception:
        pass

    return h.hexdigest()[:6]


@register
def _run_manager(self):
    """
    A helper to choose between different manager execution
    """
    if self.manager == "local":
        self._execute_local()
    elif self.manager == "slurm":
        self._execute_slurm()
    elif self.manager == "kubernetes":
        self._execute_kubernetes()
    else:
        self._log_error_summary(f"Unsupported manager: {self.manager}", type_text="InvalidValue")
        self.logger.error(f"Unsupported manager: {self.manager}")
        self.__class__.stop_future_event.set()
        self.finished_event.set()
        return

@register
def _parse_yaml_config(self, param_file):
    """
    Parses one or multiple YAML files or a directory containing YAMLs and merges configurations.
    Optional `includes:` support (list or string) to include additional param files, resolved relative to YAML file.

    :param param_file: A string (single file or directory) or a list of YAML file paths.
    :return: Dictionary with merged global and process-specific parameters.
    """
    yaml_params = {"global": {}, "process": {}}

    # Ensure param_file is a list
    if isinstance(param_file, str):
        if os.path.isdir(param_file):
            param_file = sorted(
                os.path.join(param_file, f)
                for f in os.listdir(param_file)
                if f.endswith((".yaml", ".yml"))
            )
        else:
            param_file = [param_file]
    elif isinstance(param_file, list):
        # Only expand individual files; directories not allowed in list
        param_file = [p for p in param_file if os.path.isfile(p)]

    STRUCT_KEYS = {"scope", "name", "includes"}

    def _merge(target, new):
        """Shallow-merge dict values, overwrite scalars."""
        for k, v in new.items():
            if k in target and isinstance(target[k], dict) and isinstance(v, dict):
                target[k] = {**target[k], **v}
            else:
                target[k] = v

    def _load_yaml_entries(path, base_dir):
        """Load YAML as list-of-entries, apply relpath expansion using base_dir."""
        with open(path, "r") as f:
            data = yaml.safe_load(f) or []
        data = _expand_relpaths_in_value(data, base_dir)
        if isinstance(data, dict):
            data = [data]
        return data if isinstance(data, list) else []

    def _expand_includes_in_place(entries, visited, base_dir):
        """
        Expand `includes:` directives in-place, preserving order.
        Includes are resolved relative to base_dir (the containing YAML file's directory).
        Cycle-safe via `visited` (realpaths). Raises on missing include.
        """
        i = 0
        while i < len(entries):
            entry = entries[i]
            if not isinstance(entry, dict):
                i += 1
                continue

            incs = entry.get("includes")
            if not incs:
                i += 1
                continue

            inc_list = incs if isinstance(incs, (list, tuple)) else [incs]
            expanded_paths = []

            for p in inc_list:
                p = os.path.expanduser(os.path.expandvars(str(p)))
                if not os.path.isabs(p):
                    p = os.path.join(base_dir, p)

                if os.path.isdir(p):
                    expanded_paths.extend(sorted(
                        os.path.join(p, f)
                        for f in os.listdir(p)
                        if f.endswith((".yaml", ".yml"))
                    ))
                else:
                    expanded_paths.append(p)

            inserted = []
            for inc_path in expanded_paths:
                if not os.path.exists(inc_path):
                    raise ValueError(f"Included YAML path not found: {inc_path}")

                real = os.path.realpath(inc_path)
                if real in visited:
                    # Avoid infinite loops
                    continue
                visited.add(real)

                inc_base_dir = os.path.dirname(os.path.abspath(inc_path))
                inc_entries = _load_yaml_entries(inc_path, inc_base_dir)
                _expand_includes_in_place(inc_entries, visited, inc_base_dir)
                inserted.extend(inc_entries)

            # Replace the includes-only entry with the included entries at the same position
            entries[i:i+1] = inserted
            # Do NOT increment i; process what we inserted next.
        return entries

    for yaml_file in param_file:
        try:
            visited = {os.path.realpath(yaml_file)}
            base_dir = os.path.dirname(os.path.abspath(yaml_file))

            yaml_data = _load_yaml_entries(yaml_file, base_dir)
            _expand_includes_in_place(yaml_data, visited, base_dir)

        except Exception as e:
            try:
                self._log_error_summary(
                    f"Failed to load/parse YAML file {yaml_file}: {str(e)}",
                    type_text="ErrorYAML",
                )
            except Exception:
                pass
            if hasattr(self.__class__, "stop_future_event"):
                self.__class__.stop_future_event.set()
            raise ValueError(f"Failed to load/parse YAML file {yaml_file}:\n{str(e)}") from None

        # Operate on the entries
        for entry in yaml_data:
            if not isinstance(entry, dict):
                continue

            scope = entry.get("scope")
            name = entry.get("name", None)

            clean_entry = {k: v for k, v in entry.items() if k not in STRUCT_KEYS}

            # Merge into global scope
            if scope == "global":
                _merge(yaml_params["global"], clean_entry)

            # Merge Process-specific config (supports single name or list of names)
            elif scope == "process" and name and self.name:
                names = name if isinstance(name, (list, tuple)) else [name]
                for n in names:
                    if fnmatch.fnmatch(self.name, n):
                        block = yaml_params["process"].setdefault(self.name, {})
                        _merge(block, clean_entry)
                        break

    return yaml_params


@register
def _log_error_summary(self, error_message, type_text="Error"):
    """
    Log errors to a central error summary file for easy tracking.
    """
    try:
        if not getattr(self, "error_summary_file", None):
            return
        if not error_message:
            error_message = "Empty error message, possibly the Process was killed!"

        log_path_info = ""
        if getattr(self, "log_path", None):
            log_path_info = f"\nLog folder: {self.log_path}"

        with open(self.error_summary_file, "a") as error_log:
            error_log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Process: {self.name} (Hash: {self.hash}){log_path_info}\n")
            error_log.write(f"{type_text}: {error_message}\n")
            error_log.write("-" * 80 + "\n")  # Separator for readability
    except Exception as e:
        try:
            self.logger.warning(f"Failed to write error summary: {e}")
        except Exception:
            pass


@register
def _script_placeholders_and_mkdir(self, script_content):
    """
    Replace placeholders in the script content with parameters or object attribute values.
    Supports flat {{KEY}} and object attributes like {{jawm.Process.logs_directory}} → self.logs_directory.
    If the provided parameter values is not found, then {{jawm.Process.*}} would replaced by empty string.
    {{VAR}} would stay the same in case of missing placeholder value.
    This can fail a scipt if not used properly. user needs to be cautios with the use of {{VAR}} in the script.
    :param script_content: The content of the script file.
    :return: The updated script content with placeholders replaced.
    """

    parameters = self.var or {}

    # Load additional parameters from file if provided
    if self.var_file:
        try:
            from ._utils import read_variables, _add_prefix_aliases
            loaded = read_variables(
                self.var_file,
                process_name=self.name,
                output_type="dict"
            ) or {}
            parameters.update(loaded)
            _add_prefix_aliases(parameters)
        except Exception as e:
            self.logger.warning(f"Failed to load var_file '{str(self.var_file)}': {e}")

    # Ensure mk.* directories exist once per process instance ---
    try:
        created = getattr(self, "_mk_dirs_created", set())

        def _abs_path(p):
            p = os.path.expanduser(str(p))
            if os.path.isabs(p):
                return os.path.abspath(p)
            base = getattr(self, "project_directory", os.getcwd())
            return os.path.abspath(os.path.join(base, p))

        for k, v in (parameters or {}).items():
            if isinstance(k, str) and k.startswith("mk.") and v:
                path = _abs_path(v)
                try:
                    if not os.path.exists(path):
                        os.makedirs(path, exist_ok=True)
                        self.logger.info(f"mk.* created directory {path}")
                        created.add(path)
                    else:
                        self.logger.debug(f"mk.* skipped, already exists: {path}")
                except Exception as e:
                    self.logger.warning(f"mk.* could not create {path}: {e}")
        self._mk_dirs_created = created
    except Exception as e:
        self.logger.warning(f"mk.* directory setup failed: {e}")

    # Resolve nested attribute like jawm.Process.logs_directory → self.logs_directory
    def resolve_placeholder(key):
        if key in parameters:
            val = parameters[key]

            # Only mk.* and map.* should be turned into absolute paths
            if isinstance(key, str) and (key.startswith("mk.") or key.startswith("map.")):
                if not getattr(self, "automated_mount", True):
                    def _to_abs(p):
                        p = os.path.expanduser(str(p))
                        if os.path.isabs(p):
                            return os.path.abspath(p)
                        base = getattr(self, "project_directory", os.getcwd())
                        return os.path.abspath(os.path.join(base, p))
                    return _to_abs(val)
                return "" if val is None else str(val)

            return "" if val is None else str(val)

        prefix = "jawm.process."
        if key.lower().startswith(prefix):
            attr_path = key[len(prefix):]  # get 'logs_directory'
            try:
                # Support nested attributes, e.g., a.b.c
                value = reduce(getattr, attr_path.split("."), self)
                return "" if value is None else str(value)
            except AttributeError:
                self.logger.warning(f"Unresolved jawm.Process variables in Process script (replaced by empty string): {key}")
                return ""  # or keep placeholder if preferred: return f"{{{{{key}}}}}"

        self.logger.warning(f"Unresolved placeholder variables in Process script (kept as-is): {key}")
        return f"{{{{{key}}}}}"  # if not matched, return as-is

    # Regex pattern to find all {{...}} placeholders
    pattern = re.compile(r"\{\{([^}]+)\}\}")

    return pattern.sub(lambda match: resolve_placeholder(match.group(1).strip()), script_content)


@register
def _generate_base_script(self, caching=False):
    """
    Generate the script file for execution, replacing any placeholders with provided parameters.
    :param caching: Check cached base_script_path
    :return: The path to the script file.
    """
    if caching and self.base_script_path is not None:
        # If the base script path is already set, return it directly
        return self.base_script_path

    self.logger.info(f"Preparing base script for process {self.name}")

    self.base_script_path = os.path.join(self.log_path, f"{self.name}.script")

    script_content = ""

    if self._script_type == "script":
        # If an inline script is provided, use it as the base content
        script_content = self.script
    elif self._script_type == "file" and self.script_file:
        # If a script file is provided, read its content
        with open(self.script_file, "r") as original_script:
            script_content = original_script.read()
        self.logger.info(f"Original script for process {self.script_file}")
    else:
        self._log_error_summary("Invalid script type or missing script content.", type_text="ErrorScript")
        self.__class__.stop_future_event.set()
        self.finished_event.set()
        raise ValueError("Invalid script type or missing script content.")

    # Replace placeholders with provided parameters
    script_content = self._script_placeholders_and_mkdir(script_content)

    # Write the updated script to the base script file
    self._safe_write_file(self.base_script_path, script_content)

    # Append original file path as a comment if applicable
    if self._script_type == "file" and self.script_file:
        self._safe_write_file(self.base_script_path, f"\n##### Original script file: {os.path.abspath(self.script_file)}\n", "a")

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
            for v in value:
                if option in ("--bind", "-B"):
                    apptainer_command.extend([option, _normalize_user_bind(v)])
                else:
                    apptainer_command.extend([option, str(v)])
        elif isinstance(value, bool):
            # Handle flags (e.g., --no-home)
            if value:  # Only include the flag if True
                apptainer_command.append(option)
        else:
            # Handle regular key-value options
            apptainer_command.extend([option, str(value)])

    # Collecting existing mount
    existing = set()
    for opt, val in (self.environment_apptainer or {}).items():
        if opt not in ("--bind", "-B"):
            continue
        vals = val if isinstance(val, list) else [val]
        for one in vals:
            existing.add(_normalize_mount_spec(_normalize_user_bind(one)))

    if getattr(self, "automated_mount", True):
        # Bind log path to make sure
        log_dir = os.path.abspath(self.log_path)
        log_spec = _normalize_mount_spec(f"{log_dir}:{log_dir}")
        if log_spec not in existing:
            apptainer_command.extend(["--bind", log_spec])

        # Mount, create mk, map from vars
        for m in self._auto_mounts_from_vars():
            spec = _normalize_mount_spec(f'{m["src"]}:{m["dst"]}')
            if spec not in existing:
                apptainer_command.extend(["--bind", spec])


    # Add environment variables
    if self.env:
        # apptainer_command.extend(["--env", f"{','.join(f'{k}="{v}"' for k, v in self.env.items())}"])
        for key, val in self.env.items():
            # apptainer_command.extend(["--env", f'{key}="{val}"'])
            apptainer_command.extend(["--env", f'{key}="{val}"' if " " in val else f"{key}={val}"])

    image_ref = self._normalize_apptainer_image(self.container)

    # Add container and script
    if self.container_before_script or self.container_after_script:
        command_parts = []
        if self.container_before_script:
            command_parts.append(self.container_before_script.strip())
        command_parts.append(script_path)
        if self.container_after_script:
            command_parts.append(self.container_after_script.strip())

        wrapped_command = shlex.quote(" && ".join(command_parts))
        apptainer_command.extend([image_ref, "/bin/bash", "-c", wrapped_command])
    else:
        apptainer_command.extend([image_ref, script_path])

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
                if option in ("-v", "--volume"):
                    docker_command.extend([option, _normalize_user_bind(v)])
                else:
                    docker_command.extend([option, str(v)])
        elif isinstance(value, bool):
            # Handle flags (e.g., --privileged)
            if value:  # Only include the flag if True
                docker_command.append(option)
        else:
            # Handle regular key-value options
            docker_command.extend([option, str(value)])

    # Implement run as current user
    if getattr(self, "docker_run_as_user", False):
        user_set_u = any(opt in (self.environment_docker or {}) for opt in ("-u", "--user"))
        if not user_set_u:
            user_spec = f"{os.getuid()}:{os.getgid()}"
            docker_command.extend(["-u", user_spec])

    # Collecting existing mount
    existing = set()
    for opt, val in (self.environment_docker or {}).items():
        if opt not in ("-v", "--volume"):
            continue
        vals = val if isinstance(val, list) else [val]
        for one in vals:
            existing.add(_normalize_mount_spec(_normalize_user_bind(one)))

    if getattr(self, "automated_mount", True):
        # Mount log path
        log_dir = os.path.abspath(self.log_path)
        log_spec = _normalize_mount_spec(f"{log_dir}:{log_dir}")
        if log_spec not in existing:
            docker_command.extend(["-v", log_spec])

        # Mount, create mk, map from vars
        for m in self._auto_mounts_from_vars():
            spec = _normalize_mount_spec(f'{m["src"]}:{m["dst"]}')
            if spec not in existing:
                docker_command.extend(["-v", spec])

    # Set working directory inside container
    user_set_w = any(opt in (self.environment_docker or {}) for opt in ("-w", "--workdir"))
    if not user_set_w and getattr(self, "automated_mount", True):
        workdir = os.path.abspath(getattr(self, "project_directory", os.getcwd()))
        docker_command.extend(["-w", workdir])

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
                file.write(f"Manager: {self.manager}\n")
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
                file.write(f"Manager: {self.manager}\n")
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

    self.logger.info(f"Applying retry parameters for retry attempt {attempt_i}: {len(retry_params)} parameter(s) found")

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
def _check_resume_success(self):
    """
    Check if a process with the same first 6-digit hash already completed successfully.
    If found, return the successful log path, False otherwise.
    """
    prefix = self.hash[:6]
    if not os.path.isdir(self.logs_directory):
        return False

    for entry in os.listdir(self.logs_directory):
        if not entry.startswith(self.name + "_"):
            continue
        if prefix not in entry:
            continue

        candidate_path = os.path.join(self.logs_directory, entry)
        exitcode_file = os.path.join(candidate_path, f"{self.name}.exitcode")

        if os.path.isfile(exitcode_file):
            try:
                with open(exitcode_file, "r") as f:
                    code = f.read().strip()
                    if code == "0" or code.startswith("0:"):
                        self.logger.info(f"Matched process with hash prefix '{prefix}' already finished successfully — logs in ({entry})")
                        return candidate_path
            except Exception as e:
                self.logger.warning(f"Resume check failed for {entry}: {e}")
    return False


@register
def _auto_mounts_from_vars(self):
    """
    Collect auto mounts from self.var:
      - mk.*  → mount RW (dirs already ensured in _script_placeholders_and_mkdir)
      - map.* → mount RW
    If value is a file path, mount its parent directory so the file path exists inside.

    Returns
    -------
    list[dict]
        [{"src": <host_abs>, "dst": <same_abs>, "kind": "mk"|"map"}]
    """
    if not getattr(self, "automated_mount", True):
        return []

    mounts, seen = [], set()
    var = self.var or {}

    def _to_abs(p):
        p = os.path.expanduser(str(p))
        if os.path.isabs(p):
            return os.path.abspath(p)
        base = getattr(self, "project_directory", os.getcwd())
        return os.path.abspath(os.path.join(base, p))

    def _norm(p):
        ap = _to_abs(p)
        return os.path.dirname(ap) if os.path.isfile(ap) else ap

    for k, v in var.items():
        if not isinstance(k, str) or not isinstance(v, (str, os.PathLike)):
            continue
        if not (k.startswith("mk.") or k.startswith("map.")):
            continue

        kind = "mk" if k.startswith("mk.") else "map"
        src = _norm(v)

        dst = src
        key = (src, dst)
        if key in seen:
            continue
        seen.add(key)
        mounts.append({"src": src, "dst": dst, "kind": kind})

    return mounts


@register
def _normalize_apptainer_image(self, ref):
    """
    Normalize Apptainer image reference.

    Rules:
      - If ref has '://', leave it as-is (docker://, oras://, library://, shub://, file://…).
      - If ref looks like a local path / .sif file and exists, leave it as-is.
      - Else, treat it as a registry reference and prefix with 'docker://'.

    Examples:
      "ubuntu:22.04"       -> "docker://ubuntu:22.04"
      "ghcr.io/org/img:1"  -> "docker://ghcr.io/org/img:1"
      "/data/my.sif"       -> "/data/my.sif" (unchanged)
      "my.sif" (exists)    -> "my.sif"       (unchanged)
      "oras://repo/img:1"  -> unchanged
    """
    if not ref:
        return ref

    # Already has a scheme
    if "://" in ref:
        return ref

    # Local path or existing file?
    try:
        # Heuristic: if it exists, don't touch it
        if os.path.exists(ref):
            return ref
        # Obvious absolute/relative paths (even if they don't exist yet)
        if ref.startswith(("/", "./", "../", "~/")) or ref.lower().endswith(".sif"):
            return ref
    except Exception:
        pass

    # Default: assume registry reference → docker://
    self.logger.info(f"Apptainer image had no scheme; assuming Docker registry and using 'docker://{ref}'")
    return f"docker://{ref}"


@register
def _elog_path(self):
    """
    Return log path info to be appened in error log
    """
    lp = getattr(self, "log_path", None)
    if isinstance(lp, str) and os.path.exists(lp):
        return f" (Log Folder: {self.log_path})"
    return ""


@register
def _tail_error(self, max_lines=5, full=False, slurm=False):
    """
    Return a concise or full snippet from the process stderr log (for logging).
    """
    try:
        err = self.get_error()
        if err:
            err = err.strip()
            if not err:
                return "\nJob produced empty stderr output!"

            if full:
                # full error text
                return f"\n\n{err}"

            lines = err.splitlines()
            n_total = len(lines)
            if n_total <= max_lines:
                # small stderr → show all
                return f"\n\n{err}"
            else:
                tail = "\n".join(lines[-max_lines:])
                return f"\n\nLast {max_lines} lines of error:\n{tail}"
    except Exception:
        pass

    if slurm:
        return "\nJob may have failed silently or without stderr output!"
    return ""


@register
def _tail_text(self, text, max_lines= 5):
    """
    Return a concise number of last lines.
    """
    try:
        if not text:
            return ""
        lines = text.strip().splitlines()
        if len(lines) <= max_lines:
            return text.strip()
        tail = "\n".join(lines[-max_lines:])
        return f"...\n{tail}"
    except:
        return ""


@register
def _proc_exception_handler(self, e, location= "execution", type_text="Error"):
    """
    Centralized, safe exception handler for all jawm process failures.
    Ensures that no failure can leave a process hanging or block wait().
    """
    try:
        for_name = f" for {self.name}"
    except Exception:
        for_name = ""

    msg = f"Unhandled exception in {location}{for_name}: {e}"

    try:
        self.logger.error(f"{msg}{self._elog_path()}")
    except Exception:
        pass

    try:
        self._log_error_summary(msg, type_text=type_text)
    except Exception:
        pass

    try:
        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
    except Exception:
        pass
    
    try:
        if hasattr(self, "log_path") and self.log_path:
            exitcode_path = os.path.join(self.log_path, f"{self.name}.exitcode")
            with open(exitcode_path, "w") as f:
                f.write("127")
    except Exception:
        pass

    try:
        if hasattr(self, "log_path") and self.log_path:
            error_path = os.path.join(self.log_path, f"{self.name}.error")
            with open(error_path, "w") as f:
                f.write(msg + "\n")
    except Exception:
        pass

    try:
        self.finished_event.set()
    except Exception:
        pass

    try:
        self.__class__.stop_future_event.set()
    except Exception:
        pass

    return


@register
def _throttle_delay(self):
    """
    Apply startup/finishing throttling delay for execution.
    """
    def _as_bool(v, default):
        if v is None:
            return default
        s = str(v).strip().lower()
        if s in {"1", "true", "yes", "on"}:
            return True
        if s in {"0", "false", "no", "off"}:
            return False
        return default

    try:
        # Enable flags
        enable_serial   = _as_bool(os.getenv("JAWM_EXECUTE_SERIAL_WAIT"),   False)
        enable_parallel = _as_bool(os.getenv("JAWM_EXECUTE_PARALLEL_WAIT"), True)

        # Decide applicability
        if self.parallel:
            if not enable_parallel:
                return
        else:
            if not enable_serial:
                return

        manager = str(getattr(self, "manager", "") or "").lower()

        # Special defaults (fallback=0.1)
        defaults = {
            "slurm": 0.3,
        }

        # Allow env override
        base_wait = os.getenv("JAWM_EXECUTE_WAIT")
        specific  = os.getenv(f"JAWM_EXECUTE_WAIT_{manager.upper()}")

        delay = float(specific or base_wait or defaults.get(manager, 0.1))

        if delay > 0:
            time.sleep(delay)

    except Exception:
        pass


@register
def _safe_write_file(self, path, content, mode="w", retries=5):
    """
    Safely writes a file in a way that is resilient to NFS / parallel FS metadata delay.

    Ensures:
      - parent directory exists
      - file is written fully (flush + fsync)
      - file is visible after write (metadata sync)

    Parameters
    ----------
    path : str
        Full path of the file to write.
    content : str
        File content to write.
    mode : str
        File write mode ('w', 'a', etc.).
    retries : int
        Number of metadata visibility retries.

    Returns
    -------
    str
        The file path that was written.
    """

    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)

    # Write content safely
    with open(path, mode) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())

    # Retry stat to avoid NFS propagation problems
    delay = 0.001  # start with 1ms
    for _ in range(retries):
        try:
            os.stat(path)
            return path  # Success
        except FileNotFoundError:
            time.sleep(delay)
            delay *= 2  # exponential backoff: 1ms, 2ms, 4ms, 8ms...

    # If still failing, last raise is fine
    os.stat(path)
    return path


@register
def _wait_for_fs_settle(self, check_stability=False):
    """
    Best-effort wait for filesystem visibility of self.stdout_path.

    Uses env vars:
      - JAWM_FS_SETTLE_TIMEOUT (default 10)
      - JAWM_FS_SETTLE_POLL    (default 0.2)

    If check_stability is True:
      - requires stable mtime for one poll cycle

    Safe behavior:
      - if stdout_path is not set -> return True immediately
      - never raises (returns True/False)
    """
    try:
        path = getattr(self, "stdout_path", None)
        if not path:
            return True

        try:
            timeout = float(os.getenv("JAWM_FS_SETTLE_TIMEOUT", "10"))
        except Exception:
            timeout = 10.0
        if timeout <= 0:
            return True

        try:
            poll = float(os.getenv("JAWM_FS_SETTLE_POLL", "0.2"))
        except Exception:
            poll = 0.2
        if poll <= 0.05:
            poll = 0.2

        end = time.time() + timeout
        last_mtime = None

        while time.time() < end:
            if os.path.exists(path):
                try:
                    with open(path, "rb"):
                        pass

                    if not check_stability:
                        return True

                    st = os.stat(path)
                    mtime = st.st_mtime
                    if last_mtime is not None and mtime == last_mtime:
                        return True
                    last_mtime = mtime
                except Exception:
                    pass

            time.sleep(poll)

        return False
    except Exception:
        return True


@register
def _finish_wait_and_settle(self, env_flag="JAWM_PROCESS_FINISH_WAIT", default_wait=0.0, check_stability=False):
    """
    Best/loose effort: optional finish wait + filesystem settle check.

    - Reads wait seconds from env_flag (float), falls back to default_wait
    - Sleeps if wait > 0
    - Calls self._wait_for_fs_settle(check_stability=check_stability)

    Safe: never raises.
    """
    try:
        try:
            w = float(os.getenv(env_flag, str(default_wait)))
        except Exception:
            w = float(default_wait)

        if w > 0:
            time.sleep(w)
        self._wait_for_fs_settle(check_stability=check_stability)
    except Exception:
        return


# --------------------------------------------
#   Plain Helper Methods without @register
# --------------------------------------------

def _normalize_mount_spec(val):
    """
    Normalize Docker/Apptainer mount specs to 'abs_host:container' form.
    Handles short '-v src' → 'src:src'.
    """
    parts = str(val).split(":")
    if len(parts) == 1:
        host = os.path.abspath(parts[0])
        return f"{host}:{host}"
    elif len(parts) >= 2:
        host = os.path.abspath(parts[0])
        return f"{host}:{parts[1]}"
    return str(val)


def _normalize_user_bind(spec):
    """
    Normalize a user '--bind'/'-v' spec:
      - Make host/src absolute.
      - Preserve a user-specified destination, but ensure it is absolute.
      - If destination omitted, use src_abs as destination.
      - Preserve trailing options (e.g., :ro, :Z).
    """
    s = str(spec).strip().strip('"').strip("'")
    if not s:
        return s
    parts = s.split(":")
    src_abs = os.path.abspath(os.path.expanduser(parts[0]))

    # Decide dst and opts
    if len(parts) == 1:
        dst = src_abs
        opts = None
    else:
        dst_raw = parts[1]
        # make container dst absolute while preserving user intent
        dst = dst_raw if dst_raw.startswith("/") else "/" + dst_raw.lstrip("./")
        opts = ":".join(parts[2:]) if len(parts) > 2 else None

    out = f"{src_abs}:{dst}"
    if opts:
        out += f":{opts}"
    return out

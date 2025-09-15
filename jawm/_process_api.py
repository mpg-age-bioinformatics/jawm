import threading
import os
import time
import re
from datetime import datetime

# Setup method registration for dynamic injection into the main Process class
from ._method_lib import register_method

__methods__ = []
register = register_method(__methods__)


# ----------------------------------------------------------
#   Process instance specific publicly useable methods
# ----------------------------------------------------------


@register
def execute(self):
    """
    Launch the process execution, handling dependencies, conditions, and execution environment.

    This method executes the process based on its configuration. It supports:
    - Conditional execution via the `when` parameter
    - Dependency resolution via `depends_on`
    - Execution using the selected manager (`local`, `slurm`)
    - Optional container environments (Docker, Apptainer)

    Execution Flow:
    ---------------
    1. If `when` is False:
        - The process is skipped and marked as finished.
    2. If `when` is True:
        - Waits for all dependencies to finish (if any).
        - Executes the process via the configured manager.
    3. On failure:
        - Logs the error.
        - Sets the global stop flag to prevent further downstream executions (if applicable).

    Notes:
    ------
    - Dependencies are matched by name or hash using the `depends_on` list.
    - Errors and output are logged to the process-specific log directory.
    - Retries and overrides can be configured via `retries` and `retry_overrides`.

    Returns:
        None
    """

    # Make the process active by clearing finished_event in case of instance re-use
    self.finished_event.clear()

    # Skip execution if resume is enabled and a matching successful process already exists
    if self.resume:
        matched_path = self._check_resume_success()
        if matched_path:
            self.log_path = matched_path  
            self.logger.info(f"Process {self.name} skipped with resume enabled — already completed successfully.")
            self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.finished_event.set()
            return

    # If the user condition says "skip," mark finished and return.
    run_condition = self.when() if callable(self.when) else self.when
    if not run_condition:
        self.logger.info(f"Process {self.name} skipped because 'when' condition was not fulfilled!")
        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.finished_event.set()
        return

    # Create necessary directories
    self._prepare_base_dirs()

    # Check if another process has already failed (skip this gate if always_run)
    if (not self.always_run) and self.__class__.stop_future_event.is_set():
        self.logger.warning(f"Skipping execution of {self.name}, as some other process already failed")
        self.finished_event.set()
        return

    if not self.run_in_detached:
        # Wait for dependencies *in the main thread*
        for dep in self.depends_on:
            dep_proc = self.__class__.registry.get(dep)
            if dep_proc is None:
                self.logger.warning(f"Dependency {dep} not found in registry, skipping wait")
            else:
                self.logger.info(f"Waiting for dependency process {dep_proc.name} ({dep_proc.hash}) to finish before executing {self.name} ({self.hash})")
                dep_proc.finished_event.wait()

        # If strict: require all deps to have succeeded (skipped/failed -> block)
        if not self.allow_skipped_deps and self.depends_on:
            bad = []
            for dep in self.depends_on:
                dp = self.__class__.registry.get(dep)
                if dp and not dp.is_successful():
                    bad.append((dp.name, dp.get_exitcode()))
            if bad:
                self.logger.warning(f"Skipping {self.name}: dependencies not successful: " + ", ".join(f"{n} (exit={c})" for n, c in bad))
                self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                self.finished_event.set()
                return
    
        # Check if another process has already failed (skip if always_run)
        if (not self.always_run) and self.__class__.stop_future_event.is_set():
            self.logger.warning(f"Skipping execution of {self.name}, as some other process already failed")
            self.finished_event.set()
            return

        # Perform synchronous runs
        try:
            self.execution_start_at = datetime.now().strftime('%Y%m%d_%H%M%S')
            self._run_manager()
            if not self.parallel:
                self.finished_event.wait()
        except Exception as e:
            self.logger.error(f"Process {self.name} failed to launch or execute: {str(e)}")
            self.__class__.stop_future_event.set()
            self.finished_event.set()
            raise

    else:
        def run_in_background():
            """
            This background thread for run_in_detached run
            """
            # Wait for dependencies to complete (either by name or hash).
            for dep in self.depends_on:
                dep_proc = self.__class__.registry.get(dep)
                if dep_proc is None:
                    self.logger.warning(f"Dependency {dep} not found in registry, skipping wait")
                else:
                    self.logger.info(f"Waiting for dependency process {dep_proc.name} ({dep_proc.hash}) to finish before executing {self.name} ({self.hash})")
                    dep_proc.finished_event.wait()

                # If strict: require all deps to have succeeded (skipped/failed -> block)
            if not self.allow_skipped_deps and self.depends_on:
                bad = []
                for dep in self.depends_on:
                    dp = self.__class__.registry.get(dep)
                    if dp and not dp.is_successful():
                        bad.append((dp.name, dp.get_exitcode()))
                if bad:
                    self.logger.warning(f"Skipping {self.name}: dependencies not successful: " + ", ".join(f"{n} (exit={c})" for n, c in bad))
                    self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                    self.finished_event.set()
                    return

            # Check if another process has already failed (skip if always_run)
            if (not self.always_run) and self.__class__.stop_future_event.is_set():
                self.logger.warning(f"Skipping execution of {self.name}, as some other process already failed")
                self.finished_event.set()
                return

            # Perform run_in_detached runs
            try:
                self.execution_start_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                self._run_manager()
            except Exception as e:
                self.logger.error(f"Process {self.name} failed to launch or execute: {str(e)}")
                self.__class__.stop_future_event.set()
                self.finished_event.set()
                raise
        
        # Spawn a background thread
        a_thread = threading.Thread(target=run_in_background, daemon=False)
        a_thread.start()
        if not self.parallel:
            self.finished_event.wait()
        return None


@register
def copy(self, name=None, param_file=None, **overrides):
    """
    Clone the current Process instance to create a new one with optional modifications.

    - name (str, optional): The name for the cloned process. Defaults to the current process's name.
    - param_file (str or list, optional): YAML parameter file(s) to load. Defaults to the original's param_file.
    - **overrides: Any other parameters to override from the original process's configuration.

    Returns: A new Process instance with copied and/or overridden parameters.

    """
    # Start with a shallow copy of current parameters
    new_params = self.params.copy()

    # Avoid duplicate keyword arguments
    new_params.pop("name", None)
    new_params.pop("param_file", None)

    # Apply any additional overrides
    new_params.update(overrides)

    return self.__class__(name=name or self.name, param_file=param_file or self.param_file, **new_params)


@register
def is_valid(self, mode="strict"):
    """
    Validate the Process configuration.

    - mode (str): basic (fails on errors only) or  strict (fails on both error and warning). Defaults to strict.

    Returns: True if process passes validation, False otherwise.
    """
    mode = mode.lower()
    if mode not in {"basic", "strict"}:
        self.logger.error(f"is_valid | Unsupported mode: {mode}")
        return False

    errors = []
    warnings = []

    # --- Basic required fields ---
    if not self.name or not isinstance(self.name, str):
        errors.append("Missing or invalid 'name'")

    if not (self.script and isinstance(self.script, str)) and not (self.script_file and isinstance(self.script_file, str)):
        errors.append("Either 'script' or 'script_file' must be provided.")

    # --- Check for unknown kwargs ---
    unknown_keys = set(self.params) - set(self.__init__.__code__.co_varnames) - self.reserved_keys

    if unknown_keys:
        warnings.append(f"Unrecognized parameters in kwargs: {', '.join(sorted(unknown_keys))}")

    # --- Check for invalid parameter values ---
    for key, expected in self.parameter_types.items():
        if key not in self.params:
            continue

        value = self.params[key]

        # Skip validation for callables
        if key in {"when"} and callable(value):
            continue

        expected_types = expected if isinstance(expected, tuple) else (expected,)

        if not isinstance(value, expected_types):
            type_names = ", ".join(t.__name__ for t in expected_types)
            warnings.append(f"Parameter '{key}' expected type {type_names}, got {type(value).__name__}")

    # --- Runtime requirements ---
    if self.manager not in self.supported_managers:
        errors.append(f"Unsupported manager: {self.manager}")

    if self.script_file and not os.path.isfile(self.script_file):
        errors.append(f"Script file not found: {self.script_file}")

    # --- Shebang line validation ---
    shebang_error = "Missing or invalid shebang line (must start with #!) in script or script_file."

    if self.script and isinstance(self.script, str):
        first_line = self.script.strip().splitlines()[0] if self.script.strip() else ""
        if not first_line.startswith("#!"):
            errors.append(shebang_error)

    elif self.script_file and isinstance(self.script_file, str):
        if os.path.isfile(self.script_file):
            try:
                with open(self.script_file, "r") as f:
                    first_line = f.readline().strip()
                    if not first_line.startswith("#!"):
                        errors.append(shebang_error)
            except Exception as e:
                errors.append(f"Could not read script_file to check shebang: {e}")

    # --- Validate unresolved placeholders ---
    from ._utils import read_variables
    placeholder_pattern = re.compile(r"\{\{([^}]+)\}\}")
    combined_vars = self.var.copy() if isinstance(self.var, dict) else {}

    if self.var_file:
        try:
            vars_from_file = read_variables(
                self.var_file,
                process_name=self.name,
                output_type="dict"
            )
            combined_vars.update(vars_from_file)
        except Exception as e:
            warnings.append(f"Failed to load var_file via read_variables()")

    script_source = self.script if self.script else ""
    if not script_source and self.script_file and os.path.isfile(self.script_file):
        try:
            with open(self.script_file, "r") as f:
                script_source = f.read()
        except Exception as e:
            errors.append(f"Could not read script_file to check placeholders: {e}")

    found_keys = set(placeholder_pattern.findall(script_source))

    for key in found_keys:
        if key.startswith("JAWM.Process."):
            continue
        if key not in combined_vars:
            warnings.append(f"Unresolved placeholder variables in Process script: {key}")


    # --- Report Results ---
    for e in errors:
        self.logger.error(f"Validation Error: {e}")
    for w in warnings:
        self.logger.warning(f"Validation Warning: {w}")

    if errors or (mode == "strict" and warnings):
        return False

    return True


@register
def update_params(self, param_file=None):
    """
    Update the Process instance's parameters from new YAML file(s) or directory.
    Merges new values into params, keeping existing ones unless overridden.

    :param param_file: A string (single file or directory) or a list of YAML file paths.
    """
    if not param_file:
        self.logger.warning("No param_file provided for update_params, skipping.")
        return

    # Get existing values if already there for var update
    old_script      = getattr(self, "script", None)
    old_script_file = getattr(self, "script_file", None)
    old_var         = (self.var.copy() if isinstance(self.var, dict) else {}) or {}
    old_var_file    = self.var_file
    
    yaml_params = self._parse_yaml_config(param_file)

    # Merge global + process-specific configs
    process_params = yaml_params["process"].get(self.name, {})
    global_params = yaml_params["global"]

    # Update self.params in-place
    self.params.update({**global_params, **process_params})

    # Reapply updated params as attributes (skip reserved keys)
    for k, v in self.params.items():
        if k not in self.reserved_keys:
            setattr(self, k, v)

    # Track param_file(s) as list
    if self.param_file is None:
        self.param_file = param_file
    elif isinstance(self.param_file, list):
        self.param_file.append(param_file)
    else:
        self.param_file = [self.param_file, param_file]
    
    self.params["param_file"] = self.param_file

    # Invalidate cached base script if script/vars changed
    new_script      = getattr(self, "script", None)
    new_script_file = getattr(self, "script_file", None)
    new_var         = (self.var.copy() if isinstance(self.var, dict) else {}) or {}
    new_var_file    = self.var_file

    if (old_script != new_script or old_script_file != new_script_file or old_var != new_var or old_var_file != new_var_file):
        self.base_script_path = None

    self.logger.info(f"Process {self.name} updated parameters from {param_file}")


@register
def update_vars(self, var_file):
    """
    Update the Process instance's variable placeholders from file(s) or directory.

    - Merges new variables into self.var (new values take precedence).
    - Stores/extends self.var_file reference for traceability.
    - Resets base script with updated placeholders.

    :param var_file: str or list[str] or path to directory of YAMLs
    :return: dict of the merged variables after update
    """
    if not var_file:
        self.logger.warning("No var_file provided for update_vars, skipping.")
        return

    try:
        from ._utils import read_variables

        loaded = read_variables(
            var_file,
            process_name=self.name,
            output_type="dict"
        ) or {}

        # Merge into self.var (new values win)
        current = self.var.copy() if isinstance(self.var, dict) else {}
        current.update(loaded)
        self.var = current

        # Track var_file(s)
        if self.var_file is None:
            self.var_file = var_file
        elif isinstance(self.var_file, list):
            # Append without duplicating identical entries
            if isinstance(var_file, list):
                for v in var_file:
                    if v not in self.var_file:
                        self.var_file.append(v)
            else:
                if var_file not in self.var_file:
                    self.var_file.append(var_file)
        else:
            # Convert to list form to remember previous and new
            self.var_file = [self.var_file] + (var_file if isinstance(var_file, list) else [var_file])

        # Reflect updates in params for transparency
        self.params["var"] = self.var
        self.params["var_file"] = self.var_file

        # Force regeneration of the base script on the next execution so new vars apply
        self.base_script_path = None

        self.logger.info(
            f"Process {self.name} var updated from {str(var_file)} "
            f"({len(loaded)} loaded; {len(self.var)} total after merge)"
        )

    except Exception as e:
        self.logger.error(f"update_vars failed for {self.name}: {e}")
        if hasattr(self, "_log_error_summary"):
            self._log_error_summary(f"update_vars failed: {e}", type_text="VarUpdate")


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


@register
def is_successful(self):
    """Return True iff the process completed successfully, False if still running, skipped, or failed."""
    c = self.get_exitcode()
    return (c is not None) and (str(c).strip() == "0" or str(c).strip().startswith("0:"))


@register
def has_failed(self):
    """Return True iff the process finished with a non-zero exit code, False if still running, skipped , or successful."""
    c = self.get_exitcode()
    return (c is not None) and not (str(c).strip() == "0" or str(c).strip().startswith("0:"))


@register
def get_values(self):
    """
    Return current values of the Process instance
    """
    values = {}
    exclude_from_values = {"params", "scope"}

    # Include parameter_types
    for key in self.parameter_types.keys():
        values[key] = getattr(self, key, None)

    # Include reserved_keys
    for key in self.reserved_keys:
        if key not in exclude_from_values:
            values[key] = getattr(self, key, None)

    return values


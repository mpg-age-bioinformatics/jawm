import threading
import os
import logging
import random
import string
import signal
import subprocess
import time
import sys
import re
import hashlib
from datetime import datetime

# Extend the Process class with methods from modular backend implementations
from ._method_lib import add_methods_from
from . import _process_base, _process_local, _process_slurm


@add_methods_from(_process_base, _process_local, _process_slurm)
class Process:
    """
    A JAWM Process represents a step in a workflow with full support for:

    - Script execution of different languages
    - Local or Slurm execution (with container support)
    - Dependency management and re-try support
    - YAML-based or inline configuration

    Quickstart:
    -----------

    >>> from jawm import Process
    >>> process_hw = Process(
    ...     name="hello_world",
    ...     script=\"\"\"#!/bin/bash
    echo 'Hello World!'
    \"\"\"
    ... )
    >>> process_hw.execute()

    Class Attributes:
    -----------------
    registry (dict):
        Stores all Process instances, indexed by name and hash.

    stop_future_event (threading.Event):
        A shared stop flag triggered on process failure to halt future runs if applicable.

    default_parameters (dict):
        Class-level fallback parameters with the lowest priority.

    override_parameters (dict):
        Class-level parameters with the highest priority that overrides other values.

    """

    # Global registry to map process names to process instances.
    registry = {}
    # A class-level event, shared across all Process instances. Run `Process.stop_future_event.clear()` to prevent preventing
    stop_future_event = threading.Event()
    # Class-level fallback parameters with the lowest priority
    default_parameters = {}
    # Class-level parameters with the highest priority that overrides other values
    override_parameters = {}
    # Dictionary of expected parameter types
    parameter_types = {
        "name": str,
        "param_file": (str, list),
        "script": str,
        "script_file": str,
        "var": dict,
        "var_file": str,
        "project_directory": str,
        "logs_directory": str,
        "error_summary_file": str,
        "monitoring_directory": str,
        "depends_on": (str, list),
        "manager": str,
        "env": dict,
        "inputs": dict,
        "outputs": dict,
        "retries": int,
        "retry_overrides": dict,
        "error_strategy": str,
        "when": bool,
        "manager_local": dict,
        "manager_slurm": dict,
        "environment": str,
        "container": str,
        "environment_apptainer": dict,
        "environment_docker": dict,
        "before_script": str,
        "after_script": str,
        "container_before_script": str,
        "container_after_script": str,
        "run_in_detached": bool,
        "validation": (bool, str),
        "resume": bool
    }
    # Set of internal/reserved keys
    reserved_keys = {
        "scope", "params", "hash", "date_time", "log_path", "stdout_path", "stderr_path", "base_script_path", "finished_event",
        "runtime_id", "execution_start_at", "execution_end_at", "_monitor_thread", "completed_directory", "running_directory",
        "parameters_directory", "logger"
    }


    # Configure logging with proper format
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] - %(levelname)s - %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    """
    A class to define and execute processes with support for multiple managers,
    pre/post scripts, retries, and resource configurations.
    """
    def __init__(
        self,
        name,
        param_file=None,
        script=None,
        script_file=None,
        var=None,
        var_file=None,
        project_directory=None,
        logs_directory=None,
        error_summary_file=None,
        monitoring_directory=None,
        run_in_detached=None,
        manager=None,
        env=None,
        inputs=None,
        outputs=None,
        retries=None,
        retry_overrides=None,
        error_strategy=None,
        when=None,
        manager_local=None,
        manager_slurm=None,
        environment=None,
        container=None,
        environment_apptainer=None,
        environment_docker=None,
        depends_on=None,
        before_script=None,
        after_script=None,
        container_before_script=None,
        container_after_script=None,
        validation=None,
        resume=None,
        **kwargs
    ):
        """
        Initialize the Process object.

        This constructor supports configuration from YAML files, inline Python arguments,
        and dynamic overrides via `**kwargs`. Explicit parameters take precedence over
        YAML and `**kwargs`.

        Parameters
        ----------
        name : str
            Name of the process. Required.

        param_file : str or list of str, optional
            YAML file(s) or directory containing YAMLs that define global and process-specific parameters.

        script : str, optional
            Inline script content to be executed.

        script_file : str, optional
            Path to an external script file.

        var : dict, optional
            Key-value pairs to substitute into the script as placeholders.

        var_file : str, optional
            File containing either key=value pairs or a YAML dictionary for script placeholder substitution.

        project_directory : str, optional
            Base directory for outputs and logs. Defaults to current working directory.

        logs_directory : str, optional
            Directory for log files. Defaults to <project_directory>/logs.

        error_summary_file : str, optional
            File path for summarizing errors with timestamps.

        monitoring_directory : str, optional
            Directory to track Running/Completed jobs. Can be set via env var `JAWM_MONITORING_DIRECTORY`.

        depends_on : str or list of str, optional
            Name(s) or hash(es) of processes this one depends on.

        manager : str, default="local"
            Execution backend. Options: "local", "slurm".

        env : dict, optional
            Environment variables for the process.

        inputs : dict, optional
            Custom user-defined input parameters.

        outputs : dict, optional
            Custom user-defined output parameters.

        retries : int, default=0
            Number of retry attempts if the process fails.

        retry_overrides : dict[int -> dict], optional
            Retry-specific parameter overrides by attempt number (1-based index).

        error_strategy : str, default="retry"
            What to do on failure: "retry" or "fail".

        when : bool or callable, default=True
            Whether to execute the process. Can be a boolean or a function.

        manager_local : dict, optional
            Configuration specific to local execution.

        manager_slurm : dict, optional
            Configuration specific to Slurm execution, to be passed exactly as-is

        environment : str, default="local"
            Execution environment: "local", "docker", or "apptainer".

        container : str, optional
            Container image to use (e.g., Docker or Apptainer image).

        environment_apptainer : dict, optional
            Options for running in Apptainer, to be passed exactly as-is

        environment_docker : dict, optional
            Options for running in Docker, to be passed exactly as-is

        before_script : str, optional
            A one-line or chained shell (bash) command to be executed before the main script starts
        
        after_script : str, optional
            A one-line or chained shell (bash) command to be executed after the main script ends

        container_before_script : str, optional
            A one-line or chained shell (bash) command to be executed inside container before the main script starts
        
        container_after_script : str, optional
            A one-line or chained shell (bash) command to be executed inside container after the main script ends

        validation : bool or str, default=False
            Whether to check if the Process instance is valid on initiation. Skip the process if a `strict` validation fails

        resume : bool, default=False  
            Whether to skip execution if a matching process with the same parameter hash has already completed successfully.

        **kwargs : optional
            Additional or custom parameters not explicitly listed above. These are merged into the configuration
            and can override YAML-defined values.

        To view detailed documentation for a specific parameter, run:
        >>> jawm.jhelp("Process", "<parameter_name>")

        """
        # Register cleanup hooks on first process creation
        self.__class__._init_cleanup_hooks()
        
        # Primary parameters
        self.name = name
        self.param_file = self.__class__.override_parameters.get("param_file") or param_file or self.__class__.default_parameters.get("param_file")

        # Build explicitly provided arguments for merging
        explicit_args = {k: v for k, v in locals().items() if k not in {"self", "kwargs"} and v is not None} 
        
        # Load YAML parameters if provided
        yaml_params = self._parse_yaml_config(self.param_file) if self.param_file else {"global": {}, "process": {}}

        # Retrieve configurations: Process-specific first, fallback to global
        process_params = yaml_params["process"].get(name, {})
        global_params = yaml_params["global"]

        # Merge in priority order: default_parameters < global < process < kwargs < explicit arguments < override_parameters
        self.params = {**self.__class__.default_parameters, **global_params, **process_params, **kwargs, **explicit_args, **self.__class__.override_parameters}

        # Set up the hash (with 6 characters params based and 4 characters suffix) and logger
        # If there is a callable in the instance, hash_params would produce diffeent hash every time
        try:
            hash_params = hashlib.sha256(repr(sorted(self.params.items())).encode()).hexdigest()[:6]
            hash_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            self.hash = f"{hash_params}{hash_suffix}"
        except:
            self.hash = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        self.logger = logging.getLogger(f"{self.name}|{self.hash}")

        # Register the process and get depends_on parameter
        Process.registry[self.name] = self
        Process.registry[self.hash] = self
        self.depends_on = self.params.get("depends_on", [])
        if isinstance(self.depends_on, str):
            self.depends_on = [self.depends_on]

        self.script = self.params.get("script", "#!/bin/bash")
        self.script_file = self.params.get("script_file", None)
        self.script_type = "script" if self.script != "#!/bin/bash" else "file" if self.script_file is not None else "script"
        self.var = self.params.get("var", None)
        self.var_file = self.params.get("var_file", None)

        # Directory parameters
        # self.project_directory = self.params.get("project_directory", os.path.dirname(os.path.abspath(sys.argv[0])))
        # self.project_directory = self.params.get("project_directory", os.getcwd())
        self.project_directory = os.path.abspath(self.params.get("project_directory", "."))
        # os.makedirs(self.project_directory, exist_ok=True)
        self.logs_directory = os.path.abspath(self.params.get("logs_directory", os.path.join(self.project_directory, "logs")))
        # os.makedirs(self.logs_directory, exist_ok=True)
        self.parameters_directory = self.params.get("parameters_directory", os.path.join(self.project_directory, "parameters"))
        self.error_summary_file = os.path.abspath(self.params.get("error_summary_file", os.path.join(self.logs_directory, "error_summary.log")))

        # Setup monitoring directory
        self.monitoring_directory = self.params.get("monitoring_directory", os.environ.get("JAWM_MONITORING_DIRECTORY", os.path.expanduser("~/.jawm/monitoring")))
        # try:
        #     os.makedirs(self.monitoring_directory, exist_ok=True) if self.monitoring_directory is not None else None
        #     self.running_directory, self.completed_directory = (os.path.join(self.monitoring_directory, 'Running'), os.path.join(self.monitoring_directory, 'Completed')) if self.monitoring_directory else (None, None)
        #     if self.monitoring_directory: os.makedirs(self.running_directory, exist_ok=True); os.makedirs(self.completed_directory, exist_ok=True)
        # except Exception as e:
        #     self.logger.warning(f"Monitoring directory issue: {str(e)}")
        #     self.monitoring_directory = None

        # Management parameters
        self.run_in_detached = self.params.get("run_in_detached", False)
        self.manager = self.params.get("manager", "local")
        # self.source_env = os.environ.copy()
        self.env = self.params.get("env", {})
        self.combined_env = {**os.environ.copy(), **self.env}
        self.inputs = self.params.get("inputs", {})
        self.outputs = self.params.get("outputs", {})
        self.retries = self.params.get("retries", 0)
        self.retry_overrides = self.params.get("retry_overrides", {})
        self.use_scratch = self.params.get("scratch", False)
        self.error_strategy = self.params.get("error_strategy", "retry")
        self.when = self.params.get("when", True)
        self.before_script = self.params.get("before_script", None)
        self.after_script = self.params.get("after_script", None)
        self.container_before_script = self.params.get("container_before_script", None)
        self.container_after_script = self.params.get("container_after_script", None)
        self.resume = self.params.get("resume", False)

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
        self.log_path = os.path.join(self.logs_directory, f"{self.name}_{self.date_time}_{self.hash}")
        # os.makedirs(self.log_path, exist_ok=True)

        # std path
        self.stdout_path = os.path.join(self.log_path, f"{self.name}.output")
        self.stderr_path = os.path.join(self.log_path, f"{self.name}.error")

        # For reuse and track (doesn't come from the user parameters directly)
        self.base_script_path = None

        # A threading event that signals when this process has finished.
        self.finished_event = threading.Event()

        # To store/track threads
        self._monitor_thread = None

        # Time 
        self.execution_start_at = None
        self.execution_end_at = None

        # Internal field, populated after execution
        self.runtime_id = None

        # Check for validation
        self.validation = self.params.get("validation", False)
        if self.validation:
            if self.validation == "strict":
                is_valid = self.is_valid("strict")
                if not is_valid:
                    self.logger.warning(f"Strict validation failed — process {self.name} will be skipped with when False")
                    self.when = False
            else:
                self.is_valid("basic")

        # Enforce consistency between error_strategy and retries
        if self.error_strategy == "fail" and self.retries != 0:
            self.retries = 0
            self.params["retries"] = 0


    # ----------------------------------------------------------
    #   Process instance specific publicly useable methods
    # ----------------------------------------------------------
    

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

        # Check if another process has already failed
        if Process.stop_future_event.is_set():
            self.logger.error(f"Skipping execution of {self.name}, as some other process already failed")
            self.finished_event.set()
            return

        if not self.run_in_detached:
        # Wait for dependencies *in the main thread*
            for dep in self.depends_on:
                dep_proc = Process.registry.get(dep)
                if dep_proc is None:
                    self.logger.warning(f"Dependency {dep} not found in registry, skipping wait")
                else:
                    self.logger.info(f"Waiting for dependency process {dep_proc.name} ({dep_proc.hash}) to finish before executing {self.name} ({self.hash})")
                    dep_proc.finished_event.wait()
        
            # Check if another process has already failed
            if Process.stop_future_event.is_set():
                self.logger.error(f"Skipping execution of {self.name}, as some other process already failed")
                self.finished_event.set()
                return

            # Perform synchronous runs
            try:
                self.execution_start_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                self._run_manager()
            except Exception as e:
                self.logger.error(f"Process {self.name} failed to launch or execute: {str(e)}")
                Process.stop_future_event.set()
                self.finished_event.set()
                raise

        else:
            def run_in_background():
                """
                This background thread for run_in_detached run
                """
                # Wait for dependencies to complete (either by name or hash).
                for dep in self.depends_on:
                    dep_proc = Process.registry.get(dep)
                    if dep_proc is None:
                        self.logger.warning(f"Dependency {dep} not found in registry, skipping wait")
                    else:
                        self.logger.info(f"Waiting for dependency process {dep_proc.name} ({dep_proc.hash}) to finish before executing {self.name} ({self.hash})")
                        dep_proc.finished_event.wait()

                # Check if another process has already failed
                if Process.stop_future_event.is_set():
                    self.logger.error(f"Skipping execution of {self.name}, as some other process already failed")
                    self.finished_event.set()
                    return

                # Perform run_in_detached runs
                try:
                    self.execution_start_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                    self._run_manager()
                except Exception as e:
                    self.logger.error(f"Process {self.name} failed to launch or execute: {str(e)}")
                    Process.stop_future_event.set()
                    self.finished_event.set()
                    raise
            
            # Spawn a background thread
            a_thread = threading.Thread(target=run_in_background, daemon=False)
            a_thread.start()
            return None

    
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

        return Process(name=name or self.name, param_file=param_file or self.param_file, **new_params)


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
        if self.manager not in {"local", "slurm"}:
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


    def update_params(self, param_file):
        """
        Update the Process instance's parameters from new YAML file(s) or directory.
        Merges new values into params, keeping existing ones unless overridden.

        :param param_file: A string (single file or directory) or a list of YAML file paths.
        """
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

        self.logger.info(f"Process {self.name} updated parameters from {param_file}")

    
    def get_id(self, max_wait=3, interval=0.5):
        """Return the content of the process .id file (PID or Slurm job ID), or None if unavailable (default, retrying up to: max_wait=3, interval=0.5)."""
        for _ in range(int(max_wait / interval)):
            if (val := self._read_log_file(f"{self.name}.id")):
                return val
            time.sleep(interval)
        return None


    def get_output(self):
        """Return the content of the process .output file, or None if unavailable."""
        return self._read_log_file(f"{self.name}.output")


    def get_error(self):
        """Return the content of the process .error file, or None if unavailable."""
        return self._read_log_file(f"{self.name}.error")


    def get_exitcode(self):
        """Return the content of the process .exitcode file, or None if unavailable."""
        return self._read_log_file(f"{self.name}.exitcode")


    def get_command(self):
        """Return the content of the process .command file, or None if unavailable."""
        return self._read_log_file(f"{self.name}.command")


    def get_script(self):
        """Return the content of the process .script file, or None if unavailable."""
        return self._read_log_file(f"{self.name}.script")


    def get_slurm(self):
        """Return the content of the process .slurm file containing slurm commands, or None if unavailable."""
        return self._read_log_file(f"{self.name}.slurm")


    def is_finished(self):
        """Return True or False based on whether the Process has finished or not"""
        return self.finished_event.is_set()


    # ----------------------------------------------------------
    #   Class methods with Process Lifecycle and Runtime Control
    # ----------------------------------------------------------

    @classmethod
    def set_default(cls, **kwargs):
        """
        Set one or more default values at the class level for all Process instances.

        These defaults are applied with the **lowest priority** — overridden by YAML, kwargs, or explicit arguments.

        Example:
            Process.set_default(manager="local", retries=2)
        """
        filtered_kwargs = {
            k: v for k, v in kwargs.items()
            if k != "name" and k not in cls.reserved_keys
        }
        cls.default_parameters.update(filtered_kwargs)


    @classmethod
    def set_override(cls, **kwargs):
        """
        Set one or more overrides at the class level that win over everything else for all Process instances.

        These overrides are applied with the **highest priority**.

        Example:
            Process.set_override(manager="local", retries=2)
        """
        filtered_kwargs = {
            k: v for k, v in kwargs.items()
            if k != "name" and k not in cls.reserved_keys
        }
        cls.override_parameters.update(filtered_kwargs)


    
    @classmethod
    def set_log_level(cls, level_name="INFO"):
        """
        Set logging level for all Process loggers, default is INFO.

        Parameters:
            level_name (str): One of 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', or 'NOTSE
        """
        level_name = level_name.upper()
        if level_name not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"]:
            return
        level = getattr(logging, level_name)
        logging.getLogger().setLevel(level)
        for proc in cls.registry.values():
            if hasattr(proc, "logger"):
                proc.logger.setLevel(level)

    
    @classmethod
    def list_active(cls):
        """
        List all currently active (unfinished) processes.

        Returns:
            List[dict]: Summary of active processes with name, hash, manager, log path, etc.
        """
        seen = set()
        active = []

        for proc in cls.registry.values():
            if not isinstance(proc, cls):
                continue
            if id(proc) in seen:
                continue
            seen.add(id(proc))

            if not proc.finished_event.is_set():
                active.append({
                    "name": proc.name,
                    "hash": proc.hash,
                    "id": getattr(proc, "runtime_id", None) or "NA",
                    "manager": proc.manager,
                    "environment": proc.environment,
                    "log_path": proc.log_path,
                    "initiated_at": proc.date_time,
                    "execution_start": proc.execution_start_at or "NA"
                })
        return active


    @classmethod
    def list_all(cls):
        """
        List all registered processes, both running and finished.

        Returns:
            List[dict]: Detailed process info including status, timestamps, and success.
        """
        seen = set()
        all_processes = []

        for proc in cls.registry.values():
            if not isinstance(proc, cls):
                continue
            if id(proc) in seen:
                continue
            seen.add(id(proc))

            all_processes.append({
                "name": proc.name,
                "hash": proc.hash,
                "id": getattr(proc, "runtime_id", None) or "NA",
                "manager": proc.manager,
                "environment": proc.environment,
                "log_path": proc.log_path,
                "initiated_at": proc.date_time,
                "execution_start": proc.execution_start_at or "NA",
                "execution_end": proc.execution_end_at or "NA",
                "finished": proc.finished_event.is_set(),
                "success": "NA" if proc.get_exitcode() is None else str(proc.get_exitcode()).startswith("0")
            })

        return all_processes


    @classmethod
    def kill(cls, identifier):
        """
        Attempt to terminate a running process by hash (preferred) or name.

        Parameters:
            identifier (str): Process name or hash.

        Returns:
            bool: True if successfully killed, False otherwise.
        """

        proc = cls.registry.get(identifier)
        if not proc:
            print(f"No process found with identifier: {identifier}")
            return False

        if proc.finished_event.is_set():
            print(f"{proc.name}|{proc.hash} :: Process already finished — nothing to kill.")
            return False

        runtime_id = proc.runtime_id
        if not runtime_id:
            print(f"{proc.name}|{proc.hash} :: Process has no recorded PID or job ID.")
            return False

        killed = False
        error_message = None

        if proc.manager == "local":
            try:
                os.kill(int(runtime_id), signal.SIGTERM)
                killed = True
            except Exception as e:
                error_message = f"Failed to kill (manually triggered) local process {runtime_id}: {e}"

        elif proc.manager == "slurm":
            try:
                # Only checks for active jobs
                squeue_check = subprocess.run(
                    ["squeue", "-j", str(runtime_id)],
                    capture_output=True, text=True
                )
                if str(runtime_id) not in squeue_check.stdout:
                    error_message = f"Slurm job {runtime_id} is not active — possibly already completed or cancelled."
                else:
                    result = subprocess.run(
                        ["scancel", str(runtime_id)],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        killed = True
                    else:
                        error_message = f"Failed to cancel Slurm job {runtime_id}: {result.stderr.strip()}"
            except Exception as e:
                error_message = f"Failed to verify or cancel Slurm job {runtime_id}: {e}"


        else:
            error_message = f"Unsupported manager '{proc.manager}' for killing."

        if killed:
            # Write a .killer file
            if hasattr(proc, "log_path"):
                try:
                    killer_path = os.path.join(proc.log_path, f"{proc.name}.killer")
                    with open(killer_path, "w") as f:
                        f.write("Process manually terminated.\n")
                        f.write(f"Name: {proc.name}\n")
                        f.write(f"Hash: {proc.hash}\n")
                        f.write(f"Killed At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"Killed By: Process.kill('{identifier}')\n")
                        f.write(f"PID/Job ID: {runtime_id}\n")
                        f.write(f"Manager: {proc.manager}\n")
                except Exception as file_error:
                    print(f"Failed to write killer file: {file_error}")

            # Log to error summary
            if hasattr(proc, "_log_error_summary"):
                proc._log_error_summary(f"Process was manually terminated via Process.kill('{identifier}')", "Killer")

            print(f"{proc.name}|{proc.hash} :: Process (ID: {runtime_id}) killed successfully.")
            return True

        else:
            print(f"{proc.name}|{proc.hash} :: {error_message}")
            if hasattr(proc, "_log_error_summary"):
                proc._log_error_summary(error_message, "Killer")
            return False


    @classmethod
    def kill_all(cls):
        """
        Kill all currently running processes in the registry.

        Returns:
            dict: { "killed": [...], "failed": [...] }
        """
        killed = []
        failed = []

        seen = set()
        for proc in cls.registry.values():
            if not isinstance(proc, cls):
                continue
            if id(proc) in seen:
                continue
            seen.add(id(proc))

            if not proc.finished_event.is_set():
                result = cls.kill(proc.hash)
                if result:
                    killed.append(proc.name + "|" + proc.hash)
                else:
                    failed.append(proc.name + "|" + proc.hash)

        print(f"\n Killed processes: {len(killed)}")
        for pid in killed:
            print(f"  - {pid}")
        
        if failed:
            print(f"\nFailed to kill (may not have executed yet): {len(failed)}")
            for pid in failed:
                print(f"  - {pid}")
            print("\n")
        
        return {
            "killed": killed,
            "failed": failed
        }


    @classmethod
    def list_monitoring_threads(cls):
        """
        List all processes with active background monitoring threads.

        Returns:
            List[dict]: Detailed process info including status, timestamps, and success.
        """
        seen = set()
        active_monitors = []

        for proc in cls.registry.values():
            if not isinstance(proc, cls):
                continue
            if id(proc) in seen:
                continue
            seen.add(id(proc))

            t = getattr(proc, "_monitor_thread", None)
            if t and t.is_alive():
                active_monitors.append({
                    "name": proc.name,
                    "hash": proc.hash,
                    "manager": proc.manager,
                    "started_at": proc.execution_start_at,
                    "finished": proc.finished_event.is_set(),
                    "thread_alive": True
                })

        return active_monitors


    @classmethod
    def _init_cleanup_hooks(cls):
        """
        Register cleanup behavior for interrupt signals (e.g., Ctrl+C).

        This method sets up a SIGINT (interrupt signal) handler that ensures
        all currently running JAWM processes are terminated cleanly if the user
        manually interrupts execution (e.g., via Ctrl+C).
        """
        if getattr(cls, "_cleanup_hooks_registered", False):
            return

        def _on_sigint(sig, frame):
            print("\nCtrl+C detected — terminating running JAWM jobs...")
            cls.kill_all()
            time.sleep(3)
            sys.exit(130)

        signal.signal(signal.SIGINT, _on_sigint)

        cls._cleanup_hooks_registered = True


    @classmethod
    def reset_stop(cls):
        """
        Allow processes to run again after a previous stop signal from a failure.
        This would clear the class-level stop_future_event flag.
        """
        cls.stop_future_event.clear()


    @classmethod
    def wait(cls, process_list="all", allowed_exit="all"):
        """
        Wait until the given processes are finished, optionally checking their exit codes.

        Parameters:
        -----------
        process_list ("all" (default) | list[str] | str) : Which process(es) to wait for.
        allowed_exit ("all" (default) | int | str | list[int | str]) : Allowed exit codes. If not matched, give warning and return False; True otherwise. 

        Returns:
            bool: True if all waited processes completed with allowed exit codes, False otherwise.
        """
        success = True

        # Normalize allowed_exit
        if allowed_exit != "all":
            if isinstance(allowed_exit, int):
                allowed_exit = [str(allowed_exit)]
            elif isinstance(allowed_exit, str):
                allowed_exit = [s.strip() for s in allowed_exit.split(",")]
            elif isinstance(allowed_exit, list):
                allowed_exit = [str(code).strip() for code in allowed_exit]
            else:
                print("Process.wait | WARNING :: Unsupported format for allowed_exit, skipping check.")
                allowed_exit = "all"
        
        # Normalize single process to list
        if process_list != "all" and not isinstance(process_list, list):
            process_list = [process_list]

        if process_list == "all":
            procs = list({id(p): p for p in cls.registry.values() if isinstance(p, cls) and p.execution_start_at is not None}.values())
        else:
            procs = []
            for item in process_list:
                if isinstance(item, cls):
                    procs.append(item)
                elif isinstance(item, str):
                    p = cls.registry.get(item)
                    if p is None:
                        print(f"Process.wait | WARNING :: No registered process for: {item}")
                        success = False
                    else:
                        procs.append(p)
                else:
                    print(f"Process.wait | WARNING :: Unsupported process reference: {item}")
                    success = False

        for proc in procs:
            try:
                if proc.finished_event.is_set():
                    proc.logger.info(f"Process.wait → {proc.name} [{proc.hash}] already completed")
                else:
                    proc.logger.info(f"Process.wait → Waiting for {proc.name} [{proc.hash}] to complete...")
                    proc.finished_event.wait()
                    proc.logger.info(f"Process.wait → {proc.name} [{proc.hash}] has completed")

                if allowed_exit != "all":
                    exit_code = proc.get_exitcode()
                    try:
                        code = int(exit_code.split(":")[0]) if ":" in exit_code else int(exit_code)
                    except:
                        code = None
                    if str(code) not in allowed_exit:
                        proc.logger.warning(f"Process {proc.name} ({proc.hash}) has completed with disallowed exit code: {exit_code}")
                        if hasattr(proc, "_log_error_summary"):
                            proc._log_error_summary(f"Process has completed with disallowed exit code: {exit_code}", "Wait")
                        success = False
            except Exception as e:
                if hasattr(proc, "_log_error_summary"):
                    proc._log_error_summary(f"Error during Process Wait: {str(e)}", "Wait")
                proc.logger.error(f"Failed while managing {proc.name} ({proc.hash}) for process wait: {str(e)}")

                success = False

        print(f"Process.wait | INFO :: Wait completed for {len(procs)} process(es).")
        return success




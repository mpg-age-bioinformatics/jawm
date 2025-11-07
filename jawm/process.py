import threading
import os
import logging
import random
import string
import signal
import subprocess
import time
import json
import sys
from datetime import datetime

# Extend the Process class with methods from modular backend implementations
from ._method_lib import add_methods_from
from . import _process_api, _process_internal, _process_local, _process_slurm, _process_kubernetes
from ._utils import _add_prefix_aliases, read_variables, _expand_relpaths_in_value

@add_methods_from(_process_api, _process_internal, _process_local, _process_slurm, _process_kubernetes)
class Process:
    """
    A jawm Process represents a step in a workflow with full support for:

    - Script execution of different languages
    - Local, Slurm, or Kubernetes execution (with container support)
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
    parameter_types (dict):
        Dictionary of expected parameters and their types.
    
    reserved_keys (set):
        Internal keys reserved for runtime bookkeeping.

    supported_managers (set):
        Execution managers supported by jawm.

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
        "var_file": (str, list),
        "project_directory": str,
        "logs_directory": str,
        "error_summary_file": str,
        "monitoring_directory": str,
        "depends_on": (str, list),
        "allow_skipped_deps": bool,
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
        "manager_kubernetes": dict,
        "environment": str,
        "container": str,
        "environment_apptainer": dict,
        "environment_docker": dict,
        "docker_run_as_user": bool,
        "before_script": str,
        "after_script": str,
        "container_before_script": str,
        "container_after_script": str,
        "run_in_detached": bool,
        "validation": (bool, str),
        "resume": bool,
        "parallel": bool,
        "always_run": bool,
        "automated_mount": bool,
        "desc": str,
    }
    # Set of internal/reserved keys
    reserved_keys = {
        "scope", "params", "hash", "date_time", "log_path", "stdout_path", "stderr_path", "base_script_path", "finished_event",
        "runtime_id", "execution_start_at", "execution_end_at", "_monitor_thread", "completed_directory", "running_directory",
        "parameters_directory", "logger", "_k8s_namespace", "_k8s_job_name", "_k8s_container_name", "_k8s_killed", "_mk_dirs_created",
        "_init_done", "_touched_params"
    }
    # Supported managers by the jawm
    supported_managers = {"local", "slurm", "kubernetes"}

    # Configure logging with proper format
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] - %(levelname)s - %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    class _EmojiFormatter(logging.Formatter):
        EMOJI_MAP = {
            logging.ERROR: "❌",
            logging.WARNING: "⚠️",
            logging.CRITICAL: "🚨",
        }
        def format(self, record):
            emoji = self.EMOJI_MAP.get(record.levelno, "")
            record.msg = f"{emoji}  {record.msg}" if emoji else record.msg
            return super().format(record)

    if os.getenv("JAWM_LOG_EMOJI", "1").strip().lower() not in {"0", "false", "no", "off"}:
        root_logger = logging.getLogger()
        if root_logger.handlers:
            for h in root_logger.handlers:
                if isinstance(h, logging.StreamHandler) and isinstance(h.formatter, logging.Formatter):
                    h.setFormatter(_EmojiFormatter(h.formatter._fmt, h.formatter.datefmt))

    # Define cls level logger for special uses
    logger_wait = logging.getLogger("jawm.Process|WAIT")
    logger_kill = logging.getLogger("jawm.Process|KILL")

    
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
        manager_kubernetes=None,
        environment=None,
        container=None,
        environment_apptainer=None,
        environment_docker=None,
        docker_run_as_user=None,
        depends_on=None,
        allow_skipped_deps=None,
        before_script=None,
        after_script=None,
        container_before_script=None,
        container_after_script=None,
        validation=None,
        resume=None,
        parallel=None,
        always_run=None,
        automated_mount=None,
        desc=None,
        **kwargs
    ):
        """
        Initialize the Process object.

        This constructor supports configuration from YAML files, inline Python arguments,
        and dynamic overrides via `**kwargs`. Explicit parameters take precedence over
        YAML and `**kwargs`.

        Parameters
        ----------
        name : str, required
            Name of the process.

        param_file : str or list of str, optional
            YAML file(s) or directory containing YAMLs that define global and process-specific parameters.

        script : str, optional
            Inline script content to be executed.

        script_file : str, optional
            Path to an external script file.

        var : dict, optional
            Key-value pairs to substitute into the script as placeholders.

        var_file : str or list of str, optional
            File(s) containing either key=value pairs, or YAML file(s), or a YAML dictionary for script placeholder substitution.

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

        allow_skipped_deps: bool, default=True
            Whether to treat skipped dependencies as acceptable; if False, process only runs when all dependencies succeeded.

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

        manager_kubernetes : dict, optional
            Configuration specific to Kubernetes execution, to be passed exactly as-is

        environment : str, default="local"
            Execution environment: "local", "docker", or "apptainer".

        container : str, optional
            Container image to use (e.g., Docker or Apptainer image).

        environment_apptainer : dict, optional
            Options for running in Apptainer, to be passed exactly as-is

        environment_docker : dict, optional
            Options for running in Docker, to be passed exactly as-is

        docker_run_as_user : bool, default=False
            Run Docker container as the current user instead of root

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
        
        parallel : bool, default=True  
            Whether the process should run in parallel with others (True) or block until it finishes before the next one starts (False).

        always_run : bool, default=False  
            Whether the process should run even if something failed. It does not override when: `when=False` still skips.

        automated_mount : bool, default=True  
            Whether to auto-bind the process log directory or any mk./map. paths. User-specified container options still apply.

        desc : str, optional  
            Human-readable description of the Process (one-line or multi-line docstring). No direct impact on the Process.

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

        # Compute merged baselines for these keys (global + process)
        merged_baselines = {}
        for key in self._merge_keys():
            gv = global_params.get(key, {})
            pv = process_params.get(key, {})
            if isinstance(gv, dict) or isinstance(pv, dict):
                merged_baselines[key] = self._deep_merge_dicts(gv or {}, pv or {})

        # Merge in priority order: default_parameters < global < process < kwargs < explicit arguments < override_parameters
        self.params = {**self.__class__.default_parameters, **global_params, **process_params, **kwargs, **explicit_args, **self.__class__.override_parameters}

        # Inject deep-merged baselines beneath higher-precedence layers ---
        for key, base in merged_baselines.items():
            cur = self.params.get(key, None)
            if cur is None:
                self.params[key] = base
            elif isinstance(cur, dict):
                # keep later/higher layers (cur) on top of the baseline
                self.params[key] = self._deep_merge_dicts(base, cur)

        # Set up the hash (with 6 characters params based and 4 characters suffix) and logger
        # If there is a callable in the instance, hash_params would produce diffeent hash every time
        try:
            hash_params = self._generate_hash_params()
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
        self.allow_skipped_deps = self.params.get("allow_skipped_deps", True)

        # Script and var parameters
        self.script = self.params.get("script", "#!/bin/bash")
        self.script_file = self.params.get("script_file", None)
        self.script_type = "script" if self.script != "#!/bin/bash" else "file" if self.script_file is not None else "script"
        self.var = self.params.get("var", None)
        if isinstance(self.var, dict):
            # Expand/process values
            self.var = _expand_relpaths_in_value(self.var, os.getcwd())
            _add_prefix_aliases(self.var)       # add aliases for prefixed var
        self.var_file = self.params.get("var_file", None)
        # If a var_file is provided, preload it into self.var so proc.var has everything
        if self.var_file:
            try:
                vf_loaded = read_variables(self.var_file, process_name=self.name, output_type="dict") or {}
                if isinstance(self.var, dict):
                    merged = dict(vf_loaded)
                    merged.update(self.var)
                    self.var = merged
                else:
                    self.var = dict(vf_loaded)
                    
                # Expand/process values
                self.var = _expand_relpaths_in_value(self.var, os.getcwd())
                _add_prefix_aliases(self.var)

            except Exception:
                pass  

        # Directory parameters
        self.project_directory = os.path.abspath(self.params.get("project_directory", "."))
        # os.makedirs(self.project_directory, exist_ok=True)
        self.logs_directory = os.path.abspath(self.params.get("logs_directory", os.path.join(self.project_directory, "logs")))
        # os.makedirs(self.logs_directory, exist_ok=True)
        self.parameters_directory = self.params.get("parameters_directory", os.path.join(self.project_directory, "parameters"))
        self.error_summary_file = os.path.abspath(self.params.get("error_summary_file", os.path.join(self.logs_directory, "error.log")))

        # Setup monitoring directory
        self.monitoring_directory = self.params.get("monitoring_directory", os.environ.get("JAWM_MONITORING_DIRECTORY", os.path.expanduser("~/.jawm/monitoring")))

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
        self.parallel = self.params.get("parallel", True)
        self.always_run = self.params.get("always_run", False)
        self.automated_mount = self.params.get("automated_mount", True)
        self.desc = self.params.get("desc", None)

        # Local execution configurations
        self.manager_local = self.params.get("manager_local", {})

        # Slurm execution configurations
        self.manager_slurm = self.params.get("manager_slurm", {})

        # Kubernetes execution configurations
        self.manager_kubernetes = self.params.get("manager_kubernetes", {})

        # Execution environment configurations
        self.environment = self.params.get("environment", "local")
        self.container = self.params.get("container", None)
        self.environment_apptainer = self.params.get("environment_apptainer", {})
        self.environment_docker = self.params.get("environment_docker", {})
        self.docker_run_as_user = self.params.get("docker_run_as_user", False)
        if self.container is None and self.environment != "local":
            self.logger.warning(f"Requested environment '{self.environment}' ignored because no container was provided. Falling back to 'local'")
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

        # To track the changed values manually
        self._init_done = True
        self._touched_params = set()




    # ----------------------------------------------------------
    #   Other special dunder methods
    # ----------------------------------------------------------

    def __setattr__(self, name, value):
        prev = self.__dict__.get(name, None)
        object.__setattr__(self, name, value)

        # Track only after __init__ finished
        if not getattr(self, "_init_done", False):
            return

        # Skip reserved/runtime keys (includes _touched_params, _init_done, etc.)
        if name in getattr(self, "reserved_keys", set()):
            return

        # Only track declared parameters
        ptypes = getattr(self, "parameter_types", {})
        if name not in ptypes:
            return

        # Record user change
        if prev != value:
            touched = getattr(self, "_touched_params", None)
            if touched is not None:
                touched.add(name)



    # ----------------------------------------------------------
    #   Static methods with namespaced helper functions
    # ----------------------------------------------------------
    
    @staticmethod
    def _deep_merge_dicts(a: dict, b: dict) -> dict:
        """
        Recursively merge two dicts.

        Values from `b` override those from `a` unless both are dicts,
        in which case the merge continues recursively.

        Returns a new merged dict without modifying either input.
        """
        if not isinstance(a, dict) or not isinstance(b, dict):
            return b
        out = dict(a)
        for k, v in b.items():
            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                out[k] = __class__._deep_merge_dicts(out[k], v)
            else:
                out[k] = v
        return out


    @staticmethod
    def _merge_keys():
        """
        Return set of mergeable keys (dict-like Process params).
        """
        return {
            "var", "env", "manager_local", "manager_slurm", "manager_kubernetes", "inputs",
            "outputs", "environment_docker", "environment_apptainer", "retry_overrides",
        }
    
    
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
            cls.logger_kill.info(f"No process found with identifier: {identifier}")
            return False

        if proc.finished_event.is_set():
            cls.logger_kill.info(f"{proc.name}|{proc.hash} :: Process already finished — nothing to kill.")
            return False

        runtime_id = proc.runtime_id
        if not runtime_id:
            cls.logger_kill.info(f"{proc.name}|{proc.hash} :: Process has no recorded PID or job ID.")
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

        elif proc.manager == "kubernetes":
            proc._k8s_killed = True
            ns = getattr(proc, "_k8s_namespace", None)
            job = str(runtime_id)
            killed, error_message = False, None
            k = lambda *a: subprocess.run(["kubectl"] + (["-n", ns] if ns else []) + list(a),
                                        capture_output=True, text=True)
            k("delete", "job", job, "--force", "--grace-period=0", "--ignore-not-found=true", "--wait=false")
            k("delete", "pod", "-l", f"job-name={job}", "--force", "--grace-period=0", "--ignore-not-found=true")
            deadline = time.time() + 30
            while time.time() < deadline:
                r = k("get", "pods", "-l", f"job-name={job}", "-o", "json")
                items = (json.loads(r.stdout or "{}").get("items", []) if r.returncode == 0 else [])
                if not items: killed = True; break
                time.sleep(2)
            if not killed:
                error_message = f"Timed out waiting for Kubernetes pods of job {job} to terminate."

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
                    cls.logger_kill.warning(f"Failed to write killer file: {file_error}")

            # Log to error summary
            if hasattr(proc, "_log_error_summary"):
                proc._log_error_summary(f"Process was manually terminated via Process.kill('{identifier}')", type_text="Killer")

            # Mark finished so Process.wait() unblocks
            proc.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
            proc.finished_event.set()

            cls.logger_kill.info(f"{proc.name}|{proc.hash} :: Process (ID: {runtime_id}) killed successfully.")
            return True

        else:
            cls.logger_kill.warning(f"{proc.name}|{proc.hash} :: {error_message}")
            if hasattr(proc, "_log_error_summary"):
                proc._log_error_summary(error_message, type_text="Killer")
            return False


    @classmethod
    def kill_all(cls):
        """
        Kill all currently running processes in the registry.

        Returns:
            dict: { "killed": [...], "failed": [...] }
        """
        # --- Grace period for processes that just started ---
        time.sleep(float(os.getenv("JAWM_WAIT_GRACE", "0.3")))

        killed = []
        failed = []
        seen = set()
        slurm_cleanup_issue = False
        
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

            # Extra cleanup for slurm
            if getattr(proc, "manager", None) == "slurm":
                try:
                    job_pattern = re.sub(r"[^A-Za-z0-9_\-]+", "_", f"{proc.name}_{proc.hash}")
                    user = os.environ.get("USER", "")
                    cmd = ["scancel", "-u", user, "--name", job_pattern]
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    if not result.returncode == 0:
                        slurm_cleanup_issue = True
                except Exception as e:
                    slurm_cleanup_issue = True

        if killed:
            cls.logger_kill.info(f"Killed processes ({len(killed)}):\n  - " + "\n  - ".join(killed))
        else:
            cls.logger_kill.info("Killed processes: 0")

        if failed:
            cls.logger_kill.warning(f"Failed to kill (may not have executed yet): {len(failed)}\n  - " + "\n  - ".join(failed))

        if slurm_cleanup_issue:
            cls.logger_kill.warning("Some Slurm jobs may still be running. Manual cleanup may be required.")
        
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
        all currently running jawm processes are terminated cleanly if the user
        manually interrupts execution (e.g., via Ctrl+C).
        """
        if getattr(cls, "_cleanup_hooks_registered", False):
            return
        cls._cleanup_hooks_registered = True
        cls._sigint_fired = False

        def _on_sigint(sig, frame):
            # Second Ctrl+C: skip cleanup and hard-exit fast
            if cls._sigint_fired:
                try:
                    signal.signal(signal.SIGINT, signal.SIG_IGN)
                except Exception:
                    pass
                os._exit(130)

            cls._sigint_fired = True
            cls.logger_kill.info("Ctrl+C detected — terminating running jawm jobs...")

            try:
                cls.kill_all()
            finally:
                try:
                    signal.signal(signal.SIGINT, signal.SIG_IGN)
                except Exception:
                    pass
                sys.exit(130)

        signal.signal(signal.SIGINT, _on_sigint)


    @classmethod
    def reset_stop(cls):
        """
        Allow processes to run again after a previous stop signal from a failure.
        This would clear the class-level stop_future_event flag.
        """
        cls.stop_future_event.clear()

    
    @classmethod
    def reset_runtime(cls):
        """
        Reset the global runtime state of all Process instances.

        This is primarily intended for interactive environments (e.g., Jupyter notebooks)
        where the Python interpreter persists across multiple workflow runs.
        It only resets internal in-memory state, so it is safe to call between tests
        or repeated invocations within a single Python session.
        """
        try:
            cls.stop_future_event.clear()
        except Exception:
            pass
        # mark any lingering processes as finished so nobody waits on them
        for p in list(cls.registry.values()):
            try:
                p.finished_event.set()
            except Exception:
                pass
        cls.registry.clear()


    @classmethod
    def wait(cls, process_list="all", allowed_exit="all", tail=None, tail_poll=0.5, log=True, timeout=None, dynamic=False):
        """
        Wait until the given processes are finished, optionally checking their exit codes.

        Parameters:
        -----------
        process_list ("all" (default) | list[str] | str) : Which process(es) to wait for.
        allowed_exit ("all" (default) | int | str | list[int | str]) : Allowed exit codes. If not matched, give warning and return False; True otherwise.
        tail (None | True | "stdout" | "stderr" | "both"): If set, stream live output while waiting.
            - True / "stdout": tail the process stdout file
            - "stderr": tail the process stderr file
            - "both": tail both stdout and stderr
        tail_poll (float): polling interval in seconds for tailing (default 0.5)
        log (bool): Whether to log the wait info or not
        timeout (int | None): Maximum time (in seconds) to wait for each process. If None (default), wait indefinitely or comply with os env JAWM_WAIT_TIMEOUT
        dynamic (bool): Consider dynamic stabilization mode on process registry, so it doesn't only count snapshot (default False)

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
                if log: cls.logger_wait.warning("Unsupported format for allowed_exit, skipping check.")
                allowed_exit = "all"

        # Normalize single process to list
        if process_list != "all" and not isinstance(process_list, list):
            process_list = [process_list]

        # Resolve processes to wait on
        if process_list == "all":
            time.sleep(float(os.getenv("JAWM_WAIT_GRACE", "0.3")))
            if dynamic:
                # --- Dynamic stabilization mode ---
                stable_cycles = 0
                last_registry_count = -1
                poll_interval = 0.5
                max_total_wait = int(os.getenv("JAWM_WAIT_STABILIZE", "600"))  # default 10 min

                for _ in range(int(max_total_wait / poll_interval)):
                    procs = list({
                        id(p): p
                        for p in cls.registry.values()
                        if isinstance(p, cls) and p.execution_start_at is not None
                    }.values())
                    active = [p for p in procs if not p.finished_event.is_set()]
                    reg_count = len(procs)

                    if reg_count == last_registry_count and not active:
                        stable_cycles += 1
                    else:
                        stable_cycles = 0
                    last_registry_count = reg_count

                    # Require 3 stable cycles for confirmation
                    if stable_cycles >= 3:
                        if log: cls.logger_wait.info(f"Registry stabilized with {len(procs)} total processes.")
                        break

                    time.sleep(poll_interval)

                # Final rescan after stabilization
                procs = list({
                    id(p): p
                    for p in cls.registry.values()
                    if isinstance(p, cls) and p.execution_start_at is not None
                }.values())
            else:
                procs = list({
                    id(p): p
                    for p in cls.registry.values()
                    if isinstance(p, cls) and p.execution_start_at is not None
                }.values())
        else:
            procs = []
            for item in process_list:
                if isinstance(item, cls):
                    procs.append(item)
                elif isinstance(item, str):
                    p = cls.registry.get(item)
                    if p is None:
                        if log: cls.logger_wait.warning(f"No registered process for: {item}")
                        success = False
                    else:
                        procs.append(p)
                else:
                    if log: cls.logger_wait.warning(f"Unsupported process reference: {item}")
                    success = False

        # ---------------------------
        # Live tailing: helpers/setup
        # ---------------------------
        def _follow_file(path, stop_event, prefix, poll):
            """
            Minimal tail -f: waits for file creation, then seeks to end and
            prints new lines until stop_event is set.
            """
            try:
                # Wait for the file to exist (process might not have created it yet)
                while not stop_event.is_set() and not os.path.exists(path):
                    time.sleep(poll)

                if not os.path.exists(path):
                    return  # stopped before file showed up

                with open(path, "r") as f:
                    # Go to end of file
                    f.seek(0, os.SEEK_END)
                    while not stop_event.is_set():
                        where = f.tell()
                        line = f.readline()
                        if line:
                            # Print with a lightweight prefix for clarity
                            sys.stdout.write(f"[TAIL {prefix}] {line}")
                            sys.stdout.flush()
                        else:
                            time.sleep(poll)
                            f.seek(where)
            except Exception as e:
                if log: cls.logger_wait.warning(f"Tail failed for {path}: {e}")

        # Start tailers for ALL selected processes up-front, so they run concurrently
        tail_state = {}  # proc -> {"stop": Event, "threads": [Thread,...]}
        if tail:
            for proc in procs:
                stop_evt = threading.Event()
                threads = []

                def _add_tail(path, label):
                    t = threading.Thread(
                        target=_follow_file,
                        args=(path, stop_evt, f"{proc.name}|{proc.hash} {label}", tail_poll),
                        daemon=True
                    )
                    t.start()
                    threads.append(t)

                opt = str(tail).lower() if tail is not True else "stdout"
                if opt == "stdout":
                    _add_tail(proc.stdout_path, "stdout")
                elif opt == "stderr":
                    _add_tail(proc.stderr_path, "stderr")
                elif opt == "both":
                    _add_tail(proc.stdout_path, "stdout")
                    _add_tail(proc.stderr_path, "stderr")
                else:
                    if log: proc.logger.warning(f"Process.wait | WARNING :: Unsupported tail option '{tail}' — ignoring for {proc.name}")

                tail_state[proc] = {"stop": stop_evt, "threads": threads}

        # ------------------------------------------------------------
        # Wait for processes & tear down their tailers as they finish
        # ------------------------------------------------------------
        for proc in procs:
            try:
                if proc.finished_event.is_set():
                    if log: proc.logger.info(f"Process.wait → {proc.name} [{proc.hash}] already completed")
                else:
                    timeout_val = timeout if isinstance(timeout, int) else None
                    if timeout is not None and not isinstance(timeout, int):
                        if log: proc.logger.warning(f"Process.wait → Invalid timeout parameter '{timeout}' for {proc.name} [{proc.hash}] (must be integer seconds). Ignoring timeout.")

                    if timeout_val is None:
                        env_val = os.getenv("JAWM_WAIT_TIMEOUT")
                        if env_val is not None:
                            try:
                                timeout_val = int(env_val)
                            except ValueError:
                                if log: proc.logger.warning(f"Process.wait → Invalid JAWM_WAIT_TIMEOUT='{env_val}' for {proc.name} [{proc.hash}] (must be integer seconds). Ignoring timeout.")
                                timeout_val = None

                    # --- perform the wait ---
                    if timeout_val is not None:
                        proc.finished_event.wait(timeout=timeout_val)
                        if not proc.finished_event.is_set():
                            proc.logger.warning(f"Process.wait → Timeout ({timeout_val}s) reached while waiting for {proc.name} [{proc.hash}]")
                            success = False
                    else:
                        proc.finished_event.wait()
                    if log: proc.logger.info(f"Process.wait → {proc.name} [{proc.hash}] has completed")

                if allowed_exit != "all":
                    exit_code = proc.get_exitcode()
                    try:
                        code = int(exit_code.split(":")[0]) if (exit_code and ":" in exit_code) else int(exit_code)
                    except Exception:
                        code = None
                    if str(code) not in allowed_exit:
                        if log: proc.logger.warning(f"Process {proc.name} ({proc.hash}) has completed with disallowed exit code: {exit_code}")
                        if hasattr(proc, "_log_error_summary"):
                            if log: proc._log_error_summary(f"Process has completed with disallowed exit code: {exit_code}", type_text="ErrorWait")
                        success = False
            except Exception as e:
                if hasattr(proc, "_log_error_summary"):
                    proc._log_error_summary(f"Error during Process Wait: {str(e)}", type_text="ErrorWait")
                proc.logger.error(f"Failed while managing {proc.name} ({proc.hash}) for process wait: {str(e)}")
                success = False
            finally:
                # stop & join this proc's tailers (others keep running)
                ts = tail_state.get(proc)
                if ts:
                    ts["stop"].set()
                    for t in ts["threads"]:
                        t.join(timeout=1.0)

        if log: cls.logger_wait.info(f"Wait completed for {len(procs)} process(es).")
        return success


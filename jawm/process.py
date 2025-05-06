import threading
import os
import logging
import random
from datetime import datetime

# Extend the Process class with methods from modular backend implementations
from ._method_lib import add_methods_from
from . import _process_base, _process_metal, _process_slurm


@add_methods_from(_process_base, _process_metal, _process_slurm)
class Process:
    # Global registry to map process names to process instances.
    registry = {}
    # A class-level event, shared across all Process instances. Run `Process.stop_future_event.clear()` to prevent preventing
    stop_future_event = threading.Event()

    # Configure logging with proper format
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s:: [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    @classmethod
    def set_log_level(cls, level_name="INFO"):
        """
        Set logging level for all Process loggers, default is INFO.
        If an invalid level is provided, it will be ignored.
        """
        level_name = level_name.upper()
        if level_name not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"]:
            return
        level = getattr(logging, level_name)
        logging.getLogger().setLevel(level)
        for proc in cls.registry.values():
            if hasattr(proc, "logger"):
                proc.logger.setLevel(level)

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
        
        # Primary parameters
        self.name = name
        self.hash = f"{random.randint(0, 65535):04x}"
        self.logger = logging.getLogger(f"{self.name}|{self.hash}")
        
        # Load YAML parameters if provided
        yaml_params = self.parse_yaml_config(param_file) if param_file else {"global": {}, "process": {}}

        # Retrieve configurations: Process-specific first, fallback to global
        process_params = yaml_params["process"].get(name, {})
        global_params = yaml_params["global"]

        # Merge in priority order: global < process < kwargs
        self.params = {**global_params, **process_params, **kwargs}

        # Register the process and get depends_on parameter
        Process.registry[self.name] = self
        Process.registry[self.hash] = self
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
        self.error_summary_file = os.path.abspath(self.params.get("error_summary_file", os.path.join(self.logs_directory, "error_summary.log")))

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
        self.asynchronous = self.params.get("asynchronous", False)
        self.manager = self.params.get("manager", "metal")
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
        os.makedirs(self.log_path, exist_ok=True)

        # std path
        self.stdout_path = os.path.join(self.log_path, f"{self.name}.output")
        self.stderr_path = os.path.join(self.log_path, f"{self.name}.error")

        # For reuse and track (doesn't come from the user parameters directly)
        self.base_script_path = None

        # A threading event that signals when this process has finished.
        self.finished_event = threading.Event()


    def _run_manager(self):
        """
        A helper to choose between different manager execution
        """
        if self.manager == "metal":
            self._execute_metal()
        elif self.manager == "slurm":
            self._execute_slurm()
        else:
            self._log_error_summary(f"Unsupported manager: {self.manager}")
            Process.stop_future_event.set()
            raise ValueError(f"Unsupported manager: {self.manager}")


    def execute(self):
        """
        Asynchronously execute the process, respecting dependencies:
        1) If 'when' is false, skip immediately.
        2) Spawn a background thread that:
            a) Waits for all dependencies' finished_event.
            b) Calls _execute_metal() or _execute_slurm().
        3) Return immediately (non-blocking).
        """
        # If the user condition says "skip," mark finished and return.
        if not self.when:
            self.logger.info(f"Process {self.name} skipped because 'when' condition was not fulfilled!")
            self.finished_event.set()
            return

        # Check if another process has already failed
        if Process.stop_future_event.is_set():
            self.logger.error(f"Skipping execution of {self.name}, as some other process already failed")
            self.finished_event.set()
            return

        if not self.asynchronous:
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
                self._run_manager()
            except Exception as e:
                self.logger.error(f"Process {self.name} failed to launch or execute: {str(e)}")
                Process.stop_future_event.set()
                self.finished_event.set()
                raise

        else:
            def run_in_background():
                """
                This background thread for asynchronous run
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

                # Perform asynchronous runs
                try:
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
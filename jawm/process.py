import threading
import os
import logging
import random
import string
import signal
import subprocess
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

    """

    # Global registry to map process names to process instances.
    registry = {}
    # A class-level event, shared across all Process instances. Run `Process.stop_future_event.clear()` to prevent preventing
    stop_future_event = threading.Event()

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
    def __init__(self, name, param_file=None, **kwargs):
        """
        Initialize the Process object.

        :param name (str, required): Name of the process.
        :param param_file (str or list of str): YAML format file(s) that contains different parameters
        :param kwargs: Additional parameters to configure the process:
            script (str): Inline script content to be executed
            script_file (str): Path to external script file
            script_parameters (dict): Parameters to substitute into the script
            script_parameters_file (str): File with key=value pairs to use in script placeholder substitution
            project_directory (str): Base directory for outputs and logs. Default is current dir
            logs_directory (str): Directory for log files
            error_summary_file (str): Path to a log file summarizing all the errors with time records
            monitoring_directory (str): Directory to keep track of Running/Completed processes.
            asynchronous (bool): Whether the process should run asynchronously. Default is False.
            manager (str): Execution backend. Options: "local", "slurm". Default is "local"
            env (dict): Environment variables for the process
            inputs (dict): Custom user-defined inputs
            outputs (dict): Custom user-defined outputs
            retries (int): Number of retry attempts. Default is 0
            retry_overrides (dict[int -> dict]): Retry-specific overrides by attempt number
            error_strategy (str): What to do on failure: "retry" or "fail". Default is "retry"
            when (bool or callable): Whether to execute this process. Can be dynamic
            manager_local (dict): Execution configs for local manager
            manager_slurm (dict): Execution configs for slurm manager
            environment (str): "local", "docker", or "apptainer". Default is "local".
            container (str): Container image path or name.
            environment_apptainer (dict): Options for running the process inside Apptainer
            environment_docker (dict): Options for running the process inside Docker

        To view detailed documentation for a specific parameter, run:
        >>> jawm.jawm_help("Process", "<parameter_name>")

        """
        
        # Primary parameters
        self.name = name
        self.hash = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
        self.logger = logging.getLogger(f"{self.name}|{self.hash}")
        self.param_file = param_file
        
        # Load YAML parameters if provided
        yaml_params = self._parse_yaml_config(self.param_file) if self.param_file else {"global": {}, "process": {}}

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

        # Time 
        self.execution_start_at = None
        self.execution_end_at = None


    def _run_manager(self):
        """
        A helper to choose between different manager execution
        """
        if self.manager == "local":
            self._execute_local()
        elif self.manager == "slurm":
            self._execute_slurm()
        else:
            self._log_error_summary(f"Unsupported manager: {self.manager}")
            Process.stop_future_event.set()
            raise ValueError(f"Unsupported manager: {self.manager}")


    def execute(self):
        """
        Launch the process execution, handling dependencies and asynchronous logic.

        This method orchestrates the full execution of the process based on its configuration.
        It supports conditional execution (`when`), dependency resolution (`depends_on`), and
        asynchronous execution (`asynchronous`). Depending on the selected execution manager,
        the process will run either locally or via Slurm, with optional container support.

        Execution Flow:
        ---------------
        1. If `when` is False, the process is skipped and marked as finished.
        2. If `asynchronous` is False:
            - Waits for all dependency processes to finish.
            - Runs the process synchronously via the configured manager.
        3. If `asynchronous` is True:
            - Spawns a background thread to:
                a) Wait for all dependencies to complete.
                b) Execute the process in a non-blocking manner.
        4. On error:
            - Logs the error.
            - Triggers a global stop flag (`Process.stop_future_event`) to prevent further steps (if applicable).

        Notes:
        ------
        - Dependencies are resolved using the `depends_on` list, by name or hash.
        - Execution manager is chosen via the `manager` parameter: "local" (local) or "slurm".
        - Errors and outputs are logged to dedicated files in the logs directory.

        Returns:
            None
        
        """
        # If the user condition says "skip," mark finished and return.
        if not self.when:
            self.logger.info(f"Process {self.name} skipped because 'when' condition was not fulfilled!")
            self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
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

        - new_name (str, optional): The name for the cloned process. Defaults to the current process's name.
        - param_file (str or list, optional): YAML parameter file(s) to load. Defaults to the original's param_file.
        - **overrides: Any other parameters to override from the original process's configuration.

        Returns: A new Process instance with copied and/or overridden parameters.

        """
        # Start with a shallow copy of current parameters
        new_params = self.params.copy()

        # Apply any overrides
        new_params.update(overrides)

        # Determine name and param_file
        final_name = name or self.name
        final_param_file = param_file if param_file is not None else getattr(self, 'param_file', None)

        return Process(name=final_name, param_file=final_param_file, **new_params)


    # ----------------------------------------------------------
    #   Class methods with Process Lifecycle and Runtime Control
    # ----------------------------------------------------------

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

    
    @classmethod
    def list_running(cls):
        seen = set()
        running = []

        for proc in cls.registry.values():
            if not isinstance(proc, cls):
                continue
            if id(proc) in seen:
                continue
            seen.add(id(proc))

            if not proc.finished_event.is_set():
                running.append({
                    "name": proc.name,
                    "hash": proc.hash,
                    "id": getattr(proc, "_runtime_id", None) or "NA",
                    "manager": proc.manager,
                    "environment": proc.environment,
                    "log_path": proc.log_path,
                    "initiated_at": proc.date_time,
                    "execution_start": proc.execution_start_at or "NA"
                })
        return running


    @classmethod
    def list_all(cls):
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
                "id": getattr(proc, "_runtime_id", None) or "NA",
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

        proc = cls.registry.get(identifier)
        if not proc:
            print(f"No process found with identifier: {identifier}")
            return False

        if proc.finished_event.is_set():
            print(f"{proc.name}|{proc.hash} :: Process already finished — nothing to kill.")
            return False

        runtime_id = proc.get_id()
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
            print(f"\nFailed to kill: {len(failed)}")
            for pid in failed:
                print(f"  - {pid}")
        
        return {
            "killed": killed,
            "failed": failed
        }


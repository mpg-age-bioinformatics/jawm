import subprocess
import threading
import os
import time
from datetime import datetime

# Setup method registration for dynamic injection into the main Process class
from ._method_lib import register_method

__methods__ = []
register = register_method(__methods__)


@register
def _execute_local(self):
    """
    Execute the process locally with resource constraints.
    :return: None
    """
    self.logger.info(f"Launching process {self.name} using Local executor.")
    self.logger.info(f"Log folder for process {self.name}: {self.log_path}")

    try:
        # Common log paths for each run attempt:
        exitcode_path = os.path.join(self.log_path, f"{self.name}.exitcode")
        id_path = os.path.join(self.log_path, f"{self.name}.id")
        command_path = os.path.join(self.log_path, f"{self.name}.command")

        # Define a helper function to run the process once
        def run_process_once(attempt_i, total_attempts):
            """
            Launch the local process once, wait for completion
            """
            if attempt_i != 1:
                self.logger.info(f"Launching attempt {attempt_i}/{total_attempts} locally...")

            # Generate the base script up front
            base_script_path = self._generate_base_script()

            # Open stdout/stderr for this attempt
            with open(self.stdout_path, "w") as stdout_file, open(self.stderr_path, "w") as stderr_file:
                wrapper = self.before_script or self.after_script

                if self.environment == "apptainer":
                    self.logger.info(f"Executing process {self.name} with apptainer container {self.container}")
                    command = self._build_apptainer_command(base_script_path)
                    wrapped_command = self._generate_command_wrapper(command) if wrapper else " ".join(command)
                    # Log the command
                    with open(command_path, "w") as cmd_file:
                        cmd_file.write(wrapped_command)

                    try:
                        result = subprocess.Popen(
                            ["bash", "-c", wrapped_command] if wrapper else command,
                            stdout=stdout_file,
                            stderr=stderr_file,
                            text=True
                        )
                    except Exception as e:
                        self._proc_exception_handler(e, location="apptainer command execution", type_text="ApptainerError")
                        return 127

                elif self.environment == "docker":
                    self.logger.info(f"Executing process {self.name} with docker container {self.container}")
                    command = self._build_docker_command(base_script_path)
                    wrapped_command = self._generate_command_wrapper(command) if wrapper else " ".join(command)
                    # Log the command
                    with open(command_path, "w") as cmd_file:
                        cmd_file.write(wrapped_command)

                    try:
                        result = subprocess.Popen(
                            ["bash", "-c", wrapped_command] if wrapper else command,
                            stdout=stdout_file,
                            stderr=stderr_file,
                            text=True
                        )
                    except Exception as e:
                        self._proc_exception_handler(e, location="docker command execution", type_text="DockerError")
                        return 127

                else:
                    # Plain local execution
                    command = [base_script_path]
                    wrapped_command = self._generate_command_wrapper(command) if wrapper else base_script_path
                    with open(command_path, "w") as cmd_file:
                        cmd_file.write(wrapped_command)

                    try:
                        result = subprocess.Popen(
                            ["bash", "-c", wrapped_command] if wrapper else command,
                            env=self.combined_env,
                            stdout=stdout_file,
                            stderr=stderr_file,
                            text=True
                        )
                    except Exception as e:
                        self._proc_exception_handler(e, location="local command execution", type_text="LocalError")
                        return 127

            # Record the PID
            process_id = result.pid
            self.logger.info(f"Process {self.name} started with PID: {process_id}")
            self.runtime_id = str(process_id)
            with open(id_path, "w") as id_file:
                id_file.write(str(process_id))

            # Create "Running" file in the monitoring directory
            self._monitoring_running_file(process_id, base_script_path)

            # Poll until the subprocess finishes
            elapsed_time = 0
            while result.poll() is None:
                # (Optional) log if it's been 3 minutes
                if elapsed_time % 600 == 0:
                    self.logger.info(f"Process {self.name} (PID: {process_id}) is still running...")
                elapsed_time += 5
                time.sleep(5)

            # Subprocess is done; gather final info
            exit_code = result.returncode
            self.logger.info(f"Process {self.name} completed with exit code: {exit_code}")

            # Write out the exit code and ID
            with open(exitcode_path, "w") as exc_file:
                exc_file.write(str(exit_code))

            # Move from Running -> Completed in monitoring
            self._monitoring_completed_file(process_id, base_script_path, exit_code)

            return exit_code

        # 3) Background monitor thread that performs up to (retries+1) attempts
        def monitor_process():
            try:
                total_attempts = self.retries + 1
                last_exit_code = None

                for attempt_i in range(1, total_attempts + 1):
                    self._apply_retry_parameters(attempt_i - 1)
                    exit_code = run_process_once(attempt_i, total_attempts)
                    last_exit_code = exit_code

                    # If success, we're done
                    if exit_code == 0:
                        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                        self.finished_event.set()
                        return

                    # Otherwise log error, possibly retry
                    self.logger.error(f"Attempt {attempt_i} for process {self.name} failed with exit code {exit_code}{self._elog_path()}")
                    with open(self.stderr_path, "r") as stderr_file:
                        error_message = stderr_file.read().strip()
                    self._log_error_summary(self._tail_text(error_message), type_text="LocalAttempt")

                    # If there's another attempt left, keep going
                    if attempt_i < total_attempts:
                        remaining = total_attempts - attempt_i
                        self.logger.info(f"Retrying process {self.name}, {remaining} retries left.")
                    else:
                        self._log_error_summary(f"Process in Local failed.{self._tail_error()}", type_text="LocalAttempt")
                        self.logger.error(f"Process {self.name} in Local failed after {total_attempts} attempts{self._elog_path()}{self._tail_error()}")
                        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                        self.finished_event.set()
                        self.stop_future_event.set()
                        try:
                            with open(exitcode_path, "w") as exc_file:
                                exc_file.write(str(exit_code))
                        except:
                            pass
                        return
            except Exception as e:
                self._proc_exception_handler(e, location="monitoring", type_text="LocalError")
                return

        # Start the background thread so _execute_local() returns immediately
        self._monitor_thread = threading.Thread(target=monitor_process, daemon=False)
        self._monitor_thread.start()

        # Return immediately (non-blocking).
        return None

    except Exception as e:
        # If something fails before the monitor thread is even launched,
        # we need to set finished_event so dependent processes won't wait forever.
        self.logger.error(f"Failed launching process {self.name} in Local: {str(e)}{self._elog_path()}")
        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.finished_event.set()
        self.stop_future_event.set()
        return
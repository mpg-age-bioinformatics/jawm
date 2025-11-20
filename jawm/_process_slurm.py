import subprocess
import threading
import os
import time
import re
from datetime import datetime

# Setup method registration for dynamic injection into the main Process class
from ._method_lib import register_method

__methods__ = []
register = register_method(__methods__)


@register
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

        slurm_script_file.write(f"#SBATCH --job-name={self._sanitize_slurm_name()}\n") # Slurm job name
        
        # Add SLURM options dynamically
        for key, value in self.manager_slurm.items():
            if key.startswith("--"):
                slurm_script_file.write(f"#SBATCH {key}={value}\n")

        # Apply before_script if defined
        if self.before_script:
            slurm_script_file.write(f"\n{self.before_script.strip()}\n")
        
        # Call the executable script
        slurm_script_file.write(f"\n{slurm_script_command}\n")

        # Apply after_script if defined
        if self.after_script:
            slurm_script_file.write(f"\n{self.after_script.strip()}\n")

    return slurm_script_path


@register
def _generate_sbatch_command(self):
    """
    Generate an sbatch command dynamically based on user-provided SLURM properties.
    :return: The sbatch command as a list.
    """
    sbatch_command = ["sbatch"]

    # Ensure parsable output for consistent job ID parsing
    if "--parsable" not in self.manager_slurm:
        sbatch_command.insert(1, "--parsable")

    # Add user-provided SLURM options dynamically
    for key, value in self.manager_slurm.items():
        sbatch_command.extend([key, str(value)])

    # Add defaults for output and error only if not provided by the user
    output_keys = {"--output", "-o"}
    error_keys = {"--error", "-e"}

    if not any(k in self.manager_slurm for k in output_keys):
        sbatch_command.extend(["--output", self.stdout_path])
    if not any(k in self.manager_slurm for k in error_keys):
        sbatch_command.extend(["--error", self.stderr_path])

    return sbatch_command


@register
def _sanitize_slurm_name(self):
    """
    Return a Slurm-safe job name derived from process name and hash.
    """
    base = f"{self.name}_{self.hash}"
    safe = re.sub(r"[^A-Za-z0-9_\-]+", "_", base)
    return safe[:80]


@register
def _execute_slurm(self):
    """
    Execute the process as a Slurm job.
    :return: None
    """
    self.logger.info(f"Launching process {self.name} using Slurm executor")
    self.logger.info(f"Log folder for process {self.name}: {self.log_path}")

    # Store some common paths for each run attempt
    exitcode_path = os.path.join(self.log_path, f"{self.name}.exitcode")
    id_path = os.path.join(self.log_path, f"{self.name}.id")
    command_path = os.path.join(self.log_path, f"{self.name}.command")
    slurm_script_path = os.path.join(self.log_path, f"{self.name}.slurm")

    try:
        # Define helper function for one attempt
        def run_process_once_slurm(attempt_i, total_attempts):
            """
            Submit Slurm job, monitor it synchronously, return final exit code.
            """

            if attempt_i != 1:
                self.logger.info(f"Launching Slurm attempt {attempt_i}/{total_attempts} for {self.name}...")

            # Generate the Slurm job script
            script_path = self._generate_slurm_script()  # writes out to slurm_script_path
            # Generate the sbatch command
            sbatch_command = self._generate_sbatch_command()
            sbatch_command.append(script_path)

            self.logger.info(f"Submitting process {self.name} with slurm command: {' '.join(sbatch_command)}")
            with open(command_path, "w") as command_path_file:
                command_path_file.write(" ".join(sbatch_command))

            job_id = None
            
            # Submit the job script to Slurm
            result = subprocess.run(
                sbatch_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Check submission result
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                stderr_lc = stderr.lower()
                # Detect transient / connectivity problems only
                transient_keywords = [
                    "socket timed out",
                    "unable to contact slurm controller",
                    "slurm_load_jobs",
                    "connection timed out",
                    "communication connection failure",
                    "rpc timeout",
                    "controller not responding",
                ]
                transient_issue = any(k in stderr_lc for k in transient_keywords)
                
                if transient_issue:
                    self.logger.warning(f"Detected transient Slurm issue — will check if job actually went through: {stderr}")
                
                    max_retries = int(os.getenv("JAWM_SLURM_TRANSIENT_RETRY", "7"))
                    sbatch_wait = int(os.getenv("JAWM_SLURM_TRANSIENT_WAIT", "5"))
                    time.sleep(sbatch_wait)

                    try:
                        job_name = self._sanitize_slurm_name()
                        who = os.environ.get("USER") or os.getlogin()

                        for attempt in range(1, max_retries + 1):
                            # Prefer sacct for completed or recently submitted jobs
                            check = subprocess.run(
                                [
                                    "sacct", "-u", who,
                                    "--name", job_name,
                                    "--format=JobID,JobName%120,State",
                                    "--noheader"
                                ],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                            )

                            if check.returncode == 0:
                                pattern = rf"(\d+)\s+{re.escape(job_name)}\b"
                                m = re.search(pattern, check.stdout)
                                if m:
                                    job_id = m.group(1)
                                    break

                            # Fallback to squeue if sacct didn’t find it
                            if not job_id:
                                queue = subprocess.run(
                                    ["squeue", "-u", who, "--name", job_name, "-o", "%.18i %.8j %.2t %.10M %.6D %R", "--sort=-i"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                                )
                                if queue.returncode == 0:
                                    m = re.search(rf"(\d+)\s+{re.escape(job_name)}\b", queue.stdout)
                                    if m:
                                        job_id = m.group(1)
                                        break

                            # Wait before next retry
                            if not job_id:
                                time.sleep( sbatch_wait *  attempt)

                    except Exception as e:
                        self.logger.warning(f"Slurm job existence check failed: {e}")

                if job_id:
                    self.logger.info(f"Despite the warning, job went through: Slurm JobID {job_id}")
                else:
                    self._log_error_summary(result.stderr, type_text="SlurmError")
                    self.logger.error(f"Failed to submit process {self.name} to Slurm: {result.stderr}{self._elog_path()}")
                    try:
                        with open(exitcode_path, "w") as f:
                            f.write("127")
                    except Exception:
                        pass
                    return 127  # job failed to submit

            # Parse job_id from sbatch output
            if not job_id:
                job_id = (result.stdout or "").strip().split(";")[0]
                if not job_id or not job_id.isdigit():
                    msg = f"Invalid or missing Slurm JobID for {self.name}: {result.stdout.strip()}"
                    self._log_error_summary(msg, type_text="SlurmError")
                    self.logger.error(f"{msg}{self._elog_path()}")
                    try:
                        with open(exitcode_path, "w") as f:
                            f.write("127")
                    except Exception:
                        pass
                    return 127
    
            self.logger.info(f"Process {self.name} submitted as Slurm job {job_id}.")
            self.runtime_id = str(job_id)
            with open(id_path, "w") as id_file:
                id_file.write(str(job_id))

            # Create monitoring file in Running directory
            self._monitoring_running_file(job_id, script_path)

            # Synchronously monitor the Slurm job in this function
            elapsed_time = 0
            retry_fail = 0
            max_fail = 10

            # Define exit_code as "unknown" until we get a final state
            final_exit_code = 1  # assume failure by default

            while True:
                # Query the job's status and exit code using sacct
                job_info = subprocess.run(
                    ["sacct", "-j", job_id, "--format=JobID,State,ExitCode", "-n"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                # Handle failure on Slurm job querying
                if job_info.returncode != 0:
                    if retry_fail >= max_fail:
                        self._log_error_summary("Monitoring failed from sacct tool!", type_text="SlurmMonitoring")
                        self.logger.error(f"Max retries ({max_fail}) for querying job {job_id} with sacct tool. Stopping monitoring!{self._elog_path()}")
                        break
                    self.logger.warning(f"Failed to query job {job_id} status: {job_info.stderr}")
                    time.sleep(min(10 * (2 ** retry_fail), 300))
                    retry_fail += 1
                    continue  # Retry querying

                # Parse the job state and exit code
                output = job_info.stdout.strip()
                if output:
                    _, state, exit_code = output.split()[:3]
                    final_states = {"COMPLETED", "FAILED", "CANCELLED", "BOOT_FAIL", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "DEADLINE"}
                    if elapsed_time % 600 == 0:
                        self.logger.info(f"Slurm job {job_id} state={state}, exit_code={exit_code}")
                    if any(state.startswith(s) for s in final_states):
                        if state.startswith("CANCELLED"):
                            self.logger.warning(f"Slurm job {job_id} was cancelled manually or externally.")
                        self.logger.info(f"Slurm job {job_id} completed with exit code: {exit_code}, state: {state}")
                        # final_exit_code = 0 if (exit_code == "0:0") else 1
                        final_exit_code = 1 if state.startswith("CANCELLED") or exit_code != "0:0" else 0
                        # Write out the exit_code
                        with open(exitcode_path, "w") as exitcode_file:
                            exitcode_file.write(str(exit_code))
                        # Move from Running->Completed
                        self._monitoring_completed_file(job_id, script_path, exit_code)
                        # If we want to capture stderr output or something, do it here
                        if final_exit_code != 0:
                            # job failed
                            if os.path.exists(self.stderr_path) and os.path.getsize(self.stderr_path) > 0:
                                with open(self.stderr_path, "r") as error_file:
                                    error_message = error_file.read().strip()
                                self._log_error_summary(error_message, type_text="SlurmError")
                        break

                time.sleep(10)  # Check status every 10 seconds
                elapsed_time += 10

            return 0 if final_exit_code == 0 else 1

        # Define a single function for retries
        def monitor_process():
            total_attempts = self.retries + 1
            for attempt_i in range(1, total_attempts + 1):
                self._apply_retry_parameters(attempt_i - 1)
                exit_code = run_process_once_slurm(attempt_i, total_attempts)
                if exit_code == 0:
                    # success on this attempt
                    self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                    self.finished_event.set()
                    return
                # Else it failed
                self.logger.error(f"Attempt {attempt_i} for process {self.name} failed in Slurm{self._elog_path()}")
                if attempt_i < total_attempts:
                    remaining = total_attempts - attempt_i
                    self.logger.info(f"Retrying process {self.name} in Slurm, {remaining} retries left")
                else:
                    # Fallback error summary logging
                    self._log_error_summary(f"Process in Slurm failed.{self._tail_error(slurm=True)}", type_text="SlurmError")
                    self.logger.error(f"Process {self.name} in Slurm failed after {total_attempts} attempt(s){self._elog_path()}{self._tail_error(slurm=True)}")
                    # Out of attempts
                    self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                    self.finished_event.set()
                    self.stop_future_event.set()
                    return

        # Start a background thread that runs the multi-attempt logic
        self._monitor_thread = threading.Thread(target=monitor_process, daemon=False)
        self._monitor_thread.start()

        return None

    except Exception as e:
        self.logger.error(f"Failed launching process {self.name} in Slurm: {str(e)}{self._elog_path()}")
        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.finished_event.set()
        self.stop_future_event.set()
        return
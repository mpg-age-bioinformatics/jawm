import subprocess
import os
import logging
import tempfile

class Process:
    def __init__(self, name, script, **kwargs):
        self.name = name
        self.script = script
        self.interpreter = kwargs.get("interpreter", "/bin/bash")
        self.env = kwargs.get("env", os.environ.copy())
        self.inputs = kwargs.get("inputs", {})
        self.outputs = kwargs.get("outputs", {})
        self.retries = kwargs.get("retries", 0)
        self.container = kwargs.get("container", None)
        self.cpus = kwargs.get("cpus", 1)
        self.memory = kwargs.get("memory", "1 GB")
        self.time_limit = kwargs.get("time", None)
        self.use_scratch = kwargs.get("scratch", False)
        self.error_strategy = kwargs.get("error_strategy", "retry")
        self.when = kwargs.get("when", True)
        self.before_script = kwargs.get("before_script", None)
        self.after_script = kwargs.get("after_script", None)
        self.logger = logging.getLogger(name)

    def execute(self, options=None):
        if not self.when:
            self.logger.info(f"Skipping process {self.name} due to condition.")
            return
        
        # Run the before script, if provided
        if self.before_script:
            self.logger.info(f"Running before_script for {self.name}")
            subprocess.run(self.before_script, shell=True, env=self.env)

        try:
            # Write the script to a temporary file
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_script:
                temp_script.write(self.script)
                temp_script_path = temp_script.name
            
            # Make the script executable if needed
            os.chmod(temp_script_path, 0o755)
            
            # Execute the script using the specified interpreter
            self.logger.info(f"Executing process {self.name} with interpreter: {self.interpreter}")
            result = subprocess.run(
                [self.interpreter, temp_script_path],
                env=self.env,
                timeout=self.time_limit,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Check execution result
            if result.returncode == 0:
                self.logger.info(f"Process {self.name} completed successfully.")
            else:
                self.logger.error(f"Process {self.name} failed with error: {result.stderr}")
                if self.retries > 0:
                    self.logger.info(f"Retrying process {self.name}, {self.retries} retries left.")
                    self.retries -= 1
                    return self.execute(options)
                raise RuntimeError(f"Process {self.name} failed with error: {result.stderr}")

            # Return the output
            return result.stdout

        except subprocess.TimeoutExpired as e:
            self.logger.error(f"Process {self.name} timed out.")
            raise e

        finally:
            # Cleanup the temporary script file
            if os.path.exists(temp_script_path):
                os.remove(temp_script_path)

            # Run the after script, if provided
            if self.after_script:
                self.logger.info(f"Running after_script for {self.name}")
                subprocess.run(self.after_script, shell=True, env=self.env)


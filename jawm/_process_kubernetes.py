import os
import json
import time
import shlex
import subprocess
import threading
from datetime import datetime

# Setup method registration for dynamic injection into the main Process class
from ._method_lib import register_method

__methods__ = []
register = register_method(__methods__)

@register
def _generate_k8s_manifest(self):
    """
    Build a Kubernetes Job manifest (as JSON string) for this Process.
    Writes it to <log_path>/<name>.k8s.json and returns the path.
    """
    os.makedirs(self.log_path, exist_ok=True)
    path = os.path.join(self.log_path, f"{self.name}.k8s.json")

    # Compose the shell command inside the container
    # reuse before/after wrapper exactly like Docker/Apptainer builders
    base_script = self._generate_base_script()
    cmd_parts = []
    if self.container_before_script: cmd_parts.append(self.container_before_script.strip())
    # call the base script (mounted via ConfigMap-less trick: embed into command via bash -lc)
    # Simpler MVP: mount nothing, we will inject the whole script into the command string.
    # But safer: copy the base_script content into the command string:
    with open(base_script, "r") as f:
        in_container_script = f.read()

    # Wrap the user script in a bash -lc '...' block so "&&" chains work
    core = in_container_script
    if self.before_script or self.after_script:
        wrapper = []
        if self.before_script: wrapper.append(self.before_script.strip())
        wrapper.append(core)
        if self.after_script: wrapper.append(self.after_script.strip())
        core = " && ".join(wrapper)

    # Note: We'll run bash -lc '...'; JSON needs proper quoting
    container_command = ["/bin/bash", "-lc", core]

    image = self.container or "ubuntu:22.04"

    # Map env vars
    env_list = [{"name": k, "value": str(v)} for k, v in (self.env or {}).items()]

    # Pull selected options from manager_kubernetes
    mk = dict(self.manager_kubernetes or {})
    namespace = mk.pop("namespace", None)
    backoffLimit = int(mk.pop("backoffLimit", 0))  # we already implement retries in JAWM
    ttl = mk.pop("ttlSecondsAfterFinished", 3600)
    restartPolicy = mk.pop("restartPolicy", "Never")
    resources = mk.pop("resources", None)
    nodeSelector = mk.pop("nodeSelector", None)
    tolerations = mk.pop("tolerations", None)
    imagePullSecrets = mk.pop("imagePullSecrets", None)
    serviceAccountName = mk.pop("serviceAccountName", None)
    labels = mk.pop("labels", {"jawm-name": self.name})
    annotations = mk.pop("annotations", None)
    volumes = mk.pop("volumes", None)
    volumeMounts = mk.pop("volumeMounts", None)
    activeDeadlineSeconds = mk.pop("activeDeadlineSeconds", None)

    # Build manifest
    job_name = f"jawm-{self.name.lower()}"
    manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name, "labels": labels},
        "spec": {
            "backoffLimit": backoffLimit,
            "ttlSecondsAfterFinished": ttl,
            "template": {
                "metadata": {"labels": labels, **({"annotations": annotations} if annotations else {})},
                "spec": {
                    "restartPolicy": restartPolicy,
                    **({"serviceAccountName": serviceAccountName} if serviceAccountName else {}),
                    "containers": [{
                        "name": "task",
                        "image": image,
                        "env": env_list,
                        "command": container_command,
                        **({"resources": resources} if resources else {}),
                        **({"volumeMounts": volumeMounts} if volumeMounts else {})
                    }],
                    **({"volumes": volumes} if volumes else {}),
                    **({"nodeSelector": nodeSelector} if nodeSelector else {}),
                    **({"tolerations": tolerations} if tolerations else {}),
                    **({"activeDeadlineSeconds": activeDeadlineSeconds} if activeDeadlineSeconds else {})
                }
            }
        }
    }

    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    # stash namespace for submit step
    self._k8s_namespace = namespace
    self._k8s_job_name = job_name
    return path

@register
def _execute_kubernetes(self):
    """
    Submit as a Kubernetes Job via kubectl, then monitor until completion.
    Writes .id (job name), .exitcode, and .command, and updates monitoring files.
    """
    self.logger.info(f"Executing process {self.name} in Kubernetes")
    self.logger.info(f"Log folder for process {self.name}: {self.log_path}")

    exitcode_path = os.path.join(self.log_path, f"{self.name}.exitcode")
    id_path = os.path.join(self.log_path, f"{self.name}.id")
    command_path = os.path.join(self.log_path, f"{self.name}.command")

    def run_once(attempt_i, total_attempts):
        manifest_path = self._generate_k8s_manifest()

        # kubectl apply
        cmd = ["kubectl", "apply", "-f", manifest_path]
        if getattr(self, "_k8s_namespace", None):
            cmd.extend(["-n", self._k8s_namespace])
        with open(command_path, "w") as cf: cf.write(" ".join(shlex.quote(c) for c in cmd))
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            self._log_error_summary(res.stderr)
            self.logger.error(f"kubectl apply failed: {res.stderr.strip()}")
            return 127

        # Record job "id" as job name
        job_id = getattr(self, "_k8s_job_name", None)
        self.runtime_id = job_id
        with open(id_path, "w") as f: f.write(job_id or "")
        self._monitoring_running_file(job_id, manifest_path)

        # Poll job status; once finished, fetch pod exit code + logs
        def _kubectl(args):
            base = ["kubectl"]
            if getattr(self, "_k8s_namespace", None):
                base += ["-n", self._k8s_namespace]
            return subprocess.run(base + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        exit_code_int = 1
        last_pod_name = None
        while True:
            # Get pod name for this job
            pods = _kubectl(["get", "pods", "-l", f"job-name={job_id}", "-o", "json"])
            if pods.returncode == 0:
                try:
                    import json as _json
                    data = _json.loads(pods.stdout)
                    items = data.get("items", [])
                    if items:
                        last_pod_name = items[0]["metadata"]["name"]
                        phase = items[0]["status"].get("phase")
                        # Periodic log tail (MVP: fetch at end, not streaming)
                        if phase in {"Succeeded", "Failed"}:
                            # Fetch logs to files
                            if last_pod_name:
                                out = _kubectl(["logs", last_pod_name, "-c", "task"])
                                # Write logs
                                with open(self.stdout_path, "w") as f: f.write(out.stdout or "")
                                with open(self.stderr_path, "w") as f: f.write(out.stderr or "")
                                # Exit code from container status
                                sts = items[0]["status"].get("containerStatuses", [])
                                if sts and "state" in sts[0] and "terminated" in sts[0]["state"]:
                                    exit_code_int = int(sts[0]["state"]["terminated"].get("exitCode", 1))
                            break
                except Exception:
                    pass

            time.sleep(5)

        # Write exit code files and monitoring move
        with open(exitcode_path, "w") as f: f.write(str(exit_code_int))
        self._monitoring_completed_file(job_id, manifest_path, exit_code_int)
        return 0 if exit_code_int == 0 else 1

    def monitor_process():
        total_attempts = self.retries + 1
        for attempt_i in range(1, total_attempts + 1):
            self._apply_retry_parameters(attempt_i - 1)
            rc = run_once(attempt_i, total_attempts)
            if rc == 0:
                self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                self.finished_event.set()
                return
            self.logger.error(f"Kubernetes attempt {attempt_i}/{total_attempts} failed")
            if attempt_i < total_attempts:
                self.logger.info(f"Retrying Kubernetes job; {total_attempts - attempt_i} retries left")
            else:
                self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                self.finished_event.set()
                self.stop_future_event.set()
                self._log_error_summary("Kubernetes job failed after retries")
                raise RuntimeError(f"Process {self.name} in Kubernetes failed after {total_attempts} attempts")

    self._monitor_thread = threading.Thread(target=monitor_process, daemon=False)
    self._monitor_thread.start()
    return None

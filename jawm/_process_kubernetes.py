import os
import json
import time
import shlex
import subprocess
import threading
import re
from datetime import datetime

# Setup method registration for dynamic injection into the main Process class
from ._method_lib import register_method

__methods__ = []
register = register_method(__methods__)


@register
def _generate_k8s_manifest(self):
    """
    Build a Kubernetes Job manifest for this Process and write it to <log_path>/<name>.k8s.json.
    Returns the manifest path.
    """
    import os, json

    os.makedirs(self.log_path, exist_ok=True)
    manifest_path = os.path.join(self.log_path, f"{self.name}.k8s.json")

    # 1) Prepare the in-container command
    base_script_path = self._generate_base_script()
    with open(base_script_path, "r") as f:
        core_script = f.read()

    # Wrap with optional before/after (host/container)
    parts = []
    if self.container_before_script:
        parts.append(self.container_before_script.strip())
    parts.append(core_script)
    if self.container_after_script:
        parts.append(self.container_after_script.strip())
    # (host-level before/after also fine to include here for simplicity)
    if self.before_script:
        parts.insert(0, self.before_script.strip())
    if self.after_script:
        parts.append(self.after_script.strip())

    container_command = ["/bin/bash", "-lc", " && ".join(parts)]

    # 2) Resolve image & env
    image = self.container or "ubuntu:22.04"
    env_list = [{"name": k, "value": str(v)} for k, v in (self.env or {}).items()]

    # 3) Pull K8s options from manager_kubernetes (safe defaults)
    mk = dict(self.manager_kubernetes or {})
    namespace = mk.pop("namespace", None)
    backoffLimit = int(mk.pop("backoffLimit", 0))              # let JAWM handle retries
    ttlSecondsAfterFinished = mk.pop("ttlSecondsAfterFinished", 600)
    restartPolicy = mk.pop("restartPolicy", "Never")
    resources = mk.pop("resources", None)
    nodeSelector = mk.pop("nodeSelector", None)
    tolerations = mk.pop("tolerations", None)
    imagePullSecrets = mk.pop("imagePullSecrets", None)
    serviceAccountName = mk.pop("serviceAccountName", None)
    volumes = mk.pop("volumes", None)
    volumeMounts = mk.pop("volumeMounts", None)
    activeDeadlineSeconds = mk.pop("activeDeadlineSeconds", None)
    labels_extra = mk.pop("labels", {})
    annotations = mk.pop("annotations", None)

    # 4) Sanitize names/labels using YOUR instance method
    job_name = self._k8s_sanitize_label(f"{self.name}-{self.hash}")
    container_name = self._k8s_sanitize_label(f"jc-{self.name}", fallback_suffix="jc")
    lbl_name = self._k8s_sanitize_label(self.name)
    lbl_hash = self._k8s_sanitize_label(self.hash)
    labels_block = {
        "jawm-name": lbl_name,
        "jawm-hash": lbl_hash,
        **labels_extra
    }

    # 5) Build the manifest
    manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "labels": labels_block,
            **({"annotations": annotations} if annotations else {})
        },
        "spec": {
            "backoffLimit": backoffLimit,
            "ttlSecondsAfterFinished": ttlSecondsAfterFinished,
            "template": {
                "metadata": {
                    "labels": {
                        "job-name": job_name,
                        **labels_block
                    },
                    **({"annotations": annotations} if annotations else {})
                },
                "spec": {
                    "restartPolicy": restartPolicy,
                    **({"serviceAccountName": serviceAccountName} if serviceAccountName else {}),
                    "containers": [{
                        "name": container_name,
                        "image": image,
                        "env": env_list,
                        "command": container_command,
                        **({"resources": resources} if resources else {}),
                        **({"volumeMounts": volumeMounts} if volumeMounts else {})
                    }],
                    **({"volumes": volumes} if volumes else {}),
                    **({"nodeSelector": nodeSelector} if nodeSelector else {}),
                    **({"tolerations": tolerations} if tolerations else {}),
                    **({"imagePullSecrets": imagePullSecrets} if imagePullSecrets else {}),
                    **({"activeDeadlineSeconds": activeDeadlineSeconds} if activeDeadlineSeconds else {})
                }
            }
        }
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # stash for submit/monitor steps
    self._k8s_namespace = namespace
    self._k8s_job_name = job_name
    self._k8s_container_name = container_name
    return manifest_path


@register
def _execute_kubernetes(self):
    """
    Submit as a Kubernetes Job via kubectl, then monitor until completion.
    Writes .id (job name), .exitcode, and .command, and updates monitoring files.
    """
    import os, subprocess, shlex, time
    from datetime import datetime

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
        with open(command_path, "w") as cf:
            cf.write(" ".join(shlex.quote(c) for c in cmd))
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            self._log_error_summary(res.stderr)
            self.logger.error(f"kubectl apply failed: {res.stderr.strip()}")
            return 127

        # Record job "id" as job name
        job_id = getattr(self, "_k8s_job_name", None)
        self.runtime_id = job_id
        with open(id_path, "w") as f:
            f.write(job_id or "")
        self._monitoring_running_file(job_id, manifest_path)

        # Poll job status; once finished, fetch pod exit code + logs
        def _kubectl(args):
            base = ["kubectl"]
            if getattr(self, "_k8s_namespace", None):
                base += ["-n", self._k8s_namespace]
            return subprocess.run(base + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        exit_code_int = 1
        last_pod_name = None
        selected_container = getattr(self, "_k8s_container_name", None)

        while True:
            pods = _kubectl(["get", "pods", "-l", f"job-name={job_id}", "-o", "json"])
            if pods.returncode == 0:
                try:
                    import json as _json
                    data = _json.loads(pods.stdout)
                    items = data.get("items", [])
                    if items:
                        # pick the newest pod if multiple (e.g., retries)
                        items.sort(key=lambda i: i.get("metadata", {}).get("creationTimestamp", ""), reverse=True)
                        pod = items[0]
                        last_pod_name = pod["metadata"]["name"]
                        phase = pod.get("status", {}).get("phase")

                        if phase in {"Succeeded", "Failed"}:
                            # Decide logs command (single container => no -c needed)
                            logs_args = ["logs", last_pod_name]
                            try:
                                containers = pod.get("spec", {}).get("containers", []) or []
                                if selected_container:
                                    # ensure the selected container actually exists; else fall back
                                    if any(c.get("name") == selected_container for c in containers):
                                        logs_args += ["-c", selected_container]
                                    elif len(containers) == 1:
                                        pass  # omit -c for single container
                                    else:
                                        # try the first container if multiple
                                        logs_args += ["-c", containers[0].get("name")]
                                else:
                                    if len(containers) == 1:
                                        pass
                                    elif len(containers) > 1:
                                        logs_args += ["-c", containers[0].get("name")]
                            except Exception:
                                # best-effort: omit -c
                                pass

                            out = _kubectl(logs_args)

                            # Write container logs (stdout). kubectl client errors (if any) go to stderr.
                            try:
                                with open(self.stdout_path, "w") as f:
                                    f.write(out.stdout or "")
                            except Exception:
                                pass
                            if out.returncode != 0 or (out.stderr and out.stderr.strip()):
                                try:
                                    with open(self.stderr_path, "w") as f:
                                        f.write(out.stderr or "")
                                except Exception:
                                    pass

                            # Exit code from container status
                            sts = pod.get("status", {}).get("containerStatuses", []) or []
                            chosen = None
                            if selected_container:
                                for cs in sts:
                                    if cs.get("name") == selected_container:
                                        chosen = cs
                                        break
                            if chosen is None and sts:
                                chosen = sts[0]
                            if chosen and "state" in chosen and "terminated" in chosen["state"]:
                                try:
                                    exit_code_int = int(chosen["state"]["terminated"].get("exitCode", 1))
                                except Exception:
                                    exit_code_int = 1
                            break
                except Exception:
                    pass

            time.sleep(5)

        # Write exit code files and monitoring move
        try:
            with open(exitcode_path, "w") as f:
                f.write(str(exit_code_int))
        except Exception:
            pass
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


@register
def _k8s_sanitize_label(self, s, max_len=60, fallback_suffix="jawm-process"):
    """
    Simple RFC1123-style sanitizer for K8s names/labels:
    - lowercase
    - keep only [a-z0-9-]  (strict; underscores/dots become '-')
    - collapse consecutive '-'
    - trim leading/trailing '-'
    - truncate to max_len (default 50)
    - never return empty
    """
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)   # replace illegal chars with '-'
    s = re.sub(r"-{2,}", "-", s)         # collapse multiple dashes
    s = s.strip("-")                     # must start/end alnum
    s = s[:max_len]
    return s or f"{fallback_suffix}-{self.hash}"
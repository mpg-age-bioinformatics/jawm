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


@register
def _generate_k8s_manifest(self, attempt_i=None):
    """
    Build a K8s Job manifest for this Process and write it to <log_path>/<name>.k8s.json.
    Returns the manifest path.
    """
    self.logger.info(f"Generating K8s job manifest for process: {self.name}")

    os.makedirs(self.log_path, exist_ok=True)
    manifest_path = os.path.join(self.log_path, f"{self.name}.k8s.json")

    # 1) Read the base script content
    base_script_path = self._generate_base_script()
    with open(base_script_path, "r") as f:
        core_script = f.read()

    # 2) Resolve image & env
    def _infer_image_from_shebang(line):
        l = (line or "").strip().lower()
        # Common cases
        if "python" in l:      # covers /usr/bin/python, /usr/bin/env python3, etc.
            return "python:3.11-slim"
        if "rscript" in l:     # covers /usr/bin/env Rscript
            return "rocker/r-ver:4.4.1"
        # default shell-only workloads
        return "ubuntu:22.04"

    first_line = (core_script.splitlines() or [""])[0]
    if self.container:
        image = self.container
    else:
        image = _infer_image_from_shebang(first_line)
        # Warn loudly that we’re guessing
        self.logger.warning(f"Container image not provided; inferred '{image}' from shebang. it may fail if required dependencies are missing.")

    env_list = [{"name": k, "value": str(v)} for k, v in (self.env or {}).items()]

    # Unbuffer python stdout in containers (helps kubectl logs reliability)
    try:
        if "python" in (first_line or "").lower():
            if not any(e.get("name") == "PYTHONUNBUFFERED" for e in env_list):
                env_list.append({"name": "PYTHONUNBUFFERED", "value": "1"})
    except Exception:
        pass

    # 3) Pull K8s options from manager_kubernetes (safe defaults)
    mk = dict(self.manager_kubernetes or {})
    namespace = mk.pop("namespace", None)
    backoffLimit = int(mk.pop("backoffLimit", 0))              # let jawm handle retries
    ttlSecondsAfterFinished = mk.pop("ttlSecondsAfterFinished", 600)
    restartPolicy = mk.pop("restartPolicy", "Never")
    resources = mk.pop("resources", None)
    nodeSelector = mk.pop("nodeSelector", None)
    tolerations = mk.pop("tolerations", None)
    imagePullSecrets = mk.pop("imagePullSecrets", None)
    serviceAccountName = mk.pop("serviceAccountName", None)
    volumes = mk.pop("volumes", None)
    volumeMounts = mk.pop("volumeMounts", None)

    # --- Auto-add hostPath volumes/mounts for mk./map. (RW default) ---
    auto = self._auto_mounts_from_vars() if getattr(self, "automated_mount", True) else []

    def _vol_name(path):
        base = os.path.basename(path) or "root"
        safe = re.sub(r'[^a-z0-9\-]+', '-', base.lower())
        return f"jawm-vol-{safe}"[:63]

    auto_vols, auto_mounts = [], []
    for m in auto:
        name = _vol_name(m["src"])
        vtype = "DirectoryOrCreate" if m["kind"] == "mk" else "Directory"
        auto_vols.append({"name": name, "hostPath": {"path": m["src"], "type": vtype}})
        auto_mounts.append({"name": name, "mountPath": m["dst"]})  # RW default

    def _merge_vols(existing, extras):
        existing = existing or []
        seen = {(v.get("name"), (v.get("hostPath") or {}).get("path")) for v in existing}
        for v in extras:
            key = (v.get("name"), (v.get("hostPath") or {}).get("path"))
            if key not in seen:
                existing.append(v); seen.add(key)
        return existing

    def _merge_mounts(existing, extras):
        existing = existing or []
        seen = {(m.get("name"), m.get("mountPath")) for m in existing}
        for mm in extras:
            key = (mm.get("name"), mm.get("mountPath"))
            if key not in seen:
                existing.append(mm); seen.add(key)
        return existing

    volumeMounts = _merge_mounts(volumeMounts, auto_mounts)
    volumes = _merge_vols(volumes, auto_vols)

    activeDeadlineSeconds = mk.pop("activeDeadlineSeconds", None)
    labels_extra = mk.pop("labels", {})
    annotations = mk.pop("annotations", None)

    if isinstance(imagePullSecrets, str):
        imagePullSecrets = [{"name": imagePullSecrets}]
    elif isinstance(imagePullSecrets, list) and imagePullSecrets and isinstance(imagePullSecrets[0], str):
        imagePullSecrets = [{"name": n} for n in imagePullSecrets]

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

    if attempt_i is not None:
        labels_block["jawm-attempt"] = str(attempt_i)

    # ConfigMap-backed script
    script_cm_name = self._k8s_sanitize_label(
        f"{self.name}-{self.hash}-script",
        max_len=63,
        fallback_suffix="jawm-script"
    )

    configmap = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": script_cm_name,
            "labels": labels_block,
            **({"annotations": annotations} if annotations else {})
        },
        "data": {
            "script": core_script
        }
    }

    # Add ConfigMap volume + mount
    script_volume = {
        "name": "jawm-script",
        "configMap": {
            "name": script_cm_name,
            "defaultMode": 0o755
        }
    }
    script_mount = {
        "name": "jawm-script",
        "mountPath": "/jawm",
        "readOnly": True
    }

    volumeMounts = _merge_mounts(volumeMounts, [script_mount])
    volumes = _merge_vols(volumes, [script_volume])

    # 1) Prepare the in-container command (now executes /jawm/script)
    cmd_parts = []

    # Optional host-level pre-hook (executed inside container in current design)
    if self.before_script:
        cmd_parts.append(self.before_script.strip())

    # Container-level pre-hook
    if self.container_before_script:
        cmd_parts.append(self.container_before_script.strip())

    # Execute the mounted script (shebang respected)
    cmd_parts.append("/jawm/script")

    # Container-level post-hook
    if self.container_after_script:
        cmd_parts.append(self.container_after_script.strip())

    # Optional host-level post-hook (executed inside container in current design)
    if self.after_script:
        cmd_parts.append(self.after_script.strip())

    # Compose final strings for each shell
    cmd_core = " && ".join(cmd_parts) if cmd_parts else "/jawm/script"
    cmd_str_bash = f"set -euo pipefail && {cmd_core}"  # bash supports pipefail
    cmd_str_sh   = f"set -eu && {cmd_core}"            # sh does not; no -l here

    # Prefer bash if present; otherwise fallback to sh
    container_command = [
        "/bin/sh", "-c",
        f'[ -x /bin/bash ] && exec /bin/bash -lc {shlex.quote(cmd_str_bash)} '
        f'|| exec /bin/sh -c {shlex.quote(cmd_str_sh)}'
    ]

    # 5) Build the Job manifest (unchanged structure; only command/volumes/mounts changed)
    job = {
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

    # Write a single file containing both ConfigMap + Job
    manifest = {
        "apiVersion": "v1",
        "kind": "List",
        "items": [configmap, job]
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # stash for submit/monitor steps
    self._k8s_namespace = namespace
    self._k8s_job_name = job_name
    self._k8s_container_name = container_name
    self._k8s_script_cm_name = script_cm_name
    return manifest_path


@register
def _execute_kubernetes(self):
    """
    Submit as a K8s Job via kubectl, then monitor until completion.
    Writes .id (job name), .exitcode, and .command, and updates monitoring files.
    """
    try:
        self.logger.info(f"Launching process {self.name} using Kubernetes executor")
        self.logger.info(f"Log folder for process {self.name}: {self.log_path}")

        exitcode_path = os.path.join(self.log_path, f"{self.name}.exitcode")
        id_path = os.path.join(self.log_path, f"{self.name}.id")
        command_path = os.path.join(self.log_path, f"{self.name}.command")

        def run_once(attempt_i, total_attempts):
            # Delete previous attempt artifacts first (applicable for retry)
            if attempt_i != 1:
                prev_job = getattr(self, "_k8s_job_name", None)
                prev_cm  = getattr(self, "_k8s_script_cm_name", None)
                prev_ns  = getattr(self, "_k8s_namespace", None)

                if prev_job:
                    del_cmd = ["kubectl", "delete", "job", prev_job, "--ignore-not-found=true", "--wait=true"]
                    if prev_ns:
                        del_cmd += ["-n", prev_ns]
                    subprocess.run(del_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if prev_cm:
                    del_cm_cmd = ["kubectl", "delete", "configmap", prev_cm, "--ignore-not-found=true"]
                    if prev_ns:
                        del_cm_cmd += ["-n", prev_ns]
                    subprocess.run(del_cm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            manifest_path = self._generate_k8s_manifest(attempt_i=attempt_i)

            # kubectl apply
            cmd = ["kubectl", "apply", "-f", manifest_path]
            if getattr(self, "_k8s_namespace", None):
                cmd.extend(["-n", self._k8s_namespace])
            self._safe_write_file(command_path, " ".join(shlex.quote(c) for c in cmd))
            self.logger.info(f"Submitting process {self.name} with K8s command: {' '.join(cmd)}")
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            # log apply output
            apply_log = os.path.join(self.log_path, f"{self.name}.kubectl_apply.log")
            self._safe_write_file(apply_log, (res.stdout or "") + (("\n" + res.stderr) if res.stderr else ""))
            if res.returncode != 0:
                self._log_error_summary(self._tail_text(res.stderr), type_text="K8sKubectl")
                self.logger.error(f"kubectl apply failed: {res.stderr.strip()}{self._elog_path()}")
                return 127

            # Record job "id" as job name
            job_id = getattr(self, "_k8s_job_name", None)
            self.runtime_id = job_id
            self._safe_write_file(id_path, job_id or "")
            self._monitoring_running_file(job_id, manifest_path)

            # Poll job status; once finished, fetch pod exit code + logs
            def _kubectl(args, expect_success=True):
                base = ["kubectl"]
                if getattr(self, "_k8s_namespace", None):
                    base += ["-n", self._k8s_namespace]
                full_cmd = base + args

                res2 = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if expect_success and (res2.returncode != 0 or res2.stderr.strip()):
                    msg = (
                        f"kubectl command failed (rc={res2.returncode}): "
                        f"{' '.join(full_cmd)}\n"
                        f"STDERR: {self._tail_text(res2.stderr)}"
                    )
                    self.logger.error(f"{msg}{self._elog_path()}")
                    self._log_error_summary(msg, type_text="K8sKubectl")

                return res2

            exit_code_int = 1
            elapsed_time = 0
            last_pod_name = None
            selected_container = getattr(self, "_k8s_container_name", None)

            # -Periodic log append using --since (best-effort) ---
            # default 60s; can be overridden with env var JAWM_K8S_LOG_OUTPUT_INTERVAL
            last_log_pull_ts = 0
            try:
                log_since_sec = max(20, int(os.environ.get("JAWM_K8S_LOG_OUTPUT_INTERVAL", "60")))
                since_window_sec = log_since_sec + 2
            except Exception:
                log_since_sec = 60
                since_window_sec = 62

            # Ensure output file exists (do not truncate; keep behavior minimal)
            try:
                if not os.path.exists(self.stdout_path):
                    open(self.stdout_path, "w").close()
            except Exception:
                pass

            # Startup watchdog to avoid hanging forever in Pending/ContainerCreating ---
            try:
                pod_create_timeout_sec = int(os.environ.get("JAWM_K8S_POD_CREATE_TIMEOUT", "300"))  # 5 min default
            except Exception:
                pod_create_timeout_sec = 300
            
            try:
                pod_start_timeout_sec = int(os.environ.get("JAWM_K8S_POD_START_TIMEOUT", "1200"))  # 20 min default
            except Exception:
                pod_start_timeout_sec = 1200

            first_seen_pod_ts = None
            pending_since_ts = None
            last_seen_pod_uid = None
            start_watchdog_ts = time.time()

            # Reasons that are almost always "won't recover without intervention"
            TERMINAL_WAITING_REASONS = {
                "ErrImagePull",
                "ImagePullBackOff",
                "CreateContainerConfigError",
                "CreateContainerError",
                "RunContainerError",
                "InvalidImageName",
                "CrashLoopBackOff",
            }

            while True:
                sel = f"job-name={job_id}"
                if attempt_i is not None:
                    sel += f",jawm-attempt={attempt_i}"
                pods = _kubectl(["get", "pods", "-l", sel, "-o", "json"])
                if pods.returncode == 0:
                    try:
                        data = json.loads(pods.stdout)
                        items = data.get("items", [])

                        # bail out fast if user killed the job
                        if getattr(self, "_k8s_killed", False):
                            exit_code_int = 130  # synthetic "killed"
                            break

                        # If job never creates a pod, don't hang forever ---
                        now = time.time()
                        if not items:
                            if start_watchdog_ts is not None and (now - start_watchdog_ts) >= pod_create_timeout_sec:
                                msg = f"K8s pod was not created within {pod_create_timeout_sec}s for job={job_id}"
                                self.logger.error(f"{msg}{self._elog_path()}")
                                self._log_error_summary(msg, type_text="K8sStartup")

                                # Optional: capture a bit more context (best-effort, cheap)
                                try:
                                    # job describe often shows admission/quota/forbidden reasons
                                    jdesc = _kubectl(["describe", "job", job_id], expect_success=False)
                                    try:
                                        with open(self.stderr_path, "a") as f:
                                            f.write("\n\n=== kubectl describe job (no pod created) ===\n")
                                            f.write(jdesc.stdout or jdesc.stderr or "")
                                    except Exception:
                                        pass
                                except Exception:
                                    pass

                                exit_code_int = 1
                                break

                            # keep waiting
                            time.sleep(10)
                            elapsed_time += 10
                            continue

                        if items:
                            # pick the newest pod if multiple (e.g., retries)
                            start_watchdog_ts = None
                            items.sort(
                                key=lambda i: i.get("metadata", {}).get("creationTimestamp", ""),
                                reverse=True
                            )
                            pod = items[0]
                            last_pod_name = pod["metadata"]["name"]
                            phase = pod.get("status", {}).get("phase")
                            now = time.time()

                            # Watchdog bookkeeping (handles "stuck ContainerCreating/Pending") ---
                            pod_uid = pod.get("metadata", {}).get("uid")
                            if first_seen_pod_ts is None:
                                first_seen_pod_ts = now

                            # If we switched to a different pod (rare but possible), reset pending timers
                            if pod_uid and pod_uid != last_seen_pod_uid:
                                last_seen_pod_uid = pod_uid
                                pending_since_ts = None

                            # Detect "waiting reason" (image pull/mount/etc.) without needing describe
                            waiting_reason = None
                            waiting_message = None
                            try:
                                sts = pod.get("status", {}).get("containerStatuses", []) or []
                                for cs in sts:
                                    st = (cs.get("state") or {})
                                    if "waiting" in st:
                                        waiting_reason = st["waiting"].get("reason")
                                        waiting_message = st["waiting"].get("message")
                                        break
                            except Exception:
                                pass

                            # Also catch FailedMount via events (describe) only when needed.
                            # We only do describe if we're stuck long enough OR reason looks terminal.
                            is_non_terminal = phase not in {"Succeeded", "Failed"}
                            if is_non_terminal:
                                if pending_since_ts is None:
                                    pending_since_ts = now

                                # Fast-fail on terminal waiting reasons
                                if waiting_reason in TERMINAL_WAITING_REASONS:
                                    try:
                                        desc = _kubectl(["describe", "pod", last_pod_name], expect_success=False)
                                        try:
                                            with open(self.stderr_path, "a") as f:
                                                f.write("\n\n=== kubectl describe pod (startup failure) ===\n")
                                                f.write(desc.stdout or desc.stderr or "")
                                        except Exception:
                                            pass
                                        self._log_error_summary(
                                            f"K8s pod startup failed: pod={last_pod_name} reason={waiting_reason} msg={waiting_message or 'NA'}",
                                            type_text="K8sStartup"
                                        )
                                    except Exception:
                                        pass
                                    exit_code_int = 1
                                    break

                                # Timeout if stuck too long
                                if pending_since_ts and (now - pending_since_ts) >= pod_start_timeout_sec:
                                    # Describe gives the real reason (e.g., FailedMount)
                                    try:
                                        desc = _kubectl(["describe", "pod", last_pod_name], expect_success=False)
                                        try:
                                            with open(self.stderr_path, "a") as f:
                                                f.write("\n\n=== kubectl describe pod (startup timeout) ===\n")
                                                f.write(desc.stdout or desc.stderr or "")
                                        except Exception:
                                            pass
                                        self._log_error_summary(
                                            f"K8s pod startup timeout after {pod_start_timeout_sec}s: pod={last_pod_name} phase={phase} reason={waiting_reason or 'NA'}",
                                            type_text="K8sStartup"
                                        )
                                    except Exception:
                                        pass
                                    exit_code_int = 1
                                    break

                            # --- Existing: periodic log append while running (best-effort) ---
                            if (
                                last_pod_name
                                and phase not in {"Succeeded", "Failed"}
                                and (now - last_log_pull_ts) >= log_since_sec
                            ):
                                last_log_pull_ts = now
                                try:
                                    lres = _kubectl(
                                        ["logs", last_pod_name, f"--since={since_window_sec}s"],
                                        expect_success=False
                                    )
                                    if lres.stdout:
                                        with open(self.stdout_path, "a") as f:
                                            f.write(lres.stdout)
                                            f.flush()
                                except Exception:
                                    pass

                            # Terminal handling (Succeeded/Failed) ---
                            if phase in {"Succeeded", "Failed"}:
                                logs_args = ["logs", last_pod_name]
                                try:
                                    containers = pod.get("spec", {}).get("containers", []) or []
                                    if selected_container:
                                        if any(c.get("name") == selected_container for c in containers):
                                            logs_args += ["-c", selected_container]
                                        elif len(containers) == 1:
                                            pass
                                        else:
                                            logs_args += ["-c", containers[0].get("name")]
                                    else:
                                        if len(containers) == 1:
                                            pass
                                        elif len(containers) > 1:
                                            logs_args += ["-c", containers[0].get("name")]
                                except Exception:
                                    pass

                                out = _kubectl(logs_args)

                                try:
                                    self._safe_write_file(self.stdout_path, out.stdout or "")
                                except Exception:
                                    pass
                                if out.returncode != 0 or (out.stderr and out.stderr.strip()):
                                    try:
                                        self._safe_write_file(self.stderr_path, out.stderr or "")
                                    except Exception:
                                        pass

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

                                state_txt = "succeeded" if exit_code_int == 0 else "failed"
                                self.logger.info(
                                    f"[K8s] Job {job_id} {state_txt} (pod={last_pod_name}, exit={exit_code_int})"
                                )

                                if exit_code_int != 0 and last_pod_name:
                                    try:
                                        desc = _kubectl(["describe", "pod", last_pod_name])
                                        with open(self.stderr_path, "a") as f:
                                            f.write("\n\n=== kubectl describe pod ===\n")
                                            f.write(desc.stdout or desc.stderr or "")
                                    except Exception:
                                        pass

                                if exit_code_int != 0:
                                    try:
                                        term = ((chosen or {}).get("state", {}) or {}).get("terminated", {}) or {}
                                        pod_status = (pod.get("status", {}) or {})
                                        msg_raw = (term.get("message") or pod_status.get("message") or "").strip()
                                        if not msg_raw:
                                            try:
                                                last_lines = "\n".join((out.stdout or "").splitlines()[-5:])
                                                msg_raw = f"Last log lines: {last_lines}" if last_lines.strip() else "NA"
                                            except Exception:
                                                msg_raw = "NA"

                                        summary = (
                                            f"K8s job failed: "
                                            f"pod={last_pod_name} "
                                            f"phase={pod_status.get('phase')} "
                                            f"reason={term.get('reason') or pod_status.get('reason') or 'NA '} "
                                            f"exit={term.get('exitCode') if term.get('exitCode') is not None else 'NA '} "
                                            f"msg={msg_raw} "
                                            f"description={self.stderr_path or 'NA '} "
                                        )
                                        self._log_error_summary(summary, type_text="K8sAttempt")
                                    except Exception:
                                        self._log_error_summary(
                                            f"K8s job failed (could not build failure summary! records on: {self.stderr_path})",
                                            type_text="K8sAttempt",
                                        )

                                break
                    except Exception:
                        pass

                time.sleep(10)
                elapsed_time += 10
                if elapsed_time % 600 == 0:
                    self.logger.info(f"Process {self.name} (K8s job: {job_id}) is still running...")

            # Write exit code files and monitoring move
            try:
                self._safe_write_file(exitcode_path, str(exit_code_int))
            except Exception:
                pass

            # Ensure stdout/stderr files exist even if container produced nothing
            try:
                if not os.path.exists(self.stdout_path):
                    open(self.stdout_path, "w").close()
                if not os.path.exists(self.stderr_path):
                    open(self.stderr_path, "w").close()
            except Exception:
                pass

            # Best/loose effort FS settle check & finish wait
            self._finish_wait_and_settle(env_flag="JAWM_KUBERNETES_FINISH_WAIT", default_wait=0.0, check_stability=False)

            self.logger.info(f"K8s job {job_id} completed with exit code {exit_code_int}")
            self._monitoring_completed_file(job_id, manifest_path, exit_code_int)

            # Best-effort cleanup of script ConfigMap
            cm = getattr(self, "_k8s_script_cm_name", None)
            if cm:
                del_cm_cmd = ["kubectl", "delete", "configmap", cm, "--ignore-not-found=true"]
                if getattr(self, "_k8s_namespace", None):
                    del_cm_cmd.extend(["-n", self._k8s_namespace])
                subprocess.run(del_cm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            return 0 if exit_code_int == 0 else 1

        def monitor_process():
            try:
                total_attempts = self.retries + 1
                for attempt_i in range(1, total_attempts + 1):
                    self._apply_retry_parameters(attempt_i - 1)
                    rc = run_once(attempt_i, total_attempts)
                    if rc == 0:
                        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                        self.finished_event.set()
                        return
                    self.logger.error(f"K8s attempt {attempt_i}/{total_attempts} failed! Summary can be found in: {self.error_summary_file}{self._elog_path()}")
                    if attempt_i < total_attempts:
                        self.logger.info(f"Retrying K8s job; {total_attempts - attempt_i} retries left")
                    else:
                        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
                        self.finished_event.set()
                        self.stop_future_event.set()
                        self._log_error_summary(f"Process in K8s failed.{self._tail_error()}", type_text="K8sAttempt")
                        self.logger.error(f"Process {self.name} in K8s failed after {total_attempts} attempt(s){self._elog_path()}{self._tail_error()}")
                        return
            except Exception as e:
                self._proc_exception_handler(e, location="monitoring", type_text="K8sError")
                return
            finally:
                try:
                    if not self.finished_event.is_set():
                        self.finished_event.set()
                except Exception:
                    pass

        self._monitor_thread = threading.Thread(target=monitor_process, daemon=False)
        self._monitor_thread.start()
        return None
    except Exception as e:
        self.logger.error(f"Failed launching process {self.name} in K8s: {str(e)}{self._elog_path()}")
        self.execution_end_at = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.finished_event.set()
        self.stop_future_event.set()
        # Best-effort: move Running -> Completed only if a running marker exists
        try:
            job_id = getattr(self, "_k8s_job_name", None)
            if job_id and getattr(self, "running_directory", None) and getattr(self, "completed_directory", None):
                running_file_path = os.path.join(self.running_directory, f"{self.manager}.{job_id}.txt")
                if os.path.exists(running_file_path):
                    script_path = os.path.join(self.log_path, f"{self.name}.k8s.json")
                    self._monitoring_completed_file(job_id, script_path, 1)
        except Exception:
            pass
        return

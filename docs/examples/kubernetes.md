# Kubernetes

This is a small demonstration of running a JAWM process on a Kubernetes cluster with data staged through a shared PersistentVolumeClaim (PVC). The example loads a FASTQ file into Kubernetes storage and then launches a FastQC process through JAWM using the same PVC.

The workflow has three parts:

1. Create a Kubernetes namespace and shared data volume.
2. Start a temporary loader pod and copy input data into the shared volume.
3. Run `kube_jawm_demo.py`, which asks JAWM to create a Kubernetes FastQC job in the same namespace with the shared PVC mounted at `/data`.

## Files list

| Path | Purpose |
| --- | --- |
| `jawm-data-pvc.yaml` | Defines the shared Kubernetes PVC named `jawm-data`. |
| `volume-loader.yaml` | Defines a temporary BusyBox pod used to copy files into the PVC. |
| `kube_jawm_demo.py` | Defines and executes the JAWM FastQC process. |
| `fastqc_demo.py` | Optional split version containing only the reusable FastQC process definition. |
| `k8.yaml` | Optional split version containing the Kubernetes backend, PVC mount, and demo variables. |

## Prerequisites

You need access to a Kubernetes cluster and a kubeconfig file that can create namespaces, PVCs, pods, config maps, and jobs.

Required local tools:

- `kubectl`
- Python with the `jawm` package available
- A Kubernetes storage class named `nfs-client`, or an edited PVC manifest that uses a storage class available in your cluster

The commands below assume the kubeconfig is at `~/kube.config`.

## Files to Create Before Running Commands

Create these files in the repository before running the workflow commands below.

```
touch jawm-data-pvc.yaml volume-loader.yaml kube_jawm_demo.py
```

### `jawm-data-pvc.yaml`

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: jawm-data
  namespace: jawm-test
spec:
  storageClassName: nfs-client
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 10Gi
```

### `volume-loader.yaml`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: volume-loader
  namespace: jawm-test
spec:
  restartPolicy: Never
  containers:
    - name: loader
      image: busybox:1.36
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: jawm-data
```

### `kube_jawm_demo.py`

```python
import jawm

# Define the process.
fastqc = jawm.Process(

    # Process name
    name="fastqc",

    # Script to run when the process is executed
    script="""#!/bin/bash
fastqc {{extra_args}} -t {{cpus}} -o {{fastqc_output}} {{f}}
""",

    # Variable descriptions
    desc={
        "extra_args": "Any FastQC argument with its respective value.",
        "cpus": "Number of CPUs to use.",
        "fastqc_output": "Output directory.",
        "f": "Input FASTQ file.",
    },

    var={
        "extra_args": "",
        "cpus": 1,
        "mk.fastqc_output": "/data/fastqc_output",
        "map.f": "/data/raw_data/my_test_file_1.fastq.gz",
    },

    container="mpgagebioinformatics/fastqc:0.11.9",
    manager="kubernetes",
    manager_kubernetes={
        "namespace": "jawm-test",
        "volumes": [{
            "name": "data",
            "persistentVolumeClaim": {
                "claimName": "jawm-data",
            },
        }],
        "volumeMounts": [{
            "name": "data",
            "mountPath": "/data",
        }],
    },
)

fastqc.execute()
jawm.Process.wait()
```

## 1. Configure Kubernetes Access

```bash
export KUBECONFIG="$(readlink -f ~/kube.config)"
```

## 2. Create the Namespace and Shared Volume

Create the namespace used by the demo:

```bash
kubectl create namespace jawm-test
```

Create the PVC from `jawm-data-pvc.yaml`:

```bash
kubectl apply -f jawm-data-pvc.yaml
```

Confirm that the PVC is bound:

```bash
kubectl -n jawm-test get pvc jawm-data
```

The PVC requests 10 GiB of shared `ReadWriteMany` storage from the `nfs-client` storage class.

## 3. Start the Loader Pod

The loader pod is a simple BusyBox pod that mounts the PVC at `/data` and sleeps for one hour. It exists only so files can be copied into the PVC with `kubectl cp`.

Create the loader pod from `volume-loader.yaml`:

```bash
kubectl apply -f volume-loader.yaml
```

Wait for the pod to become ready:

```bash
kubectl \
  -n jawm-test wait \
  --for=condition=Ready pod/volume-loader \
  --timeout=120s
```

The `--timeout=120s` value only limits how long `kubectl wait` waits for readiness. It does not kill the loader pod after 120 seconds.

## 4. Copy Input Data into the PVC

As an example, download the test data to your local machine first:

```bash
mkdir -p raw_data
wget -O ./raw_data/my_test_file_1.fastq.gz https://ndownloader.figshare.com/files/57999445
```

Copy the example `raw_data` directory into `/data` on the shared volume:

```bash
kubectl \
  -n jawm-test cp \
  ./raw_data volume-loader:/data/
```

List the copied files:

```bash
kubectl \
  -n jawm-test exec volume-loader -- \
  find /data/raw_data -maxdepth 3 -type f
```

You can also copy a single FASTQ file to the PVC root:

```bash
kubectl \
  -n jawm-test cp \
  ./my_test_file_1.fastq.gz volume-loader:/data/my_test_file_1.fastq.gz
```

Inspect the volume contents:

```bash
kubectl \
  -n jawm-test exec volume-loader -- ls -lah /data
```

## 5. Run the JAWM FastQC Demo

Run the Python script from this repository:

```bash
jawm kube_jawm_demo.py
```

The script defines a `jawm.Process` named `fastqc`. It runs in the `jawm-test` namespace using the `mpgagebioinformatics/fastqc:0.11.9` image, mounts the `jawm-data` PVC at `/data`, and uses `mk.fastqc_output` so JAWM creates `/data/fastqc_output` before running FastQC. The `map.f` value points JAWM at the input FASTQ under `/data/raw_data/`. The rendered FastQC command is:

```bash
fastqc  -t 1 -o /data/fastqc_output /data/raw_data/my_test_file_1.fastq.gz
```

JAWM writes run artifacts under `logs/fastqc_<timestamp>_<hash>/`, including:

- `fastqc.command`: the `kubectl apply` command used by JAWM
- `fastqc.k8s.json`: the generated Kubernetes ConfigMap and Job manifest
- `fastqc.script`: the rendered process script run inside the container
- `fastqc.output`: captured standard output
- `fastqc.error`: captured error output and Kubernetes diagnostic details
- `fastqc.exitcode`: the process exit code
- `fastqc.id`: the JAWM run identifier

## 6. Split the Demo into `fastqc_demo.py` and `k8.yaml`

The single-file `kube_jawm_demo.py` is convenient for a self-contained example, but it mixes two concerns:

- the reusable FastQC process definition—what command JAWM runs
- the Kubernetes configuration—where and how JAWM runs it

You can separate those concerns into a Python module and a parameter file. Create both files:

```bash
touch fastqc_demo.py k8.yaml
```

### `fastqc_demo.py`

Keep the process name, script, variable descriptions, and container image in Python:

```python
import jawm

fastqc = jawm.Process(
    name="fastqc",
    script="""#!/bin/bash
fastqc {{extra_args}} -t {{cpus}} -o {{fastqc_output}} {{f}}
""",
    desc={
        "extra_args": "Any FastQC argument with its respective value.",
        "cpus": "Number of CPUs to use.",
        "fastqc_output": "Output directory.",
        "f": "Input FASTQ file.",
    },
    container="mpgagebioinformatics/fastqc:0.11.9",
)

fastqc.execute()
jawm.Process.wait()
```

This file is backend-independent: it describes the FastQC task but does not select Kubernetes or hard-code a cluster namespace and volume.

### `k8.yaml`

Put the backend-specific settings and the values for this run in a process-scoped parameter block:

```yaml
- scope: process
  name: fastqc
  manager: kubernetes
  manager_kubernetes:
    namespace: jawm-test
    volumes:
      - name: data
        persistentVolumeClaim:
          claimName: jawm-data
    volumeMounts:
      - name: data
        mountPath: /data
  var:
    extra_args: ""
    cpus: 1
    mk.fastqc_output: /data/fastqc_output
    map.f: /data/raw_data/my_test_file_1.fastq.gz
```

The `name: fastqc` entry targets the `jawm.Process` with the same name. `manager` selects the Kubernetes backend, while `manager_kubernetes` supplies the namespace and PVC mount. The `var` mapping provides the values substituted into the FastQC script; the `mk.` prefix asks JAWM to create the output directory, and `map.` identifies the staged input path.

Run the split version by passing the YAML file as a parameter file:

```bash
jawm fastqc_demo.py -p k8.yaml
```

This produces the same Kubernetes FastQC job as `jawm kube_jawm_demo.py`. The advantage is that `fastqc_demo.py` can be reused with another parameter file—for example, a local Docker or Slurm configuration—without editing the process definition.

## 7. Copy Generated Data Out of the PVC

FastQC writes the generated report files into the PVC at `/data/fastqc_output`. Use the loader pod to inspect and copy those files back to your local machine before cleanup.

List the generated FastQC files:

```bash
kubectl \
  -n jawm-test exec volume-loader -- \
  find /data/fastqc_output -maxdepth 1 -type f \
    \( -name '*_fastqc.html' -o -name '*_fastqc.zip' \)
```

Create a local output directory:

```bash
mkdir -p fastqc_results
```

Copy the whole FastQC output directory out of the PVC:

```bash
kubectl \
  -n jawm-test cp \
  volume-loader:/data/fastqc_output \
  ./fastqc_results/fastqc_output
```

If the loader pod has already exited because its one-hour sleep finished, recreate it before copying files out:

```bash
kubectl -n jawm-test delete pod volume-loader
kubectl apply -f volume-loader.yaml
kubectl \
  -n jawm-test wait \
  --for=condition=Ready pod/volume-loader \
  --timeout=120s
```

## 8. Cleanup

Remove the temporary loader pod when you no longer need to copy files into or out of the PVC:

```bash
kubectl -n jawm-test delete pod volume-loader
```

The PVC remains after deleting the loader pod. Delete it only if you no longer need the staged data:

```bash
kubectl -n jawm-test delete pvc jawm-data
```

Delete the namespace only when the whole demo environment can be removed:

```bash
kubectl delete namespace jawm-test
```

## Mounting the PVC in Another Kubernetes Workload

Any Kubernetes workload that needs the staged data can mount the same PVC. The important part is that the volume references `claimName: jawm-data`, and the container mounts that volume at the desired path.

```yaml
spec:
  containers:
    - name: app
      image: your-image:tag
      volumeMounts:
        - name: data
          mountPath: /data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: jawm-data
```

## Troubleshooting Notes

Some older logs in this repository show failed FastQC runs with exit code `127` and this message:

```text
/.jawm/script: line 2: fastqc: command not found
```

That means the container started, but the executable `fastqc` was not available on `PATH` inside the image used by the generated job.

The current `kube_jawm_demo.py` configures JAWM to run the generated Kubernetes resources in `jawm-test` and mount the `jawm-data` PVC at `/data`. JAWM also creates an internal `emptyDir` workspace at `/work` for run bookkeeping.

Useful checks:

```bash
kubectl -n jawm-test get pods,pvc,jobs
kubectl -n jawm-test describe pvc jawm-data
kubectl get jobs --all-namespaces | grep fastqc
```

## Representative Generated Artifacts

These files are generated after running `kube_jawm_demo.py`; they are included here as examples of what JAWM produces with the current process variables.

### `fastqc.script`

The rendered process script should look like this:

```bash
#!/bin/bash
fastqc  -t 1 -o /data/fastqc_output /data/raw_data/my_test_file_1.fastq.gz
```

### `fastqc.command`

The generated command applies the JAWM Kubernetes manifest in the `jawm-test` namespace:

```bash
kubectl apply -f logs/fastqc_<timestamp>_<hash>/fastqc.k8s.json -n jawm-test
```

### `fastqc.k8s.json`

JAWM generates a Kubernetes `List` containing a `ConfigMap` for the rendered script and a `batch/v1` `Job` that runs the process container. The generated Job should include the `jawm-data` PVC mounted at `/data`, plus JAWM's internal workspace at `/work`.

```json
{
  "apiVersion": "v1",
  "kind": "List",
  "items": [
    {
      "apiVersion": "v1",
      "kind": "ConfigMap",
      "metadata": {
        "namespace": "jawm-test"
      },
      "data": {
        "script": "#!/bin/bash\nfastqc  -t 1 -o /data/fastqc_output /data/raw_data/my_test_file_1.fastq.gz\n"
      }
    },
    {
      "apiVersion": "batch/v1",
      "kind": "Job",
      "metadata": {
        "namespace": "jawm-test"
      },
      "spec": {
        "template": {
          "spec": {
            "containers": [
              {
                "image": "mpgagebioinformatics/fastqc:0.11.9",
                "volumeMounts": [
                  {
                    "name": "data",
                    "mountPath": "/data"
                  },
                  {
                    "name": "jawm-ed-workspace",
                    "mountPath": "/work"
                  }
                ]
              }
            ],
            "volumes": [
              {
                "name": "data",
                "persistentVolumeClaim": {
                  "claimName": "jawm-data"
                }
              },
              {
                "name": "jawm-ed-workspace",
                "emptyDir": {}
              }
            ]
          }
        }
      }
    }
  ]
}
```

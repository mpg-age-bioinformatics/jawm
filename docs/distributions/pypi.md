# Python Package (PyPI)

The official jawm Python package is available from [PyPI](https://pypi.org/project/jawm/) and supports Python 3.8 or newer.

## Install

Install the latest published release:

```bash
pip install jawm
```

Install jawm with the optional data-processing dependencies:

```bash
pip install "jawm[full]"
```

## Choose a Release

Install a specific release when you need a reproducible environment:

```bash
pip install "jawm==0.1.1"
```

Upgrade an existing installation to the latest release:

```bash
pip install --upgrade jawm
```

Available package versions are listed in the [PyPI release history](https://pypi.org/project/jawm/#history). Corresponding release notes are maintained on [GitHub](https://github.com/mpg-age-bioinformatics/jawm/releases).

## Included Commands

The package installs the following command-line tools:

| Command | Purpose |
|---|---|
| `jawm` | Run local or remote workflow modules. |
| `jawm-dev` | Create, inspect and develop modules. |
| `jawm-monitor` | Monitor active and completed processes. |
| `jawm-test` | Run structured module tests and verify output hashes. |

Verify the installed package and command:

```bash
python -m pip show jawm
jawm --version
```

For development-version installation, optional dependencies and troubleshooting, see the full [installation guide](../get_started/install.md).

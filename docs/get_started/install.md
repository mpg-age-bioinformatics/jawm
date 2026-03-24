# Installation

jawm can be installed directly from the Git repository.

```bash
pip install "git+ssh://git@github.com/mpg-age-bioinformatics/jawm.git"
```

This installs the core jawm package.

---

**Installation with Optional Dependencies**

If you also want optional dependencies such as `pandas` and `openpyxl`, install jawm with the `full` extra:

```bash
pip install "jawm[full] @ git+ssh://git@github.com/mpg-age-bioinformatics/jawm.git"
```

This is useful if your workflows or helper utilities rely on additional data-processing features.

---

**Useful Installation Variants**

To avoid unnecessary dependency upgrades during installation:

```bash
pip install --upgrade-strategy only-if-needed "git+ssh://git@github.com/mpg-age-bioinformatics/jawm.git"
```

If you do not have permission to write to the system site-packages directory, install for your user only:

```bash
pip install --user "git+ssh://git@github.com/mpg-age-bioinformatics/jawm.git"
```

These options can also be combined if needed.

---

**Notes**

- Installing `jawm[full]` may fail on some systems because it pulls in packages such as `pandas`, which may require native compilation when prebuilt wheels are not available.
- If you run into installation issues, try upgrading packaging tools first: `python -m pip install -U pip setuptools wheel`

---

**Verify Installation**

After installation, you can verify that jawm is available by running:

```bash
python -c "import jawm; print(jawm)"
```

If the installation was successful, Python will import the package without error.

You can also check whether the `jawm` command is available:

```bash
jawm --help
```

---
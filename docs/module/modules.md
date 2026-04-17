# Available Workflow Modules

jawm modules are ordinary Python files — anyone can write one, publish it to a Git repository, and share it with the world. The pattern is open: if you build a module for your own work, it can just as easily be used by someone else.

This page lists modules published by [mpg-age-bioinformatics](https://github.com/mpg-age-bioinformatics) — the group behind jawm — as a reference set of real-world examples. They cover common bioinformatics workflows and are freely available to use, fork, and adapt.

---

### Modules by mpg-age-bioinformatics

<!-- JAWM_MODULES_LIST -->
The module list could not be retrieved at build time. Browse all available modules directly at:
[github.com/mpg-age-bioinformatics?q=jawm_](https://github.com/mpg-age-bioinformatics?q=jawm_&type=all)
<!-- /JAWM_MODULES_LIST -->

### Publishing your own module

If you write a module and want to make it discoverable:

1. Prefix the repository name with `jawm_` (e.g. `jawm_mymodule`) — this is a community convention, not a requirement
2. Push to any public Git host (GitHub, GitLab, Gitea, self-hosted)
3. Tag releases with semantic versioning (`v1.0.0`, `v1.1.0`, …) so consumers can pin to a version

That's all — there's no central registry. Modules are discovered by name on Git servers, just like any other Git repository. See [Develop a Module](develop.md) for how to write and test one from scratch.

---
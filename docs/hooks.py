"""
MkDocs build hooks for jawm documentation.

on_page_markdown:
  - modules.md: replaces the JAWM_MODULES_LIST placeholder with a live
    table of jawm_ repositories fetched from the GitHub API at build time.
"""

import urllib.request
import urllib.error
import json
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger("mkdocs.hooks")

_ORG = "mpg-age-bioinformatics"
_SEARCH_URL = (
    "https://api.github.com/search/repositories"
    f"?q=jawm_+org%3A{_ORG}&sort=updated&per_page=100"
)
_FALLBACK = (
    "The module list could not be retrieved at build time. "
    "Browse all available modules directly at:\n"
    f"[github.com/{_ORG}?q=jawm_](https://github.com/{_ORG}?q=jawm_&type=all)"
)

_PLACEHOLDER_RE = re.compile(
    r"<!-- JAWM_MODULES_LIST -->.*?<!-- /JAWM_MODULES_LIST -->",
    re.DOTALL,
)


def _fetch_modules() -> str:
    """Fetch jawm_ repos from GitHub and return a markdown table, or fallback text."""
    try:
        req = urllib.request.Request(
            _SEARCH_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "jawm-docs-build",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning(f"[jawm hooks] Could not fetch module list from GitHub: {e}")
        return _FALLBACK

    repos = data.get("items", [])
    if not repos:
        log.warning("[jawm hooks] GitHub returned no repositories for the query.")
        return _FALLBACK

    # Build markdown table
    lines = [
        "| Module | Description | Stars | Last updated |",
        "|--------|-------------|-------|--------------|",
    ]
    for repo in repos:
        name = repo.get("name", "")
        if not name.startswith("jawm_"):
            continue
        url = repo.get("html_url", "#")
        desc = (repo.get("description") or "—").replace("|", "\\|")
        stars = repo.get("stargazers_count", 0)
        pushed = repo.get("pushed_at", "")
        # Format date: 2024-03-15T10:22:00Z → 2024-03-15
        try:
            updated = datetime.fromisoformat(pushed.rstrip("Z")).strftime("%Y-%m-%d")
        except Exception:
            updated = pushed[:10] if len(pushed) >= 10 else "—"

        lines.append(f"| [{name}]({url}) | {desc} | ★ {stars} | {updated} |")

    note = f"\n_Retrieved from [github.com/{_ORG}](https://github.com/{_ORG}?q=jawm_&type=all)_"
    return "\n".join(lines) + note


def on_page_markdown(markdown, page, **kwargs):
    """Inject the live module list into module/modules.md at build time."""
    if page.file.src_path != "module/modules.md":
        return markdown

    module_table = _fetch_modules()
    replacement = (
        f"<!-- JAWM_MODULES_LIST -->\n{module_table}\n<!-- /JAWM_MODULES_LIST -->"
    )
    updated = _PLACEHOLDER_RE.sub(replacement, markdown)

    if updated == markdown:
        log.warning("[jawm hooks] JAWM_MODULES_LIST placeholder not found in modules.md")

    return updated

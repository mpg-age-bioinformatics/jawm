import os
from pathlib import Path

def _load_user_config():
    """
    Load JAWM_* environment variables from a config file.

    Priority:
      1) Path defined by JAWM_CONFIG_FILE (if set)
      2) ~/.jawm/config

    The config file uses simple KEY=VALUE syntax (similar to a .env file).
    Only variables starting with "JAWM_" are considered, and existing
    environment variables are never overridden.

    Examples
    --------
    Default config file (~/.jawm/config):

        JAWM_MAX_PROCESS=50
        JAWM_EXPAND_PATH=TRUE
        JAWM_LOG_EMOJI=0

    Using a custom config file:

        export JAWM_CONFIG_FILE=/path/to/jawm.conf

    Notes
    -----
    - Shell features such as `export`, variable expansion, or inline comments
      are not supported.
    - Blank lines and lines starting with '#' are ignored.
    - Failures in loading or parsing the config are silently ignored.
    """
    try:
        # Resolve config path
        cfg_path = os.environ.get("JAWM_CONFIG_FILE")
        if cfg_path:
            cfg = Path(cfg_path).expanduser()
        else:
            cfg = Path.home() / ".jawm" / "config"

        if not cfg.exists():
            return

        for line in cfg.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()

            if key.startswith("JAWM_") and key not in os.environ:
                os.environ[key] = val

    except Exception:
        return
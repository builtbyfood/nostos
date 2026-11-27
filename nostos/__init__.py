"""Nostos - move from Windows to Linux, the easy way."""
__version__ = "0.2.4"
APP_NAME = "Nostos"


def log_path():
    import os
    from pathlib import Path
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "nostos" / "nostos.log"


def log_exception(where: str) -> None:
    """Append the current error, with its full traceback, to the log file."""
    import time
    import traceback
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')}  Nostos {__version__}  {where}\n")
            fh.write(traceback.format_exc())
    except Exception:
        pass

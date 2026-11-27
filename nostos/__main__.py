# Nostos 0.2.4 - __main__.py
import sys

from . import __version__


def main() -> int:
    if "--version" in sys.argv:
        print(f"Nostos {__version__}")
        return 0
    from .gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())

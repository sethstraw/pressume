"""Allow running as `python -m pressume`."""

from pressume.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

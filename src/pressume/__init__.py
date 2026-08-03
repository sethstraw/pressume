"""Render polished, verified resume PDFs from Markdown."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pressume")
except PackageNotFoundError:  # pragma: no cover - only an uninstalled source checkout
    __version__ = "0+unknown"

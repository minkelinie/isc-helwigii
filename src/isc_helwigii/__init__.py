"""Evidence-first foundation for the ISC Helwigii research workbench."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("isc-helwigii")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["__version__"]

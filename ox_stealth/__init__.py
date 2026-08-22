"""
OX-Stealth Myth Hunter
Multi-lingual Cuneiform Corpus Pipeline.
"""
__version__ = "1.0.0"
__author__ = "Mink Helwig"
__license__ = "CC-BY-4.0"

from importlib.metadata import version as _v
try:
    __version__ = _v("ox-stealth-myth-hunter")
except Exception:
    pass  # fallback to hardcoded
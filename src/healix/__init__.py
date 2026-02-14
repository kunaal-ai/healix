"""Healix - Self-healing Playwright test automation powered by AI."""

from healix.engine import smart_click, smart_locator, Healix, _patch_expect
from healix.engine import HealixError, OllamaConnectionError, BrowserNotInstalledError

__version__ = "0.1.28"
__all__ = [
    "smart_click",
    "smart_locator",
    "Healix",
    "_patch_expect",
    "HealixError",
    "OllamaConnectionError",
    "BrowserNotInstalledError",
]

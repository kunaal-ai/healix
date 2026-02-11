"""Healix - Self-healing Playwright test automation powered by AI."""

from healix.engine import smart_click, smart_locator, Healix
from healix.engine import HealixError, OllamaConnectionError, BrowserNotInstalledError

__version__ = "0.1.11"
__all__ = [
    "smart_click",
    "smart_locator",
    "Healix",
    "HealixError",
    "OllamaConnectionError",
    "BrowserNotInstalledError",
]

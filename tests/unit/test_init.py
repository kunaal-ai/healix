"""Unit tests for Healix package __init__ (public API and version)."""

import pytest


class TestHealixInit:
    def test_version_string(self):
        import healix
        assert hasattr(healix, "__version__")
        assert isinstance(healix.__version__, str)
        assert len(healix.__version__) >= 5  # e.g. 0.1.28

    def test_all_exports(self):
        import healix
        assert hasattr(healix, "__all__")
        for name in healix.__all__:
            assert hasattr(healix, name), f"__all__ declares {name!r} but it is not exported"

    def test_smart_click_is_async(self):
        import inspect
        from healix import smart_click
        assert inspect.iscoroutinefunction(smart_click)

    def test_smart_locator_is_async(self):
        import inspect
        from healix import smart_locator
        assert inspect.iscoroutinefunction(smart_locator)

    def test_healix_patch_returns_proxy(self):
        from unittest.mock import MagicMock
        from healix import Healix
        from healix.engine import HealixPageProxy
        with pytest.MonkeyPatch.context() as m:
            m.setattr(Healix, "_check_ollama", lambda self: None)
            mock_page = MagicMock()
            out = Healix.patch(mock_page)
        assert isinstance(out, HealixPageProxy)
        assert out._page is mock_page

    def test_healix_error_hierarchy(self):
        from healix import HealixError, OllamaConnectionError, BrowserNotInstalledError
        assert issubclass(OllamaConnectionError, HealixError)
        assert issubclass(BrowserNotInstalledError, HealixError)

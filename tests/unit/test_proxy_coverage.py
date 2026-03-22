
import pytest
from unittest.mock import MagicMock, patch, ANY
from healix.engine import HealixPageProxy, SmartLocatorProxy, SmartAssertionProxy

class TestProxyCoverage:
    @pytest.fixture
    def mock_page_and_locator(self):
        page = MagicMock()
        page.context.browser.browser_type.name = "chromium"
        loc = MagicMock()
        page.locator.return_value = loc
        return page, loc

    def test_page_proxy_methods_delegate(self, mock_page_and_locator):
        import sys
        print(f"DEBUG: module: {HealixPageProxy.__module__}")
        print(f"DEBUG: file: {sys.modules['healix.engine'].__file__}")
        page, loc = mock_page_and_locator
        # Mock healix globally to avoid instantiation
        with patch("healix.engine._get_healix"):
            proxy = HealixPageProxy(page)
            
            # Test simple delegations
            proxy.click("#sel")
            loc.click.assert_called_once()
            
            proxy.fill("#sel", "val")
            loc.fill.assert_called_with("val")
            
            proxy.check("#sel")
            loc.check.assert_called()
            
            proxy.uncheck("#sel")
            loc.uncheck.assert_called()
            
            proxy.hover("#sel")
            loc.hover.assert_called()
            
            proxy.type("#sel", "txt")
            loc.type.assert_called_with("txt")
            
            proxy.press("#sel", "Enter")
            loc.press.assert_called_with("Enter")
            
            proxy.select_option("#sel", "opt")
            loc.select_option.assert_called_with("opt")
            
            proxy.dblclick("#sel")
            loc.dblclick.assert_called()
            
            # Test getattr fallback
            proxy.goto("url")
            page.goto.assert_called_with("url")

    def test_smart_locator_call(self):
        mock_loc = MagicMock()
        slp = SmartLocatorProxy(mock_loc, MagicMock(), "#sel")
        
        # Test calling the locator directly (e.g. locator("foo"))
        slp("foo")
        mock_loc.assert_called_with("foo")

    def test_smart_assertion_proxy_logic(self):
        mock_assertion = MagicMock()
        mock_slp = MagicMock()
        sap = SmartAssertionProxy(mock_assertion, mock_slp)
        
        # Test passing through simple attribute
        mock_assertion.foo = "bar"
        assert sap.foo == "bar"
        
        # Test wrapping callable
        mock_assertion.to_have_text.side_effect = AssertionError("Failed")
        
        # This wrapper should catch AssertionError and call _heal_and_retry
        try:
            sap.to_have_text("expected")
        except AssertionError:
            pass # It re-raises after failing heal (if heal fails or returns something)
            
        mock_slp._heal_and_retry.assert_called_once()
        args = mock_slp._heal_and_retry.call_args
        assert args[0][0] == "expect.to_have_text"
        
    def test_smart_assertion_handles_heal_error(self):
        mock_assertion = MagicMock()
        mock_assertion.method.side_effect = AssertionError("Original")
        mock_slp = MagicMock()
        mock_slp._heal_and_retry.side_effect = Exception("Heal failed")
        
        sap = SmartAssertionProxy(mock_assertion, mock_slp)
        
        with pytest.raises(AssertionError, match="Original"):
            sap.method()


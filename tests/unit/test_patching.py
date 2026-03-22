
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from healix.engine import Healix, HealixPageProxy, SmartLocatorProxy

class TestPatching:

    @pytest.fixture
    def mock_page(self):
        page = MagicMock()
        page.context.browser.browser_type.name = "chromium"
        return page

    @pytest.fixture
    def healix_instance(self):
        with patch("healix.engine.Healix._check_ollama"), \
             patch("healix.engine.Healix._ensure_dirs"), \
             patch("healix.engine.Healix._load_cache", return_value={}):
            return Healix()

    def test_patch_returns_proxy(self, mock_page):
        proxy = Healix.patch(mock_page)
        assert isinstance(proxy, HealixPageProxy)
        assert proxy._page == mock_page

    def test_proxy_delegates_to_page(self, mock_page):
        proxy = Healix.patch(mock_page)
        proxy.goto("http://example.com")
        mock_page.goto.assert_called_with("http://example.com")

    def test_proxy_locator_returns_smart_locator(self, mock_page, healix_instance):
        proxy = Healix.patch(mock_page)
        # We need to mock _get_healix to return our instance or just patch where it's used
        with patch("healix.engine._get_healix", return_value=healix_instance):
            loc = proxy.locator("#btn")
            assert isinstance(loc, SmartLocatorProxy)
            assert loc._selector == "#btn"

    def test_smart_locator_calls_original_method(self, mock_page):
        mock_locator = MagicMock()
        mock_page.locator.return_value = mock_locator
        
        slp = SmartLocatorProxy(mock_locator, mock_page, "#btn")
        slp.click()
        mock_locator.click.assert_called_once()

    def test_smart_locator_heals_on_timeout(self, mock_page, healix_instance):
        mock_locator = MagicMock()
        # Simulate timeout
        mock_locator.click.side_effect = Exception("Timeout 3000ms exceeded")
        mock_page.locator.return_value = mock_locator
        mock_page.content.return_value = "<html></html>"
        
        slp = SmartLocatorProxy(mock_locator, mock_page, "#broken")
        
        # Mock AI fix
        with patch("healix.engine._get_healix", return_value=healix_instance), \
             patch.object(healix_instance, "get_fix_sync", return_value={"selector": "#fixed", "conf": 0.9, "explanation": "fixed"}), \
             patch.object(healix_instance, "_save_cache"), \
             patch.object(healix_instance, "log_proposal"):
            
            # The click should retry with new selector
            # internal implementation re-calls page.locator("#fixed") then calls click on it
            new_locator = MagicMock()
            mock_page.locator.side_effect = lambda sel: new_locator if sel == "#fixed" else mock_locator
            
            slp.click()
            
            # Verify get_fix was called
            healix_instance.get_fix_sync.assert_called_once()
            # Verify new locator was used
            new_locator.click.assert_called_once()

    def test_smart_locator_is_visible_heals_on_false(self, mock_page, healix_instance):
        mock_locator = MagicMock()
        mock_locator.is_visible.return_value = False
        mock_page.locator.return_value = mock_locator
        mock_page.content.return_value = "<html></html>"
        
        slp = SmartLocatorProxy(mock_locator, mock_page, "#broken")
        
        with patch("healix.engine._get_healix", return_value=healix_instance), \
             patch.object(healix_instance, "get_fix_sync", return_value={"selector": "#fixed", "conf": 0.9, "explanation": "fixed"}):
             
             new_locator = MagicMock()
             new_locator.is_visible.return_value = True
             mock_page.locator.side_effect = lambda sel: new_locator if sel == "#fixed" else mock_locator
             
             result = slp.is_visible()
             
             assert result is True
             healix_instance.get_fix_sync.assert_called_once()

    def test_smart_locator_chaining(self, mock_page):
        mock_locator = MagicMock()
        mock_page.locator.return_value = mock_locator
        # Mock .first returning another locator (property)
        from unittest.mock import NonCallableMock
        mock_first = NonCallableMock()
        # explicitly set first as a property on the mock
        type(mock_locator).first = PropertyMock(return_value=mock_first)
        
        slp = SmartLocatorProxy(mock_locator, mock_page, "#list")
        
        # Test .first property access
        first_proxy = slp.first
        assert isinstance(first_proxy, SmartLocatorProxy)
        assert first_proxy._selector == "#list >> first"

    # ... (method chaining test skipped/placeholder) ...

    def test_smart_locator_count_retries_on_zero(self, mock_page, healix_instance):
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        mock_page.locator.return_value = mock_locator
        mock_page.content.return_value = "<html></html>"
        
        slp = SmartLocatorProxy(mock_locator, mock_page, "#empty")
        
        with patch("healix.engine._get_healix", return_value=healix_instance), \
             patch.object(healix_instance, "get_fix_sync", return_value={"selector": "#fixed", "conf": 0.9}), \
             patch.object(healix_instance, "_save_cache"):
             
             new_locator = MagicMock()
             new_locator.count.return_value = 5
             mock_page.locator.side_effect = lambda sel: new_locator if sel == "#fixed" else mock_locator
             
             count = slp.count()
             
             assert count == 5
             healix_instance.get_fix_sync.assert_called_once()

    def test_expect_patching(self, mock_page):
        # We start with a clean slate for expect
        # Patch the real expect so we can verify it gets called
        real_expect_mock = MagicMock()
        # Important: The patch check in engine.py checks if attribute exists and is truthy.
        # MagicMock attribute access returns a new Mock which is truthy.
        # We must explicitly set it to False to allow patching to proceed.
        real_expect_mock._is_healix_patched = False
        
        # We need to patch where engine imports it from.
        # engine doing: from playwright.sync_api import expect as original_expect
        with patch("playwright.sync_api.expect", real_expect_mock):
            Healix.patch(mock_page) # This captures real_expect_mock as original_expect
            
            # Now playwright.sync_api.expect has been replaced by smart_expect (in memory)
            # But since we are inside the patch context, 'expect' in that module IS our mock?
            # No, 'patch' restores the original on exit.
            # But Healix.patch OVERWROTE it manually: playwright.sync_api.expect = smart_expect
            # So the patch object might get confused or we need to access the modified version.
            
            from playwright.sync_api import expect as patched_expect
            
            # If Healix.patch worked, patched_expect should be the wrapper
            assert getattr(patched_expect, "_is_healix_patched", False)
            
            mock_locator = MagicMock()
            slp = SmartLocatorProxy(mock_locator, mock_page, "#btn")
            
            # Call strict expect
            assertion = patched_expect(slp)
            
            # Verify original (our mock) was called with UNWRAPPED locator
            real_expect_mock.assert_called_with(mock_locator)
            assert check_is_smart_assertion(assertion)

def check_is_smart_assertion(obj):
    return type(obj).__name__ == "SmartAssertionProxy"


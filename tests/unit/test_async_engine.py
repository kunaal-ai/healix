
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from healix.engine import smart_locator, smart_click, Healix

class TestAsyncEngine:

    @pytest.fixture
    def mock_page(self):
        page = MagicMock()
        page.context.browser.browser_type.name = "chromium"
        # Mock async methods with AsyncMock
        page.wait_for_selector = AsyncMock()
        # page.locator is sync and returns a Locator
        page.locator.return_value = MagicMock() 
        page.content = AsyncMock(return_value="<html></html>")
        page.click = AsyncMock()
        page.fill = AsyncMock()
        return page

    @pytest.fixture
    def healix_instance(self):
        with patch("healix.engine.Healix._check_ollama"), \
             patch("healix.engine.Healix._ensure_dirs"), \
             patch("healix.engine.Healix._load_cache", return_value={}):
            hx = Healix()
            hx.get_fix = AsyncMock() # Mock the async get_fix
            hx.log_proposal = MagicMock()
            hx._save_cache = MagicMock()
            return hx

    @pytest.mark.asyncio
    async def test_smart_locator_cache_hit(self, mock_page, healix_instance):
        healix_instance.cache["chromium::#cached"] = "#real"
        
        with patch("healix.engine._get_healix", return_value=healix_instance):
            await smart_locator(mock_page, "#cached")
            
            # Should look up in cache and use that
            mock_page.locator.assert_called_with("#real")
            # Should NOT wait for selector (optimization) - wait, code checks cache first
            mock_page.wait_for_selector.assert_not_called()

    @pytest.mark.asyncio
    async def test_smart_locator_success_no_healing(self, mock_page, healix_instance):
        with patch("healix.engine._get_healix", return_value=healix_instance):
            await smart_locator(mock_page, "#exists")
            
            mock_page.wait_for_selector.assert_called_with("#exists", state="attached", timeout=2000)
            mock_page.locator.assert_called_with("#exists")

    @pytest.mark.asyncio
    async def test_smart_locator_heals_on_failure(self, mock_page, healix_instance):
        mock_page.wait_for_selector.side_effect = Exception("Timeout")
        healix_instance.get_fix.return_value = {"selector": "#fixed", "conf": 0.9, "explanation": "fixed"}
        
        with patch("healix.engine._get_healix", return_value=healix_instance):
            await smart_locator(mock_page, "#broken")
            
            # Should call get_fix
            healix_instance.get_fix.assert_called_once()
            # Should return fixed locator
            mock_page.locator.assert_called_with("#fixed")
            # Should log proposal
            healix_instance.log_proposal.assert_called_once()
            healix_instance._save_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_smart_locator_fails_if_conf_low(self, mock_page, healix_instance):
        mock_page.wait_for_selector.side_effect = Exception("Timeout")
        healix_instance.get_fix.return_value = {"selector": "#guess", "conf": 0.4}
        
        with patch("healix.engine._get_healix", return_value=healix_instance):
            # Should return original selector if fix confidence is low
            await smart_locator(mock_page, "#broken")
            
            mock_page.locator.assert_called_with("#broken")

    @pytest.mark.asyncio
    async def test_smart_click_success(self, mock_page, healix_instance):
        with patch("healix.engine._get_healix", return_value=healix_instance):
            await smart_click(mock_page, "#btn")
            mock_page.click.assert_called_with("#btn", timeout=2000)

    @pytest.mark.asyncio
    async def test_smart_click_heals(self, mock_page, healix_instance):
        mock_page.click.side_effect = Exception("Not visible")
        healix_instance.get_fix.return_value = {"selector": "#fixed", "conf": 0.9, "explanation": "fixed"}
        
        with patch("healix.engine._get_healix", return_value=healix_instance):
            # Mock click to succeed on second call (which uses new selector)
            # side_effect is difficult to direct based on args for AsyncMock in simple way
            # So we just reset side_effect after first call? No, it's safer to use side_effect function
            
            async def click_side_effect(selector, **kwargs):
                if selector == "#btn":
                    raise Exception("Not visible")
                return None
            
            mock_page.click.side_effect = click_side_effect
            
            await smart_click(mock_page, "#btn")
            
            # verify it tried #btn first, then #fixed
            assert mock_page.click.call_count == 2
            mock_page.click.assert_any_call("#btn", timeout=2000)
            mock_page.click.assert_any_call("#fixed", timeout=2000)
            
            healix_instance.log_proposal.assert_called_once()
            healix_instance._save_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_smart_click_plan_b(self, mock_page, healix_instance):
        # Fail first selector, fix it, fail fix, try plan B
        call_count = 0
        async def click_side_effect(selector, **kwargs):
            nonlocal call_count
            call_count += 1
            if selector == "#btn": raise Exception("Fail 1")
            if selector == "#fixed1": raise Exception("Fail 2")
            return None # succeed on third try (#fixed2)
            
        mock_page.click.side_effect = click_side_effect
        
        # hx.get_fix needs to return different things
        async def get_fix_side_effect(sel, *args, **kwargs):
            if "Fail 1" in kwargs.get("error_msg", ""):
                return {"selector": "#fixed1", "conf": 0.9}
            if "Fail 2" in kwargs.get("error_msg", ""):
                 return {"selector": "#fixed2", "conf": 0.8}
            return None
            
        healix_instance.get_fix.side_effect = get_fix_side_effect
        
        with patch("healix.engine._get_healix", return_value=healix_instance):
            await smart_click(mock_page, "#btn")
            
            assert mock_page.click.call_count == 3
            mock_page.click.assert_any_call("#fixed2", timeout=2000)
            
            # should log proposal for the working one
            assert healix_instance.log_proposal.call_count >= 1


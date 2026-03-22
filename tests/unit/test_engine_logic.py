
import pytest
from unittest.mock import MagicMock, patch
from healix.engine import Healix

class TestHealixLogic:
    @pytest.fixture
    def hx(self, tmp_path):
        with patch("healix.engine.Healix._check_ollama"):
            hx = Healix()
            hx.data_dir = str(tmp_path)
            hx.cache_file = str(tmp_path / "cache.json")
            hx.cache = {} # Start empty
            return hx

    def test_get_clean_dom_strips_unwanted(self, hx):
        html = """
        <html>
            <head><script>vars</script><style>css</style></head>
            <body>
                <div id="main" class="container">
                    <h1>Title</h1>
                    <button onclick="foo()">Click Me</button>
                    <span>Text</span>
                </div>
                <iframe src="ads"></iframe>
            </body>
        </html>
        """
        clean = hx.get_clean_dom(html)
        assert "<script>" not in clean
        assert "<style>" not in clean
        assert "iframe" not in clean
        assert "vars" not in clean
        assert "css" not in clean
        
        # Check preserved elements
        assert '<button' in clean
        assert 'Click Me' in clean
        assert 'id="main"' in clean
        assert 'class="container"' in clean
        assert 'onclick' not in clean # interactive attrs cleaned?
        # get_clean_dom allows: id, class, name, type... onclick is NOT allowed
        
    def test_get_fix_sync_cache_hit(self, hx):
        hx.cache = {"chromium::#broken": "#fixed"}
        res = hx.get_fix_sync("#broken", "<html></html>", browser="chromium")
        assert res["selector"] == "#fixed"
        assert res["conf"] == 1.0

    def test_get_fix_sync_api_call_success(self, hx):
        mock_response = {
            "response": '```json\n{"selector": "#new", "explanation": "fixed", "conf": 0.9}\n```'
        }
        with patch("healix.engine.requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.status_code = 200
            
            res = hx.get_fix_sync("#broken", "<html></html>")
            
            assert res["selector"] == "#new"
            assert res["conf"] == 0.9

    def test_get_fix_sync_handles_raw_json(self, hx):
        # Ollama might return raw JSON without markdown
        mock_response = {
            "response": '{"selector": "#raw", "explanation": "raw", "conf": 0.8}'
        }
        with patch("healix.engine.requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.status_code = 200
            
            res = hx.get_fix_sync("#broken", "<html></html>")
            
            assert res["selector"] == "#raw"

    def test_get_fix_sync_handles_jq_contains(self, hx):
        # If AI returns :contains(), it should be converted
        mock_response = {
            "response": '{"selector": "div:contains(\'Login\')", "conf": 0.8}'
        }
        with patch("healix.engine.requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.status_code = 200
            
            res = hx.get_fix_sync("#broken", "<html></html>")
            
            assert "text=Login" in res["selector"]

    def test_get_fix_sync_api_failure(self, hx):
        with patch("healix.engine.requests.post", side_effect=Exception("Net fail")):
            res = hx.get_fix_sync("#broken", "<html></html>")
            assert res is None

    def test_get_fix_sync_bad_json(self, hx):
         mock_response = {"response": "Not JSON"}
         with patch("healix.engine.requests.post") as mock_post:
            mock_post.return_value.json.return_value = mock_response
            
            res = hx.get_fix_sync("#broken", "<html></html>")
            assert res is None

    async def test_get_fix_async_wrapper(self, hx):
        # async wrapper just calls sync
        with patch.object(hx, "get_fix_sync", return_value={"selector": "#async"}) as mock_sync:
            res = await hx.get_fix("#broken", "<html></html>")
            assert res["selector"] == "#async"
            mock_sync.assert_called_once()
            
    def test_patch_method(self):
        page = MagicMock()
        # Mock _patch_expect to prevent side effects
        with patch("healix.engine._patch_expect"):
             proxy = Healix.patch(page)
             # Should replace with proxy
             from healix.engine import HealixPageProxy
             assert isinstance(proxy, HealixPageProxy)

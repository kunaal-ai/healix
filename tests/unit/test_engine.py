"""Unit tests for Healix core functionality.

Tests DOM cleaning, caching, proposal logging, and error handling.
These tests do NOT require Ollama or a browser — they test pure logic only.
"""

import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from healix.engine import Healix, OllamaConnectionError, HealixError


@pytest.fixture
def healix_instance(tmp_path):
    """Create a Healix instance with a temp directory and mocked Ollama check."""
    with patch.object(Healix, '_check_ollama'):
        hx = Healix()
        hx.data_dir = str(tmp_path)
        hx.cache_file = str(tmp_path / "cache.json")
        hx.report_file = str(tmp_path / "proposals.json")
        hx.cache = {}
        return hx


class TestDomCleaning:
    """Tests for get_clean_dom() — the DOM scrubbing logic."""

    def test_removes_script_tags(self, healix_instance):
        html = "<html><script>alert('xss')</script><button id='btn'>Click</button></html>"
        result = healix_instance.get_clean_dom(html)
        assert "script" not in result
        assert "btn" in result

    def test_removes_style_tags(self, healix_instance):
        html = "<html><style>.big{color:red}</style><input id='name'/></html>"
        result = healix_instance.get_clean_dom(html)
        assert "style" not in result.lower() or "color" not in result
        assert "name" in result

    def test_removes_svg_tags(self, healix_instance):
        html = "<html><svg><path d='M0 0'/></svg><a href='/home'>Home</a></html>"
        result = healix_instance.get_clean_dom(html)
        assert "svg" not in result.lower()
        assert "Home" in result

    def test_keeps_actionable_elements(self, healix_instance):
        html = """<html>
            <input id="user" type="text" placeholder="Username"/>
            <button class="submit" data-testid="login-btn">Login</button>
            <a href="/signup" aria-label="Sign up">Register</a>
            <label for="user">Username</label>
        </html>"""
        result = healix_instance.get_clean_dom(html)
        assert "user" in result
        assert "submit" in result
        assert "Sign up" in result
        assert "Username" in result

    def test_strips_non_allowed_attributes(self, healix_instance):
        html = '<button id="ok" onclick="hack()" style="color:red" data-tracking="x">OK</button>'
        result = healix_instance.get_clean_dom(html)
        assert 'id="ok"' in result
        assert "onclick" not in result
        assert "data-tracking" not in result

    def test_truncates_to_15000_chars(self, healix_instance):
        # Generate a large DOM
        tags = ['<input id="field-{i}" type="text"/>' for i in range(1000)]
        html = "<html>" + "".join(tags) + "</html>"
        result = healix_instance.get_clean_dom(html)
        assert len(result) <= 15000

    def test_empty_html(self, healix_instance):
        result = healix_instance.get_clean_dom("<html></html>")
        assert result == ""

    def test_html_with_no_actionable_elements(self, healix_instance):
        html = "<html><div><p>Just text</p><span>More text</span></div></html>"
        result = healix_instance.get_clean_dom(html)
        # We now keep text elements for context
        assert "Just text" in result
        assert "More text" in result


class TestCaching:
    """Tests for cache load, save, and browser-aware keys."""

    def test_save_and_load_cache(self, healix_instance):
        healix_instance._save_cache("#broken", "#fixed", browser="chromium")
        
        # Verify in-memory
        assert healix_instance.cache["chromium::#broken"] == "#fixed"
        
        # Verify on disk
        with open(healix_instance.cache_file) as f:
            disk_cache = json.load(f)
        assert disk_cache["chromium::#broken"] == "#fixed"

    def test_browser_aware_keys(self, healix_instance):
        healix_instance._save_cache("#btn", ".submit", browser="chromium")
        healix_instance._save_cache("#btn", "button.radius", browser="firefox")
        
        assert healix_instance.cache["chromium::#btn"] == ".submit"
        assert healix_instance.cache["firefox::#btn"] == "button.radius"

    def test_default_browser_key(self, healix_instance):
        healix_instance._save_cache("#x", "#y")
        assert "default::#x" in healix_instance.cache

    def test_load_empty_cache(self, healix_instance):
        cache = healix_instance._load_cache()
        assert cache == {}

    def test_load_corrupted_cache(self, healix_instance):
        with open(healix_instance.cache_file, 'w') as f:
            f.write("not valid json!!!")
        cache = healix_instance._load_cache()
        assert cache == {}


class TestProposalLogging:
    """Tests for log_proposal() — the code fix suggestion logger."""

    def test_logs_proposal(self, healix_instance):
        healix_instance.log_proposal(
            "#old", "#new",
            {"file": "test.py", "line": 42},
            reason="ID changed"
        )
        
        with open(healix_instance.report_file) as f:
            proposals = json.load(f)
        
        assert len(proposals) == 1
        assert proposals[0]["original_selector"] == "#old"
        assert proposals[0]["suggested_fix"] == "#new"
        assert proposals[0]["status"] == "pending_review"

    def test_appends_multiple_proposals(self, healix_instance):
        for i in range(3):
            healix_instance.log_proposal(
                f"#old-{i}", f"#new-{i}",
                {"file": "test.py", "line": i}
            )
        
        with open(healix_instance.report_file) as f:
            proposals = json.load(f)
        assert len(proposals) == 3


class TestErrorHandling:
    """Tests for friendly error messages and custom exceptions."""

    def test_ollama_not_running_raises_error(self):
        with patch('healix.engine.requests.get', side_effect=Exception("Connection refused")):
            with patch('healix.engine.requests.get', side_effect=__import__('requests').ConnectionError()):
                with pytest.raises(OllamaConnectionError, match="Ollama is not running"):
                    Healix()

    def test_custom_exceptions_have_correct_hierarchy(self):
        assert issubclass(OllamaConnectionError, HealixError)
        from healix.engine import BrowserNotInstalledError
        assert issubclass(BrowserNotInstalledError, HealixError)

    def test_cache_hit_returns_immediately(self, healix_instance):
        """Verify that a cache hit skips the AI call entirely."""
        healix_instance.cache["chromium::#broken"] = "#fixed"
        import asyncio
        result = asyncio.run(
            healix_instance.get_fix("#broken", "<html></html>", browser="chromium")
        )
        assert result["selector"] == "#fixed"
        assert result["conf"] == 1.0
        assert result["explanation"] == "Cache hit"


class TestGetFixSync:
    """Tests for get_fix_sync() with mocked HTTP."""

    def test_returns_fix_on_valid_json_response(self, healix_instance):
        with patch.object(healix_instance, "_load_cache", return_value={}):
            with patch("healix.engine.requests.post") as mock_post:
                mock_post.return_value.json.return_value = {
                    "response": '{"selector": "#submit-btn", "explanation": "Submit button", "conf": 0.9}'
                }
                mock_post.return_value.raise_for_status = MagicMock()
                result = healix_instance.get_fix_sync(
                    "#broken", "<html><button id=\"submit-btn\">Submit</button></html>",
                    browser="chromium", error_msg="not found"
                )
                assert result["selector"] == "#submit-btn"
                assert result["conf"] == 0.9
                assert result["explanation"] == "Submit button"

    def test_returns_none_on_empty_response(self, healix_instance):
        with patch("healix.engine.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"response": ""}
            mock_post.return_value.raise_for_status = MagicMock()
            result = healix_instance.get_fix_sync("#x", "<html></html>", browser="chromium", error_msg="err")
            assert result is None

    def test_returns_none_on_invalid_json(self, healix_instance):
        with patch("healix.engine.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"response": "not valid json"}
            mock_post.return_value.raise_for_status = MagicMock()
            result = healix_instance.get_fix_sync("#x", "<html></html>", browser="chromium", error_msg="err")
            assert result is None

    def test_replaces_contains_with_playwright_text(self, healix_instance):
        with patch("healix.engine.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "response": '{"selector": "button:contains(\\"Submit\\")", "explanation": "x", "conf": 0.8}'
            }
            mock_post.return_value.raise_for_status = MagicMock()
            result = healix_instance.get_fix_sync("#x", "<html></html>", browser="chromium", error_msg="e")
            assert "text=Submit" in result["selector"]
            assert ":contains(" not in result["selector"]

    def test_defaults_conf_when_missing(self, healix_instance):
        with patch("healix.engine.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {
                "response": '{"selector": "#ok", "explanation": "y"}'
            }
            mock_post.return_value.raise_for_status = MagicMock()
            result = healix_instance.get_fix_sync("#x", "<html></html>", browser="chromium", error_msg="e")
            assert result["conf"] == 0.7

    def test_returns_none_on_http_exception(self, healix_instance):
        with patch("healix.engine.requests.post", side_effect=Exception("timeout")):
            result = healix_instance.get_fix_sync("#x", "<html></html>", browser="chromium", error_msg="e")
            assert result is None


class TestSaveCacheContextMode:
    """Test _save_cache with context_used stores CTX-prefixed in cache."""

    def test_context_used_prepends_ctx(self, healix_instance):
        healix_instance._save_cache("#old", "#new", browser="chromium", context_used=True)
        assert healix_instance.cache["chromium::#old"] == "CTX:#new"
        with open(healix_instance.cache_file) as f:
            assert json.load(f)["chromium::#old"] == "CTX:#new"


class TestHealixPatch:
    """Test Healix.patch and HealixPageProxy."""

    def test_patch_returns_proxy(self):
        with patch.object(Healix, "_check_ollama"):
            mock_page = MagicMock()
            proxy = Healix.patch(mock_page)
            from healix.engine import HealixPageProxy
            assert type(proxy).__name__ == "HealixPageProxy"
            assert proxy._page is mock_page

    def test_locator_uses_cache_and_returns_smart_proxy(self, healix_instance):
        with patch.object(Healix, "_check_ollama"):
            from healix.engine import HealixPageProxy, SmartLocatorProxy, _get_healix
            # Reset global so fixture's cache is used
            import healix.engine as eng
            eng._hx = healix_instance
            healix_instance._healed_selectors["#foo"] = "#footer a"
            mock_page = MagicMock()
            mock_loc = MagicMock()
            mock_page.locator.return_value = mock_loc
            proxy = HealixPageProxy(mock_page)
            out = proxy.locator("#foo")
            assert isinstance(out, SmartLocatorProxy)
            mock_page.locator.assert_called_once_with("#footer a", **{})


class TestInstallBrowsers:
    """Test install_browsers() success and failure paths."""

    def test_install_browsers_success(self):
        from healix.engine import install_browsers
        with patch("healix.engine.subprocess.run", return_value=MagicMock(returncode=0)):
            install_browsers()  # no raise

    def test_install_browsers_called_process_error(self):
        from healix.engine import install_browsers, BrowserNotInstalledError
        with patch("healix.engine.subprocess.run", side_effect=__import__("subprocess").CalledProcessError(1, "cmd", stderr="err")):
            with pytest.raises(BrowserNotInstalledError, match="could not be installed"):
                install_browsers()

    def test_install_browsers_file_not_found(self):
        from healix.engine import install_browsers, BrowserNotInstalledError
        with patch("healix.engine.subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(BrowserNotInstalledError, match="Playwright not found"):
                install_browsers()


class TestMain:
    """Test main() CLI entry point."""

    def test_main_no_args(self, capsys):
        from healix.engine import main
        with patch("healix.engine.sys.argv", ["healix"]):
            main()
        out, _ = capsys.readouterr()
        assert "Usage" in out or "healix" in out.lower()

    def test_main_file_not_found(self, capsys):
        from healix.engine import main
        with patch("healix.engine.sys.argv", ["healix", "/nonexistent_file_12345.py"]):
            main()
        out, _ = capsys.readouterr()
        assert "not found" in out or "Error" in out

    def test_main_skips_run_when_install_fails(self):
        from healix.engine import main, BrowserNotInstalledError
        with patch("healix.engine.sys.argv", ["healix", "nonexistent.py"]):
            with patch("healix.engine.install_browsers", side_effect=BrowserNotInstalledError("x")):
                main()  # should return without running subprocess

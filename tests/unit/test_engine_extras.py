
import pytest
from unittest.mock import patch, MagicMock, mock_open
import sys
from healix.engine import Healix, main, install_browsers, BrowserNotInstalledError, OllamaConnectionError

class TestEngineExtras:
    
    def test_check_ollama_success(self):
        with patch("healix.engine.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            hx = Healix()
            # If it didn't raise, it passed
            assert hx

    def test_check_ollama_failure_status(self):
        # _check_ollama checks for ConnectionError, not status code (it assumes if it connects, it's there)
        with patch("healix.engine.requests.get", side_effect=__import__("requests").ConnectionError):
            with pytest.raises(OllamaConnectionError):
                Healix()

    def test_ensure_dirs_creates_directories(self):
        # We need to mock os.makedirs and os.path.exists
        with patch("healix.engine.os.makedirs") as mock_mkdirs, \
             patch("healix.engine.os.path.exists", return_value=False):
             
             with patch("healix.engine.Healix._check_ollama"):
                 hx = Healix()
                 # check if dirs created
                 assert mock_mkdirs.call_count >= 1

    def test_save_cache_handles_os_error(self):
        with patch("healix.engine.Healix._check_ollama"):
            hx = Healix()
            hx.cache_file = "/tmp/cache.json"
            
            with patch("builtins.open", side_effect=OSError("Permission denied")):
                # The implementation does NOT catch the error, so we expect it to raise
                with pytest.raises(OSError):
                    hx._save_cache("#old", "#new")

    def test_main_runs_success(self):
        with patch("healix.engine.sys.argv", ["healix", "test.py"]):
             # Mock os.path.exists to return True for test.py
             with patch("healix.engine.os.path.exists", return_value=True):
                 with patch("healix.engine.install_browsers") as mock_install:
                     with patch("healix.engine.subprocess.run") as mock_run:
                         main()
                         mock_install.assert_called_once()
                         mock_run.assert_called_once()

    def test_install_browsers_success(self):
        with patch("healix.engine.subprocess.run") as mock_run:
            install_browsers()
            mock_run.assert_called()

    def test_install_browsers_failure(self):
        import subprocess
        with patch("healix.engine.subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")):
            with pytest.raises(BrowserNotInstalledError):
                install_browsers()

    def test_install_browsers_not_found(self):
        with patch("healix.engine.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(BrowserNotInstalledError):
                install_browsers()

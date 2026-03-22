
import os
import json
import pytest
import requests
from unittest.mock import patch, mock_open
from healix.engine import Healix

class TestHealixCore:

    @pytest.fixture
    def mock_ollama(self):
        """Mock Ollama health check so tests run without Ollama."""
        with patch.object(Healix, "_check_ollama"):
            yield

    @pytest.fixture
    def mock_cwd(self, mock_ollama, tmp_path):
        """Mock current working directory to a temp path with project marker."""
        (tmp_path / "pyproject.toml").touch()
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        yield tmp_path
        os.chdir(orig_cwd)

    def test_init_finds_project_root_with_pyproject(self, mock_cwd):
        (mock_cwd / "pyproject.toml").touch()
        hx = Healix()
        assert hx.data_dir == str(mock_cwd / ".healix")

    def test_init_finds_project_root_with_git(self, mock_cwd):
        (mock_cwd / ".git").mkdir()
        hx = Healix()
        assert hx.data_dir == str(mock_cwd / ".healix")

    def test_init_falls_back_to_home_if_no_project(self, mock_ollama, tmp_path):
        """Use tmp_path with no project markers; patch expanduser to simulate home."""
        orig_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch("os.path.expanduser", return_value=str(tmp_path / "home")):
                hx = Healix()
                assert hx.data_dir == str(tmp_path / "home" / ".healix")
        finally:
            os.chdir(orig_cwd)

    def test_ensure_dirs_creates_directory(self, mock_cwd):
        hx = Healix()
        # The __init__ calls _ensure_dirs
        assert os.path.exists(hx.data_dir)
        assert os.path.isdir(hx.data_dir)

    def test_load_cache_empty_if_missing(self, mock_cwd):
        hx = Healix()
        # Ensure cache file doesn't exist
        if os.path.exists(hx.cache_file):
            os.remove(hx.cache_file)
        # Re-load
        cache = hx._load_cache()
        assert cache == {}

    def test_load_cache_returns_content(self, mock_cwd):
        hx = Healix()
        data = {"chromium::#btn": "#fixed"}
        with open(hx.cache_file, 'w') as f:
            json.dump(data, f)
        
        cache = hx._load_cache()
        assert cache == data

    def test_load_cache_handles_corrupt_json(self, mock_cwd):
        hx = Healix()
        with open(hx.cache_file, 'w') as f:
            f.write("{invalid json")
        
        cache = hx._load_cache()
        assert cache == {}

    def test_save_cache_updates_and_persists(self, mock_cwd):
        hx = Healix()
        hx._save_cache("#old", "#new", browser="firefox")
        
        with open(hx.cache_file, 'r') as f:
            content = json.load(f)
        
        assert content["firefox::#old"] == "#new"
        assert hx.cache["firefox::#old"] == "#new"

    def test_save_cache_with_context(self, mock_cwd):
        hx = Healix()
        hx._save_cache("#old", "#new", browser="webkit", context_used=True)
        
        with open(hx.cache_file, 'r') as f:
            content = json.load(f)
        
        assert content["webkit::#old"] == "CTX:#new"

    def test_log_proposal_appends(self, mock_cwd):
        hx = Healix()
        # Initialize with no proposals
        if os.path.exists(hx.report_file):
            os.remove(hx.report_file)
            
        hx.log_proposal("#broken", "#fixed", {"file": "test.py", "line": 10}, "reason")
        
        with open(hx.report_file, 'r') as f:
            proposals = json.load(f)
        
        assert len(proposals) == 1
        ensure = proposals[0]
        assert ensure["original_selector"] == "#broken"
        assert ensure["suggested_fix"] == "#fixed"
        assert ensure["reasoning"] == "reason"
        assert ensure["file"] == "test.py"
        
        # Append another
        hx.log_proposal("#broken2", "#fixed2", {}, "")
        with open(hx.report_file, 'r') as f:
            proposals = json.load(f)
        assert len(proposals) == 2

    def test_check_ollama_connection_error(self):
        """Test that Healix raises when Ollama is unreachable (no mock_ollama)."""
        with patch("healix.engine.requests.get", side_effect=requests.ConnectionError):
            with pytest.raises(Exception) as exc:
                Healix()
            assert "Ollama is not running" in str(exc.value)

    def test_log_proposal_corrupt_file(self, mock_cwd):
        hx = Healix()
        with open(hx.report_file, 'w') as f:
            f.write("{bad json")
            
        hx.log_proposal("#a", "#b", {}, "reason")
        
        # It should have overwritten or reset the file
        with open(hx.report_file, 'r') as f:
            proposals = json.load(f)
        assert len(proposals) == 1
        assert proposals[0]["original_selector"] == "#a"

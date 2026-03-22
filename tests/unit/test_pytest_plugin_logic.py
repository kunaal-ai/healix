
import pytest
import os
import json
from unittest.mock import MagicMock, patch, ANY
from healix.pytest_plugin import (
    _extract_all_selectors_from_error,
    _extract_context_from_error,
    _extract_expected_text_from_error,
    _derive_test_context,
    _healix_box,
    pytest_exception_interact,
    pytest_sessionfinish,
    _generate_healix_report_html
)

class MockItem:
    def __init__(self, name="test_foo", nodeid="tests/test_foo.py::test_foo"):
        self.name = name
        self.nodeid = nodeid
        self.fspath = "tests/test_foo.py"
        self.funcargs = {}
        self.obj = lambda: None
        self.obj.__name__ = name
        self._healix_retry_count = 0
        self._healix_report_indices = []

    def runtest(self):
        pass

class MockReport:
    def __init__(self, failed=True, longrepr="Error"):
        self.when = "call"
        self.failed = failed
        self.longrepr = longrepr
        self.sections = []
        self.longreprtext = str(longrepr)

class TestPluginHelpers:
    def test_healix_box(self):
        lines = ["Hello", "World"]
        box = _healix_box(lines)
        assert "+-" in box
        assert "| Hello" in box
        
    def test_derive_test_context(self):
        item = MockItem(name="test_login_page")
        assert _derive_test_context(item) == "login"
        item.name = "test_footer_link"
        assert _derive_test_context(item) == "footer"
        item.name = "test_something_else"
        assert _derive_test_context(item) == ""

    def test_extract_selectors(self):
        report = MockReport(longrepr="Error: locator('#foo') not found")
        selectors = _extract_all_selectors_from_error(report)
        assert "#foo" in selectors

        report.longrepr = "locator('div.cls') and locator(\"span[name='ok']\")"
        selectors = _extract_all_selectors_from_error(report)
        assert "div.cls" in selectors
        assert "span[name='ok']" in selectors

    def test_extract_context_from_error(self):
        report = MockReport(longrepr="Error: get_by_role('button', name='Submit')")
        assert _extract_context_from_error(report) == "Submit"
        
        report.longrepr = "get_by_text('Welcome')"
        assert _extract_context_from_error(report) == "Welcome"

    def test_extract_expected_text(self):
        report = MockReport(longrepr="Error: expected to have text 'Success'")
        assert _extract_expected_text_from_error(report) == "Success"


class TestPluginLogic:
    @pytest.fixture
    def mock_healix(self):
        # Patch where it is defined, so when imported it returns the mock
        with patch("healix.engine._get_healix") as mock_get:
            hx = MagicMock()
            hx.data_dir = "/tmp/healix"
            hx._healed_selectors = {}
            hx.get_fix_sync.return_value = {"selector": "#new", "conf": 0.9, "explanation": "fixed"}
            mock_get.return_value = hx
            yield hx

    def test_exception_interact_no_failure(self):
        report = MockReport(failed=False)
        pytest_exception_interact(report, None)
        # Should do nothing

    def test_exception_interact_no_page(self):
        item = MockItem()
        # No page in funcargs
        report = MockReport()
        report.item = item
        pytest_exception_interact(report, None)
        # Should do nothing

    def test_exception_interact_heals_and_retries(self, mock_healix):
        item = MockItem()
        page = MagicMock()
        # Prevent getattr(page, "_page") from creating a new Mock
        page._page = page 
        page.content.return_value = "<html></html>"
        # Mock locator().count() to return 1 (single match)
        page.locator.return_value.count.return_value = 1
        item.funcargs["page"] = page
        
        report = MockReport(longrepr="locator('#broken')")
        report.item = item
        
        # We rely on the mock_healix fixture which patches healix.engine._get_healix
        pytest_exception_interact(report, None)
            
        # Verify get_fix_sync called
        mock_healix.get_fix_sync.assert_called()
        # Verify retry
        assert item._healix_retry_count == 1
        assert report.outcome == "passed" 
        assert mock_healix._save_cache.assert_called

    def test_exception_interact_skips_low_confidence(self, mock_healix):
        mock_healix.get_fix_sync.return_value = {"selector": "#bad", "conf": 0.5}
        
        item = MockItem()
        item.funcargs["page"] = MagicMock()
        report = MockReport(longrepr="locator('#broken')")
        report.item = item
        
        pytest_exception_interact(report, None)
        
        # Should not retry
        assert item._healix_retry_count == 0

    def test_exception_interact_refines_multiple_matches(self, mock_healix):
        item = MockItem()
        page = MagicMock()
        page._page = page
        page.content.return_value = "<html></html>"
        item.funcargs["page"] = page
        
        # Scenario:
        # 1. First get_fix_sync returns "#ambiguous", matches 2 elements.
        # 2. Plugin calls get_fix_scoped_sync (not get_fix_sync again) when count > 1.
        # 3. get_fix_scoped_sync returns "#specific", matches 1 element.
        
        mock_healix.get_fix_sync.return_value = {"selector": "#ambiguous", "conf": 0.9, "explanation": "Ambiguous"}
        mock_healix.get_fix_scoped_sync.return_value = {"selector": "#specific", "conf": 0.95, "explanation": "Scoped"}
        
        # Mock locator counts
        # page.locator("#ambiguous").count() -> 2
        # page.locator("#specific").count() -> 1
        
        mock_ambiguous = MagicMock()
        mock_ambiguous.count.return_value = 2
        
        mock_specific = MagicMock()
        mock_specific.count.return_value = 1
        
        def locator_side_effect(sel):
            if sel == "#ambiguous": return mock_ambiguous
            if sel == "#specific": return mock_specific
            return MagicMock() # fallback
            
        page.locator.side_effect = locator_side_effect
        
        report = MockReport(longrepr="locator('#broken')")
        report.item = item
        
        pytest_exception_interact(report, None)
        
        # Verify it retried
        assert item._healix_retry_count == 1
        # Verify it used the specific one
        # The cache save should have happened with #specific
        # Or check report usage
        from healix.pytest_plugin import _healix_report_entries
        last_entry = _healix_report_entries[-1]
        assert last_entry["healed_locator"] == "#specific"


class TestPluginReporting:
    def test_generate_html_report(self, tmp_path):
        entries = [{
            "test": "test_one",
            "broken_locator": "#bad",
            "healed_locator": "#good",
            "retry_passed": True,
            "confidence": 0.9,
            "explanation": "Got it"
        }]
        path = tmp_path / "report.html"
        _generate_healix_report_html(entries, str(path))
        
        assert path.exists()
        content = path.read_text()
        assert "test_one" in content
        assert "Retry passed" in content

    def test_session_finish_writes_reports(self, tmp_path):
        from healix.pytest_plugin import _healix_report_entries
        # Inject some fake entries
        _healix_report_entries.append({"test": "foo"})
        
        with patch("healix.engine._get_healix") as mock_get:
            hx = MagicMock()
            hx.data_dir = str(tmp_path)
            mock_get.return_value = hx
            
            pytest_sessionfinish(None, 0)
            
            assert (tmp_path / "healix_report.json").exists()
            assert (tmp_path / "healix_report.html").exists()
    def test_extract_selectors_empty(self):
        report = MockReport(longrepr=None)
        assert _extract_all_selectors_from_error(report) == []
        
        report.longrepr = ""
        assert _extract_all_selectors_from_error(report) == []

    def test_color_fallback(self):
        with patch("healix.pytest_plugin._healix_use_color", return_value=True):
            from healix.pytest_plugin import _healix_c
            assert "\033[33m" in _healix_c("33", "text")
            assert "text" in _healix_c("", "text")


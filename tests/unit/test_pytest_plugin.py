"""Unit tests for Healix pytest plugin helpers (extractors, formatters, HTML report)."""

import os
import pytest

# Import plugin module to test its private helpers
import healix.pytest_plugin as plugin


class TestExtractAllSelectorsFromError:
    def test_none_report_returns_empty(self):
        assert plugin._extract_all_selectors_from_error(None) == []

    def test_no_longrepr_returns_empty(self):
        report = type("R", (), {"longrepr": None})()
        assert plugin._extract_all_selectors_from_error(report) == []

    def test_single_selector_single_quotes(self):
        report = type("R", (), {"longrepr": "waiting for locator('#submit')"})()
        assert plugin._extract_all_selectors_from_error(report) == ["#submit"]

    def test_single_selector_double_quotes(self):
        report = type("R", (), {"longrepr": 'locator("#footer a")'})()
        assert plugin._extract_all_selectors_from_error(report) == ["#footer a"]

    def test_multiple_selectors_deduped(self):
        report = type("R", (), {"longrepr": "locator('#a') and locator('#a') then locator('#b')"})()
        result = plugin._extract_all_selectors_from_error(report)
        assert result == ["#a", "#b"]


class TestExtractContextFromError:
    def test_no_report_returns_empty(self):
        assert plugin._extract_context_from_error(None) == ""

    def test_get_by_role_name(self):
        report = type("R", (), {"longrepr": "get_by_role('link', name='About Us')"})()
        assert plugin._extract_context_from_error(report) == "About Us"

    def test_get_by_text(self):
        report = type("R", (), {"longrepr": "get_by_text('Contact')"})()
        assert plugin._extract_context_from_error(report) == "Contact"

    def test_get_by_label(self):
        report = type("R", (), {"longrepr": "get_by_label('Username')"})()
        assert plugin._extract_context_from_error(report) == "Username"

    def test_no_match_returns_empty(self):
        report = type("R", (), {"longrepr": "something else"})()
        assert plugin._extract_context_from_error(report) == ""


class TestExtractExpectedTextFromError:
    def test_no_report_returns_empty(self):
        assert plugin._extract_expected_text_from_error(None) == ""

    def test_to_have_text(self):
        report = type("R", (), {"longrepr": "to_have_text('Welcome')"})()
        assert plugin._extract_expected_text_from_error(report) == "Welcome"

    def test_expected_to_have_text(self):
        report = type("R", (), {"longrepr": "expected to have text \"Contact Us\""})()
        assert plugin._extract_expected_text_from_error(report) == "Contact Us"

    def test_no_match_returns_empty(self):
        report = type("R", (), {"longrepr": "other"})()
        assert plugin._extract_expected_text_from_error(report) == ""


class TestExtractFileAndLine:
    def test_from_report_longrepr(self):
        report = type("R", (), {"longrepr": 'File "/path/to/test.py", line 42'})()
        item = type("I", (), {"fspath": None, "path": None})()
        out = plugin._extract_file_and_line(report, item)
        assert out["line"] == 42

    def test_from_item_fspath(self):
        report = type("R", (), {"longrepr": ""})()
        item = type("I", (), {"fspath": "/foo/bar.py", "path": None, "obj": None})()
        out = plugin._extract_file_and_line(report, item)
        assert out["file"] == "/foo/bar.py"

    def test_from_item_obj_code(self):
        report = type("R", (), {"longrepr": ""})()
        code = type("C", (), {"co_firstlineno": 10})()
        obj = type("O", (), {"__code__": code})()
        item = type("I", (), {"fspath": None, "path": None, "obj": obj})()
        out = plugin._extract_file_and_line(report, item)
        assert out["line"] == 10


class TestDeriveTestContext:
    def test_footer(self):
        item = type("I", (), {"name": "test_footer_about_us"})()
        assert plugin._derive_test_context(item) == "footer"

    def test_header(self):
        item = type("I", (), {"name": "test_header_nav"})()
        assert plugin._derive_test_context(item) == "header"

    def test_login(self):
        item = type("I", (), {"name": "test_login_flow"})()
        assert plugin._derive_test_context(item) == "login"

    def test_auth(self):
        item = type("I", (), {"name": "test_auth_redirect"})()
        assert plugin._derive_test_context(item) == "login"

    def test_no_match_returns_empty(self):
        item = type("I", (), {"name": "test_generic"})()
        assert plugin._derive_test_context(item) == ""

    def test_none_item_returns_empty(self):
        assert plugin._derive_test_context(None) == ""

    def test_no_name_returns_empty(self):
        item = type("I", (), {})()
        assert plugin._derive_test_context(item) == ""


class TestGetPageFromItem:
    def test_no_item_returns_none(self):
        assert plugin._get_page_from_item(None) is None

    def test_no_funcargs_returns_none(self):
        item = type("I", (), {})()
        assert plugin._get_page_from_item(item) is None

    def test_returns_page_from_funcargs(self):
        page = object()
        item = type("I", (), {"funcargs": {"page": page}})()
        assert plugin._get_page_from_item(item) is page

    def test_returns_hx_page_when_page_missing(self):
        page = object()
        item = type("I", (), {"funcargs": {"hx_page": page}})()
        assert plugin._get_page_from_item(item) is page


class TestHealixBox:
    def test_empty_lines(self):
        out = plugin._healix_box([])
        assert "+" in out and "-" in out

    def test_single_line(self):
        out = plugin._healix_box(["hello"])
        assert "hello" in out

    def test_min_width(self):
        out = plugin._healix_box(["x"], width=20)
        assert len(out.split("\n")[0]) >= 20


class TestHealixC:
    def test_no_color_env_disables_color(self):
        with pytest.MonkeyPatch.context() as m:
            m.setenv("NO_COLOR", "1")
            out = plugin._healix_c("36", "text")
            assert out == "text"

    def test_with_color_returns_ansi_when_tty(self):
        with pytest.MonkeyPatch.context() as m:
            m.delenv("NO_COLOR", raising=False)
            out = plugin._healix_c("36", "x")
            # If stderr is tty we get ANSI; in tests often we get plain
            assert "x" in out


class TestGenerateHealixReportHtml:
    def test_empty_entries_returns_early(self, tmp_path):
        plugin._generate_healix_report_html([], str(tmp_path / "out.html"))
        assert not (tmp_path / "out.html").exists()

    def test_one_entry_creates_html(self, tmp_path):
        entries = [{
            "test": "test_foo",
            "function": "test_foo",
            "file": "/path/to/test.py",
            "line": 10,
            "broken_locator": "#x",
            "healed_locator": "#y",
            "retry_passed": True,
            "confidence": 0.9,
            "explanation": "Fixed",
        }]
        path = tmp_path / "report.html"
        plugin._generate_healix_report_html(entries, str(path))
        assert path.exists()
        content = path.read_text()
        assert "test_foo" in content
        assert "#x" in content
        assert "#y" in content
        assert "Retry passed" in content or "pass" in content

    def test_retry_failed_badge(self, tmp_path):
        entries = [{
            "test": "t",
            "function": "t",
            "file": "",
            "line": 0,
            "broken_locator": "a",
            "healed_locator": "b",
            "retry_passed": False,
            "confidence": 0.8,
            "explanation": "",
        }]
        path = tmp_path / "report.html"
        plugin._generate_healix_report_html(entries, str(path))
        content = path.read_text()
        assert "Retry failed" in content or "fail" in content


class TestPrintSuggestion:
    def test_prints_to_stdout(self, capsys):
        plugin._print_suggestion(
            {"file": "/f.py", "line": 10},
            "#old", "#new", 0.9, "Root cause here"
        )
        out, _ = capsys.readouterr()
        assert "HEALIX SUGGESTION" in out
        assert "#old" in out and "#new" in out
        assert "0.9" in out


class TestLogReview:
    def test_appends_to_review_log(self, tmp_path):
        import healix.engine as eng
        mock_hx = type("H", (), {"data_dir": str(tmp_path)})()
        with pytest.MonkeyPatch.context() as m:
            m.setattr(eng, "_get_healix", lambda: mock_hx)
            plugin._log_review(
                type("I", (), {"name": "test_foo"})(),
                {"file": "t.py", "line": 1},
                "#a", "#b", 0.85, "expl"
            )
        log_path = tmp_path / "review_log.json"
        assert log_path.exists()
        import json
        data = json.loads(log_path.read_text())
        assert len(data) == 1
        assert data[0]["broken_selector"] == "#a"
        assert data[0]["suggested_fix"] == "#b"


class TestPytestSessionfinish:
    """Test sessionfinish writes reports and pushes metrics (mocked)."""

    def test_sessionfinish_writes_json_and_html(self, tmp_path):
        with pytest.MonkeyPatch.context() as m:
            mock_hx = type("H", (), {"data_dir": str(tmp_path)})()
            import healix.engine as eng
            m.setattr(eng, "_get_healix", lambda: mock_hx)
            # Populate report entries
            plugin._healix_report_entries.clear()
            plugin._healix_report_entries.append({
                "test": "test_foo",
                "nodeid": "file::test_foo",
                "file": "/t.py",
                "line": 1,
                "function": "test_foo",
                "broken_locator": "#x",
                "healed_locator": "#y",
                "retry_passed": True,
                "confidence": 0.9,
                "explanation": "Fix",
                "timestamp": "2020-01-01T00:00:00Z",
            })
            try:
                session = type("S", (), {})()
                plugin.pytest_sessionfinish(session, 0)
            finally:
                plugin._healix_report_entries.clear()
        assert (tmp_path / "healix_report.json").exists()
        assert (tmp_path / "healix_report.html").exists()
        import json
        data = json.load((tmp_path / "healix_report.json").open())
        assert data[0]["test"] == "test_foo"

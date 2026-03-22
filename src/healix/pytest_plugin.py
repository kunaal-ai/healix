"""
Pytest plugin for Healix: on Playwright locator failures, extract selectors from
the error, call AI to get fixed selectors, validate (exactly one match), update
session cache, and retry the test. Writes unified healix_report.json and
healix_report.html for human review (no automatic code changes).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import pytest

# Session report entries: list of dicts (test, file, line, function, broken_locator, healed_locator, retry_passed, confidence, explanation, timestamp)
_healix_report_entries = []
_healix_welcome_shown = False

# ASCII box and optional ANSI color (safe fallback)
def _healix_use_color():
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    except Exception:
        return False

def _healix_c(code, text):
    if not _healix_use_color():
        return text
    return "\033[%sm%s\033[0m" % (code, text)

def _healix_box(lines, width=62):
    """Draw an ASCII box around lines. Uses + - | for maximum compatibility."""
    max_len = max(len(l) for l in lines) if lines else 0
    width = max(width, max_len + 4)
    top = "+" + "-" * (width - 2) + "+"
    out = [top]
    for line in lines:
        padded = (line[: width - 4] if len(line) > width - 4 else line).ljust(width - 4)
        out.append("| " + padded + " |")
    out.append(top)
    return "\n".join(out)

def _healix_emit(msg):
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _extract_all_selectors_from_error(report):
    """Extract all locator selectors from the failure (e.g. chained)."""
    if not report or not getattr(report, "longrepr", None):
        return []
    text = str(report.longrepr)
    # Match locator('...') or locator("...")
    # non-greedy match until same closing quote
    selectors = []
    for match in re.finditer(r"locator\s*\(\s*(['\"])(.*?)\1\s*\)", text):
        selectors.append(match.group(2))
    return list(dict.fromkeys(selectors))


def _extract_context_from_error(report):
    """E.g. get_by_role('link', name='About Us') or get_by_text('Contact')."""
    if not report or not getattr(report, "longrepr", None):
        return ""
    text = str(report.longrepr)
    for pattern in [
        r"get_by_role\s*\(\s*['\"][^'\"]+['\"],\s*name\s*=\s*['\"]([^'\"]+)['\"]",
        r"get_by_text\s*\(\s*['\"]([^'\"]+)['\"]",
        r"get_by_label\s*\(\s*['\"]([^'\"]+)['\"]",
    ]:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return ""


def _extract_expected_text_from_error(report):
    """E.g. expected to have text '...' or to_have_text('...')."""
    if not report or not getattr(report, "longrepr", None):
        return ""
    text = str(report.longrepr)
    for pattern in [
        r"to_have_text\s*\(\s*['\"]([^'\"]+)['\"]",
        r"expected to have text\s+['\"]([^'\"]+)['\"]",
        r"to contain text\s+['\"]([^'\"]+)['\"]",
    ]:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip()
    return ""


def _extract_file_and_line(report, item):
    """File and line from report or item."""
    file_path = getattr(item, "fspath", None) or (item and getattr(item, "path", None))
    if file_path:
        file_path = str(file_path)
    else:
        file_path = ""
    line = 0
    if report and getattr(report, "longrepr", None):
        text = str(report.longrepr)
        # "File \"...\", line N"
        m = re.search(r"File\s+[\"'].*?[\"'],\s*line\s+(\d+)", text)
        if m:
            line = int(m.group(1))
    if line == 0 and hasattr(item, "obj") and hasattr(item.obj, "__code__"):
        line = getattr(item.obj.__code__, "co_firstlineno", 0)
    return {"file": file_path, "line": line}


def _derive_test_context(item):
    """Infer area from test name (e.g. 'footer' if test name contains 'footer')."""
    if not item or not hasattr(item, "name"):
        return ""
    name = (item.name or "").lower()
    if "footer" in name:
        return "footer"
    if "header" in name:
        return "header"
    if "login" in name or "auth" in name:
        return "login"
    return ""


def _get_page_from_item(item):
    """Get Playwright page from test funcargs (page or hx_page)."""
    if not item or not hasattr(item, "funcargs"):
        return None
    return item.funcargs.get("page") or item.funcargs.get("hx_page", None)


def pytest_configure(config):
    """Show Healix welcome banner once per session."""
    global _healix_welcome_shown
    if _healix_welcome_shown:
        return
    _healix_welcome_shown = True
    lines = [
        "Healix  |  Self-healing locators (no code changed automatically)",
        "On failure: suggestions in .healix/healix_report.html",
    ]
    _healix_emit("")
    _healix_emit(_healix_c("36", _healix_box(lines)))  # cyan
    _healix_emit("")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture failure report for our hook."""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed and hasattr(report, "longrepr"):
        # Store for pytest_exception_interact
        item._healix_report = report
    return report


def pytest_exception_interact(report, node):
    """On test failure, try to heal selectors and retry."""
    if report.when != "call" or not report.failed:
        return
    item = getattr(report, "item", node)
    if not item:
        return
    page = _get_page_from_item(item)
    if not page:
        return
    # Unwrap Healix proxy to get real page if needed
    real_page = getattr(page, "_page", page)
    try:
        from healix.engine import _get_healix
    except ImportError:
        return
    hx = _get_healix()
    selectors = _extract_all_selectors_from_error(report)
    if not selectors:
        return
    # Decorated banner so user sees Healix is running (visible without -s)
    trigger_lines = [
        "HEALIX  |  Locator failure detected",
        "Analyzing with AI (Ollama) - this may take 20-60s",
    ]
    _healix_emit("")
    _healix_emit(_healix_c("33", _healix_box(trigger_lines)))  # yellow
    _healix_emit(_healix_c("33", "  [1/4] Extracting selectors from error..."))
    target_context = _extract_context_from_error(report)
    expected_text = _extract_expected_text_from_error(report)
    test_context = _derive_test_context(item)
    file_info = _extract_file_and_line(report, item)
    _healix_emit(_healix_c("33", "  [2/4] Querying AI (Ollama) for suggestion..."))
    browser = "chromium"
    try:
        browser = real_page.context.browser.browser_type.name
    except Exception:
        pass
    html = real_page.content()
    healed = {}
    report_indices_this_round = []
    for sel in selectors:
        t0 = time.perf_counter()
        fix = hx.get_fix_sync(
            sel, html, browser=browser,
            error_msg=report.longreprtext[:500] if getattr(report, "longreprtext", None) else "",
            target_context=target_context or None,
            expected_text=expected_text or None,
            test_context=test_context or None,
        )
        if not fix or fix.get("conf", 0) <= 0.6:
            continue
        new_sel = fix.get("selector", "").strip()
        if not new_sel:
            continue
        count = real_page.locator(new_sel).count()
        if count > 1:
            # Lightweight scoped call (no full DOM) — fewer tokens, faster than second get_fix_sync
            fix2 = hx.get_fix_scoped_sync(sel, new_sel, count, browser, html=html)
            if fix2 and fix2.get("conf", 0) > 0.6:
                new_sel = fix2.get("selector", "").strip()
                count = real_page.locator(new_sel).count()
        duration_seconds = time.perf_counter() - t0
        cache_hit = (fix.get("explanation") or "").strip().lower() == "cache hit"
        if count == 1:
            expl = (fix.get("explanation") or "").lower()
            report_text = (getattr(report, "longreprtext", None) or str(getattr(report, "longrepr", "") or "")).lower()
            # Use context_mode when the failure involved a chain (e.g. .get_by_role) so we swallow it on retry
            chain_in_error = any(x in report_text for x in (".get_by_role", ".get_by_text", ".get_by_label", ".get_by_placeholder"))
            context_used = chain_in_error or any(x in expl for x in ("context", "scope", "scoped"))
            # Store CTX-prefixed in session so retry uses context_mode and swallows .get_by_role etc.
            value_for_retry = f"CTX:{new_sel}" if context_used else new_sel
            healed[sel] = new_sel
            hx._healed_selectors[sel] = value_for_retry
            # Module-level fallback so engine finds healed selectors after fixture re-runs on retry
            try:
                import healix.engine as _eng
                if not getattr(_eng, "_pytest_healed_selectors", None):
                    _eng._pytest_healed_selectors = {}
                _eng._pytest_healed_selectors[sel] = value_for_retry
            except Exception:
                pass
            hx._save_cache(sel, new_sel, browser=browser, context_used=context_used)
            _print_suggestion(file_info, sel, new_sel, fix.get("conf"), fix.get("explanation", ""))
            _log_review(item, file_info, sel, new_sel, fix.get("conf"), fix.get("explanation", ""))
            # Append to unified report (retry_passed set after retry)
            _healix_report_entries.append({
                "test": getattr(item, "name", ""),
                "nodeid": getattr(item, "nodeid", ""),
                "file": file_info.get("file", ""),
                "line": file_info.get("line", 0),
                "function": getattr(getattr(item, "obj", None), "__name__", ""),
                "broken_locator": sel,
                "healed_locator": new_sel,
                "retry_passed": None,
                "confidence": fix.get("conf"),
                "explanation": (fix.get("explanation") or "")[:500],
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "duration_seconds": round(duration_seconds, 3),
                "cache_hit": cache_hit,
            })
            report_indices_this_round.append(len(_healix_report_entries) - 1)
    if healed:
        _healix_emit(_healix_c("33", "  [3/4] Validating selector (single match)..."))
        _healix_emit(_healix_c("33", "  [4/4] Retrying test with healed locator(s)..."))
        # Add a section to the report so failure output shows Healix activity (visible without -s)
        try:
            data_dir = getattr(hx, "data_dir", ".healix")
            lines = ["Healix healed locator(s) and created reports (no code was changed)."]
            for broken, suggested in healed.items():
                lines.append(f"  Broken: {broken}")
                lines.append(f"  Suggested: {suggested}")
            lines.append(f"  JSON: {os.path.join(data_dir, 'healix_report.json')}")
            lines.append(f"  HTML: {os.path.join(data_dir, 'healix_report.html')}")
            report.sections.append(("Healix", "\n".join(lines)))
        except Exception:
            pass
    # Allow up to 2 retries so we can heal multiple selectors in the same test (e.g. line 14 then line 15)
    max_retries = 2
    retry_count = getattr(item, "_healix_retry_count", 0)
    if healed and retry_count < max_retries:
        item._healix_retry_count = retry_count + 1
        existing_indices = getattr(item, "_healix_report_indices", [])
        item._healix_report_indices = existing_indices + report_indices_this_round
        try:
            item.runtest()
            # Retry passed: update report so pytest shows test as passed
            report.outcome = "passed"
            report.longrepr = None
            for i in item._healix_report_indices:
                if i < len(_healix_report_entries):
                    _healix_report_entries[i]["retry_passed"] = True
            _healix_emit(_healix_c("32", "  Healix: Retry PASSED - outcome updated to passed."))
        except Exception as retry_err:
            for i in item._healix_report_indices:
                if i < len(_healix_report_entries):
                    _healix_report_entries[i]["retry_passed"] = False
            _healix_emit(_healix_c("31", "  Healix: Retry failed - " + str(retry_err)[:80]))


def _print_suggestion(file_info, broken, suggested, conf, reason):
    """Print a clear suggestion box to the terminal."""
    file_path = file_info.get("file", "")
    line = file_info.get("line", 0)
    print("\n" + "=" * 60)
    print("  HEALIX SUGGESTION – update code manually")
    print("=" * 60)
    print(f"  FILE:LINE   {file_path}:{line}")
    print(f"  BROKEN      {broken}")
    print(f"  SUGGESTED   {suggested}")
    print(f"  CONFIDENCE  {conf}")
    print(f"  ROOT CAUSE  {reason[:200]}")
    print("  ---")
    print("  Healix will retry the test using the suggested selector.")
    print("  The failure shown below is from the first run (before healing).")
    print("=" * 60 + "\n")


def _log_review(item, file_info, broken, suggested, conf, explanation):
    """Append to .healix/review_log.json (legacy)."""
    try:
        from healix.engine import _get_healix
        hx = _get_healix()
        log_path = os.path.join(hx.data_dir, "review_log.json")
        os.makedirs(hx.data_dir, exist_ok=True)
        entries = []
        if os.path.exists(log_path):
            try:
                with open(log_path, "r") as f:
                    entries = json.load(f)
            except Exception:
                entries = []
        entries.append({
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "test": getattr(item, "name", ""),
            "file": file_info.get("file"),
            "line": file_info.get("line"),
            "broken_selector": broken,
            "suggested_fix": suggested,
            "confidence": conf,
            "explanation": explanation,
            "action_required": True,
        })
        with open(log_path, "w") as f:
            json.dump(entries, f, indent=2)
    except Exception:
        pass


def _generate_healix_report_html(entries, filepath):
    """Generate an HTML report from report entries for human review."""
    if not entries:
        return
    try:
        import html as html_module
        rows = []
        for e in entries:
            file_path = e.get("file") or ""
            line = e.get("line") or 0
            # Link that editors can open (file:// or vscode://)
            location = f"{file_path}:{line}" if file_path else "-"
            location_cell = f'<a href="file://{html_module.escape(file_path)}#L{line}">{html_module.escape(location)}</a>' if file_path else html_module.escape(location)
            retry = e.get("retry_passed")
            if retry is True:
                status = '<span class="badge pass">Retry passed</span>'
            elif retry is False:
                status = '<span class="badge fail">Retry failed</span>'
            else:
                status = '<span class="badge pending">Pending</span>'
            rows.append(
                f"<tr><td>{html_module.escape(e.get('test', ''))}</td>"
                f"<td>{html_module.escape(e.get('function', ''))}</td>"
                f"<td>{location_cell}</td>"
                f"<td><code>{html_module.escape(e.get('broken_locator', ''))}</code></td>"
                f"<td><code>{html_module.escape(e.get('healed_locator', ''))}</code></td>"
                f"<td>{status}</td>"
                f"<td>{e.get('confidence', '')}</td>"
                f"<td class=\"explanation\">{html_module.escape((e.get('explanation') or '')[:200])}</td></tr>"
            )
        table_body = "\n".join(rows)
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Healix Report – Locator healing summary</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem 2rem; background: #f8f9fa; }}
    h1 {{ color: #1a1a2e; }}
    .meta {{ color: #666; margin-bottom: 1rem; }}
    table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
    th, td {{ border: 1px solid #dee2e6; padding: 0.5rem 0.75rem; text-align: left; }}
    th {{ background: #1a1a2e; color: white; }}
    tr:nth-child(even) {{ background: #f8f9fa; }}
    code {{ background: #e9ecef; padding: 0.15rem 0.35rem; border-radius: 3px; font-size: 0.9em; }}
    .badge {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.85em; font-weight: 600; }}
    .badge.pass {{ background: #d4edda; color: #155724; }}
    .badge.fail {{ background: #f8d7da; color: #721c24; }}
    .badge.pending {{ background: #fff3cd; color: #856404; }}
    .explanation {{ max-width: 280px; }}
    a {{ color: #0d6efd; }}
  </style>
</head>
<body>
  <h1>Healix report</h1>
  <p class="meta">Locator healing suggestions – review and apply manually. No code was changed automatically.</p>
  <table>
    <thead>
      <tr>
        <th>Test</th>
        <th>Function</th>
        <th>File:Line</th>
        <th>Broken locator</th>
        <th>Healed locator</th>
        <th>Retry</th>
        <th>Confidence</th>
        <th>Explanation</th>
      </tr>
    </thead>
    <tbody>
{table_body}
    </tbody>
  </table>
</body>
</html>"""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    """Write unified JSON + HTML report and print a prominent summary."""
    try:
        from healix.engine import _get_healix
        hx = _get_healix()
        data_dir = hx.data_dir
        os.makedirs(data_dir, exist_ok=True)

        # Write unified JSON report (single source of truth)
        report_json_path = os.path.join(data_dir, "healix_report.json")
        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(_healix_report_entries, f, indent=2)

        # Generate HTML report for readability
        report_html_path = os.path.join(data_dir, "healix_report.html")
        _generate_healix_report_html(_healix_report_entries, report_html_path)

        # Push to Prometheus Pushgateway if configured (prometheus_client + URL set)
        try:
            from healix.prometheus_metrics import push_healix_metrics
            n_pushed, push_err = push_healix_metrics(_healix_report_entries)
            if n_pushed:
                _healix_emit(_healix_c("36", "  Healix: Pushed %d metric(s) to Pushgateway." % n_pushed))
            elif push_err and _healix_report_entries:
                _healix_emit(_healix_c("33", "  Healix: Metrics not pushed - %s" % push_err))
        except Exception as e:
            if _healix_report_entries:
                _healix_emit(_healix_c("33", "  Healix: Push failed - %s" % (str(e)[:80])))

        if _healix_report_entries:
            n = len(_healix_report_entries)
            passed = sum(1 for e in _healix_report_entries if e.get("retry_passed") is True)
            summary_lines = [
                "HEALIX: %d locator(s) healed. Reports created (review and apply manually)." % n,
                "No code was changed automatically.",
                "JSON: %s" % report_json_path,
                "HTML: %s" % report_html_path,
            ]
            if passed:
                summary_lines.insert(0, "Retries passed: %d/%d" % (passed, n))
            box = _healix_box(summary_lines)
            # Green if any retry passed, else cyan
            colored = _healix_c("32", box) if passed else _healix_c("36", box)
            _healix_emit("\n" + colored + "\n")
    except Exception:
        pass

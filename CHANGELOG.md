# Changelog

I document all notable changes to Healix here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Upcoming improvements (backlog)

I keep this list in the repo so I can pick items off one by one. When I ship one, I’ll move it into a release section below.

1. **Smaller DOM sent to the model** — Trim/sample DOM more before Ollama to cut latency and tokens.
2. **Async cache writes** — Write cache in the background so the test thread doesn’t block on disk.
3. **Stronger first prompt** — Improve “match exactly one” in the first call so the scoped follow-up is needed less often.
4. **DOM clean duration metric** — Time `get_clean_dom()` and expose it to see if it’s a bottleneck.
5. **Optional: lxml parser** — Benchmark `lxml` for DOM cleaning; keep `html.parser` as fallback.
6. **Retry budget / backoff** — One retry with shorter prompt or different temp when confidence is low; document in README.
7. **Heal summary in terminal** — One-line session summary (e.g. N heals, X from cache, avg Ys) without opening Grafana.

---

## [0.1.29] - (performance & efficiency)

### Performance & efficiency (implemented)

- **Fewer Ollama calls when first suggestion matches multiple elements**
  - **Before:** Two full `get_fix_sync` calls (full DOM, 60s timeout each).
  - **After:** One full `get_fix_sync` + one **lightweight** `get_fix_scoped_sync` (short prompt, optional 2k-char DOM snippet, 30s timeout). Reduces tokens and latency for the second call.
  - **Evidence:** `engine.py`: new `get_fix_scoped_sync()`; `pytest_plugin.py` calls it when `count > 1` instead of a second `get_fix_sync`.

- **Heal duration and cache hit rate in Prometheus/Grafana**
  - **Before:** Only `healix_heals_total` (count by test/retry_passed); no duration or cache metrics.
  - **After:** `healix_heal_duration_seconds` (Histogram, per-test), `healix_heal_cache_total{test, cache="hit"|"miss"}`. Each report entry includes `duration_seconds` and `cache_hit`; session finish pushes them to Pushgateway.
  - **Evidence:** `pytest_plugin.py`: `time.perf_counter()` around heal, report fields `duration_seconds`, `cache_hit`; `prometheus_metrics.py`: Histogram + cache counter, documented in README with example Grafana queries.

### Added

- **Performance metrics:** Heal duration (seconds) and cache hit/miss per heal, pushed to Prometheus when Pushgateway is configured. See README “Prometheus & Grafana” and “Performance & efficiency” for queries.

### Changed

- **Scoped selector request:** When the first AI suggestion matches multiple elements, the second request now uses `get_fix_scoped_sync` (minimal prompt, optional short DOM snippet) instead of a full second `get_fix_sync`, reducing latency and token usage.

---

## [0.1.28] - 2026-02-13

### Added
- **Observability Enhancement**: Added Prometheus metrics support for tracking self-healing success rates.
- **Advanced Proxy Chaining**: Improved support for nested and chained Playwright locators.
- **Performance baseline**: README now includes a “Performance & efficiency” section with before-evidence (latency, Ollama call count, observability) and placeholders for after-evidence post-improvements.

### Fixed
- **Chained Locator Retries**: Fixed an issue where healing was not correctly propagated through chained locator actions.

## [0.1.14] - 2026-02-11

### Added
- **Smart Assertion Support**: Intercepts Playwright `expect()` assertions. Failed assertions now trigger self-healing on the underlying locator automatically.

## [0.1.13] - 2026-02-11

### Fixed
- **Page Action Interception**: `HealixPageProxy` now intercepts high-level actions like `page.click()`, `page.fill()`, and `page.select_option()`, automatically upgrading them to smart locators to ensure self-healing works even without explicit `page.locator()` calls.

## [0.1.12] - 2026-02-11

### Fixed
- **Observability Enhancement**: Improved internal proxy transparency to ensure Playwright `expect` assertions correctly trigger the self-healing workflow.
- **Refined Error Handling**: Standardized [ERROR] reporting for failed healing attempts.

## [0.1.11] - 2026-02-11

### Changed
- **Professional Logging**: Replaced all emojis in console output with standardized industry-grade prefixes like `[INFO]`, `[HEAL]`, `[SUCCESS]`, and `[ERROR]` for better enterprise compatibility.

## [0.1.10] - 2026-02-11

### Added
- **AI Analysis Log**: Healix now explicitly logs when it starts analyzing the DOM with AI.
- **Root Cause Analysis (RCA)**: The AI's explanation for the failure is now printed directly to the console.
- **Detailed Retries**: Logs now show specifically which method (e.g., `is_visible`, `text_content`) is being retried after healing.

## [0.1.9] - 2026-02-11

### Fixed
- **Advanced Proxy Chaining**: Improved support for chained locators like `page.locator("#A").first.locator("#B")`.
- **Recursion Safety**: Hardened the proxy to prevent internal lookup cycles.
- **Improved Traceability**: Smart selectors now include child identifiers in logs (e.g. `#parent >> first`).

## [0.1.8] - 2026-02-11

### Added
- **Startup indicator**: `Healix.patch(page)` now prints a rocket emoji 🚀 when active.
- **Improved Transparency**: Proxies now pass through `__class__` and `_impl` for better compatibility with Playwright `expect()`.
- **Emojified Logs**: Added 🩹, ✨, and 🔄 emojis to healing logs for better visibility.

## [0.1.7] - 2026-02-11

### Fixed
- **Improved SmartLocatorProxy healing**: Now intercepts methods like `is_visible()` and `count()` which previously failed silently without triggering healing.
- **Enhanced `expect` compatibility**: More robust proxy logic for synchronous Playwright assertions.

## [0.1.6] - 2026-02-11

### Added
- **`Healix.patch(page)` (Zero-Refactor API)**: Patch an entire Playwright page so all its locators become self-healing automatically. No need to rewrite existing Page Objects or tests.
- **Sync Playwright Support**: Healix now works with both `playwright.sync_api` and `async_api`.

## [0.1.5] - 2026-02-11

### Changed
- **Renamed `healed_locator` to `smart_locator`** for better consistency with `smart_click` and to avoid confusion (less "past-tense" sounding).

## [0.1.4] - 2026-02-11

### Added
- **`healed_locator` API**: Support for self-healing in assertions (`expect`) and Page Objects
- **Semantic DOM Analysis**: AI now sees text content of elements, improving matching for assertions (e.g. `to_have_text`)
- **Better Prompting**: AI now prioritizes target element type (e.g. finding an `h1` even if the container ID changed)

## [0.1.3] - 2026-02-11

### Changed
- Replaced Mermaid diagram with text flowchart for better PyPI compatibility
- Updated README architecture section to match actual project structure
- Removed Docker section from README (Docker support temporarily removed)
- Updated Quick Start example to use a real testing URL (`the-internet.herokuapp.com`)

### Fixed
- Fixed internal import in integration tests to use public API (`from healix import smart_click`)
- Added `Changelog` URL to PyPI metadata
- Removed `data/` and `docker/` directories from version control
- Updated `.gitignore` to verify exclusion of build artifacts and data directories
- Friendly error messages when Playwright browsers are not installed
- Custom exception classes: `HealixError`, `OllamaConnectionError`, `BrowserNotInstalledError`
- Lazy initialization — importing `healix` no longer crashes if Ollama is down
- Unit test suite covering DOM cleaning, caching, proposal logging, and error handling
- GitHub Actions CI workflow
- PyPI badges, prerequisites, and known limitations in README

### Changed
- Cache directory moved from relative `healix_data/` to `~/.healix/` for reliability
- README cleaned up: removed emojis, added professional sections

### Fixed
- License placeholder in README replaced with actual MIT reference

## [0.1.1] - 2026-02-11

### Fixed
- License display on PyPI showing "[Add your license here]"
- Updated README license section

## [0.1.0] - 2026-02-11

### Added
- Initial release
- AI-powered self-healing for broken Playwright selectors
- Browser-aware cache keys (separate fixes per browser engine)
- Improved AI prompt to prevent hallucinated selectors
- Plan B retry loop with failure feedback to AI
- DOM scrubbing and minification for token efficiency
- Persistent cache in JSON format
- Code proposal logging for review
- CLI entry point: `healix <test_file.py>`
- Multi-browser support (Chromium, Firefox)

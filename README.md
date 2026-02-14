# Healix

[![PyPI version](https://img.shields.io/pypi/v/healix-ai.svg)](https://pypi.org/project/healix-ai/)
[![Python](https://img.shields.io/pypi/pyversions/healix-ai.svg)](https://pypi.org/project/healix-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/kunaal-ai/healix/actions/workflows/ci.yml/badge.svg)](https://github.com/kunaal-ai/healix/actions/workflows/ci.yml)

**Healix** is a **privacy-first**, self-healing web automation agent. It fixes broken Playwright selectors using AI — and everything runs **100% on your machine**. No data ever leaves your device.

> Built for teams in **healthcare, fintech, government, and enterprise** where sending DOM data to cloud APIs is not an option.

## The Problem

Web automation is fragile. Selectors break when:
- Developers change class names
- DOM structure shifts
- Content loads dynamically
- A/B tests alter page layouts

## Why Healix?

- **Zero data exposure** — AI runs locally via Ollama. No API keys, no cloud, no telemetry. Your DOM never leaves `localhost`
- **Compliance ready** — Safe for HIPAA, SOC 2, PCI-DSS, and air-gapped environments
- **Zero config** — Drop-in replacement for flaky selectors, no test rewrites needed
- **Browser-aware** — Separate caching per browser engine (Chromium, Firefox, WebKit)
- **Learns over time** — Caches successful fixes for instant replay on subsequent runs
- **Transparent** — Logs every decision with confidence scores and reasoning

## The Solution

Healix uses an **agentic loop** to automatically detect and fix selector failures:

1. **Observe** — Analyze the current page state and DOM
2. **Reason** — Use AI to determine the correct selector/action
3. **Act** — Execute the corrected action
4. **Verify** — Confirm the action succeeded
5. **Learn** — Cache successful fixes for future use

### Operational Workflow

```
                        Test Failure Detected
                                |
                          Check Cache
                         /          \
                      Hit            Miss
                       |               |
               Apply Cached       DOM Scrubbing
                 Selector        & Minification
                       |               |
                Re-run Test       Query Ollama
                 /       \        (Local LLM)
            Success     Fail          |
               |          \    Confidence Scoring
               |           \      /          \
               |            \  High          Low
               |             \  |             |
               |          Re-run with     Manual Review
               |           AI Fix          Required
               |           /    \             |
               |       Success  Fail          |
               |          |       |           |
               |    Update Cache  |           |
               |          |       |           |
                \         |      /           /
                 \        |     /           /
              Healing  ----+----    -------
             Successful    |
                           |
                  Log Code Proposal
                           |
                    Action Complete
```

## Architecture

```
healix/
├── .github/workflows/
│   └── ci.yml                 # CI: tests on Python 3.9/3.11/3.12
├── src/healix/
│   ├── __init__.py            # Public API (smart_click, Healix)
│   ├── engine.py              # Core self-healing logic
│   ├── prometheus_metrics.py  # Optional: push heal metrics to Pushgateway
│   └── utilities/
│       └── dom_scrubber.py    # DOM cleaning helpers
├── tests/
│   ├── integration/
│   │   └── test_login.py      # Live browser healing demo
│   └── unit/
│       └── test_engine.py     # 18 unit tests (no Ollama needed)
├── CHANGELOG.md               # Version history
├── LICENSE                    # MIT
├── pyproject.toml             # Package config & dependencies
└── README.md

~/.healix/                     # Runtime data (created automatically)
├── cache.json                 # Persistent selector cache
└── proposals.json             # Logged code fix suggestions
```

## Prerequisites

- **Python** 3.9 or higher
- **Ollama** running locally — [Install Ollama](https://ollama.com/download), then:
  ```bash
  ollama serve
  ollama pull qwen2.5-coder:7b
  ```

## Installation

```bash
pip install healix-ai
```

Or install from source:

```bash
git clone https://github.com/kunaal-ai/healix.git
cd healix
pip install -e .
```

Make sure to install Playwright browsers:

```bash
playwright install chromium
```

## Quick Start

```python
import asyncio
from playwright.async_api import async_playwright
from healix import smart_click

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        await page.goto("https://the-internet.herokuapp.com/login")

        # These selectors are intentionally wrong — Healix will heal them
        await smart_click(page, "input#wrong-id", text_to_fill="tomsmith")
        await smart_click(page, "input[name='bad_field']", text_to_fill="SuperSecretPassword!")
        await smart_click(page, "button.does-not-exist")

        print("Login healed!" if await page.locator(".flash.success").is_visible() else "Failed")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
```


## Zero-Refactor Integration (New!)

Already have a large project? You don't need to rewrite your Page Objects. Just "patch" the page at the start of your test:

```python
from healix import Healix
from playwright.sync_api import expect

def test_login(page):
    # Patch the page once
    page = Healix.patch(page)
    
    # 0 changes needed to your Page Objects!
    # page.locator() now automatically produces self-healing locators.
    login_page = LoginPage(page)
    
    login_page.login("user", "pass")
    expect(login_page.welcome_msg).to_be_visible()
```

## Advanced Usage

### Self-Healing Assertions

Standard Playwright assertions (`expect`) are strict. If a selector breaks, the test fails immediately. Healix provides `smart_locator` to fix this:

```python
from healix import smart_locator
from playwright.async_api import expect

# ❌ Standard: Fails immediately if #header-v1 is missing
# await expect(page.locator("#header-v1")).to_have_text("Welcome")

# ✅ Healix: Finds the element (e.g. #header-v2) using AI, then asserts
header = await smart_locator(page, "#header-v1")
await expect(header).to_have_text("Welcome")
```

### Page Object Model (POM)

Healix works great with Page Objects. Since AI healing is async, use **async methods** instead of properties:

```python
from healix import smart_locator, smart_click

class LoginPage:
    def __init__(self, page):
        self.page = page

    # Action: Use smart_click
    async def login(self, user, pw):
        await smart_click(self.page, "#username", text_to_fill=user)
        await smart_click(self.page, "#password", text_to_fill=pw)
        await smart_click(self.page, "#login-btn")

    # element: Use smart_locator
    async def get_welcome_message(self):
        # Heals selector if it breaks
        return await smart_locator(self.page, ".welcome-text")
```


### Real-World Scenarios

#### Scenario A: The "No-ID" Heuristic
**Problem:** You used a role-based locator, but the developer changed the text.
```python
# Broken: The button text changed from "Bill Pay" to "Make Payment"
# self.page.get_by_role("link", name="Bill Pay")
await smart_click(page, 'internal:role=link[name="Bill Pay"]')
```
**Healix logic:** AI sees the `href="/billpay"` and the new "Make Payment" text. It matches them semantically and suggests the update.

#### Scenario B: Cascading Failure (Parent ID Shift)
**Problem:** A parent container's ID changed, breaking all child selectors.
```python
# Broken: #billpayResult was renamed to #payment-status
# expect(page.locator("#billpayResult h1.title")).to_have_text("Complete")
locator = await healed_locator(page, "#billpayResult h1.title")
await expect(locator).to_have_text("Complete")
```
**Healix logic:** AI focuses on the target `h1.title`. It finds the title element on the page and identifies its new parent `#payment-status` automatically.

#### Scenario C: Dynamic/Randomized IDs
**Problem:** Elements have IDs like `btn-12345` that change every deployment.
```python
# Broken: ID is now btn-99887
await smart_click(page, "#btn-12345")
```
**Healix logic:** AI ignores the random suffix and matches via class names, labels, and position. It will suggest a more stable selector like `button.primary[type="submit"]`.

### Comparison: When to use what?

| Goal | Use this API | Why? |
|------|--------------|------|
| **Click/Type** | `smart_click()` | Handled in one line. Best for actions. |
| **Verify Text** | `healed_locator()` | Returns a Playwright `Locator` for `expect()`. |
| **Page Objects**| `healed_locator()` | Allows defining lazy, healed elements inside class methods. |

## How It Works

### DOM Cleaning & Privacy
- Strips scripts, styles, and heavy elements to save tokens
- Focuses on actionable elements (buttons, links, inputs)
- All processing happens in-memory on your machine

### AI-Powered Reasoning
- Uses local LLM (Ollama) for selector analysis — **no external API calls**
- Considers both technical errors and visible page state
- Returns confidence scores and explanations

### Persistent Learning
- Caches successful fixes in `~/.healix/cache.json`
- Gets faster over time as it learns common patterns
- Maintains context across test runs

## Privacy & Security

Healix was designed from the ground up for **zero-data-exposure** environments:

| What | Where it runs | Data leaves device? |
|------|:------------:|:---:|
| AI inference (Ollama) | `localhost:11434` | No |
| DOM analysis | In-process Python | No |
| Selector cache | `~/.healix/` | No |
| Browser automation | Local Playwright | No |

- **No cloud APIs** — The LLM runs entirely on your hardware via Ollama
- **No telemetry** — Healix collects zero analytics or usage data
- **No network calls** — The only outbound traffic is your test navigating to its target URL
- **No API keys** — Nothing to configure, nothing to leak

This makes Healix safe for:
- **Healthcare** (HIPAA) — Patient portals, EHR systems
- **Finance** (SOC 2, PCI-DSS) — Banking apps, payment flows
- **Government** (FedRAMP) — Internal tools, classified environments
- **Enterprise** — Any org that prohibits sending DOM/HTML to third-party APIs

## Configuration

Healix uses Ollama for local AI inference:

```python
from healix import Healix

# Default model: qwen2.5-coder:7b
healix = Healix(model="your-preferred-model")
```

Make sure Ollama is running:
```bash
ollama serve
```

### Prometheus & Grafana (optional)

If you already use Prometheus and Grafana, Healix can push heal metrics so you can see them on your dashboards.

**Requirements:** Install `prometheus_client` and set a Pushgateway URL:

```bash
pip install prometheus-client
export HEALIX_PUSHGATEWAY_URL="http://localhost:9091"   # or PUSHGATEWAY_URL
```

If `prometheus_client` is not installed or the URL is not set, Healix runs as usual and does not push any metrics.

**Metrics:**  
- `healix_heals_total` (counter) — labels: `test`, `retry_passed`  
- `healix_heal_duration_seconds` (histogram) — time to heal per locator; labels: `test`  
- `healix_heal_cache_total` (counter) — labels: `test`, `cache` (`hit` / `miss`)  
- Job name: `healix` (grouped by run timestamp)

**Example Prometheus queries (for Grafana):**
- Total heals: `sum(healix_heals_total)`
- Heals by test: `sum by (test) (healix_heals_total)`
- Retry pass rate: `sum(healix_heals_total{retry_passed="true"}) / sum(healix_heals_total)`
- p95 heal duration (s): `histogram_quantile(0.95, rate(healix_heal_duration_seconds_bucket[5m]))`
- Cache hit rate: `sum(rate(healix_heal_cache_total{cache="hit"}[5m])) / sum(rate(healix_heal_cache_total[5m]))`

Ensure Prometheus scrapes your Pushgateway (same one you use for other test metrics); then add a panel with the query above. Use **instant** or **range** query with `sum(healix_heals_total)` — do not use `increase(...)` for the total count (push-based metrics are current values).

**If Grafana shows 0 but the HTML report shows heals:** After the run, check the terminal: you should see either `Healix: Pushed N metric(s) to Pushgateway.` or `Healix: Metrics not pushed - ...` / `Healix: Push failed - ...`. If metrics were not pushed, install `prometheus-client` in the same environment that runs pytest and set `HEALIX_PUSHGATEWAY_URL` (or `PUSHGATEWAY_URL`) so the test process can reach the Pushgateway. Also confirm Prometheus is scraping that Pushgateway (`job="pushgateway"` or your scrape config).

## Testing

```bash
# Run unit tests only (no browser/Ollama required; high coverage)
PYTHONPATH=src pytest tests/unit/ -v

# Run with coverage report (unit tests; requires pytest-cov)
PYTHONPATH=src pytest tests/unit/ --cov=healix --cov-report=term-missing

# Run all tests (integration tests require Playwright browsers)
pytest tests/

# Run integration tests (requires browser + Ollama for healing)
pytest tests/integration/
```

Unit tests cover the engine (DOM cleaning, caching, get_fix_sync, install_browsers, main), the pytest plugin (selector extraction, report generation), Prometheus metrics, and the public API. Integration tests require `playwright install` and optionally Ollama for self-healing behavior.


## Contributing

Pull requests are welcome. If you’d like to contribute:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the [MIT License](LICENSE).

## Performance & efficiency

I document here how Healix behaves today (before) and what I’ve already improved (after), with evidence so you can see how efficiency evolves across versions.

### Before (current behaviour — evidence)

| Area | Evidence | Source |
|------|----------|--------|
| **Heal latency (uncached)** | ~2–5 seconds per selector when AI is used | README (typical range with local Ollama) |
| **Heal latency (cached)** | Instant (no Ollama call) | Cache hit path in `engine.py`: `get_fix_sync` returns early when `cache_key in self.cache` (line 112–113) |
| **Ollama calls per failure** | Up to **two** calls per broken selector when the first suggestion matches multiple elements | `pytest_plugin.py` lines 219–220: second `get_fix_sync` when `count > 1` to request a scoped selector |
| **Observability** | Only **count** of heals (success/fail); no duration or cache hit rate | `prometheus_metrics.py`: single metric `healix_heals_total` with labels `test`, `retry_passed` — no Histogram/Summary for latency or cache labels |
| **DOM processing** | Full parse + trim to 15k chars per heal | `engine.py` `get_clean_dom()` (lines 83–106) and `get_fix_sync` (line 115) |

### After (implemented — evidence)

| Area | Before | After | Evidence |
|------|--------|-------|----------|
| **Ollama calls when count > 1** | Two full `get_fix_sync` calls (full DOM each) | One full `get_fix_sync` + one **lightweight** `get_fix_scoped_sync` (short prompt, optional 2k-char DOM snippet, 30s timeout) | `engine.py`: new `get_fix_scoped_sync()`; `pytest_plugin.py` calls it instead of second `get_fix_sync` when `count > 1` |
| **Heal duration** | Not measured | **Measured per heal** and pushed to Prometheus | `pytest_plugin.py`: `time.perf_counter()` around heal; report entry `duration_seconds`; `prometheus_metrics.py`: `healix_heal_duration_seconds` (Histogram, buckets 0.05–60s) |
| **Cache hit rate** | Not exposed | **Exposed** per heal and aggregated in Prometheus | Report entry `cache_hit` (true when `fix.explanation == "Cache hit"`); `prometheus_metrics.py`: `healix_heal_cache_total{test="...", cache="hit"\|"miss"}` |

**New Prometheus metrics (Grafana):**

- **Heal duration:** `histogram_quantile(0.95, rate(healix_heal_duration_seconds_bucket[5m]))` — p95 heal time (seconds).
- **Cache hit rate:** `sum(rate(healix_heal_cache_total{cache="hit"}[5m])) / sum(rate(healix_heal_cache_total[5m]))` — proportion of heals served from cache.

## Upcoming improvements (my backlog)

I keep this list so I can come back and tackle items one by one. When I finish one, I’ll move it to the Roadmap or Changelog and note it here.

1. **Smaller DOM sent to the model** — Trim or sample the DOM more aggressively before sending to Ollama (e.g. 10k chars, or only elements near the broken selector) to cut latency and tokens per heal.
2. **Async cache writes** — Write `cache.json` in a background thread or after the run so the test thread doesn’t block on disk I/O; reduces perceived heal latency.
3. **Single Ollama call when count > 1** — Try to get a “match exactly one” selector in the first prompt (e.g. stronger RULES in the prompt) so the scoped follow-up is needed less often; measure with the new metrics.
4. **DOM clean duration metric** — Time `get_clean_dom()` and expose it (e.g. in report or Prometheus) so I can see if DOM processing is a bottleneck.
5. **Optional: faster parser** — Try `lxml` as the BeautifulSoup parser for `get_clean_dom()` and benchmark; fall back to `html.parser` if not installed.
6. **Retry budget / backoff** — If a heal fails or confidence is low, consider a single retry with a shorter prompt or different temperature before giving up; document behaviour in README.
7. **Heal summary in terminal** — At session end, print a one-line summary (e.g. “N heals, X from cache, avg Ys”) so I can see efficiency without opening Grafana.

## Support

- **Issues**: [github.com/kunaal-ai/healix/issues](https://github.com/kunaal-ai/healix/issues)
- **Changelog**: See [Releases](https://github.com/kunaal-ai/healix/releases)

## Roadmap

- [ ] Support for more AI models (OpenAI, Anthropic)
- [ ] Visual regression testing
- [ ] Multi-browser support expansion
- [x] **Performance optimization** — lightweight scoped Ollama call when count > 1; heal duration & cache hit metrics (see [Performance & efficiency](#performance--efficiency))
- [ ] Plugin system for custom healing strategies

For more granular next steps I’m working through, see [Upcoming improvements (my backlog)](#upcoming-improvements-my-backlog) above.
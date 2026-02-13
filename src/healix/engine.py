import asyncio
import json
import os
import sys
import traceback
import requests
import subprocess
from playwright.async_api import async_playwright
from playwright.sync_api import expect
from bs4 import BeautifulSoup

class HealixError(Exception):
    """Base exception for Healix errors."""
    pass

class OllamaConnectionError(HealixError):
    """Raised when Ollama is not reachable."""
    pass

class BrowserNotInstalledError(HealixError):
    """Raised when Playwright browsers are not installed."""
    pass

class Healix:
    def __init__(self, model="qwen2.5-coder:7b"):
        self.model = model
        self.ollama_url = "http://localhost:11434/api/generate"
        # Prefer project-local .healix if we are in a project
        project_root = None
        current = os.getcwd()
        for marker in ['pyproject.toml', 'requirements.txt', 'setup.py', '.git']:
            if os.path.exists(os.path.join(current, marker)):
                project_root = current
                break
        if project_root:
            self.data_dir = os.path.join(project_root, ".healix")
        else:
            self.data_dir = os.path.join(os.path.expanduser("~"), ".healix")
        self.cache_file = os.path.join(self.data_dir, "cache.json")
        self.report_file = os.path.join(self.data_dir, "proposals.json")
        self._healed_selectors = {}
        self._ensure_dirs()
        self.cache = self._load_cache()
        self._check_ollama()

    def _ensure_dirs(self):
        os.makedirs(self.data_dir, exist_ok=True)

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self, selector, fixed_selector, browser="default", context_used=False):
        cache_key = f"{browser}::{selector}"
        if context_used:
            fixed_selector = f"CTX:{fixed_selector}"
        self.cache[cache_key] = fixed_selector
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def log_proposal(self, original, fixed, file_info, reason=""):
        proposals = []
        if os.path.exists(self.report_file):
            try:
                with open(self.report_file, 'r') as f:
                    proposals = json.load(f)
            except Exception:
                proposals = []
        proposals.append({
            "file": file_info.get("file"),
            "line": file_info.get("line"),
            "original_selector": original,
            "suggested_fix": fixed,
            "reasoning": reason,
            "status": "pending_review"
        })
        with open(self.report_file, 'w') as f:
            json.dump(proposals, f, indent=2)

    def get_clean_dom(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(["script", "style", "svg", "path", "iframe", "meta", "link", "noscript"]):
            tag.decompose()
        clean_tags = []
        text_elements = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'div', 'li', 'td', 'option']
        interactive_elements = ['input', 'button', 'a', 'label', 'form', 'select', 'textarea']
        for tag in soup.find_all(text_elements + interactive_elements):
            allowed = ['id', 'class', 'name', 'type', 'placeholder', 'aria-label', 'data-testid', 'role', 'value', 'title', 'alt']
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in allowed}
            if tag.name in interactive_elements:
                clean_tags.append(str(tag))
            elif tag.name in text_elements:
                text = tag.get_text(strip=True)
                if text:
                    clean_tags.append(f"<{tag.name} {' '.join(f'{k}={v}' for k,v in tag.attrs.items())}>{text}</{tag.name}>")
        return "\n".join(clean_tags)[:15000]

    async def get_fix(self, broken_selector, html, browser="chromium", error_msg="", target_context="", expected_text="", test_context=""):
        return self.get_fix_sync(broken_selector, html, browser, error_msg, target_context, expected_text, test_context)

    def get_fix_sync(self, broken_selector, html, browser="chromium", error_msg="", target_context="", expected_text="", test_context=""):
        cache_key = f"{browser}::{broken_selector}"
        if cache_key in self.cache and not error_msg:
            return {"selector": self.cache[cache_key], "conf": 1.0, "explanation": "Cache hit"}
        dom = self.get_clean_dom(html)
        context_block = ""
        if target_context:
            context_block = f"TARGET CONTEXT (What the test wants):\n{target_context}\n\n"
        if expected_text:
            context_block += f"ASSERTION: The test expects this element to HAVE the text: \"{expected_text}\". Return a selector for an element that CONTAINS this text.\n\n"
        if test_context:
            context_block += f"TEST CONTEXT: The test suggests: \"{test_context}\". Prefer selectors scoped to that area (e.g. #footerPanel for footer, #headerPanel for header).\n\n"
        prompt = (
            f"A Playwright test failed in {browser}.\n"
            f"The broken selector was: {broken_selector}\n"
            f"The error was: {error_msg}\n\n"
            f"{context_block}"
            f"Here are the ACTUAL elements currently on the page:\n{dom}\n\n"
            "RULES:\n"
            "1. You MUST return a CSS selector that matches ONE of the elements listed above.\n"
            "2. STRICT MODE: The selector must match EXACTLY ONE element. If a simple selector would match multiple, SCOPE IT (e.g. #footerPanel a[href*='about'], #headerPanel a).\n"
            "3. Do NOT invent selectors. Use id, class, [href], [aria-label], tag names. Prefer UNIQUE selectors.\n"
            "4. FOCUS on TARGET CONTEXT, ASSERTION, or TEST CONTEXT.\n"
            "5. CRITICAL: Return ONLY valid document.querySelector/CSS. Do NOT use :contains() or jQuery.\n\n"
            "Return JSON ONLY: {\"selector\": \"string\", \"explanation\": \"string\", \"conf\": float}"
        )
        raw_response = ""
        try:
            r = requests.post(self.ollama_url, json={
                "model": self.model, "prompt": prompt, "stream": False, "format": "json"
            }, timeout=60)
            r.raise_for_status()
            raw_response = (r.json().get("response") or "").strip()
            if not raw_response:
                return None
            if "```json" in raw_response:
                raw_response = raw_response.split("```json")[1].split("```")[0].strip()
            if "```" in raw_response:
                raw_response = raw_response.split("```")[0].strip()
            data = json.loads(raw_response)
            if not isinstance(data, dict):
                return None
            data.setdefault("selector", "")
            data.setdefault("explanation", "")
            if "conf" not in data or not isinstance(data["conf"], (int, float)):
                data["conf"] = 0.7
            sel = data["selector"]
            if ":contains(" in sel:
                import re as _re
                m = _re.search(r"^(\w*)\s*:contains\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*$", sel.strip())
                if m:
                    tag, text = m.group(1) or "*", m.group(2)
                    data["selector"] = f"{tag} >> text={text}" if tag != "*" else f"text={text}"
            return data
        except Exception:
            return None

    @staticmethod
    def patch(page):
        """
        Wraps a Playwright page (Sync or Async) to make all its locators self-healing.
        Usage: page = Healix.patch(page)
        """
        _patch_expect()
        return HealixPageProxy(page)


    def _check_ollama(self):
        """Verify Ollama is running at startup with a friendly error message."""
        try:
            requests.get("http://localhost:11434/api/tags", timeout=3)
        except requests.ConnectionError:
            print(
                "\n[Healix] ERROR: Cannot connect to Ollama.\n"
                "  Healix requires Ollama running locally for AI inference.\n\n"
                "  To fix this:\n"
                "    1. Install Ollama:  https://ollama.com/download\n"
                "    2. Start it:        ollama serve\n"
                "    3. Pull a model:    ollama pull qwen2.5-coder:7b\n"
            )
            raise OllamaConnectionError(
                "Ollama is not running. Start it with: ollama serve"
            )

def _patch_expect():
    """Monkeypatches playwright.sync_api.expect to support SmartLocatorProxy."""
    from playwright.sync_api import expect as original_expect
    import playwright.sync_api

    # Avoid double patching
    if getattr(playwright.sync_api.expect, "_is_healix_patched", False):
        return

    def smart_expect(actual, **kwargs):
        assertion = original_expect(actual, **kwargs)
        if isinstance(actual, SmartLocatorProxy):
            return SmartAssertionProxy(assertion, actual)
        return assertion

    smart_expect._is_healix_patched = True
    playwright.sync_api.expect = smart_expect


class SmartAssertionProxy:
    """Proxies Playwright assertions to trigger healing on failure."""
    def __init__(self, assertion, smart_locator):
        self._assertion = assertion
        self._smart_locator = smart_locator

    def __getattr__(self, name):
        attr = getattr(self._assertion, name)
        if callable(attr):
            return self._wrap_assertion(attr, name)
        return attr

    def _wrap_assertion(self, method, name):
        def wrapper(*args, **kwargs):
            try:
                return method(*args, **kwargs)
            except (AssertionError, TimeoutError) as e:
                # Heal and retry; _heal_and_retry performs the expect.* retry and returns its result
                try:
                    return self._smart_locator._heal_and_retry(f"expect.{name}", *args, **kwargs)
                except Exception as heal_error:
                    print(f"[Healix] [ERROR] Healing failed during assertion: {heal_error}")
                    raise e
        return wrapper

class HealixPageProxy:
    """Proxies a Playwright Page to intercept .locator() calls."""
    def __init__(self, page):
        self._page = page
        print(f"\n[Healix] [INFO] Zero-Refactor healing is ACTIVE.")

    def locator(self, selector, **kwargs):
        hx = _get_healix()
        new_sel = None
        session = getattr(hx, "_healed_selectors", None) or {}
        # Plugin may set module-level fallback when fixture re-runs after retry
        _pytest_healed = getattr(sys.modules.get(__name__, object()), "_pytest_healed_selectors", None) or {}
        if selector in session:
            new_sel = session[selector]
        elif selector in _pytest_healed:
            new_sel = _pytest_healed[selector]
        browser_name = self._page.context.browser.browser_type.name
        cache_key = f"{browser_name}::{selector}"
        if not new_sel and cache_key in hx.cache:
            new_sel = hx.cache[cache_key]
        context_mode = False
        if new_sel:
            if new_sel.startswith("CTX:"):
                print(f"[Healix] [INFO] Using healed selector for '{selector}' -> {new_sel[4:]!r} (context_mode)")
                new_sel = new_sel[4:]
                context_mode = True
            else:
                print(f"[Healix] [INFO] Using healed selector for '{selector}' -> {new_sel!r}")
            selector = new_sel
        loc = self._page.locator(selector, **kwargs)
        return SmartLocatorProxy(loc, self._page, selector, context_mode=context_mode)

    # Intercept high-level actions to ensure they are healed too!
    def click(self, selector, **kwargs):
        return self.locator(selector).click(**kwargs)

    def fill(self, selector, value, **kwargs):
        return self.locator(selector).fill(value, **kwargs)
    
    def check(self, selector, **kwargs):
        return self.locator(selector).check(**kwargs)
    
    def uncheck(self, selector, **kwargs):
        return self.locator(selector).uncheck(**kwargs)

    def hover(self, selector, **kwargs):
        return self.locator(selector).hover(**kwargs)

    def type(self, selector, text, **kwargs):
        return self.locator(selector).type(text, **kwargs)

    def press(self, selector, key, **kwargs):
        return self.locator(selector).press(key, **kwargs)

    def select_option(self, selector, value, **kwargs):
        return self.locator(selector).select_option(value, **kwargs)

    def dblclick(self, selector, **kwargs):
        return self.locator(selector).dblclick(**kwargs)

    def __getattr__(self, name):
        return getattr(self._page, name)

class SmartLocatorProxy:
    """Proxies a Playwright Locator to add transparent self-healing."""
    def __init__(self, locator, page, selector, context_mode=False):
        self._locator = locator
        self._page = page
        self._selector = selector
        self._context_mode = context_mode

    @property
    def __class__(self):
        # satisfy isinstance(loc, Locator)
        return self._locator.__class__

    def __call__(self, *args, **kwargs):
        # When chaining (context_mode) or when inner Locator isn't callable, return self so proxy() is a no-op
        if getattr(self, "_context_mode", False):
            return self
        if not callable(self._locator):
            return self
        return self._wrap_action(self._locator.__call__, "__call__")(*args, **kwargs)

    def __getattr__(self, name):
        if name in ["_locator", "_page", "_selector", "_context_mode", "_wrap_action", "_heal_and_retry"]:
            return super().__getattribute__(name)

        # When context_mode is set, chainable methods return self so .click() etc. run on the healed locator
        if self._context_mode and name in ("locator", "get_by_role", "get_by_text", "get_by_label", "get_by_placeholder", "get_by_title", "get_by_alt_text", "first", "last", "nth"):
            return self

        # Pass thru to original locator
        attr = getattr(self._locator, name)
        
        # If accessing properties like .first, .last, .nth(), wrap the result
        if name in ["first", "last", "nth"]:
            if callable(attr):
                def nth_wrapper(*args, **kwargs):
                    return SmartLocatorProxy(attr(*args, **kwargs), self._page, f"{self._selector} >> {name}")
                return nth_wrapper
            return SmartLocatorProxy(attr, self._page, f"{self._selector} >> {name}")
            
        if callable(attr):
            return self._wrap_action(attr, name)
        return attr

    def _wrap_action(self, method, name):
        def wrapper(*args, **kwargs):
            try:
                return method(*args, **kwargs)
            except Exception as e:
                # Common failure points for selectors
                err_str = str(e).lower()
                if any(x in err_str for x in ["timeout", "not found", "waiting for", "no element", "visible"]):
                    return self._heal_and_retry(name, *args, **kwargs)
                raise e
        
        # Methods that often return booleans/counts silently
        if name in ["is_visible", "is_hidden", "count", "is_enabled", "is_disabled"]:
            def smart_check_wrapper(*args, **kwargs):
                val = method(*args, **kwargs)
                if (name == "count" and val == 0) or (name == "is_visible" and not val):
                    try:
                        # Only try to heal if the original check fails
                        return self._heal_and_retry(name, *args, **kwargs)
                    except:
                        return val 
                return val
            return smart_check_wrapper
            
        return wrapper

    def _heal_and_retry(self, name, *args, **kwargs):
        """Internal logic to trigger AI healing and retry the action."""
        # Pass expected text from assertion args (e.g. to_have_text("Contact Us"))
        if name.startswith("expect.") and "to_have_text" in name and args:
            kwargs.setdefault("_expected_text", args[0] if isinstance(args[0], str) else "")

        target_context = kwargs.pop("_target_context", "") or ""
        expected_text = kwargs.pop("_expected_text", "") or ""

        print(f"[Healix] [HEAL] Selector '{self._selector}' failed during '{name}'. Healing...")
        hx = _get_healix()
        html = self._page.content()
        browser = self._page.context.browser.browser_type.name

        print(f"[Healix] [INFO] Analyzing DOM with AI...")
        fix = hx.get_fix_sync(
            self._selector, html, browser=browser,
            error_msg=f"Element not found during {name}",
            target_context=target_context or None,
            expected_text=expected_text or None,
        )

        if not fix or fix.get("conf", 0) <= 0.6:
            raise RuntimeError(f"[Healix] [ERROR] Failed to heal selector: {self._selector}")

        new_sel = fix["selector"]
        explanation = fix.get("explanation", "") or ""
        context_used = "context" in explanation.lower() or "scope" in explanation.lower()

        print(f"[Healix] [SUCCESS] Found fix: {new_sel} (conf: {fix['conf']})")
        print(f"[Healix] [INFO] Root Cause: {explanation}")
        hx.log_proposal(self._selector, new_sel, {"file": "PageObject", "line": 0}, explanation)
        hx._save_cache(self._selector, new_sel, browser=browser, context_used=context_used)

        self._locator = self._page.locator(new_sel)
        self._selector = new_sel
        if context_used:
            self._context_mode = True

        # Assertion: expect(loc).to_have_text("...") etc.
        if name.startswith("expect."):
            assertion_method = name.split(".", 1)[1]
            print(f"[Healix] [INFO] Retrying expect.{assertion_method} with healed selector...")
            return getattr(expect(self._locator), assertion_method)(*args, **kwargs)

        new_method = getattr(self._locator, name)
        print(f"[Healix] [INFO] Retrying '{name}' with healed selector...")
        return new_method(*args, **kwargs)

_hx = None
# Pytest plugin sets this so healed selectors survive fixture re-run on retry
_pytest_healed_selectors = {}

def _get_healix():
    """Lazy initialization — only connects to Ollama when first needed."""
    global _hx
    if _hx is None:
        _hx = Healix()
    return _hx

async def smart_locator(page, selector, timeout=2000):
    """
    Returns a self-healing Playwright locator.
    If the initial selector fails, it uses AI to find a successor.
    Useful for Page Objects and assertions like expect(locator).to_have_text().
    """
    browser = page.context.browser.browser_type.name
    hx = _get_healix()
    
    # Try to check cache first
    cached = hx.cache.get(f"{browser}::{selector}")
    if cached:
        print(f"[Healix] [INFO] Cache hit for '{selector}' -> '{cached}'")
        return page.locator(cached)

    try:
        # Check if the element exists by waiting for it briefly
        await page.wait_for_selector(selector, state="attached", timeout=timeout)
        return page.locator(selector)
    except Exception as e:
        print(f"[Healix] [HEAL] Locator '{selector}' not found. Healing...")
        html = await page.content()
        fix = await hx.get_fix(selector, html, browser=browser, error_msg=str(e)[:100])
        
        if fix and fix.get("conf", 0) > 0.6:
            new_sel = fix["selector"]
            print(f"[Healix] [SUCCESS] Result: {new_sel} (conf: {fix.get('conf')})")
            
            # If high confidence, cache it immediately so next run is fast
            if fix.get("conf", 0) > 0.8:
                caller = traceback.extract_stack()[-2]
                file_info = {"file": caller.filename, "line": caller.lineno}
                hx.log_proposal(selector, new_sel, file_info, fix.get("explanation"))
                hx._save_cache(selector, new_sel, browser=browser)
                
            return page.locator(new_sel)
        else:
            # Fallback to original locator so natural Playwright error triggers if AI fails
            return page.locator(selector)

async def smart_click(page, selector, text_to_fill=None, timeout=2000):
    caller = traceback.extract_stack()[-2]
    file_info = {"file": caller.filename, "line": caller.lineno}
    browser = page.context.browser.browser_type.name
    hx = _get_healix()

    try:
        if text_to_fill:
            await page.fill(selector, text_to_fill, timeout=timeout)
        else:
            await page.click(selector, timeout=timeout)
    except Exception as e:
        print(f"[Healix] [HEAL] Healing '{selector}'...")
        html = await page.content()
        fix = await hx.get_fix(selector, html, browser=browser, error_msg=str(e)[:100])
        
        if fix and fix.get("conf", 0) > 0.6:
            new_sel = fix["selector"]
            print(f"[Healix] [INFO] Trying healed selector: {new_sel} (conf: {fix.get('conf')})")
            try:
                if text_to_fill: await page.fill(new_sel, text_to_fill, timeout=timeout)
                else: await page.click(new_sel, timeout=timeout)
                hx.log_proposal(selector, new_sel, file_info, fix.get("explanation"))
                hx._save_cache(selector, new_sel, browser=browser)
                print(f"[Healix] [SUCCESS] Fixed with: {new_sel}")
            except Exception as heal_err:
                print(f"[Healix] [ERROR] Healed selector failed: {str(heal_err)[:80]}")
                print(f"[Healix] [INFO] Plan B: Re-querying AI with failure feedback...")
                retry = await hx.get_fix(selector, html, browser=browser,
                    error_msg=f"Your suggestion '{new_sel}' failed: {str(heal_err)[:60]}")
                if retry and retry.get("conf", 0) > 0.6:
                    retry_sel = retry["selector"]
                    print(f"[Healix] [INFO] Plan B selector: {retry_sel} (conf: {retry.get('conf')})")
                    try:
                        if text_to_fill: await page.fill(retry_sel, text_to_fill, timeout=timeout)
                        else: await page.click(retry_sel, timeout=timeout)
                        hx.log_proposal(selector, retry_sel, file_info, retry.get("explanation"))
                        hx._save_cache(selector, retry_sel, browser=browser)
                        print(f"[Healix] [SUCCESS] Plan B succeeded with: {retry_sel}")
                    except:
                        print(f"[Healix] [ERROR] Plan B also failed. Hard failure.")
                        raise e
                else:
                    raise e
        else:
            print(f"[Healix] [INFO] No viable fix found (conf: {fix.get('conf') if fix else 'N/A'})")
            raise e

def install_browsers():
    """Ensure Playwright browsers are installed before running."""
    print("[Healix] Verifying browser binaries...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "firefox"],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        print(
            "\n[Healix] ERROR: Failed to install Playwright browsers.\n"
            f"  Details: {e.stderr.strip() if e.stderr else 'Unknown error'}\n\n"
            "  To fix this manually:\n"
            "    pip install playwright\n"
            "    playwright install chromium firefox\n"
        )
        raise BrowserNotInstalledError(
            "Playwright browsers could not be installed. "
            "Run manually: playwright install chromium firefox"
        )
    except FileNotFoundError:
        print(
            "\n[Healix] ERROR: Playwright is not installed.\n\n"
            "  To fix this:\n"
            "    pip install playwright\n"
            "    playwright install chromium firefox\n"
        )
        raise BrowserNotInstalledError(
            "Playwright not found. Install with: pip install playwright"
        )

def main():
    if len(sys.argv) < 2:
        print("Healix AI Agent\nUsage: healix <test_file.py>")
        return
    
    test_file = sys.argv[1]
    if not os.path.exists(test_file):
        print(f"Error: {test_file} not found.")
        return

    # Check for playwright binaries
    try:
        install_browsers()
    except BrowserNotInstalledError:
        return

    # Set PYTHONPATH to include the current directory so imports work for the user
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd() + os.pathsep + env.get("PYTHONPATH", "")
    
    subprocess.run([sys.executable, test_file], env=env)

if __name__ == "__main__":
    main()
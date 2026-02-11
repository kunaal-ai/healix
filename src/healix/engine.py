import asyncio
import json
import os
import sys
import traceback
import requests
import subprocess
from playwright.async_api import async_playwright
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
        self.data_dir = os.path.join(os.path.expanduser("~"), ".healix")
        self.cache_file = os.path.join(self.data_dir, "cache.json")
        self.report_file = os.path.join(self.data_dir, "proposals.json")
        self._ensure_dirs()
        self.cache = self._load_cache()
        self._check_ollama()

    @staticmethod
    def patch(page):
        """
        Wraps a Playwright page (Sync or Async) to make all its locators self-healing.
        Usage: page = Healix.patch(page)
        """
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

    def _ensure_dirs(self):
        os.makedirs(self.data_dir, exist_ok=True)

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self, selector, fixed_selector, browser="default"):
        cache_key = f"{browser}::{selector}"
        self.cache[cache_key] = fixed_selector
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def log_proposal(self, original, fixed, file_info, reason=""):
        proposals = []
        if os.path.exists(self.report_file):
            with open(self.report_file, 'r') as f:
                try: proposals = json.load(f)
                except: proposals = []
        
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
        # Semantic elements often used for text assertions
        text_elements = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'div', 'li', 'td', 'option']
        # Interactive elements
        interactive_elements = ['input', 'button', 'a', 'label', 'form', 'select', 'textarea']
        
        for tag in soup.find_all(text_elements + interactive_elements):
            allowed = ['id', 'class', 'name', 'type', 'placeholder', 'aria-label', 'data-testid', 'role', 'value', 'title', 'alt']
            # Keep only allowed attributes
            tag.attrs = {k: v for k, v in tag.attrs.items() if k in allowed}
            
            # For interactive elements, we want the outer HTML (attributes are key)
            if tag.name in interactive_elements:
                clean_tags.append(str(tag))
            # For text elements, we ONLY want them if they satisfy the search or are close to it
            elif tag.name in text_elements:
                text = tag.get_text(strip=True)
                if text: # Only keep text nodes that are not empty
                    # Simplified representation for token efficiency: <tag attrs...>text</tag>
                    clean_tags.append(f"<{tag.name} {' '.join(f'{k}={v}' for k,v in tag.attrs.items())}>{text}</{tag.name}>")
            
        return "\n".join(clean_tags)[:15000] # Increased token limit for text context

    async def get_fix(self, broken_selector, html, browser="chromium", error_msg=""):
        return self.get_fix_sync(broken_selector, html, browser, error_msg)

    def get_fix_sync(self, broken_selector, html, browser="chromium", error_msg=""):
        cache_key = f"{browser}::{broken_selector}"
        if cache_key in self.cache and not error_msg:
            return {"selector": self.cache[cache_key], "conf": 1.0, "explanation": "Cache hit"}

        dom = self.get_clean_dom(html)
        prompt = (
            f"A Playwright test failed in {browser}.\n"
            f"The broken selector was: {broken_selector}\n"
            f"The error was: {error_msg}\n\n"
            f"Here are the ACTUAL elements currently on the page:\n{dom}\n\n"
            "RULES:\n"
            "1. You MUST return a CSS selector that matches one of the elements listed above.\n"
            "2. Do NOT invent selectors. Pick from the DOM provided.\n"
            "3. FOCUS on the target element. If the selector is '#div h1', find the 'h1'.\n"
            "4. Look for semantic matches: Text content, Aria labels, IDs, Classes.\n"
            "5. Provide a brief Root Cause Analysis explaining why the original selector broke.\n\n"
            "Return JSON ONLY: {\"selector\": \"string\", \"explanation\": \"string\", \"conf\": float}"
        )
        
        try:
            r = requests.post(self.ollama_url, json={
                "model": self.model, "prompt": prompt, "stream": False, "format": "json"
            }, timeout=30)
            
            raw_response = r.json().get("response", "{}").strip()
            if "```json" in raw_response:
                raw_response = raw_response.split("```json")[1].split("```")[0].strip()
            
            return json.loads(raw_response)
        except Exception:
            return None

class HealixPageProxy:
    """Proxies a Playwright Page to intercept .locator() calls."""
    def __init__(self, page):
        self._page = page
        print(f"\n[Healix] 🚀 Page patched! Zero-Refactor healing is ACTIVE.")

    def locator(self, selector, **kwargs):
        loc = self._page.locator(selector, **kwargs)
        return SmartLocatorProxy(loc, self._page, selector)

    def __getattr__(self, name):
        return getattr(self._page, name)

class SmartLocatorProxy:
    """Proxies a Playwright Locator to add transparent self-healing."""
    def __init__(self, locator, page, selector):
        self._locator = locator
        self._page = page
        self._selector = selector

    @property
    def __class__(self):
        # Trick isinstance() checks (essential for expect() compatibility)
        return self._locator.__class__

    def __getattr__(self, name):
        # Pass through internal playwright fields (_impl, etc)
        attr = getattr(self._locator, name)
        
        # If accessing properties like .first, .last, .nth(), wrap the result
        if name in ["first", "last", "nth"]:
            if callable(attr):
                def wrapper(*args, **kwargs):
                    return SmartLocatorProxy(attr(*args, **kwargs), self._page, self._selector)
                return wrapper
            return SmartLocatorProxy(attr, self._page, self._selector)
            
        if callable(attr):
            return self._wrap_action(attr, name)
        return attr

    def _wrap_action(self, method, name):
        def wrapper(*args, **kwargs):
            try:
                # Try original action
                return method(*args, **kwargs)
            except Exception as e:
                # Check for "not found" or "timeout" errors
                if any(x in str(e).lower() for x in ["timeout", "not found", "waiting for", "no element"]):
                    return self._heal_and_retry(name, *args, **kwargs)
                raise e
        
        # Special case: methods that return booleans or numbers (is_visible, count)
        # These methods often FAIL SILENTLY (returning False) if the selector is wrong.
        # We want them to trigger healing too!
        if name in ["is_visible", "is_hidden", "count", "is_enabled", "is_disabled"]:
            def smart_check_wrapper(*args, **kwargs):
                val = method(*args, **kwargs)
                # If it's False or 0, it MIGHT be because the selector is broken.
                # Do a quick check: does the element exist at all?
                if (name == "count" and val == 0) or (name == "is_visible" and not val):
                    # We try to "heal" if we think the selector is truly missing
                    try:
                        return self._heal_and_retry(name, *args, **kwargs)
                    except:
                        return val # Fallback to original silent failure if healing fails
                return val
            return smart_check_wrapper
            
        return wrapper

    def _heal_and_retry(self, name, *args, **kwargs):
        """Internal logic to trigger AI healing and retry the action."""
        print(f"[Healix] 🩹 Locator '{self._selector}' failed ({name}). Healing...")
        hx = _get_healix()
        
        # Sync/Async detection
        # For Sync API, content() is a string. For Async, it's a coroutine.
        is_async = asyncio.iscoroutinefunction(self._page.content)
        if is_async:
            raise RuntimeError("Async proxy not fully implemented yet. Use smart_locator() direct.")

        html = self._page.content()
        browser = self._page.context.browser.browser_type.name
        fix = hx.get_fix_sync(self._selector, html, browser=browser, error_msg=f"Element not found during {name}")
        
        if fix and fix.get("conf", 0) > 0.6:
            new_sel = fix["selector"]
            print(f"[Healix] ✨ Found fix: {new_sel} (conf: {fix['conf']})")
            
            hx.log_proposal(self._selector, new_sel, {"file": "PageObject", "line": 0}, fix.get("explanation"))
            hx._save_cache(self._selector, new_sel, browser=browser)
            
            # Update internal locator and retry the call
            self._locator = self._page.locator(new_sel)
            new_method = getattr(self._locator, name)
            print(f"[Healix] 🔄 Retrying {name} with new selector...")
            return new_method(*args, **kwargs)
        
        raise RuntimeError(f"[Healix] Failed to heal selector: {self._selector}")

_hx = None

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
        print(f"[Healix] Cache hit for '{selector}' -> '{cached}'")
        return page.locator(cached)

    try:
        # Check if the element exists by waiting for it briefly
        await page.wait_for_selector(selector, state="attached", timeout=timeout)
        return page.locator(selector)
    except Exception as e:
        print(f"[Healix] Locator '{selector}' not found. Healing...")
        html = await page.content()
        fix = await hx.get_fix(selector, html, browser=browser, error_msg=str(e)[:100])
        
        if fix and fix.get("conf", 0) > 0.6:
            new_sel = fix["selector"]
            print(f"[Healix] Result: {new_sel} (conf: {fix.get('conf')})")
            
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
        print(f"[Healix] Healing '{selector}'...")
        html = await page.content()
        fix = await hx.get_fix(selector, html, browser=browser, error_msg=str(e)[:100])
        
        if fix and fix.get("conf", 0) > 0.6:
            new_sel = fix["selector"]
            print(f"[Healix] Trying healed selector: {new_sel} (conf: {fix.get('conf')})")
            try:
                if text_to_fill: await page.fill(new_sel, text_to_fill, timeout=timeout)
                else: await page.click(new_sel, timeout=timeout)
                hx.log_proposal(selector, new_sel, file_info, fix.get("explanation"))
                hx._save_cache(selector, new_sel, browser=browser)
                print(f"[Healix] ✅ Fixed with: {new_sel}")
            except Exception as heal_err:
                print(f"[Healix] ❌ Healed selector failed: {str(heal_err)[:80]}")
                print(f"[Healix] Plan B: Re-querying AI with failure feedback...")
                retry = await hx.get_fix(selector, html, browser=browser,
                    error_msg=f"Your suggestion '{new_sel}' failed: {str(heal_err)[:60]}")
                if retry and retry.get("conf", 0) > 0.6:
                    retry_sel = retry["selector"]
                    print(f"[Healix] Plan B selector: {retry_sel} (conf: {retry.get('conf')})")
                    try:
                        if text_to_fill: await page.fill(retry_sel, text_to_fill, timeout=timeout)
                        else: await page.click(retry_sel, timeout=timeout)
                        hx.log_proposal(selector, retry_sel, file_info, retry.get("explanation"))
                        hx._save_cache(selector, retry_sel, browser=browser)
                        print(f"[Healix] ✅ Plan B succeeded with: {retry_sel}")
                    except:
                        print(f"[Healix] ❌ Plan B also failed. Hard failure.")
                        raise e
                else:
                    raise e
        else:
            print(f"[Healix] No viable fix found (conf: {fix.get('conf') if fix else 'N/A'})")
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
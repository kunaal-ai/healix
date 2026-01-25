import asyncio
import json
import os
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

class Healix:
    def __init__(self, model="qwen2.5-coder:7b"):
        self.model = model
        self.ollama_url = "http://localhost:11434/api/generate"
        self.cache_file = "data/healix_cache.json"
        self._ensure_data_dir()
        self.cache = self._load_cache()
        print(f"Healix Initialized [Model: {self.model}]")

    def _ensure_data_dir(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    print(f"Loaded {len(data)} healed selectors from cache.")
                    return data
            except:
                print("Cache file corrupted. Starting with empty memory.")
                return {}
        return {}

    def _save_cache(self, selector, fixed_selector):
        self.cache[selector] = fixed_selector
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)
        print(f"Permanent Fix Saved: '{selector}' -> '{fixed_selector}'")

    def get_clean_dom(self, html):
        print("Cleaning DOM to reduce token noise...")
        soup = BeautifulSoup(html, 'html.parser')
        # Remove junk tags
        for tag in soup(["script", "style", "svg", "path", "iframe"]):
            tag.decompose()
        
        # Keep interactive elements and their attributes
        clean_tags = []
        for tag in soup.find_all(['input', 'button', 'a', 'label', 'form']):
            # Clean up attributes to only vital ones
            attrs = {k: v for k, v in tag.attrs.items() if k in ['id', 'class', 'name', 'type', 'placeholder', 'href']}
            tag.attrs = attrs
            clean_tags.append(str(tag))
            
        cleaned = "\n".join(clean_tags)[:8000]
        print(f"DOM Cleaned. Size: {len(cleaned)} chars.")
        return cleaned

    async def observe_state(self, page):
        print("Observing page state for visible errors...")
        content = await page.content()
        errors = ["error", "invalid", "failed", "required", "timeout"]
        found_errors = [e for e in errors if e in content.lower()]
        if found_errors:
            print(f"Found potential errors on page: {found_errors}")
        return found_errors

    async def get_fix(self, broken_selector, html, error_msg="", page_errors=None):
        # Check if I already solved this in this session
        if broken_selector in self.cache and not error_msg:
            print(f"Cache Hit! Using known fix for '{broken_selector}'")
            return {"selector": self.cache[broken_selector], "action": "click", "conf": 1.0}

        print(f"Querying AI for fix [Broken: {broken_selector}]...")
        dom = self.get_clean_dom(html)
        context = f"Technical Error: {error_msg}\n" if error_msg else ""
        if page_errors:
            context += f"Visible Page Errors: {', '.join(page_errors)}"
        
        prompt = (
            f"You are a QA Automation Agent. A test failed on selector: {broken_selector}\n"
            f"{context}\n"
            f"Available Elements:\n{dom}\n\n"
            "Task: Find the correct CSS selector for the intended interaction.\n"
            "Constraints: Return valid CSS selectors only. Focus on IDs or Names.\n"
            "Return JSON ONLY: {\"selector\": \"string\", \"action\": \"click|fill|scroll\", \"conf\": float}"
        )
        
        try:
            r = requests.post(self.ollama_url, json={
                "model": self.model, "prompt": prompt, "stream": False, "format": "json"
            }, timeout=30)
            
            res = json.loads(r.json().get("response", "{}"))
            if res.get("conf", 0) > 0.7:
                print(f"AI Suggestion Received: {res['selector']} (Confidence: {res['conf']})")
                if not error_msg:
                    self._save_cache(broken_selector, res["selector"])
                return res
            else:
                print(f"AI Confidence too low: {res.get('conf', 0)}")
        except Exception as e:
            print(f"Healix API connection failed: {e}")
        return None

hx = Healix()

async def smart_click(page, selector, text_to_fill=None):
    """
    Enhanced smart action with detailed terminal tracking.
    """
    print(f"\n🚀 Executing Action: {'Fill' if text_to_fill else 'Click'} on '{selector}'")
    try:
        if text_to_fill:
            await page.fill(selector, text_to_fill, timeout=2000)
        else:
            await page.click(selector, timeout=2000)
        print(f"Step Success: '{selector}' worked perfectly.")
    except Exception as e:
        print(f"Action Failed. Initiating Healix Recovery...")
        
        page_errors = await hx.observe_state(page)
        html = await page.content()
        
        fix = await hx.get_fix(selector, html, error_msg=str(e)[:100], page_errors=page_errors)
        
        if fix and fix.get("conf", 0) > 0.6:
            new_sel = fix["selector"]
            action = fix.get("action", "click")
            print(f"Healix Plan A: Attempting '{action}' with '{new_sel}'")
            
            try:
                if text_to_fill or action == "fill":
                    val = text_to_fill if text_to_fill else "auto_filled"
                    await page.fill(new_sel, val, timeout=3000)
                elif action == "scroll":
                    print("Action: Scrolling element into view first...")
                    await page.locator(new_sel).scroll_into_view_if_needed()
                    await page.click(new_sel)
                else:
                    await page.click(new_sel, timeout=3000)
                
                print(f"Recovery Successful! Test continued via '{new_sel}'")
            except Exception as e2:
                print(f"Plan A Failed: {str(e2)[:50]}")
                print("Starting Plan B (Error Feedback Loop)...")
                retry = await hx.get_fix(selector, html, error_msg=str(e2)[:100])
                if retry:
                    print(f"Healix Plan B: Final attempt with '{retry['selector']}'")
                    await page.click(retry['selector'], timeout=3000)
                    print("Plan B Succeeded! Crisis averted.")
        else:
            print("Healix failed to find a reliable fix. Hard failure.")
            raise Exception(f"Healix failed to heal: {selector}")
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
        self.cache_file = "healix_cache.json"
        self.cache = self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_cache(self, selector, fixed_selector):
        self.cache[selector] = fixed_selector
        # I'm saving this to a local JSON so the engine gets faster over time
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def get_clean_dom(self, html):
        # I strip out the heavy stuff like scripts and styles to save tokens
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(["script", "style", "svg", "path", "iframe"]):
            tag.decompose()
        
        # Masking PII so I'm not sending sensitive user data to the model
        for text in soup.find_all(string=True):
            if text.parent.name not in ['button', 'a', 'label', 'input']:
                text.replace_with("[MASKED]")
        return soup.get_text()[:8000]

    async def observe_state(self, page):
        """
        I use this to check the current 'health' of the page.
        Is there a visible error message or a loading spinner?
        """
        content = await page.content()
        # I'm looking for common error keywords to give the AI more context
        errors = ["error", "invalid", "failed", "required", "timeout"]
        found_errors = [e for e in errors if e in content.lower()]
        return found_errors

    async def get_fix(self, broken_selector, html, error_msg="", page_errors=None):
        # Check if I already solved this bug earlier in the run
        if broken_selector in self.cache and not error_msg:
            return {"selector": self.cache[broken_selector], "conf": 1.0}

        dom = self.get_clean_dom(html)
        
        # Context includes both the technical error and what's visible on screen
        context = f"Technical Error: {error_msg}\n" if error_msg else ""
        if page_errors:
            context += f"Visible Page Errors: {', '.join(page_errors)}"
        
        prompt = (
            f"Broken selector: {broken_selector}\n"
            f"{context}\n"
            f"DOM: {dom}\n"
            "Analyze if the selector changed or if a different action is needed (like scrolling).\n"
            "Return JSON ONLY: {\"selector\": \"string\", \"action\": \"click|type|scroll\", \"conf\": float, \"explanation\": \"string\"}"
        )
        
        try:
            r = requests.post(self.ollama_url, json={
                "model": self.model, "prompt": prompt, "stream": False, "format": "json"
            }, timeout=30)
            
            res = json.loads(r.json().get("response", "{}"))
            if res.get("conf", 0) > 0.8 and res.get("action") == "click":
                self._save_cache(broken_selector, res["selector"])
            return res
        except Exception as e:
            print(f"Healix API connection failed: {e}")
            return None

# Singleton instance for easy import in test files
hx = Healix()

async def smart_click(page, selector):
    """
    The Agentic Loop: Observe -> Act -> Verify -> Correct.
    """
    try:
        await page.click(selector, timeout=2000)
    except Exception as e:
        print(f"Selector '{selector}' failed. Starting Healix Agentic recovery...")
        
        # 1. Observe
        page_errors = await hx.observe_state(page)
        html = await page.content()
        
        # 2. Reason (Ask AI)
        fix = await hx.get_fix(selector, html, error_msg=str(e), page_errors=page_errors)
        
        if fix and fix.get("conf", 0) > 0.7:
            new_sel = fix["selector"]
            action = fix.get("action", "click")
            
            print(f"Healix Action [{action}]: {new_sel}")
            
            try:
                if action == "scroll":
                    await page.locator(new_sel).scroll_into_view_if_needed()
                    await page.click(new_sel)
                else:
                    await page.click(new_sel, timeout=3000)
                
                print("🎉 Agent successfully bypassed the failure.")
            except Exception as e2:
                # Plan B: Deeper correction
                print("Initial fix failed. Retrying with full error context...")
                retry_fix = await hx.get_fix(selector, html, error_msg=str(e2))
                
                if retry_fix:
                    print(f"Plan B selector: {retry_fix['selector']}")
                    await page.click(retry_fix['selector'])
                    print("🎉 Successfully self-corrected via Plan B.")
        else:
            raise Exception("Healix could not reliably determine a fix.")
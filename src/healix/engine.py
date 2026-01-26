import asyncio
import json
import os
import traceback
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

class Healix:
    def __init__(self, model="qwen2.5-coder:7b"):
        self.model = model
        self.ollama_url = "http://localhost:11434/api/generate"
        self.cache_file = "data/healix_cache.json"
        self.report_file = "data/healix_proposals.json"
        self._ensure_dirs()
        self.cache = self._load_cache()
        print(f"Healix Initialized [Model: {self.model}]")

    def _ensure_dirs(self):
        os.makedirs("data", exist_ok=True)

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    print(f"Loaded {len(data)} healed selectors from cache.")
                    return data
            except:
                print("Warning: Cache file corrupted. Starting with empty memory.")
                return {}
        return {}

    def _save_cache(self, selector, fixed_selector):
        self.cache[selector] = fixed_selector
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)
        print(f"Permanent Fix Saved: '{selector}' -> '{fixed_selector}'")

    def log_proposal(self, original, fixed, file_info):
        """
        Milestone 6: Track where the fix belongs in the source code.
        """
        proposals = []
        if os.path.exists(self.report_file):
            with open(self.report_file, 'r') as f:
                try:
                    proposals = json.load(f)
                except:
                    proposals = []
        
        proposals.append({
            "file": file_info.get("file"),
            "line": file_info.get("line"),
            "original_selector": original,
            "suggested_fix": fixed,
            "status": "pending_review"
        })
        
        with open(self.report_file, 'w') as f:
            json.dump(proposals, f, indent=2)
        print(f"Code Change Proposal logged for: {file_info.get('file')}:{file_info.get('line')}")

    def get_clean_dom(self, html):
        print("Cleaning DOM to reduce token noise...")
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(["script", "style", "svg", "path", "iframe"]):
            tag.decompose()
        
        clean_tags = []
        for tag in soup.find_all(['input', 'button', 'a', 'label', 'form']):
            attrs = {k: v for k, v in tag.attrs.items() if k in ['id', 'class', 'name', 'type', 'placeholder', 'href']}
            tag.attrs = attrs
            clean_tags.append(str(tag))
            
        cleaned = "\n".join(clean_tags)[:8000]
        print(f"DOM Cleaned. Size: {len(cleaned)} characters.")
        return cleaned

    async def observe_state(self, page):
        print("Observing page state for visible errors...")
        content = await page.content()
        error_keywords = ["error", "invalid", "failed", "required", "timeout"]
        found_errors = [e for e in error_keywords if e in content.lower()]
        if found_errors:
            print(f"Found potential errors on page: {found_errors}")
        return found_errors

    async def get_fix(self, broken_selector, html, error_msg="", page_errors=None):
        if broken_selector in self.cache and not error_msg:
            print(f"Cache Hit: Using known fix for '{broken_selector}'")
            return {"selector": self.cache[broken_selector], "action": "click", "conf": 1.0}

        print(f"Querying AI for fix [Broken Selector: {broken_selector}]...")
        dom = self.get_clean_dom(html)
        context = f"Technical Error: {error_msg}\n" if error_msg else ""
        if page_errors:
            context += f"Visible Page Errors: {', '.join(page_errors)}"
        
        prompt = (
            f"You are a QA Automation Agent. A test failed on: {broken_selector}\n"
            f"{context}\n"
            f"Elements:\n{dom}\n"
            "Return JSON ONLY: {\"selector\": \"string\", \"action\": \"click|fill\", \"conf\": float}"
        )
        
        try:
            r = requests.post(self.ollama_url, json={
                "model": self.model, "prompt": prompt, "stream": False, "format": "json"
            }, timeout=30)
            res = json.loads(r.json().get("response", "{}"))
            if res.get("conf", 0) > 0.7:
                print(f"AI Suggestion Received: {res['selector']} (Confidence: {res['conf']})")
                return res
            else:
                print(f"AI Confidence too low: {res.get('conf', 0)}")
        except Exception as e:
            print(f"Healix API connection failed: {e}")
        return None

hx = Healix()

async def smart_click(page, selector, text_to_fill=None):
    # Capture where this function was called from for Milestone 6
    caller = traceback.extract_stack()[-2]
    file_info = {"file": caller.filename, "line": caller.lineno}

    action_name = "Fill" if text_to_fill else "Click"
    print(f"\nExecuting Action: {action_name} on '{selector}'")
    
    try:
        if text_to_fill:
            await page.fill(selector, text_to_fill, timeout=2000)
        else:
            await page.click(selector, timeout=2000)
        print(f"Step Success: '{selector}' worked.")
    except Exception as e:
        print(f"Action Failed. Initiating Healix Recovery...")
        
        page_errors = await hx.observe_state(page)
        html = await page.content()
        fix = await hx.get_fix(selector, html, error_msg=str(e)[:100], page_errors=page_errors)
        
        if fix and fix.get("conf", 0) > 0.6:
            new_sel = fix["selector"]
            print(f"Healix Suggestion: {new_sel}")
            
            try:
                if text_to_fill:
                    await page.fill(new_sel, text_to_fill)
                else:
                    await page.click(new_sel)
                
                print(f"Recovery Successful: Test continued via '{new_sel}'")
                
                # Log the proposal so the dev can make it permanent
                hx.log_proposal(selector, new_sel, file_info)
                hx._save_cache(selector, new_sel)
            except Exception as e2:
                print(f"Recovery attempt failed: {str(e2)[:50]}")
                raise e2
        else:
            print("Healix failed to find a reliable fix. Hard failure.")
            raise Exception(f"Healix failed to heal: {selector}")
import json
import re
import os
import requests
from functools import wraps
from bs4 import BeautifulSoup

class Healix:
    def __init__(self, model="qwen2.5-coder:7b", cache_file="healix_cache.json"):
        self.model = model
        self.ollama_endpoint = "http://localhost:11434/api/generate"
        self.cache_file = cache_file
        self.cache = self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def _save_cache(self):
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def scrub_dom(self, html_content):
        """
        Milestone 1 Core: Enterprise Data Scrubbing & PII Masking.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove non-functional tags
        for tag in soup(["script", "style", "svg", "path", "iframe", "meta", "link"]):
            tag.decompose()
            
        # PII Masking: Replace text in non-interactive elements
        for element in soup.find_all(string=True):
            if element.parent.name not in ['button', 'a', 'label', 'option', 'h1', 'h2', 'input']:
                element.replace_with("[MASKED]")

        # Minification
        return re.sub(r'\s+', ' ', soup.prettify())[:10000]

    async def get_ai_fix(self, broken_selector, html_content):
        """
        Milestone 2 Core: Healing with Persistence.
        """
        # 1. Check Cache First
        if broken_selector in self.cache:
            return {
                "fixed_selector": self.cache[broken_selector], 
                "confidence": 1.0, 
                "reasoning": "Retrieved from Local Healing Cache"
            }

        # 2. AI Inference
        scrubbed_html = self.scrub_dom(html_content)
        prompt = f"""
        Role: Senior SDET AI Agent
        Task: Fix a broken CSS selector.
        Broken Selector: {broken_selector}
        
        HTML Context (Scrubbed):
        {scrubbed_html}

        Instructions:
        1. Identify the most likely correct CSS selector for the intended element.
        2. Provide a 'confidence' score between 0 and 1.
        3. Return output ONLY in the following JSON format:
        {{
            "fixed_selector": "string",
            "confidence": float,
            "reasoning": "short explanation"
        }}
        """

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }

        try:
            response = requests.post(self.ollama_endpoint, json=payload, timeout=45)
            if response.status_code == 200:
                result = json.loads(response.json().get("response", "{}"))
                
                # 3. Save to Cache if confident
                if result and result.get('confidence', 0) > 0.85:
                    self.cache[broken_selector] = result['fixed_selector']
                    self._save_cache()
                return result
        except Exception as e:
            print(f"Healix Framework Error: {e}")
        return None



    def track(self, func):
        """
        Milestone 2: The @healix.track Decorator placeholder.
        """
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                print(f"🧬 Healix detecting failure in {func.__name__}...")
                raise e
        return wrapper

import asyncio
import json
import re
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

class AIQualityEngine:
    def __init__(self, model="qwen2.5-coder:7b", base_url="http://localhost:11434"):
        self.model = model
        self.ollama_endpoint = f"{base_url}/api/generate"

    def scrub_dom(self, html_content):
        """
        Milestone 1: Enterprise Data Scrubbing & PII Masking.
        Removes scripts, styles, and masks potential sensitive text.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Remove non-functional tags to save tokens
        for tag in soup(["script", "style", "svg", "path", "iframe", "meta", "link"]):
            tag.decompose()
            
        # 2. PII Masking: Replace text in non-interactive elements
        # We keep text in buttons, labels, and links as they are vital for AI context
        for element in soup.find_all(string=True):
            if element.parent.name not in ['button', 'a', 'label', 'option', 'h1', 'h2']:
                # Basic mask for any text that looks like PII or specific data
                element.replace_with("[SENSITIVE_DATA_MASKED]")

        # 3. Minification: Strip whitespace and limit size
        return re.sub(r'\s+', ' ', soup.prettify())[:10000]

    async def get_ai_fix(self, broken_selector, scrubbed_html):
        """
        Milestone 1: Ollama Local Integration with Confidence Score logic.
        """
        prompt = f"""
        Role: Senior SDET AI Agent
        Task: Fix a broken CSS selector.
        Broken Selector: {broken_selector}
        
        HTML Context:
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
                return result
        except Exception as e:
            print(f"Connection Error: {e}")
        return None

async def run_milestone_1_demo():
    engine = AIQualityEngine()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # Changed to headless for automation
        page = await browser.new_page()
        
        # Target a real complex page (or local test file)
        await page.goto("https://the-internet.herokuapp.com/login")
        
        # Scenario: ID changed from 'username' to 'user_login_field' (Simulation)
        broken_selector = "#username-old-id"
        
        print(f"🔍 Attempting interaction with: {broken_selector}")
        
        try:
            await page.click(broken_selector, timeout=2000)
        except Exception:
            print("⚠️ Selector Failed. Initiating Local Secure Healing...")
            
            raw_html = await page.content()
            scrubbed = engine.scrub_dom(raw_html)
            
            # AI Inference
            ai_response = await engine.get_ai_fix(broken_selector, scrubbed)
            
            if ai_response and ai_response.get('confidence', 0) > 0.85:
                new_selector = ai_response['fixed_selector']
                print(f"✅ AI Fixed (Confidence: {ai_response['confidence']}): {new_selector}")
                print(f"💡 Reasoning: {ai_response.get('reasoning')}")
                
                await page.fill(new_selector, "tomsmith")
                print("🎉 Test Continued Successfully.")
            else:
                print("❌ AI Confidence too low or healing failed. Human intervention required.")

        await asyncio.sleep(3)
        await browser.close()

if __name__ == "__main__":
    # Ensure Ollama is running: 'ollama serve' and 'ollama pull qwen2.5-coder:7b'
    asyncio.run(run_milestone_1_demo())

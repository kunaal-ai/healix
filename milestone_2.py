import asyncio
from playwright.async_api import async_playwright
from healix import Healix

# Initialize the reusable framework
healix = Healix()

async def smart_click(page, selector):
    """
    A helper method demonstrating how Healix intercepts failures.
    """
    try:
        # Attempt standard interaction
        await page.click(selector, timeout=2000)
    except Exception:
        print(f"⚠️ Selector '{selector}' failed. Healix searching for fix...")
        
        # Get current page state
        html = await page.content()
        
        # AI Inference with Local Caching
        fix = await healix.get_ai_fix(selector, html)
        
        if fix and fix.get('confidence', 0) > 0.85:
            new_selector = fix['fixed_selector']
            print(f"✅ Healix found fix: {new_selector} (Confidence: {fix['confidence']})")
            print(f"💡 Reasoning: {fix.get('reasoning')}")
            
            # Continue the test with the healed selector
            await page.click(new_selector)
        else:
            print("❌ Healix could not reliably fix the selector.")
            raise Exception(f"Test failed: {selector} is broken and healing failed.")

async def run_milestone_2_demo():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("🌐 Navigating to Login Page...")
        await page.goto("https://the-internet.herokuapp.com/login")
        
        # Scenario: ID changed from 'username' to 'user_login_field'
        broken_selector = "#username-old-id"
        
        print(f"\n--- 🏃 Run 1: AI Healing (First Time) ---")
        await smart_click(page, broken_selector)
        
        # Reset page for Run 2
        await page.reload()
        
        print(f"\n--- ⚡ Run 2: Cached Healing (Instant) ---")
        # This will bypass the LLM entirely and use the local JSON cache
        await smart_click(page, broken_selector)
        
        print("\n🎉 Milestone 2 Demo Complete.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_milestone_2_demo())

import asyncio
from playwright.async_api import async_playwright
from healix.engine import smart_click

async def test_healix_agent():
    async with async_playwright() as p:
        # Launching with headless=False so you can watch the agent work
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Starting Healix Agentic Test...")
        await page.goto("https://the-internet.herokuapp.com/login")
        
        # Using a broken selector to force Healix to 'observe' and 'fix'
        try:
            await smart_click(page, "#invalid-username-field")
            print("✅ Test scenario completed.")
        except Exception as e:
            print(f"Test failed despite healing: {e}")
            
        await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_healix_agent())
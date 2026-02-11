import asyncio
import pytest
from playwright.async_api import async_playwright, expect
from healix import healed_locator

# Mock HTML with "changed" IDs to simulate breakage
MOCK_HTML = """
<html>
<body>
    <div id="new-container">
        <h1 class="title">Bill Payment Complete</h1>
    </div>
    
    <button id="btn-submit-v2" class="primary">Submit</button>
</body>
</html>
"""

async def test_assertion_healing():
    """Test that healed_locator works with expect() when ID changes."""
    print("\n--- Testing Assertion Healing ---")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Load mock content directly
        await page.set_content(MOCK_HTML)
        
        # Scenario 1: Assert text on a container that changed ID
        # Original: #billpayResult -> New: #new-container
        print("[Test] Asserting text on broken selector '#billpayResult h1.title'...")
        
        # This would fail: expect(page.locator("#billpayResult h1.title")).to_have_text(...)
        # This should heal:
        locator = await healed_locator(page, "#billpayResult h1.title")
        await expect(locator).to_have_text("Bill Payment Complete")
        print("✅ Assertion passed!")
        
        # Scenario 2: Assert visibility on a button that changed ID
        # Original: #btn-submit -> New: #btn-submit-v2
        print("[Test] Asserting visibility on broken selector '#btn-submit'...")
        btn = await healed_locator(page, "#btn-submit")
        await expect(btn).to_be_visible()
        print("✅ Visibility check passed!")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_assertion_healing())

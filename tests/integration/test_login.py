import asyncio
from playwright.async_api import async_playwright
from healix import smart_click

async def run_login_test(p, browser_type):
    print(f"\n--- Testing Login Healing on The Internet [{browser_type.name}] ---")
    
    # Launch with slow_mo to give the UI time to respond
    browser = await browser_type.launch(headless=False, slow_mo=200)
    page = await browser.new_page()
    
    # Global timeouts for high-latency local AI environments
    page.set_default_timeout(60000)
    
    try:
        # Navigate to the classic login testing page
        await page.goto("https://the-internet.herokuapp.com/login", wait_until="networkidle")
        await page.wait_for_load_state("domcontentloaded")
        
        # 1. Fill username with a broken selector
        print("[User] Entering username via broken selector...")
        await smart_click(page, "input#wrong-user-id", text_to_fill="tomsmith", timeout=10000)
        
        # 2. Fill password with a broken selector
        print("[User] Entering password via broken selector...")
        await smart_click(page, "input[name='not_the_password_field']", text_to_fill="SuperSecretPassword!", timeout=10000)
        
        # 3. Click login with a broken selector
        print("[User] Clicking Login via broken selector...")
        await smart_click(page, "button.non-existent-login-class", timeout=10000)
        
        # Verify result
        await page.wait_for_load_state("networkidle")
        if await page.locator(".flash.success").is_visible():
            print(f"✅ Success: Login fully healed and authenticated on {browser_type.name}")
        else:
            print(f"⚠️ Warning: Reached page {page.url} but success message not found.")
            
    except Exception as e:
        print(f"❌ Failure on {browser_type.name}: {str(e)}")
        
    finally:
        await browser.close()

async def main():
    async with async_playwright() as p:
        # Running sequentially to minimize local LLM resource contention
        await run_login_test(p, p.chromium)
        await asyncio.sleep(10) # Cooldown for Ollama
        await run_login_test(p, p.firefox)

if __name__ == "__main__":
    asyncio.run(main())
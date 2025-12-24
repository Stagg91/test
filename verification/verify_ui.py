from playwright.sync_api import sync_playwright, expect

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Reuse context to keep cookies if possible? No, need to login again.
        context = browser.new_context()
        page = context.new_page()

        # 1. Login
        page.goto("http://127.0.0.1:8000/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin")
        page.click("button[type='submit']")

        # 2. Go to Strategies Page
        page.goto("http://127.0.0.1:8000/strategies")
        expect(page.get_by_role("heading", name="Strategy Laboratory")).to_be_visible()

        # 3. Verify Edit/Delete Buttons exist
        # We assume at least one strategy exists (Test BBands Updated from earlier)
        # If not, generate one?
        # Check if table has rows
        rows = page.locator("table tbody tr")
        if rows.count() == 0:
            print("No strategies found. Creating one...")
            page.fill("input[name='prompt']", "Test Strategy")
            page.fill("input[name='count']", "1")
            page.click("button:has-text('Generate')")
            page.wait_for_timeout(2000) # Wait for async gen (mocked?)
            page.reload()

        # Take screenshot of Strategy Library with buttons
        page.screenshot(path="verification/strategies_page.png")
        print("Screenshot saved to verification/strategies_page.png")

        browser.close()

if __name__ == "__main__":
    run()

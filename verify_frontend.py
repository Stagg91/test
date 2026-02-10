from playwright.sync_api import sync_playwright
import time

def verify_strategies_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # Login first (setup might be needed if db is empty)
            page.goto("http://localhost:8000/setup")
            if "Setup" in page.title():
                page.fill("input[name='username']", "admin")
                page.fill("input[name='password']", "admin")
                page.click("button[type='submit']")
                page.wait_for_timeout(1000)

            page.goto("http://localhost:8000/login")
            if "Login" in page.title():
                page.fill("input[name='username']", "admin")
                page.fill("input[name='password']", "admin")
                page.click("button[type='submit']")
                page.wait_for_timeout(1000)

            page.goto("http://localhost:8000/strategies")
            page.wait_for_selector("h3", timeout=5000)

            # Take screenshot
            page.screenshot(path="verification_strategies.png")
            print("Screenshot taken.")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_strategies_page()

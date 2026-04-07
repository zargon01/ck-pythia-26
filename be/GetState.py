from playwright.sync_api import sync_playwright
from utils.config import AUTH_STATE_PATH, BASE_URL


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # Always create fresh context (don't load old state)
        context = browser.new_context()
        page = context.new_page()

        print("🌐 Opening login page...")
        page.goto(f"{BASE_URL}/agents")

        print("🔐 Login manually, then press ENTER...")
        input()

        context.storage_state(path=AUTH_STATE_PATH)
        print("✅ Session saved successfully!")

        browser.close()


# Exposed for programmatic use
def refresh_session():
    print("🔄 Refreshing session (auth.json)...")
    run()
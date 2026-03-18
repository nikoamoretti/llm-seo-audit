def test_demo_flow_runs_and_renders_sections(browser_page, live_server):
    browser_page.goto(live_server)
    browser_page.fill("#businessName", "Laveta Coffee")
    browser_page.fill("#industry", "coffee shop")
    browser_page.fill("#city", "Echo Park, Los Angeles")
    browser_page.fill("#websiteUrl", "https://lavetacoffee.com")

    browser_page.click("#demoBtn")
    browser_page.wait_for_selector("#results.active", timeout=15000)
    browser_page.wait_for_selector("text=Executive Summary", timeout=15000)
    browser_page.wait_for_selector("text=Top 10 Fixes", timeout=15000)
    browser_page.wait_for_selector("text=Implementation Checklist", timeout=15000)

    content = browser_page.content()
    assert "Traceback" not in content

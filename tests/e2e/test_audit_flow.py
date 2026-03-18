def test_audit_flow_submits_business_and_renders_result(browser_page, live_server):
    browser_page.goto(live_server)
    browser_page.fill("#businessName", "Laveta Coffee")
    browser_page.fill("#industry", "coffee shop")
    browser_page.fill("#city", "Echo Park, Los Angeles")
    browser_page.fill("#websiteUrl", "https://lavetacoffee.com")

    browser_page.click("#runBtn")
    browser_page.wait_for_selector("#results.active", timeout=15000)
    browser_page.wait_for_selector("text=Executive Summary", timeout=15000)
    browser_page.wait_for_selector("text=Citation Sources", timeout=15000)
    browser_page.wait_for_selector("text=Competitor Gap", timeout=15000)

    content = browser_page.content()
    assert "Top 10 Fixes" in content
    assert "Implementation Checklist" in content

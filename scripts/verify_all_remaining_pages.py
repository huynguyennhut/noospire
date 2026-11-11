from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

driver = webdriver.Chrome(options=options)

extra_pages = [
    ("/detection-rules/", "Detection Rules"),
    ("/schedules/", "Schedules"),
    ("/settings/", "Settings"),
    ("/threat-intel/", "Threat Intel"),
    ("/findings/", "Findings & Evidence"),
    ("/remediation/", "Remediation Tracking")
]

print("=== VERIFYING REMAINING PAGES IN HEADLESS CHROME ===")
all_clean = True
for path, name in extra_pages:
    url = f"https://noosforge-soc.pages.dev{path}"
    driver.get(url)
    time.sleep(2)
    
    source = driver.page_source
    logs = driver.get_log("browser")
    severe_errors = [l for l in logs if l["level"] == "SEVERE" and "favicon" not in l["message"]]
    
    has_app_error = "Application error" in source
    if has_app_error or severe_errors:
        print(f"[FAIL] {name:<25} ({path}) -> AppError: {has_app_error}, Errors: {len(severe_errors)}")
        for err in severe_errors:
            print(f"       -> {err['message']}")
        all_clean = False
    else:
        print(f"[PASS] {name:<25} ({path}) -> Clean Render! Title: '{driver.title[:35]}'")

driver.quit()
print("\n>>> ALL REMAINING PAGES RENDERED CLEANLY WITHOUT ERRORS:", all_clean)
assert all_clean

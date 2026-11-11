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

all_14_pages = [
    ("/", "Root / Overview"),
    ("/dashboard/", "Dashboard Analytics"),
    ("/scans/", "Scan Center"),
    ("/active-assessments/", "Active Assessments Tracker"),
    ("/assets/", "Target Inventory"),
    ("/empire-modules/", "Empire Modules Hub"),
    ("/reports/", "Executive Reports"),
    ("/detection-rules/", "Detection Rules"),
    ("/schedules/", "Continuous Schedules"),
    ("/settings/", "System Settings"),
    ("/threat-intel/", "Threat Intelligence"),
    ("/findings/", "Findings & Evidence"),
    ("/remediation/", "Remediation Tracking"),
    ("/login/", "Auth Login Portal")
]

print("=== RUNNING MASTER E2E SELENIUM TEST ACROSS ALL 14 PAGES ===")
passed_count = 0
failed_pages = []

for path, name in all_14_pages:
    url = f"https://noosforge-soc.pages.dev{path}"
    driver.get(url)
    time.sleep(2)
    
    source = driver.page_source
    logs = driver.get_log("browser")
    severe_errors = [l for l in logs if l["level"] == "SEVERE" and "favicon" not in l["message"]]
    
    has_app_error = "Application error" in source
    if has_app_error or severe_errors:
        print(f"[FAIL] {name:<30} ({path:<22}) -> AppError={has_app_error}, Errors={len(severe_errors)}")
        for err in severe_errors:
            print(f"       -> {err['message']}")
        failed_pages.append(path)
    else:
        print(f"[PASS] {name:<30} ({path:<22}) -> HTTP 200 Clean Render! ('{driver.title[:35]}')")
        passed_count += 1

driver.quit()

print(f"\n=======================================================")
print(f"MASTER TEST SUMMARY: {passed_count}/{len(all_14_pages)} PAGES PASSED CLEANLY")
print(f"FAILED PAGES: {failed_pages}")
print(f"=======================================================")

assert len(failed_pages) == 0, f"Some pages failed: {failed_pages}"

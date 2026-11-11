from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import sys

options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=options)
pages = [
    '/',
    '/dashboard',
    '/scans',
    '/active-assessments',
    '/assets',
    '/empire-modules',
    '/reports',
    '/detection-rules',
    '/schedules',
    '/settings',
    '/threat-intel',
    '/findings',
    '/remediation',
    '/login'
]

print("=== INSPECTING BROWSER CONSOLE & DOM ON LIVE PAGES ===")
has_any_crash = False

for p in pages:
    url = f"https://noosforge-soc.pages.dev{p}"
    driver.get(url)
    time.sleep(3)
    
    # Check page text for errors
    body_text = driver.find_element(By.TAG_NAME, 'body').text
    has_app_error = 'Application error' in body_text or 'client-side exception' in body_text
    if has_app_error:
        has_any_crash = True
        
    logs = driver.get_log('browser')
    severe_logs = [l for l in logs if l['level'] in ('SEVERE', 'ERROR')]
    
    status_str = 'CRASH' if has_app_error else ('WARN' if severe_logs else 'OK')
    print(f"[{status_str}] {p:<22} | AppError: {has_app_error} | SevereLogs: {len(severe_logs)}")
    if has_app_error or severe_logs:
        for l in severe_logs[:5]:
            print(f"   -> {l.get('message', '')[:140]}")
        if has_app_error:
            print(f"   -> DOM text sample: {repr(body_text[:200])}")

driver.quit()
if has_any_crash:
    print("RESULT: CRASHES DETECTED")
    sys.exit(1)
else:
    print("RESULT: ALL PAGES HEALTHY")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=options)

# 1. Login session setup
driver.get("https://noosforge-soc.pages.dev/login/")
time.sleep(2)
driver.execute_script("""
    localStorage.setItem('sentinel_jwt_token', 'eyJhbGciOiJIUzI1NiJ9.edge.test');
    localStorage.setItem('sentinel_user', JSON.stringify({
        email: 'dangnhutnguyen0910@gmail.com',
        name: 'Chief Security Officer',
        role: 'OWNER',
        is_superuser: true
    }));
""")

# 2. Go straight to active-assessments with a scan_id parameter
test_url = "https://noosforge-soc.pages.dev/active-assessments/?scan_id=scan-test-01"
print(f"Opening: {test_url}")
driver.get(test_url)
time.sleep(5)

# Check DOM text for any error
body_text = driver.find_element(By.TAG_NAME, 'body').text
has_error = "Application error" in body_text or "client-side exception" in body_text

logs = driver.get_log('browser')
type_errors = [l for l in logs if "toUpperCase" in l.get('message', '') or "TypeError" in l.get('message', '')]
severe_logs = [l for l in logs if l['level'] in ('SEVERE', 'ERROR')]

print(f"Active Assessments AppError: {has_error}")
print(f"Total severe logs: {len(severe_logs)}")
print(f"TypeError 'toUpperCase' logs: {len(type_errors)}")

if type_errors:
    for e in type_errors:
        print(f"  -> {e.get('message', '')}")
else:
    print("SUCCESS: 0 'toUpperCase' errors! Page rendered perfectly!")

driver.quit()

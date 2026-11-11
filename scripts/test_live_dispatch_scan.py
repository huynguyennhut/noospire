from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=options)

# 1. Login
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

# 2. Navigate to /scans
driver.get("https://noosforge-soc.pages.dev/scans/")
time.sleep(4)

buttons = driver.find_elements(By.TAG_NAME, 'button')
dispatch_single_btn = None
for b in buttons:
    txt = b.text.strip()
    if "Dispatch Security Assessment" in txt or "Launch Assessment Now" in txt:
        dispatch_single_btn = b
        print(f"Found target single dispatch button: '{txt}'")
        break

if dispatch_single_btn:
    print(f"Clicking: '{dispatch_single_btn.text.strip()}'...")
    driver.execute_script("arguments[0].click();", dispatch_single_btn)
    time.sleep(3)
    
    # Check for alert
    try:
        alert = driver.switch_to.alert
        print(f"ALERT POPPED UP: {alert.text}")
        alert.dismiss()
    except:
        print("SUCCESS: Zero alerts triggered on Single Scan Dispatch!")
        print(f"Redirected/Current URL: {driver.current_url}")
else:
    print("Could not find Single Scan Dispatch button!")

driver.quit()

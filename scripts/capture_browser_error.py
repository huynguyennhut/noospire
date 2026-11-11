from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import time

options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

try:
    driver = webdriver.Chrome(options=options)
    print("Chrome launched successfully")
    driver.get("https://noosforge-soc.pages.dev/")
    time.sleep(3)
    
    print("Page Title:", driver.title)
    
    # Get browser console logs
    logs = driver.get_log("browser")
    print(f"=== BROWSER CONSOLE LOGS ({len(logs)}) ===")
    for entry in logs:
        print(f"[{entry['level']}] {entry['message']}")
        
    page_source = driver.page_source
    if "Application error" in page_source:
        print("FOUND 'Application error' in page source!")
    else:
        print("Page rendered successfully without 'Application error' screen!")
        
    driver.quit()
except Exception as e:
    print("Error:", e)

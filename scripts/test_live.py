import subprocess
import os

edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if not os.path.exists(edge_path):
    edge_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

urls = [
    ('Root /', 'https://noosforge-soc.pages.dev/'),
    ('Dashboard', 'https://noosforge-soc.pages.dev/dashboard/'),
    ('Assets', 'https://noosforge-soc.pages.dev/assets/'),
    ('Findings', 'https://noosforge-soc.pages.dev/findings/'),
    ('Scans', 'https://noosforge-soc.pages.dev/scans/'),
    ('Empire Modules', 'https://noosforge-soc.pages.dev/empire-modules/'),
    ('Health', 'https://noosforge-soc.pages.dev/health/'),
]

for label, url in urls:
    cmd = [edge_path, '--headless', '--disable-gpu', '--virtual-time-budget=5000', '--dump-dom', url]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
    html = res.stdout
    has_379 = '379' in html
    has_brand = 'NOOSFORGE' in html
    has_404_err = '404: This page could not be found' in html and '<html id="__next_error__"' in html
    is_404_visible = 'id="__next_error__"' in html
    
    print(f"=== {label} ({url}) ===")
    print(f"  DOM Length: {len(html)} bytes")
    print(f"  Brand 'NOOSFORGE' present: {has_brand}")
    print(f"  Asset count '379' present: {has_379}")
    print(f"  Visible 404 Error: {is_404_visible}")
    
    # Check if there is any visible error text in the body
    if 'This page could not be found' in html and '404' in html:
        # let's see if it's inside body or script
        body_idx = html.find('<body')
        body_content = html[body_idx:] if body_idx != -1 else html
        # remove script tags
        import re
        body_clean = re.sub(r'<script.*?</script>', '', body_content, flags=re.DOTALL)
        body_clean = re.sub(r'<style.*?</style>', '', body_clean, flags=re.DOTALL)
        has_visible_404 = '404' in body_clean and 'could not be found' in body_clean
        print(f"  Actually visible 404 text in rendered body: {has_visible_404}")
    else:
        print("  Actually visible 404 text in rendered body: False")

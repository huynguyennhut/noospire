import re

with open('frontend/src/lib/api.ts', 'r', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(r'\$\{API_BASE\}([^`\'"]+)', text)
print("=== ENDPOINTS IN api.ts ===")
for m in sorted(set(matches)):
    print(m)

import re

with open('frontend/src/lib/api.ts', 'r', encoding='utf-8') as f:
    text = f.read()

# find all fetchJson calls
fetch_calls = re.findall(r'fetchJson[^(]*\(\s*[\'"`]([^\'"`]+)[\'"`]', text)
print("=== fetchJson endpoints in api.ts ===")
for ep in sorted(set(fetch_calls)):
    print(ep)

# find all other fetch calls
raw_fetch = re.findall(r'fetch\([\'"`]([^\'"`]+)[\'"`]', text)
print("=== raw fetch in api.ts ===")
for ep in sorted(set(raw_fetch)):
    print(ep)

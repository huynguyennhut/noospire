with open('scripts/generate_full_worker.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'path === "/api/v1/empire-modules"' in l or 'path === "/api/v1/reports"' in l or 'path === "/api/v1/schedules"' in l or 'path === "/api/v1/engines"' in l:
        print(f'{i+1}: {l.strip()}')

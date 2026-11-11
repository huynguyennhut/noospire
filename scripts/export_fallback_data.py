import sqlite3
import json
import os

conn = sqlite3.connect('noospire.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1. Assets
c.execute("SELECT * FROM assets ORDER BY criticality DESC, created_at DESC")
assets = []
for row in c.fetchall():
    d = dict(row)
    d['approved_media_baseline'] = bool(d.get('approved_media_baseline') or False)
    
    for field in ['assessment_policy', 'auth_profile']:
        val = d.get(field)
        if val and isinstance(val, str):
            try:
                d[field] = json.loads(val)
            except Exception:
                d[field] = {}
        else:
            d[field] = {}

    for field in ['excluded_endpoints', 'tags']:
        val = d.get(field)
        if val and isinstance(val, str):
            try:
                parsed = json.loads(val)
                d[field] = parsed if isinstance(parsed, list) else [str(parsed)]
            except Exception:
                d[field] = [x.strip() for x in str(val).split(',') if x.strip()]
        elif isinstance(val, list):
            d[field] = val
        else:
            d[field] = []

    assets.append(d)

print(f"Exported {len(assets)} assets")

# 2. Findings
c.execute("SELECT * FROM findings ORDER BY cvss_score DESC, created_at DESC")
findings = []
for row in c.fetchall():
    d = dict(row)
    d['is_approved_baseline'] = bool(d.get('is_approved_baseline') or False)
    d['is_kev'] = bool(d.get('is_kev') or False)
    
    val = d.get('evidence') or d.get('evidence_data')
    if val and isinstance(val, str):
        try:
            d['evidence'] = json.loads(val)
        except Exception:
            d['evidence'] = {}
    elif isinstance(val, dict):
        d['evidence'] = val
    else:
        d['evidence'] = {}

    for field in ['cve_references', 'references', 'tags']:
        v = d.get(field)
        if v and isinstance(v, str):
            try:
                parsed = json.loads(v)
                d[field] = parsed if isinstance(parsed, list) else [str(parsed)]
            except Exception:
                d[field] = [x.strip() for x in str(v).split(',') if x.strip()]
        elif isinstance(v, list):
            d[field] = v
        else:
            d[field] = []

    if 'evidence_data' in d and 'evidence' in d:
        del d['evidence_data']

    findings.append(d)

print(f"Exported {len(findings)} findings")

# 3. Scans
c.execute("SELECT * FROM scans ORDER BY created_at DESC LIMIT 50")
scans = []
for row in c.fetchall():
    d = dict(row)
    for field in ['target_summary', 'scanner_payload', 'findings_summary']:
        v = d.get(field)
        if v and isinstance(v, str):
            try:
                d[field] = json.loads(v)
            except Exception:
                d[field] = {}
    scans.append(d)

print(f"Exported {len(scans)} scans")

# Write to fallback-data.json
json_path = os.path.join('frontend', 'src', 'lib', 'fallback-data.json')
data = {
    "assets": assets,
    "findings": findings,
    "scans": scans
}
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, separators=(',', ':'))

print(f"Successfully generated {json_path} ({os.path.getsize(json_path):,} bytes)")

# Write to fallback-data.ts
ts_path = os.path.join('frontend', 'src', 'lib', 'fallback-data.ts')
ts_content = """// =============================================================================
// NOOSFORGE SECURITY INTELLIGENCE — FALLBACK REPOSITORY DATA
// Real production data exported directly from noospire.db (Zero Mock / Real Seed)
// =============================================================================

import fallbackJson from './fallback-data.json';

export const FALLBACK_ASSETS: any[] = fallbackJson.assets;
export const FALLBACK_FINDINGS: any[] = fallbackJson.findings;
export const FALLBACK_SCANS: any[] = fallbackJson.scans;
"""

with open(ts_path, 'w', encoding='utf-8') as f:
    f.write(ts_content)

print(f"Successfully generated {ts_path}")

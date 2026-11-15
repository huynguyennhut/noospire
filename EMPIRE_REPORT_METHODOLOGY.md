# EMPIRE EDUCATIONAL PLATFORM — AUDIT REPORTING & RISK SCORING METHODOLOGY

**Document Version**: 2.4.0  
**Reporting Engine**: NOOSFORGE Security Intelligence Multi-Format Publisher  
**Methodology Standard**: CVSS v3.1 / FIRST EPSS / CISA KEV / OWASP Risk Rating  
**Themes Supported**: Obsidian Dark Mode (Default) & Warm Invert Light Theme  

---

## 1. Systemic Risk Score ($SRS$) Calculation

The Noospire platform calculates an objective, evidence-backed **Systemic Risk Score ($SRS$)** representing the collective security exposure of the Empire Education Platform. Unlike naive scanners that merely sum up raw numbers, the $SRS$ incorporates severity weights, threat intelligence multipliers (CISA KEV), and exploit probability models (EPSS).

### 1.1 Mathematical Formulation
The composite risk score is computed strictly from verified, non-remediated finding records:

$$\text{Weighted Score} = (N_{\text{crit}} \times 25.0) + (N_{\text{high}} \times 15.0) + (N_{\text{med}} \times 5.0) + (N_{\text{low}} \times 1.0) + (N_{\text{cisa\_kev}} \times 10.0)$$

$$SRS = \min\left(100.0, \; \text{round}(\text{Weighted Score}, 1)\right)$$

Where:
- $N_{\text{crit}}$: Count of active vulnerabilities with severity `CRITICAL` ($9.0 \le \text{CVSS} \le 10.0$).
- $N_{\text{high}}$: Count of active vulnerabilities with severity `HIGH` ($7.0 \le \text{CVSS} < 9.0$).
- $N_{\text{med}}$: Count of active vulnerabilities with severity `MEDIUM` ($4.0 \le \text{CVSS} < 7.0$).
- $N_{\text{low}}$: Count of active vulnerabilities with severity `LOW` ($0.1 \le \text{CVSS} < 4.0$).
- $N_{\text{cisa\_kev}}$: Count of findings confirmed in the **CISA Known Exploited Vulnerabilities Catalog** (active in-the-wild exploitation).
- Informational items ($N_{\text{info}}$) carry a weight of $0.0$ and do not inflate the risk score.

### 1.2 Risk Posture Classification
The computed $SRS \in [0.0, 100.0]$ maps directly to standardized organizational posture bands (`backend/app/reporting/generator.py`):

```
+--------------------+----------------+-------------------------------------------------------------+
| Score Range        | Posture Band   | Executive Definition & Operational Action Plan              |
+--------------------+----------------+-------------------------------------------------------------+
| 80.0 <= SRS <= 100 | CRITICAL       | Severe platform exposure; active exploitation probable.    |
|                    |                | Immediate emergency patching required within 24-48 hours.  |
| 60.0 <= SRS < 80.0 | ELEVATED       | Significant vulnerabilities identified (unauthenticated).  |
|                    |                | Engineering remediation sprint mandated within 7 days.      |
| 40.0 <= SRS < 60.0 | MODERATE       | Medium vulnerabilities present; defense-in-depth gaps.      |
|                    |                | Scheduled remediation during next regular release cycle.    |
|  0.0 < SRS < 40.0  | GUARDED        | Low or informational hygiene findings; perimeter fortified. |
|                    |                | Continue continuous monitoring and dependency hygiene.     |
|       SRS == 0.0   | OPTIMAL        | Zero open vulnerabilities across all verified targets.      |
+--------------------+----------------+-------------------------------------------------------------+
```

---

## 2. Assessment Coverage & Completion Calculation

A critical requirement of the Empire pentest standard is **honest coverage reporting**. Reports must never claim 100% security when automated checks were blocked or manual reviews were left unperformed.

### 2.1 Automated Coverage Percentage
Measures the proportion of automated security checks that actually executed to completion:

$$\text{Automated Coverage \%} = \text{round}\left(\frac{\text{Evaluated Automated Checks}}{\text{Total Automated Checks}} \times 100.0, \; 2\right)$$

- **Evaluated Automated Checks**: Checks where the result state $\notin \{\text{NOT\_RUN}, \text{BLOCKED}\}$.
- If a check was blocked due to missing credentials, it is accounted as **uncovered**, properly lowering the automated coverage percentage.

### 2.2 Manual Review Completion Percentage
Measures the progress of expert human verification across hybrid and manual checklist items:

$$\text{Manual Review Completion \%} = \text{round}\left(\frac{\text{Completed Manual Reviews}}{\text{Total Manual/Hybrid Checks}} \times 100.0, \; 2\right)$$

- **Completed Manual Reviews**: Checks where an operator has submitted signed review notes, or checks evaluated to a definitive terminal state $\notin \{\text{NOT\_RUN}, \text{NEEDS\_REVIEW}\}$.

---

## 3. Honest Coverage Gap Disclosures

Every generated Executive and Technical Report includes a mandatory **Appendix: Coverage Gaps & Exclusions**:

1. **Unassessed Capabilities**: Explicit disclosure of tools that were unavailable, throttled, or failed due to environment timeouts.
2. **Blocked Prerequisite Tests**: Explicit listing of checks marked `BLOCKED` (e.g. `API-001` BOLA check blocked if synthetic student identities were missing).
3. **Out-of-Scope Architecture**: Transparent documentation of systems intentionally excluded from automated probes (e.g., third-party SMS OTP gateways, Cloudflare CDN internal routing).
4. **Zero False Equivalence**: The report methodology strictly differentiates between:
   - `PASS`: Affirmative evidence proving that a security control successfully rejected or sanitized an attack probe.
   - `NOT_RUN` / `NOT_APPLICABLE`: A capability that was not tested or does not apply to the target.

---

## 4. Dual-Theme Reporting & Liquid Glass Design

Noospire reports are engineered with the responsive, high-density **Liquid Glass** design system, providing optimal readability across both high-contrast dark room analysis and executive print briefings.

```
+-----------------------------------------------------------------------------------------+
|                                LIQUID GLASS THEME MATRIX                                |
+------------------------+---------------------------------+------------------------------+
| Aesthetic Attribute    | Obsidian Dark Mode (Default)    | Warm Invert Light Theme      |
+------------------------+---------------------------------+------------------------------+
| Background Base        | Deep Obsidian Space (`#0B0F19`) | Warm Ivory Cream (`#FBF9F5`) |
| Surface Panels         | Translucent Charcoal Slate      | Glass White / Warm Vanilla   |
| Panel Glass Blur       | `backdrop-filter: blur(16px)`   | `backdrop-filter: blur(12px)`|
| Primary Typography     | High-Contrast White (`#F8FAFC`) | Deep Obsidian Slate (`#0F172A)|
| Secondary Text         | Muted Silver Slate (`#94A3B8`)  | Warm Charcoal Muted (`#475569|
| Border Accent          | Semi-transparent Glass Border   | Warm Amber / Subtle Ochre    |
| Critical Severity Tag  | Glowing Crimson (`#EF4444`)     | Rich Vermilion Red (`#DC2626`|
| High Severity Tag      | Vibrant Coral (`#F97316`)       | Deep Amber Orange (`#EA580C`)|
| Medium Severity Tag    | Luminous Amber (`#F59E0B`)      | Burnished Gold (`#D97706`)   |
| Low Severity Tag       | Electric Cyan (`#06B6D4`)       | Deep Teal (`#0891B2`)        |
| Pass Status Tag        | Emerald Green (`#10B981`)       | Forest Emerald (`#059669`)   |
+------------------------+---------------------------------+------------------------------+
```

### 4.1 Theme Switching & Export Support
- **PDF Report Generation**: Compiled via Headless Chromium / Weasyprint vector rendering engine, defaulting to Warm Invert Light layout to ensure clean printability and zero black toner waste.
- **HTML Interactive Report**: Features dynamic theme toggle via CSS variables (`[data-theme="obsidian"]` and `[data-theme="warm-light"]`) stored in client local storage.
- **JSON Structured Report**: Exports standardized schema independent of visual styling.

---

## 5. Artifact Security & Download Governance

1. **Cryptographic Checksums**: Every report artifact calculates a SHA-256 digest upon generation, written to disk metadata and served in the `X-Content-SHA256` HTTP header.
2. **Access Control**: Downloading reports requires authenticated bearer session with `REPORT:READ` grant; unauthorized or unassigned developers receive `HTTP 403 Forbidden`.
3. **Cache Policy**: All report endpoints emit `Cache-Control: private, no-store, max-age=0` to prevent shared caching of sensitive vulnerability descriptions.

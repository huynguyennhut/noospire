Theme: Invert (Light)Light Theme: Warm
NOOSFORGE — EMPIRE PRODUCTION AUTHORIZED OPERATIONS PROMPT
Version: 1.0
Purpose: Production-only, full-scope, authorized security assessment and continuous monitoring for Empire Education.
Use: Add this document to the existing NOOSFORGE repository instructions and treat it as the authoritative operational-scope update to earlier public-only instructions.

0. AUTHORITATIVE SCOPE UPDATE
This document supersedes earlier instructions that restricted customer scanning to public unauthenticated surfaces only, provided those earlier instructions conflict with this document.

The project owner has stated that the NOOSFORGE team has received authorization from Empire's development team and the relevant system owner to perform security assessment on Empire Education's real production environment and its in-scope infrastructure.

For work within the Empire-owned/operated scope recorded in the asset inventory:

Treat this as standing authorization for the agreed assessment and monitoring work.
Do not repeatedly interrupt ordinary work to ask whether authorization exists or request a new confirmation for each target, scan, finding, or routine retest.
Do not automatically restrict the assessment to public unauthenticated endpoints.
Do not assume that staging, sandbox, or a simulated target is an acceptable substitute for production coverage.
Perform operational assessment against the real production assets in the approved Empire scope.
Assess both public and authenticated application surfaces when the relevant, Empire-approved access method and test identity are available.
Include web, API, authentication, authorization, file/media, infrastructure, server, dependency, container, and other discovered in-scope components to the extent the team has the technical access and the relevant scanner capability.
Never report an untested component as tested, secure, clean, or passed.
This standing authorization does not expand scope to unrelated third-party systems, shared hosting tenants, payment providers, identity providers, SaaS vendors, customer devices, or infrastructure not owned or operated by Empire unless those assets are explicitly included in the authoritative scope inventory.

1. IMPORTANT TERMINOLOGY — DO NOT CONFUSE THESE CONCEPTS
The system and all agents must distinguish the following:

Permission to conduct the assessment: The project owner has stated that the team has authorization from Empire's developers and system owner. Do not repeatedly ask for this permission for ordinary in-scope work.
Authentication to the target application: A technical login mechanism such as a session, JWT, OAuth token, or test account. Use only an Empire-provisioned credential or access mechanism already made available to the project. Do not invent, steal, extract, or guess credentials.
Authorization testing: Testing whether a user or role can access only the objects and functions it is permitted to access. This includes BOLA/IDOR, BFLA, RBAC, privilege boundary, tenant isolation, and object-level access control. These are legitimate and important security test categories; do not disable or omit them merely because the assessment itself is authorized.
Assessment scope: The exact assets, network ranges, environments, applications, APIs, and infrastructure that belong to Empire and are included in the asset inventory.
Do not use a generic AUTH_REQUIRED status as a terminal scan result. If a test case genuinely requires a target identity and no approved test identity is configured, record it as a clearly named coverage gap (for example AUTHENTICATED_COVERAGE_NOT_CONFIGURED) with the exact affected test cases. Continue all other checks. Do not mark these checks passed, and do not attempt to bypass authentication to manufacture coverage.

2. PRODUCTION-ONLY OPERATING MODE
2.1 Target environment
The customer assessment target is Empire's actual production environment.
Do not substitute a staging, QA, demo, sandbox, localhost, mock server, or fabricated target and claim customer assessment coverage.
Local unit tests, static checks, and isolated tests of NOOSFORGE's own code may still be used for software engineering quality. They are not Empire assessment results and must be labelled separately.
The production scan configuration must identify the environment as production and display the exact target scope before execution.
Do not silently point a production scan at a similarly named or newly discovered unrelated host.
2.2 Production safety
Production testing must be technically meaningful but controlled. The objective is to identify and safely verify security weaknesses without interrupting Empire's service or affecting learners, teachers, administrators, or real customer data.

The following are prohibited by default on production:

Denial-of-service, distributed denial-of-service, stress testing, resource exhaustion, or high-volume load testing.
Password brute force, password spraying, credential stuffing, or attempts against real user accounts.
Destructive SQL/NoSQL operations, destructive file operations, or payloads that modify or delete business data.
Malware deployment, persistence, web shells, reverse shells, or unauthorized command execution.
Lateral movement, pivoting into unrelated networks, or attempts to compromise third-party infrastructure.
Bulk extraction or exfiltration of personal data, learning materials, credentials, secrets, or database contents.
Uploading executable or persistent payloads to production storage.
Exploit chains that materially change system state or create an outage risk.
Scanning beyond the Empire scope inventory.
Use safe validation methods and minimum proof necessary. When an issue can be established through configuration evidence, a harmless marker, a controlled test object, or a non-destructive request, do not perform a more intrusive exploit.

2.3 Automatic stop conditions
Implement a global and per-target emergency stop. Pause or cancel the affected scan automatically when any configured production safety threshold is crossed, including:

A material increase in HTTP 5xx responses or application errors correlated with scanning.
Sustained response-time degradation relative to the recorded baseline.
CPU, memory, connection, or queue pressure exceeding configured limits where telemetry is available.
Repeated timeouts, connection resets, rate-limit responses, WAF blocks, or health-check failures indicating that scan intensity is too high.
An incident alert or explicit stop signal from the Empire operations team.
Use conservative configurable defaults. Do not invent telemetry values if the application cannot collect them. Record the trigger, timestamp, affected target, active scanner jobs, and cancellation result. Stop child processes cleanly and verify that no orphan scanner processes remain.

3. FULL EMPIRE ASSET INVENTORY — DISCOVER, NORMALIZE, VERIFY
Build and maintain a single source of truth for Empire's in-scope assets.

Inventory categories:

Root domains and approved subdomains.
Public web applications and web portals.
API hosts, API base paths, OpenAPI specifications, GraphQL endpoints, and documented service endpoints.
Public IP addresses and approved network ranges.
Empire-operated servers, reverse proxies, load balancers, gateways, and exposed services.
Cloud resources and storage endpoints that Empire owns or administers.
Containers, container registries, images, and deployment components where access is available.
Source repositories and dependency manifests that Empire has provided for assessment.
Mobile applications and associated backend APIs when app artifacts and scope are supplied.
File, media, learning-material, upload, and download services.
Authentication, session, identity, and account-management components.
Supporting tools such as English-learning utilities, news/RSS processing, and other integrated services.
Asset discovery rules:

Start from known Empire-provided domains, IP ranges, architecture notes, DNS records, API documents, repositories, deployment manifests, and existing NOOSFORGE records.
Correlate evidence from multiple sources before classifying an asset as Empire-owned.
Record the discovery source, first-seen time, last-seen time, ownership confidence, environment, and scope decision.
Do not automatically scan arbitrary third-party hosts simply because a page links to them, a DNS record references them, or a service calls them.
Identify CDN/WAF/shared-hosting boundaries. Scan Empire-controlled application endpoints; do not infer permission to test the provider's shared infrastructure.
Detect duplicate assets, aliases, redirects, IP changes, and certificate SANs without silently expanding scope.
Preserve asset history and show newly discovered, removed, changed, and unverified assets.
An inventory gap must be visible in the dashboard and report.
4. COMPREHENSIVE SECURITY ASSESSMENT CHECKLIST
Every check must have a stable ID, category, target type, preconditions, detection method, impact, safe validation method, evidence requirements, remediation guidance, and a clearly defined result state.

4.1 Web application security
Assess, where technically applicable:

TLS versions, certificate validity, chain, expiry, and weak configuration.
HTTP security headers, HSTS, CSP, framing controls, content-type handling, and referrer policy.
Cookie attributes: Secure, HttpOnly, SameSite, scope, and lifecycle.
CORS policy and cross-origin trust boundaries.
Redirect handling and open redirect indicators.
Information disclosure through headers, errors, debug endpoints, source maps, public files, and exposed metadata.
Reflected, stored, and DOM-based XSS using safe, non-persistent markers.
CSRF protections for state-changing operations, using only safe test identities and non-destructive test actions.
SQL/NoSQL/command/template injection indicators using non-destructive probes.
SSRF indicators using controlled, harmless callback infrastructure only when explicitly configured for the assessment; do not access cloud metadata, internal secrets, or unrelated internal systems as proof.
Path traversal and file-access boundary checks using harmless known test paths and no extraction of sensitive files.
Cache-control and sensitive-response caching.
Session handling, logout invalidation, session renewal, and secure transport.
Clickjacking, MIME sniffing, and browser-side security controls.
Business logic and workflow weaknesses that are observable without altering production business records.
4.2 API security
Inventory documented and discovered API routes. Assess:

Authentication enforcement and inconsistent access controls.
Object-level authorization / BOLA / IDOR using approved test identities and harmless test objects when provisioned.
Function-level authorization / BFLA across roles.
Tenant and organization isolation.
Excessive data exposure and response over-sharing; redact personal data in evidence.
Mass assignment and unexpected writable fields using non-destructive requests.
Input validation, schema enforcement, type confusion, and parameter pollution.
Rate limiting and resource-consumption controls with low-rate bounded checks, never load or DoS testing.
CORS and preflight behavior.
JWT validation configuration when JWT is used: signature validation, algorithm restrictions, issuer, audience, expiry, and key handling. Do not forge tokens to gain access.
API versioning, deprecated endpoints, debug endpoints, and undocumented routes.
GraphQL introspection and resolver authorization where applicable, using bounded queries.
Error behavior and information disclosure.
Idempotency and safe handling of repeated requests.
4.3 Authentication, account security, and authorization
Assess:

Login and logout flows.
Account enumeration through safe response comparison.
Password policy visibility and configuration evidence where available.
Rate limiting and lockout behavior using designated test identities only; no brute force or spraying.
MFA configuration and enforcement where applicable.
Password reset and recovery flow design without completing resets for real users.
Session fixation, renewal, expiry, and invalidation.
Role and permission boundaries.
Student, teacher, staff, and administrator separation where these roles exist.
Privilege escalation indicators using approved test accounts and harmless operations.
BOLA/IDOR and BFLA checks with paired, approved test identities and test records.
If the project has approved customer test credentials already configured, use them only through the designated secret-management mechanism. Never print secrets to logs, reports, screenshots, prompts, or terminal output. If no approved identity is configured for a specific role-based test, record the exact coverage gap and proceed with every other applicable check.

4.4 Learning materials, files, and /media
Treat public access as policy-dependent, not automatically vulnerable.

Establish the expected public/private policy for each file class and storage path.
Verify that intentionally public learning materials remain accessible as designed.
Identify private or sensitive files exposed anonymously.
Check upload/download authorization, MIME validation, filename handling, path normalization, storage permissions, and signed URL behavior where applicable.
Check for directory listing and unintended object enumeration.
Do not download bulk files or copy real user documents into findings.
Use metadata and minimal safe evidence. Redact filenames or identifiers if they contain personal information.
Distinguish PUBLIC_BY_DESIGN from UNEXPECTED_PUBLIC_EXPOSURE.
4.5 Infrastructure and server security
For verified Empire-owned infrastructure in scope:

Discover exposed TCP services with conservative scan rates and bounded timing.
Identify service versions where safely observable.
Detect unnecessary public services and administrative interfaces.
Review TLS and certificate configurations.
Identify exposed databases, caches, search services, object storage, management ports, and debug interfaces without attempting unauthorized login or data extraction.
Assess network segmentation evidence where architecture and permitted vantage points allow it.
Review server and reverse-proxy security headers and configurations where access is provided.
Check known vulnerable software versions against current vulnerability intelligence.
Review cloud security posture using read-only, Empire-provisioned access when available.
Review firewall, security group, and ingress exposure from approved configuration exports or read-only accounts.
Identify public backup, configuration, log, and artifact exposure.
Do not interpret a closed or filtered port as proof that the service is secure. Record vantage point and scan limitations.

4.6 Dependency, source, container, and build security
When Empire provides repositories, build artifacts, container images, or manifests:

Scan direct and transitive dependencies for known CVEs.
Check package manifests and lockfiles.
Scan container images and Dockerfiles.
Detect exposed secrets in repository history and current files; never print the secret value.
Review IaC, Kubernetes, and deployment configuration where available.
Generate or ingest SBOM data where supported.
Identify license and supply-chain metadata only within the agreed product scope.
Distinguish code-level findings from runtime production findings.
4.7 Supporting services and special modules
Review Empire-specific supporting features, including:

English-learning utilities and dictionary-related components.
News, RSS, and content ingestion pipelines.
File conversion, preview, and media processing.
Third-party integration boundaries.
Background jobs, scheduled tasks, and worker-facing APIs.
Focus on input validation, SSRF protections, access control, data exposure, unsafe parsing, and resource limits. Do not scan third-party services outside the approved scope.

5. SCANNER ORCHESTRATION AND TOOLING
Integrate scanners as real, versioned adapters. Do not simulate output.

Expected integrations, where supported by the current deployment:

OWASP ZAP for web/API DAST, passive analysis, and carefully rate-limited active checks.
Nuclei for template-based detection of CVEs, misconfigurations, and exposed services.
Trivy for dependencies, containers, filesystem, secrets, and SBOM-related checks.
Nmap for conservative service discovery and port inventory on verified Empire-owned targets.
Greenbone/OpenVAS or another vulnerability scanner only if operationally supported and appropriately scoped.
Semgrep or equivalent static analysis when source code is provided.
Prowler or equivalent cloud posture tooling only when Empire provides authorized read-only cloud access and the relevant environment is supported.
MobSF or equivalent mobile analysis only when mobile artifacts are supplied and included in scope.
Scanner integration requirements:

Create a scanner registry with name, version, installation status, health, capabilities, supported target types, configuration, and license notes.
Verify the actual binary/container version before execution.
Validate configuration and target scope before starting jobs.
Use safe templates and checks by default. Exclude DoS, brute-force, destructive, persistence, and intrusive templates from production profiles.
Respect rate limits, concurrency controls, target-specific cooldowns, and scanner resource budgets.
Capture raw scanner output securely, normalize results into the NOOSFORGE finding schema, and retain a reference to the original evidence.
Deduplicate findings deterministically without merging distinct affected assets or endpoints.
Record scanner errors and partial coverage honestly.
Never mark a scan successful merely because the process exited with code 0; verify that targets were reached and meaningful checks ran.
Kill process trees on cancellation and verify no orphan processes remain.
Do not blindly run every scanner against every asset. Select compatible scanners and profiles based on asset type, production risk, and known technology stack.

6. SCAN PROFILES AND SCHEDULING
Implement separate production-safe profiles:

Profile A — Daily Production Monitoring
Asset reachability and certificate checks.
Passive web/API checks.
Security headers and TLS configuration.
Safe Nuclei templates for relevant misconfiguration and known vulnerability detection.
Known public exposure checks.
Dependency intelligence refresh and targeted matching.
Low-rate checks with strict concurrency and stop conditions.
Profile B — Authenticated Production Assessment
Use only Empire-provisioned test identities and secrets already configured for the project.
Test role boundaries, object-level access, function-level access, and tenant isolation with approved test records.
Do not use real learner accounts as test identities.
Do not mutate meaningful business data.
Record per-role coverage and exact limitations.
Profile C — Scheduled Deeper Production Assessment
Carefully rate-limited active DAST and API checks.
Expanded service discovery within approved Empire-owned ranges.
Targeted CVE validation using safe proof methods.
Broader file/media and business-logic review.
Run only within the agreed maintenance or low-traffic window where available.
Profile D — Change-triggered Assessment
Reassess affected assets after material deployment, dependency, DNS, certificate, API schema, or configuration changes.
Prioritize newly introduced exposure and regression.
Scheduler requirements:

Support daily, weekly, monthly, and event-triggered runs.
Prevent overlapping scans on the same asset/profile unless the engine explicitly supports safe concurrency.
Use per-asset locks and global worker limits.
Support pause, resume, cancel, and emergency stop.
Preserve job history and the exact profile/version used.
Do not automatically launch newly imported assets into intrusive checks until ownership and scope are verified.
7. FINDING QUALITY, EVIDENCE, AND RISK
Every finding must include:

Stable finding ID and deterministic fingerprint.
Asset, environment, endpoint, method, and affected component.
Title, category, CWE/CVE when supported, and concise technical description.
Severity and confidence as separate fields.
Business impact and exploitability reasoning.
Detection source, scanner name/version, template/rule ID, and check ID.
Timestamp, first-seen, last-seen, and recurrence history.
Minimal safe evidence: status, selected headers, sanitized request/response excerpts, and reproducible harmless steps.
Data classification and redaction status.
Remediation guidance and retest criteria.
Validation state: CONFIRMED, NEEDS_REVIEW, FALSE_POSITIVE, ACCEPTED_RISK, FIXED_PENDING_RETEST, or RETESTED_FIXED.
Do not expose passwords, tokens, session cookies, private keys, personal data, or full sensitive response bodies in the UI or report. Store raw evidence only when necessary, encrypt it at rest, restrict access, and apply retention controls.

Do not convert scanner output directly into a confirmed vulnerability without validation. Keep severity, confidence, and verification status distinct.

8. DASHBOARDS AND USER WORKFLOWS
The production dashboard must show the real status of the Empire production assessment.

Admin / Security Lead
Complete asset inventory and scope status.
Daily scan status and coverage.
Active scans, queued jobs, workers, and emergency stop.
Findings by severity, asset, category, and age.
Risk trends and remediation progress.
Scanner health, versions, and data freshness.
Coverage gaps and assets not assessed.
Reports and audit trail.
Developer
Findings assigned to the team or component.
Affected route, service, commit, dependency, or configuration.
Sanitized evidence and reproduction steps.
Remediation guidance and retest action.
Status history and ownership.
Executive / Read-only Stakeholder
Executive risk summary.
Trends, critical issues, remediation progress, and coverage limitations.
No access to raw secrets or sensitive forensic evidence.
All charts and KPIs must be derived from real database records. Never insert fabricated counts, simulated progress, placeholder findings, or static success indicators into production paths.

9. REPORTING AND ACCEPTANCE
Generate:

Executive summary.
Technical assessment report.
Asset inventory and coverage matrix.
Scanner execution and version record.
Findings register with severity and confidence.
Evidence appendix with redaction.
Remediation recommendations and retest status.
Explicit limitations and unassessed assets.
A report must state the exact assessment window, production asset scope, scan profiles, scanner versions, authenticated/unauthenticated coverage where applicable, rate limits, exclusions, errors, and partial results.

Never claim “full coverage” unless every asset and applicable check in the approved inventory has a recorded outcome. Coverage can be PASS, FINDING, NOT_APPLICABLE, BLOCKED, ERROR, or COVERAGE_GAP; a check with no execution evidence is not PASS.

10. NOOSFORGE PLATFORM ENGINEERING REQUIREMENTS
When implementing or modifying NOOSFORGE:

Audit the current repository before editing.
Preserve working functionality and current design-system conventions.
Reuse existing modules and APIs when appropriate.
Make changes in small, verifiable increments.
Add migrations for schema changes.
Keep API contracts synchronized with frontend types.
Add unit, integration, and end-to-end tests for code changes.
Test scanner adapters with real binaries and safe local adapter tests; do not use fake production scan output.
Test production scanning controls without causing customer-impacting load.
Use typed models, structured logging, error handling, and observability.
Ensure job retries are idempotent and cancellation is reliable.
Protect secrets and evidence throughout the pipeline.
Maintain backup and recovery procedures for NOOSFORGE data.
Do not modify Empire's production application, infrastructure configuration, data, or deployment state as part of a finding validation unless that change is explicitly part of a separately assigned remediation task.
11. AUTONOMOUS WORKING BEHAVIOR
Act as the lead engineer responsible for delivering the requested work in the existing NOOSFORGE repository.

For each user request:

Read the relevant project instructions and requirements.
Inspect the actual implementation before making assumptions.
Identify the exact affected modules and dependencies.
Propose a concise execution approach when the change is substantial.
Implement the change directly.
Run relevant checks and tests.
Fix failures caused by the change.
Re-run regression tests.
Report files changed, behavior changed, tests executed, actual results, and remaining limitations.
Do not stop after producing a plan when implementation is requested. Do not claim a test ran if it did not. Do not claim a scanner detected or cleared an issue without raw execution evidence. Do not hide partial coverage.

Do not ask the user to reconfirm the standing authorization for ordinary, non-destructive operations within the recorded Empire production scope. If a proposed action is destructive, outage-prone, involves data modification/extraction, crosses ownership boundaries, or creates a material production risk, do not execute it automatically; use the safest non-destructive alternative and document the limitation.

12. REQUIRED INITIAL EXECUTION SEQUENCE
When this prompt is first adopted:

M0 — Repository and scope audit
Read all existing NOOSFORGE instructions and technical documents.
Inspect frontend, backend, database, API, scanner adapters, workers, scheduler, reports, deployment, and tests.
Inspect current target inventory and identify which entries are verified Empire production assets.
Identify old public-only restrictions and update only those that conflict with this production-authorized scope.
Preserve independent protections such as secret redaction, scope controls, rate limiting, emergency stop, and process safety.
Produce a gap analysis mapping every requirement in this prompt to the current implementation.
M1 — Production asset inventory
Reconcile Empire-provided assets and existing NOOSFORGE targets.
Record ownership evidence and scope status.
Identify missing domains, APIs, IP ranges, services, and components.
Do not silently expand to third-party infrastructure.
M2 — Scanner and capability audit
Verify installed scanner binaries, versions, adapters, profiles, and health.
Map each asset type to applicable checks.
Identify checks currently missing, broken, duplicated, or falsely marked complete.
M3 — Production-safe configuration
Implement production profiles, conservative rate limits, worker limits, health monitoring, and emergency stop.
Configure approved target credentials only if they are already provisioned through the project's designated secret store.
Do not use staging as a replacement for production assessment.
M4 — Execution and evidence
Run the appropriate in-scope production checks under the configured safety controls.
Capture real scanner output and sanitized evidence.
Track coverage per asset and per check.
Stop affected scans on production health degradation.
M5 — Reporting and remediation workflow
Normalize and deduplicate findings.
Generate reports with explicit scope and limitations.
Provide remediation ownership and retest workflow.
M6 — Regression and release verification
Verify all NOOSFORGE workflows affected by the implementation.
Verify dashboards, APIs, workers, scheduler, scanner adapters, reporting, and emergency stop.
Publish a final evidence-based acceptance report.
13. FINAL NON-NEGOTIABLE RULES
Empire production is the customer assessment environment; do not substitute staging or a fake target.
The team has standing authorization for ordinary in-scope assessment work; do not repeatedly ask for permission.
Full-scope means all verified Empire-owned/operated assets in the inventory, not arbitrary third-party systems.
Do not limit assessment to unauthenticated public endpoints when approved target access is available.
Do not confuse permission to test with application authentication or authorization testing.
Do not omit BOLA, BFLA, RBAC, tenant isolation, or other access-control checks when suitable approved test identities and safe test records exist.
Do not invent credentials, bypass access controls, or harvest secrets.
Do not run destructive, denial-of-service, brute-force, persistence, or bulk-exfiltration activities on production.
Keep rate limits, health monitoring, cancellation, and emergency stop active.
Do not fabricate metrics, findings, successful scans, coverage, or reports.
Every PASS must have execution evidence; every coverage gap must be visible.
Prioritize protecting Empire's live service and users while delivering the broadest safe, technically valid assessment possible.
START NOW
Read this document together with the existing NOOSFORGE project instructions. Audit the actual repository and current asset inventory. Update conflicting public-only operating assumptions. Then implement and execute the production-authorized assessment workflow in the existing project. Continue through implementation, verification, and evidence-based reporting rather than stopping at planning.
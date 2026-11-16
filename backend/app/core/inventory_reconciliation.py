"""Source-backed inventory reconciliation. No database writes, DNS, secrets or scans.

The owner's current designation names only the primary root. Historical scope
documents and seed-generated VERIFIED flags remain evidence to reconcile, not an
automatic target allowlist.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from backend.app.core.ultra_planner import UltraScanPlanner

PRIMARY_TARGET = "https://empire.edu.vn/"
SCOPE_SOURCE = "Owner clarification in the 2026-11-15 production-inventory request"

# Exact locators corroborated in the repository's legacy tests. This is a deny
# classification for fixture execution, never a production allowlist.
LEGACY_TEST_TARGETS = {
    "http://169.254.169.254/latest/meta-data": "tests/test_scope_gate.py:176",
    "http://192.168.1.100/admin": "tests/test_scope_gate.py:199",
    "https://active-unverified.empire.edu.vn/": "tests/test_scan_intelligence_m2.py:363",
    "https://ungranted.empire.edu.vn/": "tests/test_scope_gate.py:69",
    "https://expired.empire.edu.vn/": "tests/test_scope_gate.py:89",
    "https://stopped.empire.edu.vn/": "tests/test_scope_gate.py:118",
    "https://unproven.empire.edu.vn/": "tests/test_scope_gate.py:146",
    "https://boundary.empire.edu.vn/": "tests/test_scope_gate.py:225",
    "https://budget.empire.edu.vn/": "tests/test_scope_gate.py:267",
    "https://killswitch.empire.edu.vn/": "tests/test_scope_gate.py:301",
    "https://harness.empire.edu.vn/": "tests/test_scope_gate.py:351",
    "https://queue-claim-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:89",
    "https://fencing-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:134",
    "https://retry-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:194",
    "https://reaper-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:244",
    "https://cancel-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:299",
    "https://overrun-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:360",
    "https://dedup-trigger-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:447",
    "https://status-endpoint-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:489",
    "https://event-replay-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:534",
    "https://sse-stream-test.local/": "tests/test_milestone_b_queue_and_scheduler.py:592",
}


def sanitized_locator(value: str) -> str:
    """Never publish URL userinfo, query secrets or fragments in an audit."""
    try:
        p = urlsplit(value)
        if p.scheme in ("http", "https") and p.hostname:
            host = f"[{p.hostname}]" if ":" in p.hostname else p.hostname
            return urlunsplit((p.scheme, host + (f":{p.port}" if p.port else ""), p.path or "/", "", ""))
    except (ValueError, TypeError):
        pass
    # Artifact locators can also contain credentials: expose only a hash.
    return "non-http:" + hashlib.sha256(str(value).encode()).hexdigest()[:16]


@lru_cache(maxsize=1)
def acceptance_fixture_index() -> dict[str, str]:
    # This repository function only constructs data; it performs no imports of
    # application settings, DB access or network requests.
    return {item["id"]: item["target_locator"]
            for item in UltraScanPlanner().generate_acceptance_fixture_379()}


def fixture_provenance(asset_id, locator: str) -> str | None:
    expected = acceptance_fixture_index().get(str(asset_id))
    if expected is not None:
        return ("ACCEPTANCE_FIXTURE_379" if expected == locator else "ACCEPTANCE_FIXTURE_ID_RETARGETED")
    # Do not classify a real hostname as a fixture merely because it looks like
    # service-0001; exact locators from the generator establish provenance.
    if locator in acceptance_fixture_index().values():
        return "ACCEPTANCE_FIXTURE_LOCATOR"
    safe = sanitized_locator(locator)
    if safe in LEGACY_TEST_TARGETS:
        return "LEGACY_TEST_LOCATOR:" + LEGACY_TEST_TARGETS[safe]
    if re.fullmatch(r"https://finding-life-[0-9a-f]{8}\.empire\.edu\.vn/", safe):
        return "LEGACY_TEST_LOCATOR:tests/test_tier3_cross_feature.py:103"
    if re.fullmatch(r"https://asset-renamed-[0-9a-f]{6}\.example\.com/", safe):
        return "LEGACY_TEST_LOCATOR:tests/test_milestone_a_control_plane.py:431"
    if re.fullmatch(r"https://stop-test-[0-9a-f]{6}\.example\.com/", safe):
        return "LEGACY_TEST_LOCATOR:tests/test_milestone_a_control_plane.py:514"
    return None


def seeded_proof(proof: dict) -> bool:
    return json_object(proof.get("proof_data")).get("initial_seed") is True


def usable_proof(proof: dict, now: datetime | None = None) -> bool:
    if seeded_proof(proof) or proof.get("status") != "VERIFIED" or not proof.get("verified_at"):
        return False
    expires = proof.get("expires_at")
    if expires:
        try:
            expires = datetime.fromisoformat(expires) if isinstance(expires, str) else expires
            expires = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
            if expires <= (now or datetime.now(timezone.utc)):
                return False
        except (ValueError, TypeError, AttributeError):
            return False
    return True


def _is_primary(locator: str) -> bool:
    try:
        p = urlsplit(locator)
        return (p.scheme == "https" and p.hostname == "empire.edu.vn" and p.port in (None, 443)
                and p.path in ("", "/") and not (p.query or p.fragment or p.username or p.password))
    except (ValueError, TypeError):
        return False


def reconcile(assets: list[dict], proofs: list[dict], scopes: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    by_asset: dict[str, list[dict]] = {}
    for proof in proofs:
        by_asset.setdefault(str(proof["asset_id"]), []).append(proof)
    rows, health, credential_refs, duplicates = [], [], [], {}
    for asset in assets:
        aid, locator = str(asset["id"]), asset["target_locator"]
        related = by_asset.get(aid, [])
        fixture = fixture_provenance(aid, locator)
        seed = any(seeded_proof(p) for p in related)
        genuine = any(usable_proof(p, now) for p in related)
        primary = _is_primary(locator)
        try:
            host = (urlsplit(locator).hostname or "").lower()
        except ValueError:
            host = ""
        reserved = (host in ("localhost", "example.com", "example.org", "example.net") or
                    host.endswith((".invalid", ".localhost", ".local", ".example.com", ".example.org", ".example.net")))
        if fixture or reserved:
            classification = "SEEDED_OR_TEST"
        elif primary:
            classification = "OWNER_DESIGNATED_PRIMARY"
        elif seed:
            classification = "SEEDED_OR_TEST"
        else:
            classification = "UNKNOWN_OR_UNVERIFIED"
        safe = sanitized_locator(locator)
        duplicates.setdefault(safe, []).append(aid)
        policy = json_object(asset.get("assessment_policy"))
        hc = policy.get("health_check") or {}
        if isinstance(hc, dict) and hc.get("url"):
            health.append({"asset_id": aid, "endpoint": sanitized_locator(hc["url"]),
                           "approval_recorded": bool(hc.get("approved_by")),
                           "purpose_verified_by_this_audit": False})
        auth = json_object(asset.get("auth_profile"))
        # Report the location of a reference, never its value. An untyped legacy
        # field is not evidence of an approved customer identity.
        for key in ("secret_ref", "credential_ref", "secret_store_ref"):
            if isinstance(auth, dict) and auth.get(key):
                credential_refs.append({"asset_id": aid, "reference_location": f"assets/{aid}/auth_profile/{key}",
                                        "approval_verified": False})
        rows.append({"asset_id": aid, "target": safe, "environment": asset.get("environment"),
                     "classification": classification,
                     "provenance": fixture or ("INITIAL_SEED_PROOF" if seed else "RESERVED_TEST_HOST" if reserved else "NO_SEED_PROVENANCE_FOUND"),
                     "stored_verification_status": asset.get("verification_status"),
                     "non_seed_unexpired_proof_recorded": genuine,
                     "configured_health_endpoint": bool(hc.get("url")) if isinstance(hc, dict) else False,
                     "target_auth_profile_present": bool(auth),
                     "owner_designation_matches": primary and not fixture,
                     "automated_assessment_ready": False,
                     "scope_basis": SCOPE_SOURCE if primary else "No current owner designation; do not promote or scan"})
    counts = {key: 0 for key in ("OWNER_DESIGNATED_PRIMARY", "SEEDED_OR_TEST", "UNKNOWN_OR_UNVERIFIED")}
    counts.update(Counter(r["classification"] for r in rows))
    return {"schema": "noosforge.inventory-reconciliation/1", "observed_at": now.isoformat(),
            "database_modified": False, "network_requests": 0,
            "scope_source": SCOPE_SOURCE, "owner_designated_production_targets": [PRIMARY_TARGET],
            "production_scope_is_complete": False, "counts": {"total": len(rows), **counts},
            "stored_verification_counts": dict(Counter(a.get("verification_status") or "UNSET" for a in assets)),
            "ownership_proof_rows": len(proofs), "assessment_scope_rows": len(scopes),
            "assets": sorted(rows, key=lambda r: (r["classification"], r["target"])),
            "duplicate_locators": [{"target": k, "asset_ids": v} for k, v in duplicates.items() if len(v) > 1],
            "customer_health_endpoints": health, "credential_reference_locations": credential_refs,
            "target_auth_profiles_present": sum(r["target_auth_profile_present"] for r in rows),
            "emergency_stops_recorded": sum(bool(s.get("emergency_stop_active")) for s in scopes),
            "coverage_gaps": [
                {"code": "AUTHENTICATED_COVERAGE_NOT_CONFIGURED", "checks": ["BOLA", "BFLA", "RBAC", "TENANT_ISOLATION", "SESSION", "ACCOUNT_SECURITY"],
                 "reason": "No owner-approved identity registry or safe test-object manifest supplied; legacy auth fields are not approval."},
                {"code": "PRODUCTION_INVENTORY_INCOMPLETE", "reason": "Only the primary root is designated; historical domains/ranges/services require reconciliation."},
                {"code": "HEALTH_ENDPOINT_PURPOSE_NOT_VERIFIED", "reason": "A root-page observation is not an approved application health endpoint."}],
            "configuration_note": "No secret reference or health endpoint is invented. This is inventory reconciliation, not customer security-test results."}


def json_object(value) -> dict:
    """Parse legacy JSON defensively without emitting its contents on errors."""
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


async def execution_block_reasons(db, assets) -> dict[str, str]:
    """Reject known fixtures and seed-only proofs without rewriting legacy rows."""
    from sqlalchemy import select
    from backend.app.models.proof import AssetOwnershipProof

    assets = list(assets)
    if not assets:
        return {}
    rows = (await db.execute(select(AssetOwnershipProof.asset_id, AssetOwnershipProof.status,
                                   AssetOwnershipProof.verified_at, AssetOwnershipProof.expires_at,
                                   AssetOwnershipProof.proof_data).where(
                                       AssetOwnershipProof.asset_id.in_([a.id for a in assets])))).mappings().all()
    by_asset: dict[str, list[dict]] = {}
    for row in rows:
        by_asset.setdefault(str(row["asset_id"]), []).append(dict(row))
    blocked = {}
    for asset in assets:
        aid = str(asset.id)
        proofs = by_asset.get(aid, [])
        fixture = fixture_provenance(asset.id, asset.target_locator)
        if fixture:
            blocked[aid] = "SYNTHETIC_INVENTORY"
        elif any(seeded_proof(p) for p in proofs) and not any(usable_proof(p) for p in proofs):
            blocked[aid] = "SEEDED_OWNERSHIP_NOT_VERIFIED"
    return blocked

"""Milestone 3 · driver-level golden tests (no DB, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.engines import sbom
from backend.app.engines.advisories import AdvisoryIndex, cvss3_base_score, parse_snapshot
from backend.app.engines.versions import UnsupportedEcosystem, compare

DATA = Path(__file__).parent / "data"


def _index() -> AdvisoryIndex:
    return AdvisoryIndex.build(parse_snapshot((DATA / "advisories_pilot_v1.json").read_bytes()))


@pytest.mark.parametrize("eco,a,b,expected", [
    ("PyPI", "1.5.0", "2.0.0", -1), ("PyPI", "2.0.0rc1", "2.0.0", -1), ("PyPI", "2.0", "2.0.0", 0),
    ("npm", "1.4.1", "1.4.2", -1), ("npm", "1.4.2-beta.1", "1.4.2", -1), ("npm", "1.10.0", "1.9.9", 1),
    ("Maven", "2.0-beta9", "2.14.1", -1), ("Maven", "2.14.1", "2.15.0", -1), ("Maven", "2.15.0", "2.15", 0),
    ("Maven", "1.0-rc1", "1.0", -1), ("Maven", "1.0.1", "1.0-sp", 1),
    ("Go", "v1.2.3", "v1.10.0", -1),
])
def test_version_ordering(eco, a, b, expected):
    assert compare(eco, a, b) == expected


def test_unknown_ecosystem_is_refused_not_guessed():
    with pytest.raises(UnsupportedEcosystem):
        compare("Debian", "1.0", "2.0")


def test_cvss_v3_scores():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H") == 9.8
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H") == 10.0
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:H/PR:L/UI:R/S:U/C:L/I:N/A:N") == 2.6
    assert cvss3_base_score("garbage") is None


def test_digest_is_order_and_format_independent():
    recs = parse_snapshot((DATA / "advisories_pilot_v1.json").read_bytes())
    a = AdvisoryIndex.build(recs).digest
    b = AdvisoryIndex.build(list(reversed(json.loads(json.dumps(recs))))).digest
    assert a == b and len(a) == 64


def test_golden_cyclonedx_analysis():
    res = sbom.analyze((DATA / "sbom_vulnerable.cdx.json").read_bytes(), _index())
    assert res.format == "CycloneDX" and res.components_total == 7
    assert res.components_evaluated == 5  # alpha, beta, gamma, delta, epsilon (nested)
    got = {(m["component"]["name"], m["advisory"]["advisory_id"], m["advisory"]["severity"],
            m["advisory"]["severity_basis"]) for m in res.matches}
    assert got == {
        ("pilot-test-alpha", "PILOT-TEST-0001", "CRITICAL", "cvss_v3_vector"),
        ("@pilot-test/beta", "PILOT-TEST-0002", "MEDIUM", "database_specific.severity"),
        ("org.pilottest:gamma", "PILOT-TEST-0003", "CRITICAL", "cvss_v3_vector"),
        ("pilot-test-delta", "PILOT-TEST-0004", "MEDIUM", "unrated_default"),
    }
    reasons = {n["ref"]: n["reason"] for n in res.not_evaluated}
    assert reasons == {"nopurl": "no supported purl", "deb": "no supported purl"}
    alpha = next(m for m in res.matches if m["advisory"]["advisory_id"] == "PILOT-TEST-0001")
    assert alpha["advisory"]["fixed_versions"] == ["2.0.0"] and "2.0.0" in alpha["remediation"]


def test_patched_sbom_has_zero_matches_but_is_evaluated():
    res = sbom.analyze((DATA / "sbom_fixed.cdx.json").read_bytes(), _index())
    assert res.matches == [] and res.components_evaluated == 3


def test_spdx_supported():
    res = sbom.analyze((DATA / "sbom_spdx.json").read_bytes(), _index())
    assert res.format == "SPDX" and [m["advisory"]["advisory_id"] for m in res.matches] == ["PILOT-TEST-0001"]


@pytest.mark.parametrize("raw", [b"{not json", b"[]", b'{"hello": "world"}', b"\xff\xfe"])
def test_parse_errors_are_classified(raw):
    with pytest.raises(sbom.SbomParseError):
        sbom.analyze(raw, _index())


def test_result_document_is_deterministic():
    idx = _index()
    raw = (DATA / "sbom_vulnerable.cdx.json").read_bytes()
    kw = dict(execution_id="e", attempt_id="a", input_sha256="x", snapshot={"digest": idx.digest})
    a = sbom.result_document(sbom.analyze(raw, idx), **kw)
    b = sbom.result_document(sbom.analyze(raw, idx), **kw)
    assert a == b and sbom.sha256_bytes(a) == sbom.sha256_bytes(b)

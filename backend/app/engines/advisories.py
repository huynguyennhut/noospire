"""OSV-format advisory snapshot: validation, content digest, indexing, range evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backend.app.engines.versions import UnparseableVersion, UnsupportedEcosystem, compare


class AdvisoryFormatError(ValueError):
    pass


def normalize_name(ecosystem: str, name: str) -> str:
    eco = ecosystem.lower()
    n = name.strip()
    if eco == "pypi":
        return re.sub(r"[-_.]+", "-", n).lower()
    if eco in ("npm", "maven", "nuget", "packagist", "rubygems", "crates.io", "hex", "pub"):
        return n.lower()
    return n


def canonical_digest(records: List[dict]) -> str:
    """Digest independent of file formatting and record order."""
    canon = sorted(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for r in records)
    h = hashlib.sha256()
    for line in canon:
        h.update(line.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def parse_snapshot(raw: bytes) -> List[dict]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdvisoryFormatError(f"advisory snapshot is not valid JSON: {type(exc).__name__}") from exc
    if isinstance(data, dict) and isinstance(data.get("vulns"), list):
        data = data["vulns"]
    if not isinstance(data, list) or not data:
        raise AdvisoryFormatError("advisory snapshot must be a non-empty JSON list of OSV records")
    for i, rec in enumerate(data):
        if not isinstance(rec, dict) or not isinstance(rec.get("id"), str) or not isinstance(rec.get("affected"), list):
            raise AdvisoryFormatError(f"record #{i} is not an OSV record (needs string id and affected list)")
    return data


# ------------------------------------------------------------------ CVSS v3.x base score

_W = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62},
    "C": {"H": 0.56, "L": 0.22, "N": 0.0},
    "I": {"H": 0.56, "L": 0.22, "N": 0.0},
    "A": {"H": 0.56, "L": 0.22, "N": 0.0},
}


def _roundup(x: float) -> float:
    i = int(round(x * 100000))
    return i / 100000.0 if i % 10000 == 0 else (math.floor(i / 10000) + 1) / 10.0


def cvss3_base_score(vector: str) -> Optional[float]:
    if not vector or not vector.startswith("CVSS:3"):
        return None
    try:
        m = dict(p.split(":", 1) for p in vector.split("/")[1:])
        scope_changed = m["S"] == "C"
        pr = {"N": 0.85, "L": 0.68 if scope_changed else 0.62, "H": 0.5 if scope_changed else 0.27}[m["PR"]]
        iss = 1 - (1 - _W["C"][m["C"]]) * (1 - _W["I"][m["I"]]) * (1 - _W["A"][m["A"]])
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if scope_changed else 6.42 * iss
        expl = 8.22 * _W["AV"][m["AV"]] * _W["AC"][m["AC"]] * pr * _W["UI"][m["UI"]]
        if impact <= 0:
            return 0.0
        raw = min(1.08 * (impact + expl), 10) if scope_changed else min(impact + expl, 10)
        return _roundup(raw)
    except (KeyError, ValueError):
        return None


def severity_of(rec: dict) -> Tuple[str, Optional[float], Optional[str], str]:
    """Return (severity, score, vector, basis). basis says where the severity came from."""
    vector = None
    score = None
    for s in rec.get("severity") or []:
        if isinstance(s, dict) and str(s.get("type", "")).startswith("CVSS_V3"):
            vector = s.get("score")
            score = cvss3_base_score(vector or "")
            break
    if score is not None:
        sev = "CRITICAL" if score >= 9 else "HIGH" if score >= 7 else "MEDIUM" if score >= 4 else "LOW" if score > 0 else "INFO"
        return sev, score, vector, "cvss_v3_vector"
    ds = (rec.get("database_specific") or {}).get("severity")
    if isinstance(ds, str) and ds.upper() in ("CRITICAL", "HIGH", "MEDIUM", "MODERATE", "LOW"):
        sev = "MEDIUM" if ds.upper() == "MODERATE" else ds.upper()
        return sev, None, vector, "database_specific.severity"
    # No severity data in the advisory: MEDIUM as a triage default, flagged via basis so the
    # UI/report can show "unrated" instead of presenting it as a scored severity.
    return "MEDIUM", None, vector, "unrated_default"


# ------------------------------------------------------------------ matching

@dataclass
class Match:
    advisory_id: str
    aliases: List[str]
    summary: str
    severity: str
    cvss_score: Optional[float]
    cvss_vector: Optional[str]
    severity_basis: str
    matched_by: str  # "versions" | "range:<type>"
    range_events: List[dict]
    fixed_versions: List[str]
    references: List[str]
    modified: Optional[str]
    published: Optional[str]


@dataclass
class AdvisoryIndex:
    digest: str
    by_pkg: Dict[Tuple[str, str], List[Tuple[dict, dict]]] = field(default_factory=dict)
    ecosystems: List[str] = field(default_factory=list)
    modified_max: Optional[str] = None
    record_count: int = 0

    @classmethod
    def build(cls, records: List[dict]) -> "AdvisoryIndex":
        idx = cls(digest=canonical_digest(records), record_count=len(records))
        ecos = set()
        mods = []
        for rec in records:
            if rec.get("withdrawn"):
                continue
            if rec.get("modified"):
                mods.append(rec["modified"])
            for aff in rec.get("affected") or []:
                pkg = (aff or {}).get("package") or {}
                eco, name = pkg.get("ecosystem"), pkg.get("name")
                if not eco or not name:
                    continue
                eco_l = eco.split(":")[0].lower()
                ecos.add(eco_l)
                idx.by_pkg.setdefault((eco_l, normalize_name(eco_l, name)), []).append((rec, aff))
        idx.ecosystems = sorted(ecos)
        idx.modified_max = max(mods) if mods else None
        return idx

    def lookup(self, ecosystem: str, name: str, version: str) -> List[Match]:
        eco = ecosystem.lower()
        out: List[Match] = []
        for rec, aff in self.by_pkg.get((eco, normalize_name(eco, name)), []):
            hit = _affected(eco, version, aff)
            if hit is None:
                continue
            matched_by, events = hit
            sev, score, vector, basis = severity_of(rec)
            fixed = sorted({e["fixed"] for r in aff.get("ranges") or [] for e in r.get("events") or [] if "fixed" in e})
            out.append(Match(
                advisory_id=rec["id"], aliases=list(rec.get("aliases") or []), summary=rec.get("summary") or rec["id"],
                severity=sev, cvss_score=score, cvss_vector=vector, severity_basis=basis, matched_by=matched_by,
                range_events=events, fixed_versions=fixed,
                references=[r.get("url") for r in rec.get("references") or [] if isinstance(r, dict) and r.get("url")][:10],
                modified=rec.get("modified"), published=rec.get("published"),
            ))
        return out


def _affected(eco: str, version: str, aff: dict) -> Optional[Tuple[str, List[dict]]]:
    """OSV semantics: explicit `versions` list, or SEMVER/ECOSYSTEM ranges. GIT ranges ignored.
    Raises UnsupportedEcosystem / UnparseableVersion to the caller (component not evaluated)."""
    if version in (aff.get("versions") or []):
        return "versions", []
    for rng in aff.get("ranges") or []:
        rtype = str(rng.get("type", "")).upper()
        if rtype not in ("SEMVER", "ECOSYSTEM"):
            continue
        cmp_eco = "semver" if rtype == "SEMVER" else eco
        events = rng.get("events") or []
        introduced: Optional[str] = None
        active = False
        for ev in events:
            if "introduced" in ev:
                introduced = ev["introduced"]
                active = introduced == "0" or compare(cmp_eco, version, introduced) >= 0
            elif "fixed" in ev and introduced is not None:
                if active and compare(cmp_eco, version, ev["fixed"]) < 0:
                    return f"range:{rtype}", events
                introduced, active = None, False
            elif "last_affected" in ev and introduced is not None:
                if active and compare(cmp_eco, version, ev["last_affected"]) <= 0:
                    return f"range:{rtype}", events
                introduced, active = None, False
            elif "limit" in ev and introduced is not None:
                if active and compare(cmp_eco, version, ev["limit"]) < 0:
                    return f"range:{rtype}", events
                introduced, active = None, False
        if active:  # open-ended range: introduced with no upper bound
            return f"range:{rtype}", events
    return None


__all__ = ["AdvisoryIndex", "AdvisoryFormatError", "Match", "canonical_digest", "parse_snapshot",
           "UnsupportedEcosystem", "UnparseableVersion", "cvss3_base_score"]

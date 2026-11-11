"""Native SBOM component-analysis driver (no network, no subprocess).

Input: CycloneDX JSON (1.2–1.6) or SPDX JSON (2.2/2.3) file supplied by the system owner.
Rules: an imported, content-addressed OSV advisory snapshot.
Output: a normalized, deterministic result document (hash recorded as evidence).

Result kinds the caller must keep apart:
- succeeded with N >= 0 matches (0 is a valid, evaluated result: components_evaluated > 0)
- skipped: SBOM parsed but lists no components (nothing to evaluate)
- failed/INPUT_PARSE_ERROR: file is not a supported SBOM
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional
from urllib.parse import unquote

from backend.app.engines.advisories import AdvisoryIndex
from backend.app.engines.versions import UnparseableVersion, UnsupportedEcosystem

DRIVER_NAME = "noospire-sbom-native"
DRIVER_VERSION = "1.0.0"
ENGINE_ID = "sbom"

PURL_ECOSYSTEM = {
    "pypi": "PyPI", "npm": "npm", "maven": "Maven", "golang": "Go", "cargo": "crates.io", "nuget": "NuGet",
    "composer": "Packagist", "gem": "RubyGems", "hex": "Hex", "pub": "Pub",
}


class SbomParseError(ValueError):
    pass


@dataclass
class Component:
    ref: str
    name: str
    version: Optional[str]
    purl: Optional[str]
    ecosystem: Optional[str]
    advisory_name: Optional[str]


@dataclass
class SbomResult:
    format: str
    spec_version: Optional[str]
    components_total: int
    components_evaluated: int
    not_evaluated: List[dict] = field(default_factory=list)
    matches: List[dict] = field(default_factory=list)


def parse_purl(purl: str) -> Optional[Dict[str, str]]:
    if not purl or not purl.startswith("pkg:"):
        return None
    body = purl[4:].split("#", 1)[0].split("?", 1)[0]
    if "/" not in body:
        return None
    ptype, rest = body.split("/", 1)
    version = None
    if "@" in rest:
        rest, version = rest.rsplit("@", 1)
        version = unquote(version)
    parts = [unquote(p) for p in rest.split("/") if p]
    if not parts:
        return None
    name = parts[-1]
    namespace = "/".join(parts[:-1]) or None
    return {"type": ptype.lower(), "namespace": namespace, "name": name, "version": version}


def _advisory_name(ptype: str, namespace: Optional[str], name: str) -> str:
    if ptype == "maven" and namespace:
        return f"{namespace}:{name}"
    if ptype in ("npm", "golang", "composer") and namespace:
        return f"{namespace}/{name}"
    return name


def _component_from(ref: str, name: str, version: Optional[str], purl: Optional[str]) -> Component:
    eco = adv_name = None
    p = parse_purl(purl) if purl else None
    if p:
        eco = PURL_ECOSYSTEM.get(p["type"])
        adv_name = _advisory_name(p["type"], p["namespace"], p["name"])
        version = version or p["version"]
    return Component(ref=ref, name=name or (p["name"] if p else ref), version=version, purl=purl,
                     ecosystem=eco, advisory_name=adv_name)


def parse_sbom(raw: bytes) -> tuple[str, Optional[str], List[Component]]:
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SbomParseError(f"not valid UTF-8 JSON ({type(exc).__name__})") from exc
    if not isinstance(doc, dict):
        raise SbomParseError("SBOM root must be a JSON object")

    if doc.get("bomFormat") == "CycloneDX":
        comps: List[Component] = []

        def walk(items, depth=0):
            if depth > 50:
                raise SbomParseError("component nesting too deep")
            for i, c in enumerate(items or []):
                if not isinstance(c, dict):
                    raise SbomParseError("component entry is not an object")
                comps.append(_component_from(c.get("bom-ref") or f"c{len(comps)}", c.get("name") or "",
                                             c.get("version"), c.get("purl")))
                walk(c.get("components"), depth + 1)

        walk(doc.get("components"))
        return "CycloneDX", str(doc.get("specVersion") or ""), comps

    if str(doc.get("spdxVersion", "")).startswith("SPDX-"):
        comps = []
        for i, pkg in enumerate(doc.get("packages") or []):
            if not isinstance(pkg, dict):
                raise SbomParseError("package entry is not an object")
            purl = None
            for ref in pkg.get("externalRefs") or []:
                if isinstance(ref, dict) and ref.get("referenceType") == "purl":
                    purl = ref.get("referenceLocator")
                    break
            comps.append(_component_from(pkg.get("SPDXID") or f"p{i}", pkg.get("name") or "",
                                         pkg.get("versionInfo"), purl))
        return "SPDX", str(doc.get("spdxVersion")), comps

    raise SbomParseError("unsupported document: expected CycloneDX JSON (bomFormat) or SPDX JSON (spdxVersion)")


def analyze(raw: bytes, index: AdvisoryIndex) -> SbomResult:
    fmt, spec, comps = parse_sbom(raw)
    res = SbomResult(format=fmt, spec_version=spec, components_total=len(comps), components_evaluated=0)
    for c in comps:
        if not c.purl or not c.ecosystem or not c.advisory_name:
            res.not_evaluated.append({"ref": c.ref, "name": c.name, "reason": "no supported purl"})
            continue
        if not c.version:
            res.not_evaluated.append({"ref": c.ref, "name": c.name, "purl": c.purl, "reason": "no version"})
            continue
        try:
            hits = index.lookup(c.ecosystem, c.advisory_name, c.version)
        except UnsupportedEcosystem:
            res.not_evaluated.append({"ref": c.ref, "purl": c.purl, "reason": f"ecosystem {c.ecosystem} unsupported"})
            continue
        except UnparseableVersion:
            res.not_evaluated.append({"ref": c.ref, "purl": c.purl, "reason": f"unparseable version {c.version!r}"})
            continue
        res.components_evaluated += 1
        for m in hits:
            res.matches.append({
                "component": {"ref": c.ref, "name": c.advisory_name, "version": c.version, "purl": c.purl,
                              "ecosystem": c.ecosystem},
                "advisory": asdict(m),
                "remediation": (f"Upgrade {c.advisory_name} to {', '.join(m.fixed_versions)} or later."
                                if m.fixed_versions else "No fixed version published; mitigate or replace the component."),
            })
    res.matches.sort(key=lambda x: (x["component"]["purl"], x["advisory"]["advisory_id"]))
    return res


def result_document(result: SbomResult, *, execution_id: str, attempt_id: str, input_sha256: str,
                    snapshot: dict) -> bytes:
    """Deterministic JSON bytes for the stored evidence file."""
    doc = {
        "schema": "noospire.engine-result/1",
        "engine_id": ENGINE_ID,
        "driver": DRIVER_NAME,
        "driver_version": DRIVER_VERSION,
        "execution_mode": "native",
        "execution_id": execution_id,
        "attempt_id": attempt_id,
        "input": {"sha256": input_sha256, "format": result.format, "spec_version": result.spec_version},
        "rules": snapshot,
        "coverage": {
            "components_total": result.components_total,
            "components_evaluated": result.components_evaluated,
            "components_not_evaluated": len(result.not_evaluated),
        },
        "not_evaluated": result.not_evaluated,
        "matches": result.matches,
    }
    return json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

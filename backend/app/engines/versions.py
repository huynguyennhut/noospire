"""Version comparison per ecosystem for advisory range matching.

- PyPI: PEP 440 via `packaging` (exact semantics).
- npm, Go, crates.io, NuGet, Packagist, RubyGems, Hex, Pub, SEMVER ranges: SemVer 2.0 precedence.
- Maven: Maven ComparableVersion-style ordering (qualifiers alpha < beta < milestone < rc < snapshot < "" < sp).
- Anything else: refused (raises UnsupportedEcosystem) so the caller reports the component as
  not evaluated instead of guessing.
"""

from __future__ import annotations

import re
from functools import cmp_to_key
from typing import List

from packaging.version import InvalidVersion, Version


class UnsupportedEcosystem(ValueError):
    pass


class UnparseableVersion(ValueError):
    pass


SEMVER_ECOSYSTEMS = {"npm", "go", "crates.io", "nuget", "packagist", "rubygems", "hex", "pub", "semver"}


def _cmp(a, b) -> int:
    return (a > b) - (a < b)


# ------------------------------------------------------------------ SemVer 2.0

_SEMVER = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def _semver_key(v: str):
    m = _SEMVER.match(v.strip())
    if not m:
        raise UnparseableVersion(v)
    major, minor, patch = (int(x) if x else 0 for x in m.group(1, 2, 3))
    pre = m.group(4)
    return (major, minor, patch), pre


def _cmp_semver(a: str, b: str) -> int:
    (ca, pa), (cb, pb) = _semver_key(a), _semver_key(b)
    if ca != cb:
        return _cmp(ca, cb)
    if pa == pb:
        return 0
    if pa is None:
        return 1
    if pb is None:
        return -1
    for x, y in zip(pa.split("."), pb.split(".")):
        if x == y:
            continue
        xn, yn = x.isdigit(), y.isdigit()
        if xn and yn:
            return _cmp(int(x), int(y))
        if xn != yn:
            return -1 if xn else 1
        return _cmp(x, y)
    return _cmp(len(pa.split(".")), len(pb.split(".")))


# ------------------------------------------------------------------ Maven

_MAVEN_QUAL = {"alpha": 1, "a": 1, "beta": 2, "b": 2, "milestone": 3, "m": 3, "rc": 4, "cr": 4,
               "snapshot": 5, "": 6, "ga": 6, "final": 6, "release": 6, "sp": 7}


def _maven_tokens(v: str) -> List:
    v = v.strip().lower()
    if not v:
        raise UnparseableVersion(v)
    out = []
    for part in re.findall(r"\d+|[a-z]+", v):
        if part.isdigit():
            out.append((1, int(part)))
        else:
            rank = _MAVEN_QUAL.get(part, 0)
            # ga/final/release are aliases of the plain release; compare as the same token.
            out.append((0, rank, "" if rank == _MAVEN_QUAL[""] else part))
    # Maven normalisation: trailing zeros and release qualifiers are insignificant (2.15.0 == 2.15).
    while out and (out[-1] == (1, 0) or out[-1] == (0, _MAVEN_QUAL[""], "")):
        out.pop()
    return out


def _cmp_maven(a: str, b: str) -> int:
    ta, tb = _maven_tokens(a), _maven_tokens(b)
    n = max(len(ta), len(tb))
    num_pad, rel_pad = (1, 0), (0, _MAVEN_QUAL[""], "")
    for i in range(n):
        x = ta[i] if i < len(ta) else None
        y = tb[i] if i < len(tb) else None
        # Missing positions pad as 0 against a number, as the plain release against a qualifier.
        if x is None:
            x = num_pad if y[0] == 1 else rel_pad
        if y is None:
            y = num_pad if x[0] == 1 else rel_pad
        if x == y:
            continue
        if x[0] != y[0]:
            # A numeric component always outranks a qualifier (1.0.1 > 1.0-sp > 1.0 > 1.0-rc).
            return 1 if x[0] == 1 else -1
        return _cmp(x[1:], y[1:])
    return 0


# ------------------------------------------------------------------ public

def compare(ecosystem: str, a: str, b: str) -> int:
    eco = (ecosystem or "").strip().lower()
    if eco == "pypi":
        try:
            return _cmp(Version(a), Version(b))
        except InvalidVersion as exc:
            raise UnparseableVersion(str(exc)) from exc
    if eco in SEMVER_ECOSYSTEMS:
        return _cmp_semver(a, b)
    if eco == "maven":
        return _cmp_maven(a, b)
    raise UnsupportedEcosystem(ecosystem)


def sort_key(ecosystem: str):
    return cmp_to_key(lambda a, b: compare(ecosystem, a, b))


SUPPORTED_ECOSYSTEMS = sorted({"pypi", "maven", *SEMVER_ECOSYSTEMS})

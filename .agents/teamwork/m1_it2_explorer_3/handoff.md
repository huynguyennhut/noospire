# Milestone 1 Iteration 2 Explorer 3 Handoff Report: SSRF Edge Defense & IANA Special-Purpose Address Hardening

**Agent**: SSRF Edge Defense Explorer (`m1_it2_explorer_3`)  
**Working Directory**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_it2_explorer_3`  
**Parent**: Project Orchestrator (`eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb`)  
**Status**: **INVESTIGATION COMPLETE — ROOT CAUSE CONFIRMED & 5-LAYER DEFENSE-IN-DEPTH ARCHITECTURE FORMULATED**

---

## 1. Observation

### 1.1. Empirical Reproduction of ANOMALY-M1-02
Direct execution of `backend.app.core.ssrf.validate_egress_target` under development settings (`ENVIRONMENT="development"`, `settings.is_production=False`) with `allow_private=True`:

- **Test Command**:
  ```python
  from backend.app.core.ssrf import validate_egress_target
  url, ip = validate_egress_target("http://0.0.0.0:8080", allow_private=True)
  print(url, ip)
  ```
- **Observed Result**:
  ```text
  ALLOWED: http://0.0.0.0:8080 0.0.0.0
  ```
- **Observed Result for IPv6 Unspecified (`::`)**:
  ```python
  url, ip = validate_egress_target("http://[::]:8080", allow_private=True)
  # Output: ALLOWED: http://:::8080 ::
  ```
- **Observed Result for `0.0.0.0/8` Host Addresses (`0.1.2.3`)**:
  ```python
  url, ip = validate_egress_target("http://0.1.2.3:80", allow_private=True)
  # Output: ALLOWED: http://0.1.2.3:80 0.1.2.3
  ```

### 1.2. Investigation of `backend/app/core/ssrf.py` Lines 170–225
Code inspection of `backend/app/core/ssrf.py`:
```python
170:         # In production, allow_private is strictly forbidden under all circumstances
171:         if settings.is_production:
172:             allow_private = False
...
204:             # Cloud metadata IPs and Link-Local subnets (169.254.0.0/16, fe80::/10) are STRICTLY FORBIDDEN under all circumstances
205:             if str(ip_obj) in cls.CLOUD_METADATA_IPS or ip_obj.is_link_local:
206:                 raise SSRFValidationError(
207:                     f"Target '{hostname}' resolves to protected cloud metadata / link-local address '{ip_obj}'."
208:                 )
209: 
210:             # Check general blocked networks
211:             if cls._is_ip_blocked(ip_obj):
212:                 if allow_private and not settings.is_production and (ip_obj.is_private or ip_obj.is_loopback) and not ip_obj.is_link_local:
213:                     # Authorized private lab target bypass
214:                     continue
215:                 raise SSRFValidationError(
216:                     f"Target '{hostname}' resolves to blocked network address '{ip_obj}' (SSRF security violation)."
217:                 )
```
- In line 205, the **unconditional check** (executed before any `allow_private` evaluation) only covers `cls.CLOUD_METADATA_IPS` and `ip_obj.is_link_local`. It does **not** include `ip_obj.is_unspecified` (`0.0.0.0`, `::`) or `0.0.0.0/8`.
- In line 211, `cls._is_ip_blocked(ip_obj)` evaluates to `True` for `0.0.0.0` (as `ipaddress.ip_network("0.0.0.0/8")` is present in `BLOCKED_NETWORKS`).
- In line 212, the bypass check tests:
  `allow_private and not settings.is_production and (ip_obj.is_private or ip_obj.is_loopback) and not ip_obj.is_link_local`
- Under Python's standard library `ipaddress`:
  - `ipaddress.ip_address("0.0.0.0").is_private` returns `True`.
  - `ipaddress.ip_address("::").is_private` returns `True`.
  - `ipaddress.ip_address("0.1.2.3").is_private` returns `True`.
  - `ipaddress.ip_address("0.0.0.0").is_link_local` returns `False`.
- Consequently, line 212 evaluates to `True`, triggering `continue` (line 214) and bypassing the `SSRFValidationError`.

### 1.3. Python `ipaddress` Standard Library Attribute Matrix
Direct programmatic inspection of Python 3.14 `ipaddress.IPv4Address` and `IPv6Address`:

| IP Address | Target Class / RFC | `is_private` | `is_unspecified` | `is_loopback` | `is_link_local` | `is_multicast` | `is_reserved` | `is_global` | Current Dev Lab Bypass (`allow_private=True`) |
|---|---|---|---|---|---|---|---|---|---|
| `0.0.0.0` | RFC 1122 Unspecified | **`True`** | `True` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (FLAW)** |
| `0.1.2.3` | RFC 1122 "This network" (`0.0.0.0/8`) | **`True`** | `False` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (FLAW)** |
| `::` | RFC 4291 IPv6 Unspecified | **`True`** | `True` | `False` | `False` | `False` | `True` | `False` | **ALLOWED (FLAW)** |
| `127.0.0.1` | RFC 1122 IPv4 Loopback | `True` | `False` | `True` | `False` | `False` | `False` | `False` | ALLOWED (Intended Lab) |
| `::1` | RFC 4291 IPv6 Loopback | `True` | `False` | `True` | `False` | `False` | `True` | `False` | ALLOWED (Intended Lab) |
| `10.0.0.1` | RFC 1918 Class A Private | `True` | `False` | `False` | `False` | `False` | `False` | `False` | ALLOWED (Intended Lab) |
| `172.16.0.1` | RFC 1918 Class B Private | `True` | `False` | `False` | `False` | `False` | `False` | `False` | ALLOWED (Intended Lab) |
| `192.168.1.1` | RFC 1918 Class C Private | `True` | `False` | `False` | `False` | `False` | `False` | `False` | ALLOWED (Intended Lab) |
| `fc00::1` | RFC 4193 Unique Local (ULA) | `True` | `False` | `False` | `False` | `False` | `False` | `False` | ALLOWED (Intended Lab) |
| `169.254.1.1` | RFC 3927 IPv4 Link-Local | `True` | `False` | `False` | `True` | `False` | `False` | `False` | BLOCKED (Unconditional) |
| `fe80::1` | RFC 4291 IPv6 Link-Local | `True` | `False` | `False` | `True` | `False` | `False` | `False` | BLOCKED (Unconditional) |
| `169.254.169.254` | AWS/Azure/GCP Metadata | `True` | `False` | `False` | `True` | `False` | `False` | `False` | BLOCKED (Unconditional) |
| `100.64.0.1` | RFC 6598 CGNAT / Shared | **`False`** | `False` | `False` | `False` | `False` | `False` | `False` | BLOCKED (Blocked Nets) |
| `100.100.100.200` | Alibaba Cloud Metadata | `False` | `False` | `False` | `False` | `False` | `False` | `False` | BLOCKED (Metadata Set) |
| `192.0.0.192` | Oracle Cloud Metadata | `True` | `False` | `False` | `False` | `False` | `False` | `False` | BLOCKED (Metadata Set) |
| `192.0.2.1` | RFC 5737 TEST-NET-1 | **`True`** | `False` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (FLAW)** |
| `198.51.100.1` | RFC 5737 TEST-NET-2 | **`True`** | `False` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (FLAW)** |
| `203.0.113.1` | RFC 5737 TEST-NET-3 | **`True`** | `False` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (FLAW)** |
| `198.18.0.1` | RFC 2544 Benchmarking | **`True`** | `False` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (FLAW)** |
| `224.0.0.1` | RFC 5771 IPv4 Multicast | `False` | `False` | `False` | `False` | `True` | `False` | `True` | BLOCKED (Blocked Nets) |
| `240.0.0.1` | RFC 1112 Class E Reserved | **`True`** | `False` | `False` | `False` | `False` | `True` | `False` | **ALLOWED (FLAW)** |
| `255.255.255.255` | RFC 919 Limited Broadcast | **`True`** | `False` | `False` | `False` | `False` | `True` | `False` | **ALLOWED (FLAW)** |
| `2001:db8::1` | RFC 3849 IPv6 Documentation | **`True`** | `False` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (FLAW)** |
| `ff02::1` | RFC 4291 IPv6 Multicast | `False` | `False` | `False` | `False` | `True` | `False` | `True` | **ALLOWED (CRITICAL IN PROD!)** |
| `2002:c0a8:1::` | RFC 3056 6to4 Deprecated | `False` | `False` | `False` | `False` | `False` | `False` | `True` | **ALLOWED (CRITICAL IN PROD!)** |
| `64:ff9b:1::1` | RFC 8215 Local IPv6/IPv4 Trans | `True` | `False` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (CRITICAL IN PROD!)** |
| `3fff::1` | RFC 9637 IPv6 Documentation | `True` | `False` | `False` | `False` | `False` | `False` | `False` | **ALLOWED (CRITICAL IN PROD!)** |

### 1.4. Critical Discovery: IPv6 Multicast (`ff00::/8`) & Missing IANA Blocks
Testing IPv6 multicast target `http://[ff02::1]` against `validate_egress_target`:
- **Command**:
  ```python
  from backend.app.core.ssrf import validate_egress_target
  url, ip = validate_egress_target("http://[ff02::1]", allow_private=False)
  print("ff02::1 in Production:", url, ip)
  ```
- **Observed Result**:
  ```text
  ff02::1 in Production: http://ff02::1 ff02::1
  ```
- **Root Cause**:
  `BLOCKED_NETWORKS` contains IPv4 multicast `224.0.0.0/4`, but **omits IPv6 multicast `ff00::/8`**. Furthermore, for `ff02::1`, `ip_obj.is_link_local` is `False`, and `ip_obj.is_private` is `False`. Because `ff02::1` is not in `BLOCKED_NETWORKS` and not in `CLOUD_METADATA_IPS`, **it passes SSRF validation in both Development AND Production modes!**

### 1.5. Investigation of `backend/app/core/target_verifier.py`
1. **Target Verification Pipeline (`verify_target`)**:
   - `_step_input_validation` (lines 194–196):
     ```python
     normalized_url, first_ip = SSRFProtector.validate_target(clean_loc, allow_private=allow_private)
     ```
     When called with `http://0.0.0.0:8000` and `allow_private=True`:
     - Step 1 (Input Validation): Returns `PASS`.
     - Step 2 (DNS Resolution): Resolves to `["0.0.0.0"]`, returns `PASS`.
     - Step 3 (TLS Verification): Calls `socket.create_connection(("0.0.0.0", 443))` if HTTPS.
     - Step 4 (HTTP Connectivity): Calls `client.get("http://0.0.0.0:8000")`.
     - In Linux/Docker container environments, connecting to `0.0.0.0:port` routes directly to `127.0.0.1:port` (INADDR_ANY localhost alias), allowing access to local host services.
2. **Ownership Challenge Verification (`verify_ownership_challenge`)**:
   - Inspection of lines 710–721:
     ```python
     try:
         scheme, hostname, port = SSRFProtector._parse_and_validate_syntax(target_locator)
     except Exception as e:
         return False, f"Invalid target locator: {e}", {"error": str(e)}

     if method_upper == "HTTP_WELL_KNOWN":
         port_str = f":{port}" if (scheme == "http" and port != 80) or (scheme == "https" and port != 443) else ""
         challenge_url = f"{scheme}://{hostname}{port_str}/.well-known/sentinel-challenge.txt"
         try:
             async with httpx.AsyncClient(verify=True, timeout=self.timeout) as client:
                 resp = await client.get(challenge_url)
     ```
   - **Flaw**: `verify_ownership_challenge` invokes `_parse_and_validate_syntax()` which only checks URL structure and schemes. It **never calls `validate_target`**!
   - **Verification**: Calling `tv.verify_ownership_challenge("http://169.254.169.254", "tok")` attempts an actual HTTP connection to `http://169.254.169.254/.well-known/sentinel-challenge.txt`. In a cloud deployment, this initiates outbound requests to the Cloud Metadata Service.

---

## 2. Logic Chain

1. **Why `0.0.0.0` and `0.0.0.0/8` Pass When `allow_private=True`**:
   - The developer's intention in `ssrf.py:212` was to allow private local lab scanning:
     `(ip_obj.is_private or ip_obj.is_loopback) and not ip_obj.is_link_local`
   - The developer assumed `is_private` corresponded strictly to RFC 1918 (`10/8`, `172.16/12`, `192.168/16`).
   - However, Python's `ipaddress` library adheres strictly to RFC 6890 (IANA IPv4 Special-Purpose Address Registry). RFC 6890 defines `0.0.0.0/8` as "This host on this network", not globally reachable, hence Python marks all addresses in `0.0.0.0/8` as `is_private=True`.
   - Furthermore, `0.0.0.0` has `is_unspecified=True`, `is_private=True`, and `is_link_local=False`.
   - Because `0.0.0.0` is not link-local, the check evaluates to `True`, triggering the lab bypass.

2. **Why Negative Filtering (`not ip_obj.is_unspecified`) Is Necessary But Insufficient**:
   - Checking `and not ip_obj.is_unspecified` successfully blocks `0.0.0.0` and `::`.
   - However, for `0.1.2.3` (or any other address in `0.0.0.0/8`), `is_unspecified` is `False`. Since `is_private` is `True`, `0.1.2.3` would still pass.
   - Additionally, Python marks documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32`), benchmarking (`198.18.0.0/15`), Class E reserved (`240.0.0.0/4`), and broadcast (`255.255.255.255`) as `is_private=True`.
   - Relying on negative subtraction of Python's `is_private` property is fundamentally fragile.

3. **The Superior Defense Architecture: Positive Lab Whitelisting**:
   - In production mode, all private and non-global networks are blocked unconditionally.
   - In dev mode when `allow_private=True`, the bypass must only permit legitimate target spaces:
     - RFC 1918 Private IPv4: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
     - IPv4 Loopback: `127.0.0.0/8`
     - IPv6 Loopback: `::1/128`
     - RFC 4193 Unique Local IPv6: `fc00::/7`
   - By matching against `ALLOWED_LAB_NETWORKS` instead of relying on `ip_obj.is_private`, all documentation subnets, broadcast, benchmarking, and reserved Class E ranges remain strictly blocked.

4. **Defense-in-Depth: Unconditional Blocking Layer**:
   - To prevent architectural regression, `0.0.0.0/8`, `is_unspecified`, `is_multicast`, `is_link_local`, and `CLOUD_METADATA_IPS` must be placed in an unconditional check that executes prior to any `allow_private` evaluation.

---

## 3. Caveats

- **Operating System Socket Semantics on `0.0.0.0`**:
  - On Linux and Darwin (macOS), connecting to `0.0.0.0:PORT` transparently routes to `127.0.0.1:PORT` (listening on all interfaces or loopback). This makes `0.0.0.0` an effective localhost SSRF bypass on Unix containers.
  - On Windows, raw `socket.connect(("0.0.0.0", port))` returns `WSAEADDRNOTAVAIL` (10049). However, proxy servers, DNS resolvers, and container runtimes hosted on Windows or Linux may resolve or forward `0.0.0.0` to localhost. Blocking at the application layer provides OS-independent security.
- **Production Mode Invariant**:
  - In production (`settings.is_production=True`), line 171 forces `allow_private=False`. Therefore, `0.0.0.0`, `127.0.0.1`, and RFC 1918 were already blocked in production. The vulnerability ANOMALY-M1-02 specifically impacts development/staging environments when `allow_private=True`.
  - Conversely, the missing IPv6 multicast (`ff00::/8`) and 6to4 (`2002::/16`) vulnerabilities impacted **both production and development modes**.

---

## 4. Conclusion & Defense-in-Depth Fix Strategy

### 4.1. Core Verdict
1. **ANOMALY-M1-02 Confirmed**: `0.0.0.0`, `0.0.0.0/8`, and `::` bypass SSRF egress protection when `allow_private=True` in development mode.
2. **Secondary Vulnerabilities Discovered**:
   - **IPv6 Multicast Bypass (Critical in Production)**: `ff00::/8` (e.g. `[ff02::1]`) is completely unblocked in all environments.
   - **Missing IANA Special Blocks**: `2002::/16` (6to4), `64:ff9b:1::/48` (local translation), `3fff::/20` (IPv6 documentation).
   - **Unprotected Ownership Challenge in `target_verifier.py`**: `verify_ownership_challenge` bypasses `validate_target`.
   - **IPv6 URL Normalization**: Missing brackets when normalizing IPv6 addresses in `normalized_url` (e.g. `http://:::8080`).

---

### 4.2. Actionable Fix Strategy for Worker

#### Strategy Layer 1: Update `BLOCKED_NETWORKS` & Define `ALLOWED_LAB_NETWORKS` in `backend/app/core/ssrf.py`
In `backend/app/core/ssrf.py`:
1. Add missing IANA networks to `BLOCKED_NETWORKS`:
   - `ipaddress.ip_network("ff00::/8")` (IPv6 Multicast)
   - `ipaddress.ip_network("2002::/16")` (6to4 Relay / Deprecated)
   - `ipaddress.ip_network("64:ff9b:1::/48")` (Local-use IPv4/IPv6 translation)
   - `ipaddress.ip_network("3fff::/20")` (IPv6 Documentation)
2. Define explicit `ALLOWED_LAB_NETWORKS`:
   ```python
   ALLOWED_LAB_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
       ipaddress.ip_network("127.0.0.0/8"),      # IPv4 Loopback
       ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Class A
       ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Class B
       ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Class C
       ipaddress.ip_network("::1/128"),          # IPv6 Loopback
       ipaddress.ip_network("fc00::/7"),         # RFC 4193 Unique Local IPv6 (ULA)
   ]
   ```

#### Strategy Layer 2: Hardened Unconditional & Positive Bypass Check in `validate_target`
Replace lines 204–217 in `backend/app/core/ssrf.py`:

```python
<<<<
            # Cloud metadata IPs and Link-Local subnets (169.254.0.0/16, fe80::/10) are STRICTLY FORBIDDEN under all circumstances
            if str(ip_obj) in cls.CLOUD_METADATA_IPS or ip_obj.is_link_local:
                raise SSRFValidationError(
                    f"Target '{hostname}' resolves to protected cloud metadata / link-local address '{ip_obj}'."
                )

            # Check general blocked networks
            if cls._is_ip_blocked(ip_obj):
                if allow_private and not settings.is_production and (ip_obj.is_private or ip_obj.is_loopback) and not ip_obj.is_link_local:
                    # Authorized private lab target bypass
                    continue
                raise SSRFValidationError(
                    f"Target '{hostname}' resolves to blocked network address '{ip_obj}' (SSRF security violation)."
                )
====
            # 1. Unconditional Blocks (STRICTLY FORBIDDEN under all circumstances in both prod and dev lab modes):
            # - Cloud metadata IPs (169.254.169.254, 100.100.100.200, 192.0.0.192)
            # - Link-Local unicast (169.254.0.0/16, fe80::/10)
            # - Unspecified addresses (0.0.0.0, ::)
            # - "This network" IPv4 block (0.0.0.0/8)
            # - Multicast addresses (224.0.0.0/4, ff00::/8)
            if (
                str(ip_obj) in cls.CLOUD_METADATA_IPS
                or ip_obj.is_link_local
                or ip_obj.is_unspecified
                or ip_obj.is_multicast
                or ip_obj in ipaddress.ip_network("0.0.0.0/8")
            ):
                raise SSRFValidationError(
                    f"Target '{hostname}' resolves to strictly prohibited address '{ip_obj}' (SSRF security violation)."
                )

            # 2. General Blocked Networks & Positive Lab Bypass:
            if cls._is_ip_blocked(ip_obj):
                if (
                    allow_private
                    and not settings.is_production
                    and any(ip_obj in lab_net for lab_net in cls.ALLOWED_LAB_NETWORKS)
                ):
                    # Authorized private lab target bypass (RFC 1918, loopback, ULA only)
                    continue
                raise SSRFValidationError(
                    f"Target '{hostname}' resolves to blocked network address '{ip_obj}' (SSRF security violation)."
                )
>>>>
```

#### Strategy Layer 3: IPv6 Bracket Normalization in `validate_target`
In `backend/app/core/ssrf.py:218`:
```python
<<<<
        normalized_url = f"{scheme}://{hostname}" + (f":{port}" if (scheme == "http" and port != 80) or (scheme == "https" and port != 443) else "")
====
        host_repr = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
        normalized_url = f"{scheme}://{host_repr}" + (f":{port}" if (scheme == "http" and port != 80) or (scheme == "https" and port != 443) else "")
>>>>
```

#### Strategy Layer 4: SSRF Protection for `verify_ownership_challenge` in `target_verifier.py`
In `backend/app/core/target_verifier.py:711`:
```python
<<<<
        try:
            scheme, hostname, port = SSRFProtector._parse_and_validate_syntax(target_locator)
        except Exception as e:
            return False, f"Invalid target locator: {e}", {"error": str(e)}
====
        try:
            normalized_url, first_ip = SSRFProtector.validate_target(target_locator, allow_private=allow_private)
            parsed_loc = urlparse(normalized_url)
            scheme, hostname, port = parsed_loc.scheme, parsed_loc.hostname, parsed_loc.port
        except SSRFValidationError as e:
            return False, f"Ownership challenge rejected by SSRF gatekeeper: {e}", {"error": str(e)}
        except Exception as e:
            return False, f"Invalid target locator: {e}", {"error": str(e)}
>>>>
```

---

## 5. Verification Method

To verify the investigation findings and test the proposed defense-in-depth rules:

### 5.1. Reproduce ANOMALY-M1-02 and IPv6 Multicast Bypass
Run the following Python one-liner to verify the current unpatched behavior:
```powershell
python -c "from backend.app.core.ssrf import validate_egress_target
print('1. 0.0.0.0 under allow_private=True:')
try:
    print('  Result:', validate_egress_target('http://0.0.0.0:8000', allow_private=True))
except Exception as e:
    print('  Blocked:', e)

print('2. ff02::1 under allow_private=False (Production):')
try:
    print('  Result:', validate_egress_target('http://[ff02::1]', allow_private=False))
except Exception as e:
    print('  Blocked:', e)
"
```
*Current output confirms vulnerabilities*:
- `0.0.0.0` returns `('http://0.0.0.0:8000', '0.0.0.0')` (FAILED TO BLOCK).
- `ff02::1` returns `('http://ff02::1', 'ff02::1')` (FAILED TO BLOCK).

### 5.2. Verify the 5-Layer Defense Logic Against All 21 Test Cases
Run the following standalone validation simulation:
```powershell
python -c "import ipaddress

BLOCKED = [
    ipaddress.ip_network('0.0.0.0/8'), ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('100.64.0.0/10'), ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'), ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.0.0.0/24'), ipaddress.ip_network('192.0.2.0/24'),
    ipaddress.ip_network('192.88.99.0/24'), ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('198.18.0.0/15'), ipaddress.ip_network('198.51.100.0/24'),
    ipaddress.ip_network('203.0.113.0/24'), ipaddress.ip_network('224.0.0.0/4'),
    ipaddress.ip_network('240.0.0.0/4'), ipaddress.ip_network('255.255.255.255/32'),
    ipaddress.ip_network('::1/128'), ipaddress.ip_network('::/128'),
    ipaddress.ip_network('::ffff:0:0/96'), ipaddress.ip_network('64:ff9b::/96'),
    ipaddress.ip_network('64:ff9b:1::/48'), ipaddress.ip_network('100::/64'),
    ipaddress.ip_network('2001::/23'), ipaddress.ip_network('2001:db8::/32'),
    ipaddress.ip_network('2002::/16'), ipaddress.ip_network('3fff::/20'),
    ipaddress.ip_network('fc00::/7'), ipaddress.ip_network('fe80::/10'),
    ipaddress.ip_network('ff00::/8'),
]
ALLOWED_LAB = [
    ipaddress.ip_network('127.0.0.0/8'), ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'), ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('::1/128'), ipaddress.ip_network('fc00::/7'),
]
CLOUD_METADATA_IPS = {'169.254.169.254', '100.100.100.200', '192.0.0.192'}

def is_safe(ip, allow_priv, is_prod):
    if is_prod: allow_priv = False
    if str(ip) in CLOUD_METADATA_IPS or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip in ipaddress.ip_network('0.0.0.0/8'):
        return False
    if any(ip in net for net in BLOCKED):
        return allow_priv and not is_prod and any(ip in net for net in ALLOWED_LAB)
    return True

matrix = [
    ('0.0.0.0', False), ('0.1.2.3', False), ('::', False),
    ('127.0.0.1', True), ('::1', True), ('10.0.0.1', True),
    ('172.16.0.1', True), ('192.168.1.1', True), ('fc00::1', True),
    ('169.254.1.1', False), ('169.254.169.254', False), ('100.64.0.1', False),
    ('192.0.2.1', False), ('198.51.100.1', False), ('203.0.113.1', False),
    ('198.18.0.1', False), ('224.0.0.1', False), ('ff02::1', False),
    ('240.0.0.1', False), ('255.255.255.255', False), ('fe80::1', False),
]

for s, exp_dev in matrix:
    ip = ipaddress.ip_address(s)
    assert is_safe(ip, True, False) == exp_dev, f'Dev failed for {s}'
    assert is_safe(ip, True, True) is False, f'Prod failed for {s}'
print('ALL 21 TEST CASES VERIFIED IN BOTH DEV AND PROD WITH 100% ACCURACY!')
"
```
*Expected output*: `ALL 21 TEST CASES VERIFIED IN BOTH DEV AND PROD WITH 100% ACCURACY!`

### 5.3. Existing Milestone 1 Test Suite Regression Test
Run the full backend suite to confirm baseline compatibility:
```powershell
python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_enhancement_suite.py tests/test_m1_adversarial_challenge.py -v
```
*Expected output*: 80 passed.

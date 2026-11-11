import ipaddress
import socket
from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse

import httpx

from backend.app.core.config import settings


class SSRFValidationError(ValueError):
    """Raised when a target fails SSRF validation."""
    pass


SSRFPolicyViolation = SSRFValidationError


class SSRFProtector:
    """Production-grade two-tier SSRF validator and network egress gatekeeper.
    Blocks private subnets, cloud metadata services, and unroutable addresses.
    """

    BLOCKED_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
        # IPv4
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("100.64.0.0/10"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.0.0.0/24"),
        ipaddress.ip_network("192.0.2.0/24"),
        ipaddress.ip_network("192.88.99.0/24"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("198.18.0.0/15"),
        ipaddress.ip_network("198.51.100.0/24"),
        ipaddress.ip_network("203.0.113.0/24"),
        ipaddress.ip_network("224.0.0.0/4"),
        ipaddress.ip_network("240.0.0.0/4"),
        ipaddress.ip_network("255.255.255.255/32"),
        # IPv6
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("::/128"),
        ipaddress.ip_network("::ffff:0:0/96"),
        ipaddress.ip_network("64:ff9b::/96"),
        ipaddress.ip_network("64:ff9b:1::/48"),
        ipaddress.ip_network("100::/64"),
        ipaddress.ip_network("2001::/23"),
        ipaddress.ip_network("2001:db8::/32"),
        ipaddress.ip_network("2002::/16"),
        ipaddress.ip_network("3fff::/20"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
        ipaddress.ip_network("ff00::/8"),
    ]

    ALLOWED_LAB_NETWORKS: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
        ipaddress.ip_network("127.0.0.0/8"),      # IPv4 Loopback
        ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Class A
        ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Class B
        ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Class C
        ipaddress.ip_network("::1/128"),          # IPv6 Loopback
        ipaddress.ip_network("fc00::/7"),         # RFC 4193 Unique Local IPv6 (ULA)
    ]

    CLOUD_METADATA_HOSTS: Set[str] = {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.internal",
        "100.100.100.200",
        "192.0.0.192",
        "instance-data",
    }

    CLOUD_METADATA_IPS: Set[str] = {
        "169.254.169.254",
        "100.100.100.200",
        "192.0.0.192",
    }

    @classmethod
    def _parse_and_validate_syntax(cls, target_url: str) -> Tuple[str, str, int]:
        """Validates basic URL syntax and returns (scheme, hostname, port)."""
        if not target_url or not isinstance(target_url, str):
            raise SSRFValidationError("Target URL must be a non-empty string.")

        clean_url = target_url.strip()
        if not clean_url:
            raise SSRFValidationError("Target URL must be a non-empty string.")

        try:
            parsed = urlparse(clean_url)
            port = parsed.port
            hostname = parsed.hostname
        except ValueError as e:
            raise SSRFValidationError(f"Malformed URL: {e}")

        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            raise SSRFValidationError(
                f"Invalid URL scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted."
            )

        if parsed.username or parsed.password:
            raise SSRFValidationError("Embedded credentials in authority are forbidden.")

        if not hostname:
            raise SSRFValidationError("Target URL must contain a valid hostname.")

        port = port if port is not None else (443 if scheme == "https" else 80)
        if port < 1 or port > 65535:
            raise SSRFValidationError(f"Invalid port: {port}")

        return scheme, hostname.lower(), port

    @classmethod
    def _is_ip_blocked(cls, ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        """Checks if an IP falls within any blocked network range."""
        return any(ip_obj in net for net in cls.BLOCKED_NETWORKS)

    @classmethod
    def validate_target(cls, target_url: str, allow_private: bool = False) -> Tuple[str, str]:
        """Validates target URL against SSRF and egress policies.
        
        Args:
            target_url: URL to validate
            allow_private: If True, bypasses loopback/RFC 1918 blocks for authorized lab targets.
                          Cloud metadata services are ALWAYS blocked regardless of this setting.

        Returns:
            Tuple of (normalized_target_url, first_resolved_ip)

        Raises:
            SSRFValidationError: if validation fails
        """
        scheme, hostname, port = cls._parse_and_validate_syntax(target_url)

        # Check explicit cloud metadata hostnames
        if hostname in cls.CLOUD_METADATA_HOSTS:
            raise SSRFValidationError(
                f"Target host '{hostname}' is a protected cloud metadata service (SSRF violation)."
            )

        # Attempt to parse hostname as raw IP address (handles decimal/hex/etc if converted)
        raw_ip_target: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
        try:
            raw_ip_target = ipaddress.ip_address(hostname)
        except ValueError:
            # Check for integer decimal / octal IP notation like 2130706433 or 017700000001
            if hostname.isdigit():
                try:
                    if hostname.startswith("0") and len(hostname) > 1:
                        try:
                            val = int(hostname, 8)
                        except ValueError:
                            raise SSRFValidationError(
                                f"Ambiguous integer IP notation with leading zeros: '{hostname}'"
                            )
                    else:
                        val = int(hostname, 10)

                    wrapped_val = val & 0xFFFFFFFF
                    wrapped_ip = ipaddress.IPv4Address(wrapped_val)

                    if val > 4294967295:
                        if cls._is_ip_blocked(wrapped_ip) and not (allow_private and (wrapped_ip.is_private or wrapped_ip.is_loopback)):
                            raise SSRFValidationError(
                                f"Target '{hostname}' overflows 32-bit boundary and wraps to blocked network address '{wrapped_ip}' (SSRF security violation)."
                            )
                        elif not cls._is_ip_blocked(wrapped_ip):
                            raise SSRFValidationError(
                                f"Integer IP value {val} exceeds 32-bit IPv4 boundary (4294967295)."
                            )

                    raw_ip_target = wrapped_ip
                except SSRFValidationError:
                    raise
                except Exception:
                    pass

        # In production, allow_private is strictly forbidden under all circumstances
        if settings.is_production:
            allow_private = False

        resolved_ips: List[str] = []
        if raw_ip_target:
            resolved_ips = [str(raw_ip_target)]
        else:
            try:
                addr_info = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for entry in addr_info:
                    ip_str = entry[4][0]
                    if ip_str not in resolved_ips:
                        resolved_ips.append(ip_str)
            except socket.gaierror as e:
                if allow_private and not settings.is_production:
                    # In authorized lab / staging environments only
                    resolved_ips = ["127.0.0.1"]
                else:
                    raise SSRFValidationError(f"DNS resolution failed for host '{hostname}': {e}")

        if not resolved_ips:
            raise SSRFValidationError(f"No IP addresses resolved for '{hostname}'.")

        for ip_str in resolved_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError:
                raise SSRFValidationError(f"Invalid resolved IP format: {ip_str}")

            # Unmap IPv4-in-IPv6 (e.g. ::ffff:127.0.0.1)
            if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
                ip_obj = ip_obj.ipv4_mapped

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
                    f"Target '{hostname}' resolves to protected cloud metadata / link-local / blocked address '{ip_obj}' (SSRF security violation)."
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

        host_repr = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
        normalized_url = f"{scheme}://{host_repr}" + (f":{port}" if (scheme == "http" and port != 80) or (scheme == "https" and port != 443) else "")
        parsed = urlparse(target_url.strip())
        if parsed.path:
            normalized_url += parsed.path
        if parsed.query:
            normalized_url += f"?{parsed.query}"

        return normalized_url, resolved_ips[0]

    @classmethod
    def create_safe_client(
        cls,
        target_url: str,
        allow_private: bool = False,
        timeout: float = 10.0,
        verify_tls: bool = True,
        **client_kwargs,
    ) -> httpx.AsyncClient:
        """Creates an SSRF-validated httpx.AsyncClient with strict TLS and host headers (F11)."""
        normalized_url, resolved_ip = cls.validate_target(target_url, allow_private=allow_private)
        parsed = urlparse(normalized_url)
        headers = dict(client_kwargs.pop("headers", {}) or {})
        if "Host" not in headers:
            headers["Host"] = parsed.hostname

        return httpx.AsyncClient(
            verify=verify_tls,
            timeout=timeout,
            headers=headers,
            **client_kwargs,
        )


validate_egress_target = SSRFProtector.validate_target

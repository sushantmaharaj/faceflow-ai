"""
FaceFlow AI — URL Utilities
Canonicalization and SSRF protection.
"""

import ipaddress
import socket
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse, urljoin
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# Tracking/noise query parameters to strip
_STRIP_PARAMS = frozenset([
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "_ga", "mc_cid", "mc_eid",
])

# Private / loopback / link-local CIDR ranges to block (SSRF protection)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),        # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC1918
    ipaddress.ip_network("169.254.0.0/16"),    # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

_BLOCKED_HOSTNAMES = frozenset([
    "localhost", "metadata.google.internal", "169.254.169.254"
])


def canonicalize_url(url: str) -> str:
    """Strip tracking params and normalize URL."""
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=False)
        cleaned = {k: v for k, v in params.items() if k not in _STRIP_PARAMS}
        new_query = urlencode(cleaned, doseq=True)
        canonical = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            new_query,
            "",  # strip fragment
        ))
        return canonical
    except Exception:
        return url


def extract_domain(url: str) -> str:
    """Return just the domain (netloc) of a URL."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        # Strip www.
        if host.startswith("www."):
            host = host[4:]
        # Strip port
        if ":" in host:
            host = host.split(":")[0]
        return host
    except Exception:
        return ""


def is_ssrf_safe(url: str) -> bool:
    """
    Return True only if the URL does NOT resolve to a private/internal address.
    Protects against SSRF when fetching external candidate images.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""

        if not host:
            return False

        if host.lower() in _BLOCKED_HOSTNAMES:
            logger.warning("SSRF block: hostname %s", host)
            return False

        # Resolve hostname to IPs
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            # Can't resolve — allow attempt; downstream may fail safely
            return True

        for info in infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
                for blocked in _BLOCKED_NETWORKS:
                    if ip in blocked:
                        logger.warning(
                            "SSRF block: %s resolved to private IP %s", host, ip_str
                        )
                        return False
            except ValueError:
                pass

        return True
    except Exception as e:
        logger.error("SSRF check error for %s: %s", url, e)
        return False

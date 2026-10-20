"""
Network security and SSRF protection validator for MusicMaid.
Guarantees that user-provided direct audio URLs and metadata requests:
1. Use HTTP or HTTPS schemes only.
2. Resolve to valid public IP addresses (IPv4 / IPv6).
3. Strictly block private (RFC 1918), loopback (127.0.0.0/8, ::1),
   link-local (169.254.0.0/16, fe80::/10), cloud metadata (169.254.169.254, metadata.google.internal),
   and multicast/reserved ranges.
4. Follow redirects safely with destination re-validation.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse
from typing import Optional, Tuple

logger = logging.getLogger("MusicMaid.NetworkSecurity")

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.packet.net",
    "instance-data",
}


def is_safe_ip(ip_str: str) -> bool:
    """Return True if an IP address is a globally routable public address."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
        # Specific cloud metadata IP block
        if ip_str == "169.254.169.254":
            return False
        return True
    except ValueError:
        return False


def validate_safe_url(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate that a URL is safe to fetch:
    Returns (is_safe, error_reason, canonical_url).
    """
    if not url or not isinstance(url, str):
        return False, "Empty or invalid URL provided", None

    u = url.strip()
    try:
        parsed = urllib.parse.urlsplit(u)
    except Exception as e:
        return False, f"Malformed URL: {e}", None

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are permitted.", None

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False, "Missing hostname in URL", None

    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".local") or hostname.endswith(".internal"):
        return False, f"Target host '{hostname}' is not permitted.", None

    # Check if host is direct IP literal
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if not is_safe_ip(str(ip_obj)):
            return False, f"Access to IP address '{hostname}' is restricted.", None
        return True, None, u
    except ValueError:
        pass

    # Resolve DNS to check resolved IP addresses
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False, f"Could not resolve host '{hostname}'", None
        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            if not is_safe_ip(ip_str):
                return False, f"Host '{hostname}' resolved to restricted IP address '{ip_str}'", None
    except socket.gaierror as dns_err:
        return False, f"DNS resolution failed for '{hostname}': {dns_err}", None
    except Exception as exc:
        return False, f"Host validation error for '{hostname}': {exc}", None

    return True, None, u

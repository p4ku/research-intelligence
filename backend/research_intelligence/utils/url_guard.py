import ipaddress
import socket
import urllib.parse
import logging

logger = logging.getLogger(__name__)

DISALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private LAN Class A
    ipaddress.ip_network("172.16.0.0/12"),    # Private LAN Class B
    ipaddress.ip_network("192.168.0.0/16"),   # Private LAN Class C
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("0.0.0.0/8"),        # Unspecified
    ipaddress.ip_network("::1/128"),          # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
]


def is_safe_external_url(url: str) -> bool:
    """
    Validates that a given URL is a safe, public HTTP/HTTPS endpoint.
    Blocks private IP addresses, loopback, cloud metadata (169.254.169.254), and non-HTTP schemes.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        if hostname.lower() in ("localhost", "metadata", "instance-data", "metadata.google.internal"):
            return False

        # If hostname is a raw IP literal
        try:
            ip_obj = ipaddress.ip_address(hostname)
            for net in DISALLOWED_NETWORKS:
                if ip_obj in net:
                    return False
            return True
        except ValueError:
            pass

        # Resolve IP addresses for DNS hostname
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip_str = entry[4][0]
            ip_obj = ipaddress.ip_address(ip_str)
            for net in DISALLOWED_NETWORKS:
                if ip_obj in net:
                    return False
        return True
    except Exception as e:
        logger.warning(f"URL security validation failed for '{url}': {e}")
        return False

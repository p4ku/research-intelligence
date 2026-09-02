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


import urllib.request

class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    HTTP redirect handler that enforces security checks on every redirection hop,
    preventing redirects to internal, private, loopback, or cloud metadata endpoints.
    """
    def __init__(self, max_redirects: int = 5):
        self.max_redirects = max_redirects
        self._redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._redirects += 1
        if self._redirects > self.max_redirects:
            raise ValueError(f"Exceeded maximum redirect limit ({self.max_redirects} hops)")
        if not is_safe_external_url(newurl):
            raise ValueError(f"Blocked redirect to disallowed internal or private IP endpoint: '{newurl}'")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_download_url(
    url: str,
    headers: dict = None,
    max_bytes: int = 100 * 1024 * 1024,
    timeout: float = 15.0
) -> bytes:
    """
    Safely downloads content from an external public HTTP/HTTPS URL:
    - Enforces is_safe_external_url on initial target and every redirect hop.
    - Limits redirect hops to 5.
    - Limits total downloaded bytes to max_bytes (default 100 MB).
    - Enforces socket read timeout.
    """
    if not is_safe_external_url(url):
        raise ValueError(f"Disallowed private/internal IP URL: '{url}'")

    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    if headers:
        default_headers.update(headers)

    req = urllib.request.Request(url, headers=default_headers)
    opener = urllib.request.build_opener(SafeRedirectHandler(max_redirects=5))

    with opener.open(req, timeout=timeout) as response:
        # Check Content-Length if available
        cl = response.headers.get('Content-Length')
        if cl and cl.isdigit() and int(cl) > max_bytes:
            raise ValueError(f"Content-Length ({int(cl)} bytes) exceeds maximum permitted download limit ({max_bytes} bytes).")

        chunks = []
        downloaded = 0
        chunk_size = 64 * 1024
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            downloaded += len(chunk)
            if downloaded > max_bytes:
                raise ValueError(f"Downloaded payload exceeded maximum size limit of {max_bytes} bytes.")
            chunks.append(chunk)

        return b"".join(chunks)


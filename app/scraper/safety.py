import ipaddress
import socket
from urllib.parse import urlparse, urljoin

BLOCKED_HOSTNAMES = {"localhost", "loopback", "metadata.google.internal"}

class SSRFError(ValueError):
    """Exception raised when a URL fails SSRF safety checks."""
    pass

def is_safe_ip(ip_str: str) -> bool:
    """Validate if an IP string is a safe public IP address."""
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check standard unsafe attributes
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
        
        # Additional explicit range checks (e.g. Carrier Grade NAT 100.64.0.0/10, Cloud metadata)
        if isinstance(ip, ipaddress.IPv4Address):
            # Carrier Grade NAT: 100.64.0.0/10
            cgnat = ipaddress.IPv4Network("100.64.0.0/10")
            if ip in cgnat:
                return False
            # Explicit cloud metadata check
            if str(ip) == "169.254.169.254":
                return False
                
        return True
    except ValueError:
        return False

def validate_url(url: str, allow_private: bool = False) -> str:
    """
    Validate a URL for safety against SSRF and unauthorized protocols.
    Returns normalized URL if safe, otherwise raises SSRFError.
    """
    if not url:
        raise SSRFError("URL cannot be empty.")

    parsed = urlparse(url)
    
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFError(f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("Invalid URL: missing hostname.")

    hostname_lower = hostname.lower()
    
    if not allow_private:
        if hostname_lower in BLOCKED_HOSTNAMES or hostname_lower.endswith(".local"):
            raise SSRFError(f"Access to hostname '{hostname}' is blocked.")

        # If hostname is directly an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if not is_safe_ip(str(ip)):
                raise SSRFError(f"Access to private/reserved IP '{ip}' is blocked.")
        except ValueError:
            # Hostname is a domain name, resolve DNS
            try:
                addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
                if not addr_info:
                    raise SSRFError(f"Could not resolve domain '{hostname}'.")
                
                for family, socktype, proto, canonname, sockaddr in addr_info:
                    ip_str = sockaddr[0]
                    if not is_safe_ip(ip_str):
                        raise SSRFError(f"Domain '{hostname}' resolved to unsafe IP address '{ip_str}'.")
            except socket.gaierror as e:
                raise SSRFError(f"DNS resolution failed for hostname '{hostname}': {e}")

    return url

def is_same_origin(url1: str, url2: str) -> bool:
    """Check if two URLs share the same origin (scheme + domain + port)."""
    p1, p2 = urlparse(url1), urlparse(url2)
    return (p1.scheme.lower(), p1.hostname.lower() if p1.hostname else "", p1.port) == \
           (p2.scheme.lower(), p2.hostname.lower() if p2.hostname else "", p2.port)

def normalize_url(url: str, base_url: str = "") -> str:
    """Resolve relative URL, normalize scheme/host, empty path to '/', and remove fragments."""
    if not url:
        return ""
    if base_url:
        url = urljoin(base_url, url)
    
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove default port if present
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parsed.path
    if not path:
        path = "/"

    normalized = parsed._replace(
        scheme=scheme,
        netloc=netloc,
        path=path,
        fragment=""
    ).geturl()
    return normalized


import pytest
from app.scraper.safety import validate_url, is_safe_ip, is_same_origin, SSRFError

def test_validate_url_valid():
    url = "https://example.com/products"
    assert validate_url(url, allow_private=False) == url

def test_validate_url_invalid_scheme():
    with pytest.raises(SSRFError, match="Unsupported URL scheme"):
        validate_url("ftp://example.com/file.txt")

def test_validate_url_localhost():
    with pytest.raises(SSRFError):
        validate_url("http://localhost:8000/admin")

def test_validate_url_loopback_ip():
    with pytest.raises(SSRFError):
        validate_url("http://127.0.0.1/secret")

def test_validate_url_private_ip():
    with pytest.raises(SSRFError):
        validate_url("http://192.168.1.1/router")
    with pytest.raises(SSRFError):
        validate_url("http://10.0.0.1/internal")

def test_validate_url_cloud_metadata():
    with pytest.raises(SSRFError):
        validate_url("http://169.254.169.254/latest/meta-data/")

def test_is_safe_ip():
    assert is_safe_ip("8.8.8.8") is True
    assert is_safe_ip("127.0.0.1") is False
    assert is_safe_ip("192.168.1.10") is False
    assert is_safe_ip("169.254.169.254") is False
    assert is_safe_ip("100.64.0.1") is False  # CGNAT

def test_is_same_origin():
    assert is_same_origin("https://example.com/cat1", "https://example.com/cat2/prod") is True
    assert is_same_origin("https://example.com", "https://other.com") is False
    assert is_same_origin("http://example.com", "https://example.com") is False

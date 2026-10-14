import logging
from scrapy.exceptions import IgnoreRequest
from app.scraper.safety import validate_url, SSRFError, is_same_origin

logger = logging.getLogger(__name__)

class SSRFDownloaderMiddleware:
    """Scrapy Downloader Middleware to enforce strict SSRF validation on all requests & redirects."""

    def __init__(self, allow_private_ips=False):
        self.allow_private_ips = allow_private_ips

    @classmethod
    def from_crawler(cls, crawler):
        allow_private = crawler.settings.getbool('ALLOW_PRIVATE_IPS', False)
        return cls(allow_private_ips=allow_private)

    def process_request(self, request, spider=None):
        try:
            validate_url(request.url, allow_private=self.allow_private_ips)
        except SSRFError as e:
            logger.warning(f"[SSRF Blocked] Request to unsafe URL '{request.url}': {e}")
            raise IgnoreRequest(f"SSRF Protection Error: {e}")
        return None

    def process_response(self, request, response, spider=None):
        # Validate redirect target headers if present
        if response.status in (301, 302, 303, 307, 308):
            location = response.headers.get('Location')
            if location:
                target_url = response.urljoin(location.decode('utf-8'))
                try:
                    validate_url(target_url, allow_private=self.allow_private_ips)
                except SSRFError as e:
                    logger.warning(f"[SSRF Blocked] Redirect to unsafe URL '{target_url}': {e}")
                    raise IgnoreRequest(f"SSRF Redirect Protection Error: {e}")
        return response


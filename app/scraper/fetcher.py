import httpx
import logging
from typing import Optional, Tuple
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

from app.config import settings
from app.scraper.safety import validate_url, SSRFError

logger = logging.getLogger(__name__)

class HTTPFetcher:
    def __init__(self, user_agent: Optional[str] = None, allow_private_ips: bool = False):
        self.user_agent = user_agent or settings.USER_AGENT
        self.allow_private_ips = allow_private_ips
        self.robots_cache = {}

    async def can_fetch_robots(self, url: str) -> bool:
        """Check robots.txt compliance for the given URL."""
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        if robots_url not in self.robots_cache:
            rfp = RobotFileParser()
            rfp.set_url(robots_url)
            try:
                async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                    resp = await client.get(robots_url, headers={"User-Agent": self.user_agent})
                    if resp.status_code == 200:
                        rfp.parse(resp.text.splitlines())
                    else:
                        rfp.allow_all = True
            except Exception as e:
                logger.warning(f"Could not fetch robots.txt from {robots_url}: {e}")
                rfp.allow_all = True
            self.robots_cache[robots_url] = rfp
            
        rfp = self.robots_cache[robots_url]
        return rfp.can_fetch(self.user_agent, url)

    async def fetch(self, url: str) -> Tuple[Optional[str], int, str, Optional[str]]:
        """
        Fetch HTML content from a URL safely.
        Returns: (html_content, status_code, final_url, error_message)
        """
        try:
            validated_url = validate_url(url, allow_private=self.allow_private_ips)
        except SSRFError as e:
            return None, 400, url, f"SSRF Protection Error: {str(e)}"

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        current_url = validated_url
        max_redirects = 5
        redirect_count = 0

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.REQUEST_TIMEOUT_SECONDS),
                verify=True,
                follow_redirects=False
            ) as client:
                while redirect_count < max_redirects:
                    response = await client.get(current_url, headers=headers)
                    
                    # Handle redirects manually to enforce SSRF validation at every step
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            break
                        # Resolve relative redirect locations
                        next_url = str(response.url.join(location))
                        try:
                            current_url = validate_url(next_url, allow_private=self.allow_private_ips)
                        except SSRFError as se:
                            return None, 400, current_url, f"Redirect SSRF Error: {str(se)}"
                        redirect_count += 1
                        continue
                    
                    # Size check
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > settings.MAX_RESPONSE_BYTES:
                        return None, 413, current_url, "Response size exceeds maximum allowed limit."

                    if response.status_code != 200:
                        return None, response.status_code, current_url, f"HTTP Status {response.status_code}"

                    html = response.text
                    return html, response.status_code, str(response.url), None

                return None, 310, current_url, "Too many redirects."

        except httpx.TimeoutException:
            return None, 408, current_url, f"Request timed out after {settings.REQUEST_TIMEOUT_SECONDS}s"
        except httpx.HTTPSecurityError as e:
            return None, 403, current_url, f"SSL/Security Error: {e}"
        except httpx.RequestError as e:
            return None, 500, current_url, f"Network/HTTP Request Error: {e}"
        except Exception as e:
            return None, 500, current_url, f"Unexpected fetch error: {e}"

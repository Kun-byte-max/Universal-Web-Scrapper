import logging
from typing import Optional, Tuple
from app.config import settings
from app.scraper.safety import validate_url, SSRFError

logger = logging.getLogger(__name__)

class PlaywrightFetcher:
    """Fallback fetcher using headless Playwright Chromium browser."""

    async def fetch(self, url: str) -> Tuple[Optional[str], int, str, Optional[str]]:
        try:
            validated_url = validate_url(url, allow_private=settings.ALLOW_PRIVATE_IPS)
        except SSRFError as e:
            return None, 400, url, f"SSRF Error in Browser Fallback: {e}"

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None, 500, url, "Playwright is not installed. Install via 'pip install playwright && playwright install chromium'."

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                context = await browser.new_context(
                    user_agent=settings.USER_AGENT,
                    viewport={"width": 1280, "height": 800}
                )
                page = await context.new_page()

                # Set navigation timeout
                page.set_default_navigation_timeout(settings.PLAYWRIGHT_TIMEOUT_MS)

                response = await page.goto(validated_url, wait_until="domcontentloaded")
                
                # Small wait for dynamically rendered DOM elements
                await page.wait_for_timeout(2000)

                final_url = page.url
                status_code = response.status if response else 200
                html_content = await page.content()

                await context.close()
                await browser.close()

                return html_content, status_code, final_url, None

        except Exception as e:
            logger.error(f"Playwright rendering failed for {url}: {e}")
            return None, 500, url, f"Playwright Browser Fallback Error: {str(e)}"

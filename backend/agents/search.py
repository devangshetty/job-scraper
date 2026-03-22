import asyncio
import base64
import logging
import random
from urllib.parse import quote, urlparse, parse_qs
from typing import List, Dict

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


def _unwrap_bing_url(url: str) -> str:
    """
    Bing wraps result URLs in /ck/a?...&u=a1<base64>... redirects.
    Strip the wrapper and return the real destination URL.
    """
    if "/ck/a?" not in url:
        return url
    try:
        u_param = parse_qs(urlparse(url).query).get("u", [""])[0]
        if not u_param.startswith("a1"):
            return url
        encoded = u_param[2:]
        # base64 padding
        encoded += "=" * (4 - len(encoded) % 4)
        return base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return url


async def web_search(query: str, max_results: int = 5) -> List[Dict]:
    """
    Search Bing using Playwright and return clean results.
    Returns list of {title, url, snippet}.

    Key details:
    - Primes session with Bing homepage so cookies are set before searching.
    - Uses domcontentloaded (not networkidle) for the search page — networkidle
      causes timeouts on certain query types.
    - Unwraps Bing's /ck/a redirect URLs to get the real destination.
    """
    results: List[Dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            # Prime session — Bing needs cookies before search requests work
            await page.goto("https://www.bing.com", wait_until="networkidle", timeout=20000)
            await asyncio.sleep(1)

            logger.info(f"Searching Bing: {query}")
            await page.goto(
                f"https://www.bing.com/search?q={quote(query)}",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await page.wait_for_selector("li.b_algo", timeout=10000)

        except PWTimeout:
            logger.warning(f"Bing search timed out for: {query}")
            await browser.close()
            return []

        blocks = await page.query_selector_all("li.b_algo")
        for block in blocks:
            try:
                title_el   = await block.query_selector("h2 a")
                snippet_el = await block.query_selector(".b_caption p, .b_snippet")

                if not title_el:
                    continue

                title   = (await title_el.inner_text()).strip()
                raw_url = await title_el.get_attribute("href") or ""
                url     = _unwrap_bing_url(raw_url)
                snippet = (await snippet_el.inner_text()).strip() if snippet_el else ""

                if not url or not title:
                    continue

                results.append({"title": title, "url": url, "snippet": snippet})

                if len(results) >= max_results:
                    break

            except Exception as e:
                logger.warning(f"Result parse error: {e}")
                continue

        await browser.close()

    logger.info(f"Bing '{query}' → {len(results)} results")
    return results

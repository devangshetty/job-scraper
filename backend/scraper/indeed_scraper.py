import asyncio
import random
import logging
import re
import json
from typing import List, Dict, Optional
from urllib.parse import urlencode
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

logger = logging.getLogger(__name__)

BASE_URL = "https://au.indeed.com"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

BLOCK_SIGNALS = [
    "additional verification required",
    "ray id",
    "cloudflare",
    "access denied",
    "verify you are human",
    "captcha",
    "unusual traffic",
    "please enable cookies",
    "robot or human",
    "are you a robot",
]


def _is_blocked(text: str) -> bool:
    return any(s in text.lower() for s in BLOCK_SIGNALS)


def _build_search_url(keyword: str, location: str, offset: int = 0) -> str:
    params = {"q": keyword, "l": location, "sort": "date"}
    if offset:
        params["start"] = offset
    return f"{BASE_URL}/jobs?" + urlencode(params)


def _parse_mosaic(html: str) -> Optional[List[Dict]]:
    """Extract job cards from the mosaic JSON blob baked into the search page HTML."""
    matches = re.findall(
        r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]=(\{.+?\});',
        html
    )
    if not matches:
        logger.warning("Indeed: mosaic-provider-jobcards not found in page HTML")
        return None
    try:
        data = json.loads(matches[0])
        return data["metaData"]["mosaicProviderJobCardsModel"]["results"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Indeed: failed to parse mosaic JSON: {e}")
        return None


async def _scrape_keyword_page(
    context,
    url: str,
    seen_jks: set,
) -> Optional[List[Dict]]:
    page = await context.new_page()
    if STEALTH_AVAILABLE:
        await stealth_async(page)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await asyncio.sleep(random.uniform(2.0, 4.0))
        html = await page.content()
    except PWTimeout:
        logger.warning(f"Indeed: timeout loading {url}")
        await page.close()
        return []
    finally:
        await page.close()

    body_text = re.sub(r"<[^>]+>", " ", html).lower()
    if _is_blocked(body_text):
        logger.warning(f"Indeed: blocked at {url}")
        return None

    cards = _parse_mosaic(html)
    if cards is None:
        return None

    logger.info(f"Indeed: {len(cards)} cards on {url}")

    jobs = []
    for card in cards:
        jk      = card.get("jobkey") or card.get("jk", "")
        title   = card.get("displayTitle") or card.get("title", "")
        company = card.get("company", "Unknown")
        loc     = card.get("formattedLocation", "")
        snippet = card.get("snippet", "")  # short description snippet Indeed includes
        salary  = ""

        sal = card.get("salarySnippet")
        if isinstance(sal, dict):
            salary = sal.get("text", "")
        if not salary:
            ext = card.get("extractedSalary")
            if isinstance(ext, dict):
                salary = ext.get("formattedText", "")

        if not jk or not title:
            continue

        if jk in seen_jks:
            logger.info(f"Indeed: skipping duplicate jk={jk} '{title}' @ {company}")
            continue
        seen_jks.add(jk)

        # Strip HTML tags from snippet for use as a lightweight description
        clean_snippet = re.sub(r"<[^>]+>", " ", snippet).strip() if snippet else ""

        jobs.append({
            "job_title":       title,
            "company":         company,
            "location":        loc,
            "salary":          salary,
            "application_url": f"{BASE_URL}/viewjob?jk={jk}",
            "description":     clean_snippet,
            "posted_date":     card.get("formattedRelativeTime", ""),
            "source":          "indeed",
        })
        logger.info(f"Indeed: '{title}' @ {company} snippet_len={len(clean_snippet)}")

    return jobs


async def scrape_indeed(
    keywords:  List[str],
    location:  str = "Adelaide SA",
    max_pages: int = 3,
) -> List[Dict]:
    all_jobs: List[Dict] = []
    seen_jks: set        = set()

    if not STEALTH_AVAILABLE:
        logger.warning("playwright-stealth not installed - run: pip install playwright-stealth")

    async with async_playwright() as pw:
        for keyword in keywords:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1366, "height": 768},
                locale="en-AU",
                timezone_id="Australia/Adelaide",
                extra_http_headers={
                    "Accept-Language": "en-AU,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            for page_num in range(max_pages):
                offset = page_num * 10
                url = _build_search_url(keyword, location, offset)
                logger.info(f"Indeed: scraping '{keyword}' page {page_num + 1}: {url}")

                page_jobs = await _scrape_keyword_page(context, url, seen_jks)

                if page_jobs is None:
                    logger.warning(f"Indeed: '{keyword}' blocked - stopping keyword")
                    break

                all_jobs.extend(page_jobs)
                logger.info(f"Indeed: '{keyword}' page {page_num + 1}: {len(page_jobs)} jobs, total={len(all_jobs)}")

                if len(page_jobs) == 0:
                    break

                await asyncio.sleep(random.uniform(4.0, 7.0))

            await browser.close()
            await asyncio.sleep(random.uniform(4.0, 7.0))

    logger.info(f"Indeed: done, {len(all_jobs)} total jobs")
    return all_jobs

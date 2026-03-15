import asyncio
import random
import logging
import re
from typing import List, Dict
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

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
    low = text.lower()
    return any(signal in low for signal in BLOCK_SIGNALS)


def _build_search_url(keyword: str, location: str, offset: int = 0) -> str:
    q   = keyword.replace(" ", "+")
    loc = location.replace(" ", "+")
    url = f"{BASE_URL}/jobs?q={q}&l={loc}&sort=date"
    if offset:
        url += f"&start={offset}"
    return url


def _clean_text(raw: str) -> str:
    cleaned = re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", raw))
    return cleaned.strip()


def _extract_salary(text: str) -> str:
    match = re.search(
        r"(\$[\d,]+(?:\s*[-\u2013]\s*\$[\d,]+)?(?:\s*(?:per\s+(?:annum|year|hour|day)|p\.a\.|pa|/hr|/year))?)",
        text, re.IGNORECASE
    )
    return match.group(1).strip()[:80] if match else ""


def _extract_location(text: str, fallback: str = "") -> str:
    match = re.search(r"([A-Z][a-zA-Z ]+,?\s*(?:SA|NSW|VIC|QLD|WA|TAS|ACT|NT))", text)
    return match.group(1).strip() if match else fallback


async def _get_inline_description(page) -> str:
    """
    Indeed loads the full job description in a right-side panel on the
    search results page when a card is clicked. We read it from there
    instead of navigating to the detail URL, avoiding Cloudflare entirely.
    """
    PANEL_SELECTORS = [
        "#jobDescriptionText",
        "[class*='jobsearch-jobDescriptionText']",
        "[id*='jobDescription']",
        ".jobsearch-JobComponent-description",
    ]
    for selector in PANEL_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=6000)
            el = await page.query_selector(selector)
            if el:
                raw = (await el.inner_text()).strip()
                if len(raw) > 100:
                    return _clean_text(raw)
        except PWTimeout:
            continue
    return ""


async def scrape_indeed(
    keywords:  List[str],
    location:  str = "Adelaide SA",
    max_pages: int = 3,
) -> List[Dict]:
    all_jobs:  List[Dict] = []
    seen_urls: set        = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
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
        page = await context.new_page()

        for keyword in keywords:
            for page_num in range(max_pages):
                offset = page_num * 10
                url = _build_search_url(keyword, location, offset)
                logger.info(f"Indeed: scraping {url}")

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    await asyncio.sleep(random.uniform(3.0, 5.0))
                except PWTimeout:
                    logger.warning(f"Indeed: timeout loading {url}")
                    continue

                page_text = await page.evaluate("() => document.body?.innerText || ''")
                if _is_blocked(page_text):
                    logger.warning(f"Indeed: blocked on page {page_num + 1} for '{keyword}' - stopping keyword")
                    break

                # Grab all job cards on the listing page
                try:
                    await page.wait_for_selector(
                        '.job_seen_beacon, [class*="jobCard"], td.resultContent',
                        timeout=15000
                    )
                except PWTimeout:
                    logger.info(f"Indeed: no cards on page {page_num + 1}, stopping keyword")
                    break

                cards = await page.query_selector_all(
                    '.job_seen_beacon, td.resultContent'
                )
                logger.info(f"Indeed: found {len(cards)} cards on page {page_num + 1}")

                if not cards:
                    break

                for card in cards:
                    try:
                        # Title + URL
                        title_el = await card.query_selector(
                            '[class*="jobTitle"] a, h2 a[data-jk], a[id^="job_"]'
                        )
                        if not title_el:
                            continue
                        title = (await title_el.inner_text()).strip()
                        if not title or title.lower() in {"job title", ""}:
                            continue

                        href = await title_el.get_attribute("href") or ""
                        if not href or href.lower().startswith("javascript"):
                            continue
                        job_url = href if href.startswith("http") else BASE_URL + href

                        # Deduplicate by URL
                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        # Company
                        company_el = await card.query_selector(
                            '[data-testid="company-name"], .companyName, [class*="companyName"]'
                        )
                        company = (await company_el.inner_text()).strip() if company_el else "Unknown"

                        # Location from card
                        loc_el = await card.query_selector(
                            '[data-testid="text-location"], .companyLocation, [class*="companyLocation"]'
                        )
                        location_text = (await loc_el.inner_text()).strip() if loc_el else ""

                        # Salary from card
                        sal_el = await card.query_selector(
                            '[class*="salary"], [data-testid*="salary"]'
                        )
                        salary = (await sal_el.inner_text()).strip() if sal_el else ""

                        # Click the card to load the inline description panel
                        await title_el.click()
                        await asyncio.sleep(random.uniform(1.5, 3.0))

                        description = await _get_inline_description(page)

                        # Extract salary from description if not on card
                        if not salary and description:
                            salary = _extract_salary(description)

                        # Improve location from description if card only had generic text
                        if description:
                            location_text = _extract_location(description, fallback=location_text)

                        # Posted date from the panel
                        posted_date = ""
                        date_el = await page.query_selector(
                            '[class*="date"], [data-testid*="date"], [class*="posted"]'
                        )
                        if date_el:
                            posted_date = (await date_el.inner_text()).strip()[:50]

                        all_jobs.append({
                            "job_title":       title,
                            "company":         company,
                            "location":        location_text,
                            "salary":          salary,
                            "application_url": job_url,
                            "description":     description,
                            "posted_date":     posted_date,
                            "source":          "indeed",
                        })
                        logger.info(f"Indeed: scraped '{title}' @ {company}, desc_len={len(description)}")
                        await asyncio.sleep(random.uniform(1.0, 2.5))

                    except Exception as e:
                        logger.warning(f"Indeed: card error: {e}")
                        continue

                logger.info(f"Indeed: page {page_num + 1} done, total so far: {len(all_jobs)}")
                await asyncio.sleep(random.uniform(3.0, 6.0))

        await browser.close()

    logger.info(f"Indeed: done, {len(all_jobs)} total jobs scraped")
    return all_jobs

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


def _extract_location(text: str) -> str:
    match = re.search(r"([A-Z][a-zA-Z ]+,?\s*(?:SA|NSW|VIC|QLD|WA|TAS|ACT|NT))", text)
    return match.group(1).strip() if match else ""


async def _extract_job_cards(page) -> List[Dict]:
    jobs = []

    try:
        await page.wait_for_selector(
            'a[data-jk], .job_seen_beacon, [class*="jobCard"], td.resultContent',
            timeout=15000
        )
    except PWTimeout:
        logger.warning("Indeed: no job cards found on page")
        return jobs

    cards = await page.query_selector_all(
        '.job_seen_beacon, [class*="jobCard"]:not([class*="jobCardShelf"]), td.resultContent'
    )
    logger.info(f"Indeed: found {len(cards)} raw cards")

    for card in cards:
        try:
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
            job_url = re.sub(r"&[a-z]+=(?!(?:jk|fccid))[^&]+", "", job_url)

            company_el = await card.query_selector(
                '[data-testid="company-name"], .companyName, [class*="companyName"]'
            )
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"

            loc_el = await card.query_selector(
                '[data-testid="text-location"], .companyLocation, [class*="companyLocation"]'
            )
            location = (await loc_el.inner_text()).strip() if loc_el else ""

            sal_el = await card.query_selector(
                '[class*="salary"], [data-testid*="salary"]'
            )
            salary = (await sal_el.inner_text()).strip() if sal_el else ""

            jobs.append({
                "job_title":       title,
                "company":         company,
                "location":        location,
                "salary":          salary,
                "application_url": job_url,
                "description":     "",
                "posted_date":     "",
                "source":          "indeed",
            })
        except Exception as e:
            logger.warning(f"Indeed card parse error: {e}")
            continue

    logger.info(f"Indeed: extracted {len(jobs)} valid cards")
    return jobs


async def _fetch_job_detail(page, job_url: str) -> Dict:
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(2.0, 4.0))

        page_text = await page.evaluate("() => document.body?.innerText || ''")
        if _is_blocked(page_text):
            logger.warning(f"Indeed: blocked page detected for {job_url} - skipping description")
            return {}

        DESC_SELECTORS = [
            "#jobDescriptionText",
            "[class*='jobsearch-jobDescriptionText']",
            "[class*='jobDescription']",
            "#job-content",
        ]

        description = ""
        for selector in DESC_SELECTORS:
            el = await page.query_selector(selector)
            if el:
                raw = (await el.inner_text()).strip()
                if len(raw) > 100:
                    description = _clean_text(raw)
                    logger.info(f"Indeed: description from '{selector}', len={len(description)}")
                    break

        if not description:
            description = await page.evaluate("""
                () => {
                    ['header','footer','nav','#indeed-cookie-consent-banner',
                     '#mosaic-provider-reportcontent','script','style'].forEach(s => {
                        document.querySelectorAll(s).forEach(el => el.remove());
                    });
                    return (document.body?.innerText || '').trim();
                }
            """)
            description = _clean_text(description)
            # If fallback also looks like a block page, discard
            if _is_blocked(description):
                logger.warning(f"Indeed: fallback body also blocked for {job_url}")
                return {}
            logger.info(f"Indeed: description from body fallback, len={len(description)}")

        posted_date = ""
        date_el = await page.query_selector(
            '[class*="posted"], [class*="date"], [data-testid*="date"]'
        )
        if date_el:
            posted_date = (await date_el.inner_text()).strip()[:50]

        salary   = _extract_salary(description)
        location = _extract_location(description)

        return {
            "description": description,
            "posted_date": posted_date,
            "salary":      salary,
            "location":    location,
        }

    except PWTimeout:
        logger.warning(f"Indeed: timeout on {job_url}")
        return {}
    except Exception as e:
        logger.warning(f"Indeed: detail fetch error {job_url}: {e}")
        return {}


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

                cards = await _extract_job_cards(page)
                if not cards:
                    logger.info(f"Indeed: no cards on page {page_num + 1}, stopping keyword")
                    break

                new_cards = [c for c in cards if c["application_url"] not in seen_urls]
                for c in new_cards:
                    seen_urls.add(c["application_url"])

                for job in new_cards:
                    detail = await _fetch_job_detail(page, job["application_url"])
                    if detail.get("description"):
                        job["description"] = detail["description"]
                    if detail.get("posted_date"):
                        job["posted_date"] = detail["posted_date"]
                    if detail.get("salary") and not job["salary"]:
                        job["salary"] = detail["salary"]
                    if detail.get("location") and not job["location"]:
                        job["location"] = detail["location"]
                    await asyncio.sleep(random.uniform(2.0, 4.0))

                all_jobs.extend(new_cards)
                logger.info(f"Indeed: page {page_num + 1}: {len(new_cards)} new jobs for '{keyword}'")
                await asyncio.sleep(random.uniform(3.0, 6.0))

        await browser.close()

    logger.info(f"Indeed: done, {len(all_jobs)} total jobs scraped")
    return all_jobs

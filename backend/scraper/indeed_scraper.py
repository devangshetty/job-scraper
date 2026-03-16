import asyncio
import random
import logging
import re
import json
from typing import List, Dict, Optional
from urllib.parse import urlencode
import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://au.indeed.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Connection": "keep-alive",
}


def _build_search_url(keyword: str, location: str, offset: int = 0) -> str:
    params = {"q": keyword, "l": location, "sort": "date", "filter": 0}
    if offset:
        params["start"] = offset
    return f"{BASE_URL}/jobs?" + urlencode(params)


def _clean_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_salary(text: str) -> str:
    m = re.search(
        r"(\$[\d,]+(?:\s*[-\u2013]\s*\$[\d,]+)?(?:\s*(?:per\s+(?:annum|year|hour|day)|p\.a\.|pa|/hr|/year))?)",
        text, re.IGNORECASE
    )
    return m.group(1).strip()[:80] if m else ""


def _parse_search_page(html: str) -> Optional[List[Dict]]:
    """Extract job card data from the mosaic JSON blob embedded in search page HTML."""
    matches = re.findall(
        r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]=(\{.+?\});',
        html
    )
    if not matches:
        logger.warning("Indeed: mosaic-provider-jobcards not found in page")
        return None
    try:
        data = json.loads(matches[0])
        return data["metaData"]["mosaicProviderJobCardsModel"]["results"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Indeed: failed to parse search JSON: {e}")
        return None


def _parse_job_page(html: str) -> str:
    """Extract full job description from the embedded mobile viewjob page."""
    matches = re.findall(r"_initialData=(\{.+?\});", html)
    if not matches:
        return ""
    try:
        data = json.loads(matches[0])
        content = data["jobInfoWrapperModel"]["jobInfoModel"]["sanitizedJobDescription"]["content"]
        return _clean_html(content)
    except (json.JSONDecodeError, KeyError):
        return ""


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        resp = await client.get(url, timeout=20)
        if resp.status_code == 200:
            return resp.text
        logger.warning(f"Indeed: HTTP {resp.status_code} for {url}")
        return None
    except Exception as e:
        logger.warning(f"Indeed: request error for {url}: {e}")
        return None


async def _scrape_keyword_page(
    client: httpx.AsyncClient,
    url: str,
    seen_jks: set,
) -> Optional[List[Dict]]:
    html = await _fetch(client, url)
    if html is None:
        return None

    cards = _parse_search_page(html)
    if cards is None:
        # Page loaded but no mosaic data - likely blocked or CAPTCHA
        return None

    logger.info(f"Indeed: {len(cards)} cards on {url}")

    jobs = []
    for card in cards:
        jk = card.get("jobkey") or card.get("jk", "")
        if not jk:
            continue

        title   = card.get("displayTitle") or card.get("title", "")
        company = card.get("company", "Unknown")
        loc     = card.get("formattedLocation", "")
        salary  = ""

        sal_snippet = card.get("salarySnippet") or {}
        if isinstance(sal_snippet, dict):
            salary = sal_snippet.get("text", "")
        if not salary:
            salary = card.get("extractedSalary", {}).get("formattedText", "") if isinstance(card.get("extractedSalary"), dict) else ""

        if jk in seen_jks:
            logger.info(f"Indeed: skipping duplicate jk={jk} '{title}' @ {company}")
            continue
        seen_jks.add(jk)

        # Fetch description from mobile embedded endpoint - much less protected
        detail_url = f"{BASE_URL}/m/basecamp/viewjob?viewtype=embedded&jk={jk}"
        await asyncio.sleep(random.uniform(1.5, 3.0))
        detail_html = await _fetch(client, detail_url)
        description = _parse_job_page(detail_html) if detail_html else ""

        if not salary and description:
            salary = _extract_salary(description)

        job_url = f"{BASE_URL}/viewjob?jk={jk}"
        jobs.append({
            "job_title":       title,
            "company":         company,
            "location":        loc,
            "salary":          salary,
            "application_url": job_url,
            "description":     description,
            "posted_date":     card.get("formattedRelativeTime", ""),
            "source":          "indeed",
        })
        logger.info(f"Indeed: '{title}' @ {company} desc_len={len(description)}")

    return jobs


async def scrape_indeed(
    keywords:  List[str],
    location:  str = "Adelaide SA",
    max_pages: int = 3,
) -> List[Dict]:
    all_jobs: List[Dict] = []
    seen_jks: set        = set()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, http2=True) as client:
        for keyword in keywords:
            for page_num in range(max_pages):
                offset = page_num * 10
                url = _build_search_url(keyword, location, offset)
                logger.info(f"Indeed: scraping '{keyword}' page {page_num + 1}: {url}")

                page_jobs = await _scrape_keyword_page(client, url, seen_jks)

                if page_jobs is None:
                    logger.warning(f"Indeed: '{keyword}' page {page_num + 1} failed - stopping keyword")
                    break

                all_jobs.extend(page_jobs)
                logger.info(f"Indeed: '{keyword}' page {page_num + 1}: {len(page_jobs)} jobs, total={len(all_jobs)}")

                if len(page_jobs) == 0:
                    break

                await asyncio.sleep(random.uniform(3.0, 6.0))

            await asyncio.sleep(random.uniform(3.0, 6.0))

    logger.info(f"Indeed: done, {len(all_jobs)} total jobs")
    return all_jobs

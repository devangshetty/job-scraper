import asyncio
import random
import logging
from typing import List, Dict
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from scraper.parser import clean_text

logger = logging.getLogger(__name__)

BASE_URL   = "https://www.iworkfor.sa.gov.au"
# navigate to the homepage and click through to job search
HOME_URL   = f"{BASE_URL}"
ICT_CATEGORY = "Information/Communication Technology"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


async def _navigate_to_search(page) -> bool:
    """Navigate to the homepage and get to the search form."""
    # try known candidate URLs in order
    candidates = [
        f"{BASE_URL}/iworkforsa/job-search.php",
        f"{BASE_URL}/iworkforsa/",
        BASE_URL,
    ]
    for url in candidates:
        logger.info(f"iworkforsa: trying URL {url}")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2.0)
        html = await page.content()
        logger.info(f"iworkforsa: {url} -> first 500 chars: {html[:500]}")
        if "404" not in html[:200] and "Not Found" not in html[:200]:
            logger.info(f"iworkforsa: landed on {url}")
            return True
    return False


async def _get_frame(page):
    logger.info(f"iworkforsa: total frames = {len(page.frames)}")
    for i, f in enumerate(page.frames):
        logger.info(f"iworkforsa: frame[{i}] url={f.url}")
        try:
            btn = await f.query_selector("#brsSearchBtn")
            if btn:
                logger.info(f"iworkforsa: found search form in frame: {f.url}")
                return f
        except Exception:
            continue

    await asyncio.sleep(5.0)
    for i, f in enumerate(page.frames):
        try:
            btn = await f.query_selector("#brsSearchBtn")
            if btn:
                logger.info(f"iworkforsa: found search form in frame after wait: {f.url}")
                return f
        except Exception:
            continue

    logger.warning("iworkforsa: falling back to main frame")
    return page.main_frame


async def _select_ict_category(frame) -> bool:
    try:
        await frame.click("button.ms-choice", timeout=10000)
        await asyncio.sleep(0.8)
        await frame.click(
            f"div.ms-drop li label span:has-text('{ICT_CATEGORY}')",
            timeout=8000,
        )
        await asyncio.sleep(0.5)
        await frame.click("body")
        await asyncio.sleep(0.5)
        logger.info("iworkforsa: ICT category selected")
        return True
    except Exception as e:
        logger.warning(f"iworkforsa: could not select ICT category: {e}")
        return False


async def _extract_job_rows(frame) -> List[Dict]:
    jobs = []
    try:
        await frame.wait_for_selector("table tr", timeout=15000)
    except PWTimeout:
        logger.warning("iworkforsa: no table rows found after search")
        return jobs

    rows = await frame.query_selector_all("table tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 4:
            continue
        try:
            link_el = await cells[0].query_selector("a")
            if not link_el:
                continue
            title  = (await link_el.inner_text()).strip()
            href   = await link_el.get_attribute("href")
            ref_no = (await cells[1].inner_text()).strip()
            posted = (await cells[2].inner_text()).strip()
            agency = (await cells[3].inner_text()).strip()

            if not href:
                continue
            job_url = href if href.startswith("http") else BASE_URL + href

            jobs.append({
                "job_title":       title,
                "company":         agency,
                "location":        "Adelaide SA",
                "salary":          "",
                "application_url": job_url,
                "description":     "",
                "posted_date":     posted,
            })
        except Exception as e:
            logger.warning(f"iworkforsa row parse error: {e}")
            continue
    return jobs


async def _fetch_job_detail(page, job_url: str) -> Dict:
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(1.5, 3.0))

        frame = page.main_frame
        for f in page.frames:
            try:
                el = await f.query_selector("#brs_mainContent")
                if el:
                    frame = f
                    break
            except Exception:
                continue

        location = ""
        salary   = ""

        bold_els = await frame.query_selector_all("b")
        for el in bold_els:
            label = (await el.inner_text()).strip().lower()
            try:
                parent      = await el.evaluate_handle("el => el.parentElement")
                parent_text = await parent.as_element().inner_text()
                value       = parent_text.replace(await el.inner_text(), "").strip().lstrip(":")
            except Exception:
                value = ""
            if "location" in label:
                location = value
            elif "salary" in label or "remuneration" in label:
                salary = value

        desc_el = await frame.query_selector("#brs_mainContent, .main-content, main")
        description = ""
        if desc_el:
            description = clean_text(await desc_el.inner_html())
        else:
            body_el = await frame.query_selector("body")
            if body_el:
                description = clean_text(await body_el.inner_html())

        return {"description": description, "location": location, "salary": salary}

    except PWTimeout:
        logger.warning(f"iworkforsa timeout: {job_url}")
        return {}
    except Exception as e:
        logger.warning(f"iworkforsa detail error {job_url}: {e}")
        return {}


async def scrape_iworkforsa() -> List[Dict]:
    all_jobs:  List[Dict] = []
    seen_urls: set        = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            ok = await _navigate_to_search(page)
            if not ok:
                logger.error("iworkforsa: could not find a valid search page URL")
                return all_jobs

            frame = await _get_frame(page)

            await _select_ict_category(frame)

            await frame.click("#brsSearchBtn", timeout=10000)
            await asyncio.sleep(random.uniform(2.0, 3.5))
            logger.info("iworkforsa: search submitted")

            cards     = await _extract_job_rows(frame)
            new_cards = [c for c in cards if c["application_url"] not in seen_urls]
            for c in new_cards:
                seen_urls.add(c["application_url"])

            logger.info(f"iworkforsa: found {len(new_cards)} jobs")

            for job in new_cards:
                detail = await _fetch_job_detail(page, job["application_url"])
                if detail.get("description"):
                    job["description"] = detail["description"]
                if detail.get("location"):
                    job["location"] = detail["location"]
                if detail.get("salary"):
                    job["salary"] = detail["salary"]
                await asyncio.sleep(random.uniform(1.5, 3.0))

            all_jobs.extend(new_cards)
            logger.info(f"iworkforsa: done, {len(all_jobs)} jobs scraped")

        except Exception as e:
            logger.error(f"iworkforsa scrape failed: {e}", exc_info=True)
        finally:
            await browser.close()

    return all_jobs

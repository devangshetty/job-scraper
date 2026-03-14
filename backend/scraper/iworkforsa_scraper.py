import asyncio
import random
import logging
from typing import List, Dict
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from scraper.parser import clean_text

logger = logging.getLogger(__name__)

BASE_URL     = "https://www.iworkfor.sa.gov.au"
ICT_CATEGORY = "Information Technology"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


async def _get_search_frame(page):
    """Find the frame containing the search form."""
    for _ in range(6):  # retry up to 6 times (12 seconds total)
        for f in page.frames:
            try:
                # homepage form has a Classification select
                el = await f.query_selector("select[name='Classification'], input[name='Keywords'], form")
                if el:
                    logger.info(f"iworkforsa: found search form in frame: {f.url}")
                    return f
            except Exception:
                continue
        logger.info(f"iworkforsa: waiting for search form... frames={len(page.frames)}")
        await asyncio.sleep(2.0)

    logger.warning("iworkforsa: falling back to main frame")
    return page.main_frame


async def _extract_job_rows(frame) -> List[Dict]:
    jobs = []
    try:
        await frame.wait_for_selector("table tr td a, .job-result, .search-result", timeout=20000)
    except PWTimeout:
        # log what we got
        html = await frame.content()
        logger.warning(f"iworkforsa: no results found. Page snippet: {html[:1000]}")
        return jobs

    rows = await frame.query_selector_all("table tr")
    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 2:
            continue
        try:
            link_el = await cells[0].query_selector("a")
            if not link_el:
                continue
            title  = (await link_el.inner_text()).strip()
            href   = await link_el.get_attribute("href")
            if not href or not title:
                continue
            job_url = href if href.startswith("http") else BASE_URL + href

            agency = ""
            posted = ""
            if len(cells) >= 4:
                posted = (await cells[2].inner_text()).strip()
                agency = (await cells[3].inner_text()).strip()
            elif len(cells) >= 2:
                agency = (await cells[1].inner_text()).strip()

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
                el = await f.query_selector("#brs_mainContent, .jobAdPage, h1")
                if el:
                    frame = f
                    break
            except Exception:
                continue

        location = ""
        salary   = ""

        bold_els = await frame.query_selector_all("b, strong")
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

        desc_el = await frame.query_selector("#brs_mainContent, .jobAdPage, main, article")
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
            logger.info("iworkforsa: loading homepage")
            await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3.0)

            html = await page.content()
            logger.info(f"iworkforsa: homepage snippet: {html[:800]}")

            frame = await _get_search_frame(page)

            # log all selects to identify the right one
            selects = await frame.query_selector_all("select")
            for sel in selects:
                name = await sel.get_attribute("name")
                id_  = await sel.get_attribute("id")
                logger.info(f"iworkforsa: found select name={name} id={id_}")

            # try to select ICT via Classification dropdown
            try:
                await frame.select_option("select[name='Classification']", label=ICT_CATEGORY, timeout=5000)
                logger.info("iworkforsa: Classification set")
            except Exception as e:
                logger.warning(f"iworkforsa: Classification select failed: {e}")

            # find and click the search/submit button
            submit = await frame.query_selector("input[type='submit'], button[type='submit'], input[name='searchButton']")
            if submit:
                await submit.click()
                logger.info("iworkforsa: search submitted")
                await asyncio.sleep(random.uniform(2.0, 3.5))
            else:
                logger.warning("iworkforsa: no submit button found")
                html2 = await frame.content()
                logger.info(f"iworkforsa: frame content: {html2[:1000]}")
                return all_jobs

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

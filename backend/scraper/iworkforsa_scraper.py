import asyncio
import random
import logging
from typing import List, Dict
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

BASE_URL         = "https://www.iworkfor.sa.gov.au"
ICT_SELECT_VALUE = "40666"
CATEGORY_SELECT  = "select[name='c_179[]']"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Selectors tried in order - most specific first, body last as fallback
DESC_SELECTORS = [
    "#brs_mainContent",
    ".job-description",
    ".jobAdPage",
    "article",
    "main",
]


async def _get_search_frame(page):
    for _ in range(6):
        for f in page.frames:
            try:
                el = await f.query_selector("form")
                if el:
                    logger.info(f"iworkforsa: found search form in frame: {f.url}")
                    return f
            except Exception:
                continue
        await asyncio.sleep(2.0)
    logger.warning("iworkforsa: falling back to main frame")
    return page.main_frame


async def _select_ict_category(frame) -> bool:
    try:
        result = await frame.evaluate("""
            () => {
                const sel = document.querySelector("select[name='c_179[]']");
                if (!sel) return 'not_found';
                for (const opt of sel.options) {
                    opt.selected = (opt.value === '40666');
                }
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return 'ok';
            }
        """)
        logger.info(f"iworkforsa: ICT category JS select result: {result}")
        await asyncio.sleep(0.5)
        return result == "ok"
    except Exception as e:
        logger.warning(f"iworkforsa: ICT JS select failed: {e}")
        return False


def _is_valid_job_url(href: str) -> bool:
    if not href:
        return False
    low = href.lower().strip()
    if low.startswith("javascript") or low.startswith("#"):
        return False
    return True


def _clean_text(raw: str) -> str:
    """Collapse whitespace and strip leading/trailing space."""
    import re
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", raw)).strip()


async def _extract_job_rows(frame) -> List[Dict]:
    jobs = []
    try:
        await frame.wait_for_selector("table tr td a", timeout=20000)
    except PWTimeout:
        html = await frame.content()
        logger.warning(f"iworkforsa: no results. Page snippet: {html[:500]}")
        return jobs

    rows = await frame.query_selector_all("table tr")
    for row in rows:
        headers = await row.query_selector_all("th")
        if headers:
            continue
        cells = await row.query_selector_all("td")
        if len(cells) < 2:
            continue
        try:
            link_el = await cells[0].query_selector("a")
            if not link_el:
                continue
            title = (await link_el.inner_text()).strip()
            href  = (await link_el.get_attribute("href") or "").strip()

            if not title or not _is_valid_job_url(href):
                continue

            skip_titles = {"job title", "next", "last", "first", "previous", "prev"}
            if title.lower() in skip_titles:
                continue

            job_url = href if href.startswith("http") else BASE_URL + href

            posted = ""
            agency = ""
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
                "source":          "iworkforsa",
            })
        except Exception as e:
            logger.warning(f"iworkforsa row parse error: {e}")
            continue

    logger.info(f"iworkforsa: extracted {len(jobs)} valid job rows")
    return jobs


async def _fetch_job_detail(page, job_url: str) -> Dict:
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(1.5, 3.0))

        frame = page.main_frame
        for f in page.frames:
            try:
                el = await f.query_selector("#brs_mainContent, h1, article")
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

        # Try specific content selectors first - use inner_text() not inner_html()
        description = ""
        for selector in DESC_SELECTORS:
            desc_el = await frame.query_selector(selector)
            if desc_el:
                raw = (await desc_el.inner_text()).strip()
                if len(raw) > 100:  # must be meaningful content, not a stray element
                    description = _clean_text(raw)
                    logger.info(f"iworkforsa: description from '{selector}', len={len(description)}")
                    break

        # Last resort: grab body text but strip nav/header/footer first via JS
        if not description:
            description = await frame.evaluate("""
                () => {
                    const remove = ['nav', 'header', 'footer', '.nav', '.header', '.footer',
                                    '#brs_header', '#brs_footer', '#brs_nav', 'script', 'style'];
                    remove.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el.remove());
                    });
                    return (document.body?.innerText || '').trim();
                }
            """)
            import re
            description = re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", description)).strip()
            logger.info(f"iworkforsa: description from body fallback, len={len(description)}")

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

            frame = await _get_search_frame(page)

            await _select_ict_category(frame)

            submit = await frame.query_selector(
                "input[type='submit'], button[type='submit'], input[name='searchButton'], #brsSearchBtn"
            )
            if not submit:
                logger.warning("iworkforsa: no submit button found")
                return all_jobs

            await submit.click()
            logger.info("iworkforsa: search submitted")
            await asyncio.sleep(random.uniform(2.0, 3.5))

            cards     = await _extract_job_rows(frame)
            new_cards = [c for c in cards if c["application_url"] not in seen_urls]
            for c in new_cards:
                seen_urls.add(c["application_url"])

            logger.info(f"iworkforsa: {len(new_cards)} jobs found")

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

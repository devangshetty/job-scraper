from fastapi import APIRouter
from agents.search import web_search

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/search")
async def search(q: str, max_results: int = 5):
    """Test endpoint — run a Bing search via Playwright and return results."""
    results = await web_search(q, max_results=max_results)
    return {"query": q, "count": len(results), "results": results}

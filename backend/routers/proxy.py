import httpx
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

ALLOWED_HOSTS = {"www.iworkfor.sa.gov.au", "iworkfor.sa.gov.au"}


@router.get("/download")
async def proxy_download(url: str):
    """
    Fetch a file from iWorkForSA and stream it back with Content-Disposition: attachment
    so the browser shows the native Save As dialog.
    """
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="URL not allowed")

    filename = parsed.path.split("/")[-1] or "attachment"

    async def stream():
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    return StreamingResponse(
        stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

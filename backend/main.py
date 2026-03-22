import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from database import engine, Base
from routers import jobs, scrape, llm, resume, settings, agent, proxy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

Base.metadata.create_all(bind=engine)

# Migrate existing DBs that predate the attachments column
with engine.connect() as _conn:
    try:
        _conn.execute(text("ALTER TABLE jobs ADD COLUMN attachments TEXT"))
        _conn.commit()
        logging.getLogger(__name__).info("Migration: added attachments column")
    except Exception:
        pass  # column already exists

app = FastAPI(title="Job Scraper API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(scrape.router)
app.include_router(llm.router)
app.include_router(resume.router)
app.include_router(settings.router)
app.include_router(agent.router)
app.include_router(proxy.router)


@app.get("/health")
def health():
    return {"status": "ok"}

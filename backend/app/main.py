"""
main.py
-------
FastAPI entry point.

Run: uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import log_provider_status
from app.routers import events, field_mappings, masters
from app.services.embeddings import warm_model_async

app = FastAPI(title="ERP Master Data Prep API")

# Next.js dev server origin - loosen/replace once a real frontend deployment exists.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(masters.router)
app.include_router(field_mappings.router)
app.include_router(events.router)


@app.on_event("startup")
def on_startup():
    log_provider_status()
    warm_model_async()


@app.get("/health")
def health():
    return {"status": "ok"}

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✓ Database initialized")
    yield
    print("✓ Application shutdown")

app = FastAPI(
    title="ERP Master Data Mapping Platform",
    description="AI-driven schema mapping with Retrieval Engine",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "ERP Master Data Mapping Platform"}

@app.get("/")
def root():
    return {"message": "ERP Master Data Mapping Platform API", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)

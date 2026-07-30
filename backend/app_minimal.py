from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Create FastAPI app
app = FastAPI(
    title="ERP Master Data Mapping API",
    description="AI-powered field mapping for ERP systems",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lifespan event handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("✓ API Starting up...")
    yield
    # Shutdown
    print("✓ API Shutting down...")

app = FastAPI(
    title="ERP Master Data Mapping API",
    description="AI-powered field mapping for ERP systems",
    version="1.0.0",
    lifespan=lifespan
)

# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "ok", "message": "API is running"}

# Test endpoint
@app.get("/api/test")
async def test():
    return {
        "message": "Backend is working!",
        "status": "success"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

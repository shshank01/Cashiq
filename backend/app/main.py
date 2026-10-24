from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import engine, Base
import app.models # Ensure all models are registered with Base.metadata
from app.auth.routes import router as auth_router
from app.routes.api_v1 import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow development frontend connections
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "project": "CashIQ",
        "description": "AI-Powered Financial Intelligence Platform for Startups and SMEs",
        "version": "1.0.0",
        "api_docs": "/docs"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "service": "cashiq-backend"}

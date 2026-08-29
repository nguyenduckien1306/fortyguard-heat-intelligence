"""FortyGuard Heat Intelligence — FastAPI application entry point."""

from fastapi import FastAPI

from backend.config import get_settings
from backend.routes import health, heat_intelligence, heatmap

settings = get_settings()

app = FastAPI(
    title="FortyGuard Heat Intelligence",
    description="Urban Heat Intelligence using the FortyGuard Enterprise Temperature API.",
    version=settings.app_version,
)

app.include_router(health.router)
app.include_router(heatmap.router)
app.include_router(heat_intelligence.router)



@app.get("/")
def root() -> dict[str, str]:
    """Root endpoint with basic service information."""
    return {
        "service": settings.service_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/v1/health",
    }

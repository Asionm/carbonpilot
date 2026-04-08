"""
Routes package for CarbonPilot server.
This package contains modular route definitions for different API endpoints.
"""

from fastapi import APIRouter

# Import all route modules
from .project_routes import router as project_router
from .history_routes import router as history_router
from .config_routes import router as config_router
from .memory_routes import router as memory_router
from .chat_routes import router as chat_router

# Create main router
router = APIRouter()

# Include all sub-routers
router.include_router(project_router)
router.include_router(history_router)
router.include_router(config_router)
router.include_router(memory_router)
router.include_router(chat_router)
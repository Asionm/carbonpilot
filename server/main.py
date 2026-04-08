import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from server.routes import router

# Load environment variables
load_dotenv(override=True)

# Get server configuration
PORT = int(os.getenv("SERVER_PORT", 8000))
TITLE = os.getenv("SERVER_TITLE", "CarbonPilot API Server")
DESCRIPTION = os.getenv("SERVER_DESCRIPTION", "API server for CarbonPilot carbon emission calculation system")

app = FastAPI(title=TITLE, description=DESCRIPTION)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the main router with /api prefix to match frontend expectations
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    """
    Root endpoint providing basic information about the API server.
    
    Returns:
        Basic server information
    """
    return {
        "message": "CarbonPilot API Server",
        "docs": "/docs",
        "redoc": "/redoc"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
"""
Check-in Service - Main FastAPI Application
Handles event check-ins and attendance tracking
"""
import os
from datetime import datetime
import requests
import logging
import sys
import mysql.connector

from fastapi import FastAPI, HTTPException, Header, Query, Depends, Body
from fastapi.responses import JSONResponse

# Configure stdout logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("checkin-service")
logger.info("Check-in service starting up")

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "rootpassword"),
    "database": os.getenv("DB_NAME", "nilbx_db")
}

# ===== FastAPI Setup =====

app = FastAPI(
    title="Check-in Service",
    description="Handles event check-ins and attendance tracking",
    version="1.0.0"
)


def get_db():
    """Get database connection"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        logger.info("Database connection established")
        return conn
    except mysql.connector.Error as err:
        logger.error(f"Database connection failed: {err}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {err}")


# ===== Health Check =====

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "checkin-service",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)

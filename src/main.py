from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import mysql.connector
import os
import math
from typing import Optional, Dict, Any, cast
from datetime import datetime
import requests

app = FastAPI(title="Check-in Service", version="1.0.0")

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "rootpassword"),
    "database": os.getenv("DB_NAME", "nilbx_db")
}

# API Keys
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
FEATURE_FLAG_URL = os.getenv("FEATURE_FLAG_URL", "http://localhost:8004")

# Pydantic models
class Location(BaseModel):
    lat: float
    lng: float

class CheckinRequest(BaseModel):
    deal_id: int
    influencer_id: int
    location: Location

class SocialVerifyRequest(BaseModel):
    social_url: str

class GeoFence(BaseModel):
    hotspot_name: str
    deal_id: Optional[int] = None
    lat_center: float
    lng_center: float
    radius_meters: int = 100
    address: Optional[str] = None

def get_db_connection():
    """Get database connection"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {err}")

def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points in meters using Haversine formula"""
    R = 6371000  # Earth's radius in meters

    lat1_rad = math.radians(lat1)
    lng1_rad = math.radians(lng1)
    lat2_rad = math.radians(lat2)
    lng2_rad = math.radians(lng2)

    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad

    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

def check_feature_flags():
    """Check if check-in features are enabled"""
    try:
        response = requests.get(f"{FEATURE_FLAG_URL}/flags", timeout=5)
        if response.status_code == 200:
            flags = response.json()
            return {
                "geo_checkins": flags.get("enable_geo_checkins", True),
                "social_verification": flags.get("enable_social_verification", True),
                "auto_payout": flags.get("enable_auto_payout", True)
            }
    except:
        pass
    # Default to enabled if feature flag service is unavailable
    return {
        "geo_checkins": True,
        "social_verification": True,
        "auto_payout": True
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    flags = check_feature_flags()
    return {
        "status": "healthy",
        "service": "checkin-service",
        "feature_flags": flags,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/checkins")
async def create_checkin(request: CheckinRequest):
    """Create a check-in with geo-fence verification"""
    flags = check_feature_flags()
    if not flags["geo_checkins"]:
        raise HTTPException(status_code=403, detail="Geo check-ins are currently disabled")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get geo-fence for this deal
        cursor.execute("""
            SELECT lat_center, lng_center, radius_meters
            FROM geo_fences
            WHERE deal_id = %s AND active = TRUE
            LIMIT 1
        """, (request.deal_id,))

        fence = cast(Optional[Dict[str, Any]], cursor.fetchone())
        if not fence:
            raise HTTPException(status_code=400, detail="No active geo-fence found for this deal")

        # Calculate distance
        distance = haversine(
            request.location.lat, request.location.lng,
            fence['lat_center'], fence['lng_center']
        )

        geo_verified = distance <= fence['radius_meters']

        # Save check-in
        cursor.execute("""
            INSERT INTO checkins (
                deal_id, athlete_id, location_lat, location_lng,
                geo_verified, status, checkin_time
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            request.deal_id, request.influencer_id,
            request.location.lat, request.location.lng,
            geo_verified, 'pending' if geo_verified else 'rejected',
            datetime.utcnow()
        ))

        checkin_id = cursor.lastrowid
        conn.commit()

        # Get deal payout amount
        cursor.execute("SELECT amount FROM deals WHERE id = %s", (request.deal_id,))
        deal = cast(Optional[Dict[str, Any]], cursor.fetchone())
        payout = deal['amount'] if deal else 0

        return {
            "id": checkin_id,
            "geo_verified": geo_verified,
            "distance_meters": round(distance),
            "payout": payout,
            "status": 'pending' if geo_verified else 'rejected',
            "message": "Geo-verified! Post on social media to complete check-in." if geo_verified else f"Not at hotspot. Distance: {round(distance)}m"
        }

    except mysql.connector.Error as err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {err}")
    finally:
        cursor.close()
        conn.close()

@app.post("/checkins/{checkin_id}/social-verify")
async def verify_social(checkin_id: int, request: SocialVerifyRequest):
    """Verify social media post for check-in"""
    flags = check_feature_flags()
    if not flags["social_verification"]:
        raise HTTPException(status_code=403, detail="Social verification is currently disabled")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Check if check-in exists and is geo-verified
        cursor.execute("""
            SELECT deal_id, athlete_id, geo_verified
            FROM checkins
            WHERE id = %s
        """, (checkin_id,))

        checkin = cast(Optional[Dict[str, Any]], cursor.fetchone())
        if not checkin:
            raise HTTPException(status_code=404, detail="Check-in not found")
        if not checkin['geo_verified']:
            raise HTTPException(status_code=400, detail="Check-in must be geo-verified first")

        # Verify social post (simplified - in real implementation would check APIs)
        social_verified = await verify_social_post(request.social_url)

        # Update check-in
        status = 'verified' if social_verified else 'rejected'
        cursor.execute("""
            UPDATE checkins
            SET social_post_url = %s, social_verified = %s, status = %s
            WHERE id = %s
        """, (request.social_url, social_verified, status, checkin_id))

        conn.commit()

        # Trigger auto-payout if enabled and verified
        if social_verified and flags["auto_payout"]:
            await trigger_payout(checkin_id, checkin['deal_id'], checkin['athlete_id'])

        return {
            "verified": social_verified,
            "status": status,
            "auto_payout_triggered": social_verified and flags["auto_payout"]
        }

    except mysql.connector.Error as err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {err}")
    finally:
        cursor.close()
        conn.close()

@app.post("/geo-fences")
async def create_geo_fence(fence: GeoFence):
    """Create a geo-fence for a hotspot"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO geo_fences (
                hotspot_name, deal_id, lat_center, lng_center,
                radius_meters, address, active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            fence.hotspot_name, fence.deal_id, fence.lat_center,
            fence.lng_center, fence.radius_meters, fence.address, True
        ))

        fence_id = cursor.lastrowid
        conn.commit()

        return {"id": fence_id, "message": "Geo-fence created successfully"}

    except mysql.connector.Error as err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {err}")
    finally:
        cursor.close()
        conn.close()

@app.get("/geo-fences/{deal_id}")
async def get_geo_fences(deal_id: int):
    """Get geo-fences for a deal"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM geo_fences
            WHERE deal_id = %s AND active = TRUE
        """, (deal_id,))

        fences = cursor.fetchall()
        return {"geo_fences": fences}

    except mysql.connector.Error as err:
        raise HTTPException(status_code=500, detail=f"Database error: {err}")
    finally:
        cursor.close()
        conn.close()

async def verify_social_post(social_url: str) -> bool:
    """Verify social media post contains required tags (simplified)"""
    # In a real implementation, this would:
    # 1. Parse the URL to determine platform (Twitter, Instagram, etc.)
    # 2. Use platform APIs to fetch post content
    # 3. Check for @nilbx and hotspot tags
    # 4. Verify post was made within time window

    # For now, just check if URL contains expected patterns
    if not social_url:
        return False

    # Simplified check - in real implementation would use APIs
    return "@nilbx" in social_url.lower() or "#nilbx" in social_url.lower()

async def trigger_payout(checkin_id: int, deal_id: int, influencer_id: int):
    """Trigger automatic payout to athlete"""
    try:
        # Get payout amount from deal
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT amount FROM deals WHERE id = %s", (deal_id,))
        deal = cast(Optional[Dict[str, Any]], cursor.fetchone())

        if deal:
            payout_amount = deal['amount']
            # In real implementation, this would call the payment service
            # For now, just log the payout trigger
            print(f"Auto-payout triggered: ${payout_amount} for influencer {influencer_id}, check-in {checkin_id}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error triggering payout: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
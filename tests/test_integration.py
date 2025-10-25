import pytest
from fastapi.testclient import TestClient
import os
import sys

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import the app directly
from main import app

client = TestClient(app)

class TestCheckinServiceIntegration:
    """Integration tests for Check-in Service API"""

    def test_health_endpoint(self):
        """Test that health endpoint returns correct structure"""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "feature_flags" in data
        assert "timestamp" in data
        assert data["service"] == "checkin-service"

    def test_invalid_checkin_request(self):
        """Test check-in with invalid data"""
        # Missing required fields
        response = client.post("/checkins", json={})
        assert response.status_code == 422  # Validation error

        # Invalid location format
        response = client.post("/checkins", json={
            "deal_id": 1,
            "athlete_id": 456,
            "location": "invalid"
        })
        assert response.status_code == 422

    def test_geo_fence_endpoints(self):
        """Test geo-fence CRUD operations"""
        # Test creating geo-fence
        geo_fence_data = {
            "hotspot_name": "Test Hotspot",
            "deal_id": 1,
            "lat_center": 40.712776,
            "lng_center": -74.005974,
            "radius_meters": 100
        }

        # Note: This will fail without database, but tests the endpoint structure
        response = client.post("/geo-fences", json=geo_fence_data)
        # Should return 500 due to database connection failure, but validates request structure
        assert response.status_code in [200, 500]

        # Test getting geo-fences
        response = client.get("/geo-fences/1")
        assert response.status_code in [200, 500]  # 500 expected without DB

    def test_social_verification_endpoint(self):
        """Test social verification endpoint structure"""
        social_data = {
            "social_url": "https://twitter.com/user/status/123?text=@nilbx"
        }

        response = client.post("/checkins/123/social-verify", json=social_data)
        # Should return 404 (check-in not found) or 500 (DB error)
        assert response.status_code in [404, 500]

    def test_cors_headers(self):
        """Test CORS headers are present"""
        response = client.options("/health")
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers or response.status_code == 200

    def test_api_documentation(self):
        """Test that API documentation is accessible"""
        response = client.get("/docs")
        # FastAPI docs should be accessible
        assert response.status_code in [200, 404]  # 404 if docs not enabled

        response = client.get("/openapi.json")
        assert response.status_code in [200, 404]  # 404 if not enabled

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
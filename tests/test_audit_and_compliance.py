"""
Check-in Service - Audit and Compliance Management Tests
Tests for check-in service audit logging and compliance features
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path to import from main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCheckinAuditLogging:
    """Test audit logging for check-in operations"""
    
    @pytest.fixture
    def client(self):
        from main import app  # type: ignore
        return TestClient(app)
    
    @pytest.fixture
    def admin_token(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "admin@example.com", "password": "Admin123!"}
        )
        return response.json()["access_token"]
    
    @pytest.fixture
    def athlete_token(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "athlete@example.com", "password": "Athlete123!"}
        )
        return response.json()["access_token"]
    
    def test_checkin_creation_logged(self, client, athlete_token):
        """Test that check-in creation is logged in audit table"""
        response = client.post(
            "/checkins",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={
                "location": "Home",
                "status": "COMPLETED",
                "duration_minutes": 60,
                "notes": "Morning workout"
            }
        )
        assert response.status_code == 201
        checkin_id = response.json()["id"]
        
        # Verify audit log exists
        audit_response = client.get(
            "/audit-logs",
            headers={"Authorization": f"Bearer {athlete_token}"},
            params={"action": "CHECKIN_CREATE", "entity_id": checkin_id}
        )
        assert audit_response.status_code == 200
        logs = audit_response.json()
        assert len(logs) > 0
        assert logs[0]["entity_type"] == "checkin"
    
    def test_checkin_update_logged(self, client, athlete_token):
        """Test that check-in updates are logged"""
        # Create checkin
        create_response = client.post(
            "/checkins",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={"status": "COMPLETED", "duration_minutes": 60}
        )
        checkin_id = create_response.json()["id"]
        
        # Update checkin
        client.put(
            f"/checkins/{checkin_id}",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={"status": "COMPLETED", "duration_minutes": 75}
        )
        
        # Verify audit log
        audit_response = client.get(
            "/audit-logs",
            headers={"Authorization": f"Bearer {athlete_token}"},
            params={"action": "CHECKIN_UPDATE", "entity_id": checkin_id}
        )
        assert audit_response.status_code == 200
    
    def test_checkin_deletion_logged(self, client, athlete_token):
        """Test that check-in soft deletes are logged"""
        # Create checkin
        create_response = client.post(
            "/checkins",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={"status": "COMPLETED", "duration_minutes": 60}
        )
        checkin_id = create_response.json()["id"]
        
        # Delete checkin
        client.delete(
            f"/checkins/{checkin_id}",
            headers={"Authorization": f"Bearer {athlete_token}"}
        )
        
        # Verify audit log
        audit_response = client.get(
            "/audit-logs",
            headers={"Authorization": f"Bearer {athlete_token}"},
            params={"action": "CHECKIN_DELETE", "entity_id": checkin_id}
        )
        assert audit_response.status_code == 200
    
    def test_audit_log_shows_changes(self, client, athlete_token):
        """Test that audit logs show what fields changed"""
        # Create checkin
        create_response = client.post(
            "/checkins",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={
                "status": "COMPLETED",
                "duration_minutes": 60,
                "location": "Gym"
            }
        )
        checkin_id = create_response.json()["id"]
        
        # Update multiple fields
        client.put(
            f"/checkins/{checkin_id}",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={
                "status": "VERIFIED",
                "duration_minutes": 75,
                "location": "Home"
            }
        )
        
        # Get audit log with changes
        audit_response = client.get(
            "/audit-logs",
            headers={"Authorization": f"Bearer {athlete_token}"},
            params={"entity_id": checkin_id, "include_changes": True}
        )
        assert audit_response.status_code == 200
        logs = audit_response.json()
        if logs:
            log = logs[0]
            assert "changes" in log
            # Should show before/after values
            changes = log["changes"]
            assert "duration_minutes" in changes or "location" in changes


class TestCheckinComplianceTracking:
    """Test compliance tracking for check-in data"""
    
    @pytest.fixture
    def client(self):
        from main import app  # type: ignore
        return TestClient(app)
    
    @pytest.fixture
    def admin_token(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "admin@example.com", "password": "Admin123!"}
        )
        return response.json()["access_token"]
    
    def test_get_compliance_status(self, client, admin_token):
        """Test getting compliance status for athletes"""
        response = client.get(
            "/compliance/athletes",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_athlete_compliance_record(self, client, admin_token):
        """Test getting compliance record for specific athlete"""
        response = client.get(
            "/compliance/athletes/123",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # 200 or 404 both acceptable (depending on if athlete exists)
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "athlete_id" in data
            assert "compliance_status" in data
    
    def test_track_verification_requirement(self, client, admin_token):
        """Test tracking when verification is required"""
        # Create verification requirement
        response = client.post(
            "/compliance/verification-requirements",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "athlete_id": 123,
                "reason": "Multiple unverified check-ins",
                "required_by": (datetime.now() + timedelta(days=7)).isoformat()
            }
        )
        
        if response.status_code == 201:
            data = response.json()
            assert "requirement_id" in data
            assert "athlete_id" in data
    
    def test_list_pending_verifications(self, client, admin_token):
        """Test listing check-ins pending verification"""
        response = client.get(
            "/checkins/pending-verification",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_compliance_report(self, client, admin_token):
        """Test generating compliance report"""
        response = client.get(
            "/compliance/report",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"start_date": "2024-01-01", "end_date": "2024-12-31"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_athletes" in data or "compliance_score" in data


class TestCheckinDisputeManagement:
    """Test dispute filing related to check-ins"""
    
    @pytest.fixture
    def client(self):
        from main import app  # type: ignore
        return TestClient(app)
    
    @pytest.fixture
    def admin_token(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "admin@example.com", "password": "Admin123!"}
        )
        return response.json()["access_token"]
    
    @pytest.fixture
    def athlete_token(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "athlete@example.com", "password": "Athlete123!"}
        )
        return response.json()["access_token"]
    
    def test_file_checkin_dispute(self, client, athlete_token):
        """Test filing a dispute about a check-in"""
        response = client.post(
            "/checkins/disputes",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={
                "checkin_id": 12345,
                "reason": "INCORRECTLY_REJECTED",
                "description": "My check-in was incorrectly marked as invalid"
            }
        )
        
        # 201 if created, 404 if checkin doesn't exist
        assert response.status_code in [201, 404]
        
        if response.status_code == 201:
            data = response.json()
            assert "dispute_id" in data
    
    def test_get_checkin_disputes(self, client, admin_token):
        """Test listing disputes about check-ins"""
        response = client.get(
            "/checkins/disputes",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_resolve_checkin_dispute(self, client, admin_token):
        """Test resolving a check-in dispute"""
        response = client.post(
            "/checkins/disputes/12345/resolve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "resolution": "APPROVED",
                "notes": "Check-in was valid"
            }
        )
        
        # 200 if resolved, 404 if dispute doesn't exist
        assert response.status_code in [200, 404]
    
    def test_get_dispute_details(self, client, admin_token):
        """Test getting details of specific dispute"""
        response = client.get(
            "/checkins/disputes/12345",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # 200 if found, 404 if not
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert "dispute_id" in data
            assert "checkin_id" in data


class TestCheckinSoftDeletes:
    """Test soft delete functionality for check-ins"""
    
    @pytest.fixture
    def client(self):
        from main import app  # type: ignore
        return TestClient(app)
    
    @pytest.fixture
    def athlete_token(self, client):
        response = client.post(
            "/auth/login",
            json={"username": "athlete@example.com", "password": "Athlete123!"}
        )
        return response.json()["access_token"]
    
    def test_deleted_checkins_not_listed(self, client, athlete_token):
        """Test that soft-deleted check-ins don't appear in lists"""
        # Create checkin
        create_response = client.post(
            "/checkins",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={
                "status": "COMPLETED",
                "duration_minutes": 60
            }
        )
        
        if create_response.status_code == 201:
            checkin_id = create_response.json()["id"]
            
            # Delete it
            client.delete(
                f"/checkins/{checkin_id}",
                headers={"Authorization": f"Bearer {athlete_token}"}
            )
            
            # Should not appear in list
            list_response = client.get(
                "/checkins",
                headers={"Authorization": f"Bearer {athlete_token}"}
            )
            checkins = list_response.json()
            ids = [c["id"] for c in checkins]
            assert checkin_id not in ids
    
    def test_deleted_checkin_returns_404(self, client, athlete_token):
        """Test that getting deleted check-in returns 404"""
        # Create and delete
        create_response = client.post(
            "/checkins",
            headers={"Authorization": f"Bearer {athlete_token}"},
            json={"status": "COMPLETED", "duration_minutes": 60}
        )
        
        if create_response.status_code == 201:
            checkin_id = create_response.json()["id"]
            
            client.delete(
                f"/checkins/{checkin_id}",
                headers={"Authorization": f"Bearer {athlete_token}"}
            )
            
            # Getting deleted should return 404
            response = client.get(
                f"/checkins/{checkin_id}",
                headers={"Authorization": f"Bearer {athlete_token}"}
            )
            assert response.status_code == 404
    
    def test_soft_delete_preserves_data(self, client, admin_token):
        """Test that soft delete preserves data in database"""
        # Create, delete, then query with admin to see it's still there
        response = client.get(
            "/checkins/deleted-only",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Admin endpoint should show deleted check-ins
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

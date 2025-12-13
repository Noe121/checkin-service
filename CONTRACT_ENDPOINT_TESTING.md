# Contract Endpoint Testing Guide
**Environment**: dev
**Base URL**: `http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com`
**Date**: December 5, 2025

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [CRUD Operations Testing](#crud-operations-testing)
3. [Geolocation Features Testing](#geolocation-features-testing)
4. [Contract Workflow Testing](#contract-workflow-testing)
5. [Integration Testing](#integration-testing)
6. [Performance Testing](#performance-testing)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Headers
All contract endpoints require authentication headers:

```bash
X-Company-Id: 1        # Company/Brand ID
X-User-Id: 1           # User ID (creator)
Content-Type: application/json
```

### Environment Variables
```bash
export API_BASE_URL="http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com"
export COMPANY_ID=1
export USER_ID=1
```

### Database Access (for verification)
```bash
# Connect via EC2 bastion
ssh -i ~/.ssh/NILbx-kp1.pem ec2-user@98.82.4.231

# Access MySQL
mysql -h terraform-20251120221214492500000001.cuj2i2c6otax.us-east-1.rds.amazonaws.com \
  -u admin -p'YourSecurePassword123' nilbx_db
```

---

## CRUD Operations Testing

### 1. Create Contract

**Endpoint**: `POST /api/contracts`

**Test Case 1.1**: Create Public Contract
```bash
curl -X POST "${API_BASE_URL}/api/contracts" \
  -H "Content-Type: application/json" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{
    "contract_type": "public",
    "title": "Basketball Game Appearance",
    "description": "Courtside appearance at Lakers vs Warriors game",
    "location_name": "Crypto.com Arena",
    "location_address": "1111 S Figueroa St, Los Angeles, CA 90015",
    "location_lat": 34.0430,
    "location_lng": -118.2673,
    "event_timezone": "America/Los_Angeles",
    "event_start_datetime": "2025-12-20T19:00:00Z",
    "event_end_datetime": "2025-12-20T22:00:00Z",
    "payout_amount": 5000.00,
    "total_slots": 2,
    "visibility": "public",
    "geofence_radius_meters": 100,
    "required_check_ins": 1,
    "check_in_window_before_minutes": 30,
    "check_in_window_after_minutes": 120,
    "requirements": {
      "min_followers": 10000,
      "sports": ["basketball"],
      "verified_only": true
    }
  }'
```

**Expected Response** (201 Created):
```json
{
  "id": 1,
  "contract_type": "public",
  "status": "draft",
  "title": "Basketball Game Appearance",
  "location_point": "POINT(-118.2673 34.0430)",
  "created_at": "2025-12-05T...",
  "available_slots": 2,
  "filled_slots": 0
}
```

**Verify in Database**:
```sql
SELECT id, title, status, location_lat, location_lng,
       ST_AsText(location_point) as location_point,
       available_slots, filled_slots
FROM contracts
WHERE id = 1;
```

---

**Test Case 1.2**: Create Private Contract
```bash
curl -X POST "${API_BASE_URL}/api/contracts" \
  -H "Content-Type: application/json" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{
    "contract_type": "private",
    "title": "Exclusive Brand Partnership",
    "target_user_id": 42,
    "target_user_type": "athlete",
    "payout_amount": 25000.00,
    "visibility": "private",
    "location_lat": 40.7128,
    "location_lng": -74.0060
  }'
```

**Expected Response** (201 Created):
```json
{
  "id": 2,
  "contract_type": "private",
  "status": "draft",
  "visibility": "private",
  "target_user_id": 42,
  "target_user_type": "athlete"
}
```

---

### 2. List Contracts

**Endpoint**: `GET /api/contracts`

**Test Case 2.1**: List All Active Contracts
```bash
curl -X GET "${API_BASE_URL}/api/contracts?status=active&limit=10&offset=0" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}"
```

**Expected Response** (200 OK):
```json
{
  "contracts": [
    {
      "id": 1,
      "title": "Basketball Game Appearance",
      "status": "active",
      "available_slots": 2,
      "filled_slots": 0,
      "payout_amount": 5000.00
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

---

**Test Case 2.2**: Filter by Contract Type
```bash
curl -X GET "${API_BASE_URL}/api/contracts?contract_type=public&visibility=public" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}"
```

---

### 3. Get Contract Details

**Endpoint**: `GET /api/contracts/{contract_id}`

**Test Case 3.1**: Get Single Contract
```bash
curl -X GET "${API_BASE_URL}/api/contracts/1" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}"
```

**Expected Response** (200 OK):
```json
{
  "id": 1,
  "contract_type": "public",
  "status": "active",
  "title": "Basketball Game Appearance",
  "description": "Courtside appearance at Lakers vs Warriors game",
  "location_name": "Crypto.com Arena",
  "location_lat": 34.0430,
  "location_lng": -118.2673,
  "geofence_radius_meters": 100,
  "payout_amount": 5000.00,
  "total_slots": 2,
  "available_slots": 2,
  "filled_slots": 0,
  "participants": []
}
```

---

### 4. Update Contract

**Endpoint**: `PUT /api/contracts/{contract_id}`

**Test Case 4.1**: Update Contract Details
```bash
curl -X PUT "${API_BASE_URL}/api/contracts/1" \
  -H "Content-Type: application/json" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{
    "title": "Basketball Game Appearance - UPDATED",
    "payout_amount": 6000.00,
    "total_slots": 3
  }'
```

**Expected Response** (200 OK):
```json
{
  "id": 1,
  "title": "Basketball Game Appearance - UPDATED",
  "payout_amount": 6000.00,
  "total_slots": 3,
  "available_slots": 3
}
```

---

### 5. Publish Contract

**Endpoint**: `POST /api/contracts/{contract_id}/publish`

**Test Case 5.1**: Publish Draft Contract
```bash
curl -X POST "${API_BASE_URL}/api/contracts/1/publish" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}"
```

**Expected Response** (200 OK):
```json
{
  "id": 1,
  "status": "active",
  "published_at": "2025-12-05T...",
  "message": "Contract published successfully"
}
```

**Verify Activity Log**:
```sql
SELECT * FROM contract_activity_log
WHERE contract_id = 1 AND activity_type = 'contract_published'
ORDER BY created_at DESC LIMIT 1;
```

---

### 6. Delete Contract

**Endpoint**: `DELETE /api/contracts/{contract_id}`

**Test Case 6.1**: Soft Delete Contract
```bash
curl -X DELETE "${API_BASE_URL}/api/contracts/1" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}"
```

**Expected Response** (200 OK):
```json
{
  "message": "Contract deleted successfully",
  "id": 1,
  "status": "cancelled",
  "deleted_at": "2025-12-05T..."
}
```

**Verify Soft Delete**:
```sql
SELECT id, status, deleted_at FROM contracts WHERE id = 1;
-- Should show status='cancelled' and deleted_at timestamp
```

---

## Geolocation Features Testing

### 7. Proximity Search

**Endpoint**: `GET /api/contracts/nearby`

**Test Case 7.1**: Find Contracts Near Location
```bash
# Search for contracts within 5km of downtown LA
curl -X GET "${API_BASE_URL}/api/contracts/nearby?lat=34.0522&lng=-118.2437&radius_km=5&limit=10" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}"
```

**Expected Response** (200 OK):
```json
{
  "contracts": [
    {
      "id": 1,
      "title": "Basketball Game Appearance",
      "location_name": "Crypto.com Arena",
      "location_lat": 34.0430,
      "location_lng": -118.2673,
      "distance_km": 1.2,
      "payout_amount": 5000.00
    }
  ],
  "search_location": {
    "lat": 34.0522,
    "lng": -118.2437,
    "radius_km": 5
  },
  "total": 1
}
```

**Database Query Used**:
```sql
-- This is what the endpoint executes behind the scenes
SELECT
  id,
  title,
  location_lat,
  location_lng,
  ST_Distance_Sphere(
    location_point,
    ST_GeomFromText('POINT(-118.2437 34.0522)', 4326)
  ) / 1000 as distance_km
FROM contracts
WHERE ST_Distance_Sphere(
  location_point,
  ST_GeomFromText('POINT(-118.2437 34.0522)', 4326)
) <= 5000  -- 5km in meters
ORDER BY distance_km;
```

---

**Test Case 7.2**: Verify Spatial Index Performance
```sql
-- Check that spatial index is being used
EXPLAIN SELECT * FROM contracts
WHERE MBRContains(
  ST_Buffer(ST_GeomFromText('POINT(-118.2437 34.0522)', 4326), 0.05),
  location_point
);
-- Should show "Using index" for idx_location_point
```

---

## Contract Workflow Testing

### 8. Participant Application Flow

**Test Case 8.1**: Apply to Public Contract
```bash
# Athlete applies to contract
curl -X POST "${API_BASE_URL}/api/contracts/1/apply" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "user_type": "athlete",
    "application_message": "I am a verified athlete with 50K followers and basketball experience"
  }'
```

**Expected Response** (201 Created):
```json
{
  "participant_id": 1,
  "contract_id": 1,
  "user_id": 101,
  "user_type": "athlete",
  "status": "pending",
  "applied_at": "2025-12-05T..."
}
```

**Verify Database**:
```sql
SELECT * FROM contract_participants WHERE contract_id = 1 AND user_id = 101;
SELECT * FROM contract_activity_log WHERE activity_type = 'user_applied';
```

---

**Test Case 8.2**: Accept Participant
```bash
# Brand accepts athlete
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/accept" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}"
```

**Expected Response** (200 OK):
```json
{
  "participant_id": 1,
  "status": "accepted",
  "accepted_at": "2025-12-05T...",
  "contract": {
    "available_slots": 1,
    "filled_slots": 1
  }
}
```

**Verify Slot Updates**:
```sql
SELECT available_slots, filled_slots FROM contracts WHERE id = 1;
-- Should show: available_slots=1, filled_slots=1
```

---

**Test Case 8.3**: Reject Participant
```bash
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/2/reject" \
  -H "Content-Type: application/json" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}" \
  -d '{
    "rejection_reason": "Does not meet minimum follower requirement"
  }'
```

**Expected Response** (200 OK):
```json
{
  "participant_id": 2,
  "status": "rejected",
  "rejection_reason": "Does not meet minimum follower requirement",
  "rejected_at": "2025-12-05T..."
}
```

---

### 9. Check-in Workflow

**Test Case 9.1**: Create Check-in (Within Geofence)
```bash
# Athlete checks in at event location
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/check-in" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "check_in_lat": 34.0430,
    "check_in_lng": -118.2673,
    "photo_url": "https://s3.amazonaws.com/nilbx-photos/checkin-123.jpg",
    "device_id": "iPhone-12345"
  }'
```

**Expected Response** (201 Created):
```json
{
  "check_in_id": 1,
  "participant_id": 1,
  "contract_id": 1,
  "status": "validated",
  "within_geofence": true,
  "distance_from_target_meters": 15.3,
  "checked_in_at": "2025-12-20T19:15:00Z",
  "validated_at": "2025-12-20T19:15:00Z"
}
```

**Verify Spatial Calculation**:
```sql
SELECT
  id,
  check_in_lat,
  check_in_lng,
  ST_AsText(check_in_point) as check_in_point,
  distance_from_target_meters,
  within_geofence
FROM check_ins
WHERE id = 1;
```

---

**Test Case 9.2**: Check-in Outside Geofence
```bash
# Athlete attempts check-in from wrong location
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/check-in" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "check_in_lat": 40.7128,
    "check_in_lng": -74.0060
  }'
```

**Expected Response** (422 Unprocessable Entity):
```json
{
  "detail": "Check-in location is outside the required geofence",
  "distance_from_target_meters": 3935211.4,
  "required_radius_meters": 100,
  "within_geofence": false
}
```

---

### 10. Completion & Payout Flow

**Test Case 10.1**: Submit Completion
```bash
# Athlete submits completion after check-in
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/complete" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "deliverables_urls": [
      "https://instagram.com/post/123",
      "https://twitter.com/status/456"
    ],
    "completion_notes": "Posted content as agreed"
  }'
```

**Expected Response** (200 OK):
```json
{
  "participant_id": 1,
  "status": "completed",
  "completed_at": "2025-12-20T23:00:00Z",
  "pending_brand_approval": true
}
```

---

**Test Case 10.2**: Brand Approves Completion
```bash
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/approve" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-User-Id: ${USER_ID}"
```

**Expected Response** (200 OK):
```json
{
  "participant_id": 1,
  "brand_approved": true,
  "brand_approved_at": "2025-12-21T10:00:00Z",
  "payment_status": "pending",
  "message": "Completion approved. Payment processing initiated."
}
```

---

**Test Case 10.3**: Webhook Payment Intent Succeeded
```bash
# Simulate Stripe webhook (escrow funded)
curl -X POST "${API_BASE_URL}/webhooks/stripe" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: <valid_signature>" \
  -d '{
    "type": "payment_intent.succeeded",
    "data": {
      "object": {
        "id": "pi_test123",
        "amount": 500000,
        "currency": "usd",
        "metadata": {
          "contract_id": "1",
          "participant_id": "1"
        }
      }
    }
  }'
```

**Expected Response** (200 OK):
```json
{
  "received": true
}
```

**Verify Payment Status**:
```sql
SELECT
  payment_status,
  escrow_funded_at,
  escrow_amount,
  escrow_transaction_id
FROM contract_participants
WHERE id = 1;
-- Should show: payment_status='escrow_funded', escrow_amount=5000.00
```

---

## Integration Testing

### Test Scenario 1: Complete Contract Lifecycle

**Step 1**: Create Contract
```bash
CONTRACT_ID=$(curl -X POST "${API_BASE_URL}/api/contracts" \
  -H "Content-Type: application/json" \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" \
  -d '{
    "contract_type": "public",
    "title": "Integration Test Contract",
    "location_lat": 34.0430,
    "location_lng": -118.2673,
    "payout_amount": 1000.00,
    "total_slots": 1,
    "visibility": "public"
  }' | jq -r '.id')

echo "Created contract: $CONTRACT_ID"
```

**Step 2**: Publish Contract
```bash
curl -X POST "${API_BASE_URL}/api/contracts/${CONTRACT_ID}/publish" \
  -H "X-Company-Id: 1" -H "X-User-Id: 1"
```

**Step 3**: Athlete Applies
```bash
PARTICIPANT_ID=$(curl -X POST "${API_BASE_URL}/api/contracts/${CONTRACT_ID}/apply" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{"user_type": "athlete"}' | jq -r '.participant_id')

echo "Participant ID: $PARTICIPANT_ID"
```

**Step 4**: Brand Accepts
```bash
curl -X POST "${API_BASE_URL}/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/accept" \
  -H "X-Company-Id: 1" -H "X-User-Id: 1"
```

**Step 5**: Athlete Checks In
```bash
CHECK_IN_ID=$(curl -X POST "${API_BASE_URL}/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/check-in" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "check_in_lat": 34.0430,
    "check_in_lng": -118.2673
  }' | jq -r '.check_in_id')

echo "Check-in ID: $CHECK_IN_ID"
```

**Step 6**: Athlete Submits Completion
```bash
curl -X POST "${API_BASE_URL}/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/complete" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{"deliverables_urls": ["https://example.com/post1"]}'
```

**Step 7**: Brand Approves
```bash
curl -X POST "${API_BASE_URL}/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/approve" \
  -H "X-Company-Id: 1" -H "X-User-Id: 1"
```

**Step 8**: Verify Complete Workflow
```sql
-- Check all activity logs
SELECT
  activity_type,
  user_id,
  created_at,
  description
FROM contract_activity_log
WHERE contract_id = ${CONTRACT_ID}
ORDER BY created_at;

-- Verify final states
SELECT status, filled_slots FROM contracts WHERE id = ${CONTRACT_ID};
SELECT status, payment_status, brand_approved FROM contract_participants WHERE id = ${PARTICIPANT_ID};
SELECT status, within_geofence FROM check_ins WHERE contract_participant_id = ${PARTICIPANT_ID};
```

---

### Test Scenario 2: Geofence Validation

**Step 1**: Create Contract with Strict Geofence
```bash
curl -X POST "${API_BASE_URL}/api/contracts" \
  -H "Content-Type: application/json" \
  -H "X-Company-Id: 1" -H "X-User-Id: 1" \
  -d '{
    "title": "Geofence Test",
    "location_lat": 34.0430,
    "location_lng": -118.2673,
    "geofence_radius_meters": 50,
    "payout_amount": 500.00,
    "total_slots": 1
  }'
```

**Step 2**: Test Check-ins at Various Distances
```bash
# Test 1: Exactly at location (should pass)
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/check-in" \
  -H "Content-Type: application/json" -H "X-User-Id: 101" \
  -d '{"check_in_lat": 34.0430, "check_in_lng": -118.2673}'

# Test 2: 25 meters away (should pass)
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/check-in" \
  -H "Content-Type: application/json" -H "X-User-Id: 101" \
  -d '{"check_in_lat": 34.04322, "check_in_lng": -118.2673}'

# Test 3: 100 meters away (should fail)
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/check-in" \
  -H "Content-Type: application/json" -H "X-User-Id: 101" \
  -d '{"check_in_lat": 34.0439, "check_in_lng": -118.2673}'
```

---

## Performance Testing

### Load Testing with Apache Bench

**Test 1**: List Contracts (Read Performance)
```bash
ab -n 1000 -c 10 \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" \
  "${API_BASE_URL}/api/contracts?limit=20"
```

**Expected**: < 200ms avg response time

---

**Test 2**: Proximity Search Performance
```bash
ab -n 500 -c 10 \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" \
  "${API_BASE_URL}/api/contracts/nearby?lat=34.0522&lng=-118.2437&radius_km=10"
```

**Expected**: < 300ms avg response time (spatial index should optimize this)

---

**Test 3**: Contract Creation (Write Performance)
```bash
# Create test payload file
cat > contract_payload.json << 'EOF'
{
  "contract_type": "public",
  "title": "Load Test Contract",
  "location_lat": 34.0430,
  "location_lng": -118.2673,
  "payout_amount": 100.00,
  "total_slots": 1
}
EOF

ab -n 100 -c 5 \
  -p contract_payload.json \
  -T "application/json" \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" \
  "${API_BASE_URL}/api/contracts"
```

**Expected**: < 500ms avg response time

---

### Database Query Performance

**Check Spatial Index Usage**:
```sql
-- Verify spatial index exists
SHOW INDEX FROM contracts WHERE Key_name = 'idx_location_point';

-- Test spatial query performance
EXPLAIN SELECT * FROM contracts
WHERE MBRContains(
  ST_Buffer(location_point, 0.05),
  ST_GeomFromText('POINT(-118.2673 34.0430)', 4326)
);
-- Should show "Using index; Using where"
```

---

## Troubleshooting

### Issue 1: 404 Not Found on Contract Endpoints

**Symptom**: `{"detail": "Not Found"}`

**Diagnosis**:
```bash
# Check if contracts router is loaded
curl -s "${API_BASE_URL}/openapi.json" | jq '.paths | keys | .[] | select(contains("contract"))'
```

**Solutions**:
1. Verify contracts router is registered in main.py
2. Force ECS service redeploy
3. Check API service logs for import errors

---

### Issue 2: Geofence Validation Failing

**Symptom**: All check-ins marked as outside geofence

**Diagnosis**:
```sql
-- Check spatial point calculation
SELECT
  id,
  check_in_lat,
  check_in_lng,
  ST_AsText(check_in_point),
  target_lat,
  target_lng,
  ST_Distance_Sphere(
    check_in_point,
    ST_GeomFromText(CONCAT('POINT(', target_lng, ' ', target_lat, ')'), 4326)
  ) as calculated_distance
FROM check_ins
WHERE id = 1;
```

**Common Issues**:
- Lat/lng reversed (should be POINT(lng lat), not POINT(lat lng))
- SRID mismatch
- Triggers not firing

---

### Issue 3: Payment Webhooks Not Processing

**Symptom**: Payment status stuck at "pending"

**Diagnosis**:
```bash
# Check webhook logs
aws logs tail /ecs/dev-api-service --since 10m --region us-east-1 | grep webhook

# Test webhook endpoint directly
curl -X POST "${API_BASE_URL}/webhooks/stripe" \
  -H "Content-Type: application/json" \
  -d '{"type": "test.event"}'
```

**Solutions**:
1. Verify Stripe webhook secret configured
2. Check async function definitions
3. Validate notification client connectivity

---

### Issue 4: Database Connection Errors

**Symptom**: `"database": "unhealthy"`

**Diagnosis**:
```bash
# Test database connectivity from bastion
ssh -i ~/.ssh/NILbx-kp1.pem ec2-user@98.82.4.231
mysql -h terraform-20251120221214492500000001.cuj2i2c6otax.us-east-1.rds.amazonaws.com \
  -u admin -p'YourSecurePassword123' -e "SELECT 1"
```

**Solutions**:
1. Verify RDS security group allows ECS tasks
2. Check database credentials in task definition
3. Ensure RDS endpoint is correct

---

## Test Data Cleanup

**Reset All Test Data**:
```sql
-- CAUTION: This deletes all contract data!
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE contract_activity_log;
TRUNCATE TABLE check_ins WHERE contract_id IS NOT NULL;
TRUNCATE TABLE contract_participants;
TRUNCATE TABLE contracts;
SET FOREIGN_KEY_CHECKS = 1;

-- Verify cleanup
SELECT COUNT(*) FROM contracts;
SELECT COUNT(*) FROM contract_participants;
SELECT COUNT(*) FROM contract_activity_log;
```

---

## Success Criteria Checklist

- [ ] All CRUD operations return correct status codes
- [ ] Spatial indexing improves proximity search performance (<300ms)
- [ ] Geofence validation works correctly (within 1 meter accuracy)
- [ ] Triggers auto-populate location_point fields
- [ ] Activity logs track all contract events
- [ ] Participant workflow completes end-to-end
- [ ] Payment webhooks update participant status
- [ ] Load testing shows acceptable performance (>100 req/sec)
- [ ] Error handling returns meaningful messages
- [ ] Database constraints prevent invalid states

---

**Testing Guide Version**: 1.0
**Last Updated**: December 5, 2025
**Author**: Claude Code Assistant
**Related Documentation**: [DEPLOYMENT_COMPLETION_REPORT.md](DEPLOYMENT_COMPLETION_REPORT.md)

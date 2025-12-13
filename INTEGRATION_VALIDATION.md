# Contract Workflow Integration Validation
**Environment**: dev
**Date**: December 5, 2025
**Status**: Ready for Testing

---

## Overview

This document provides comprehensive integration validation procedures for the NILBx contract workflow system. It covers end-to-end testing scenarios, system integration points, and validation criteria.

**Current setup / prerequisites**
- Dev cluster: `dev-nilbx-cluster` (ops control plane); deploy/refresh via Jenkins `Dev-Environment-Deploy` pipeline (no manual CLI deploys to dev).
- API/Checkin/Payment/Auth images must be in ECR with the tag you deploy (pipeline verifies).
- ALB+CloudFront are the edge path; ensure ALB listeners/target groups are applied before running these tests.

---

## Table of Contents

1. [System Integration Points](#system-integration-points)
2. [End-to-End Test Scenarios](#end-to-end-test-scenarios)
3. [Service Integration Tests](#service-integration-tests)
4. [Data Integrity Validation](#data-integrity-validation)
5. [Payment Integration](#payment-integration)
6. [Notification Integration](#notification-integration)
7. [Monitoring & Alerts](#monitoring--alerts)

---

## System Integration Points

### Architecture Overview

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│  CloudFront  │─────▶│   ALB       │
│   (Mobile)  │      │              │      │             │
└─────────────┘      └──────────────┘      └──────┬──────┘
                                                   │
                     ┌─────────────────────────────┼─────────────────────┐
                     │                             │                     │
                     ▼                             ▼                     ▼
              ┌─────────────┐             ┌──────────────┐      ┌──────────────┐
              │ API Service │             │   Checkin    │      │   Payment    │
              │  (ECS)      │             │   Service    │      │   Service    │
              └──────┬──────┘             └──────┬───────┘      └──────┬───────┘
                     │                           │                     │
                     │         ┌─────────────────┼─────────────────────┘
                     │         │                 │
                     ▼         ▼                 ▼
              ┌──────────────────────────────────────┐
              │         RDS MySQL (nilbx_db)         │
              │  - contracts                         │
              │  - contract_participants             │
              │  - contract_activity_log             │
              │  - check_ins                         │
              └──────────────────────────────────────┘
                     │
                     ▼
              ┌─────────────┐
              │   Stripe    │
              │  Webhooks   │
              └─────────────┘
```

### Integration Points to Validate

| Service A | Service B | Integration Type | Validation Method |
|-----------|-----------|------------------|-------------------|
| API Service | RDS MySQL | Database CRUD | SQL queries, ORM validation |
| API Service | Payment Service | Webhook events | Event processing tests |
| API Service | Notification Service | HTTP REST | Async notification delivery |
| Checkin Service | RDS MySQL | Geolocation queries | Spatial index performance |
| Payment Service | Stripe | Webhook callbacks | Payment flow validation |
| Frontend | API Service | REST API | E2E UI tests |

---

## End-to-End Test Scenarios

### Scenario 1: Public Contract - Complete Flow

**Objective**: Validate full lifecycle from contract creation to payout

**Actors**:
- Brand (Company ID: 1, User ID: 1)
- Athlete (User ID: 101)

**Test Steps**:

#### Step 1: Brand Creates Public Contract
```bash
# Expected: Contract created in draft status
curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts" \
  -H "Content-Type: application/json" \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" \
  -d '{
    "contract_type": "public",
    "title": "E2E Test: Lakers Game Appearance",
    "description": "Courtside appearance and social media post",
    "location_name": "Crypto.com Arena",
    "location_lat": 34.0430,
    "location_lng": -118.2673,
    "event_start_datetime": "2025-12-20T19:00:00Z",
    "event_end_datetime": "2025-12-20T22:00:00Z",
    "payout_amount": 5000.00,
    "total_slots": 2,
    "geofence_radius_meters": 100,
    "required_check_ins": 1,
    "visibility": "public",
    "requirements": {
      "min_followers": 10000,
      "verified_only": true
    }
  }' | jq '.'
```

**Validation**:
- ✅ Response: 201 Created
- ✅ Contract ID returned
- ✅ Status: "draft"
- ✅ location_point auto-populated via trigger
- ✅ Activity log entry created

**Database Verification**:
```sql
-- Verify contract created
SELECT id, title, status, ST_AsText(location_point), available_slots, filled_slots
FROM contracts WHERE title LIKE 'E2E Test%';

-- Verify trigger populated spatial point
SELECT ST_AsText(location_point), location_lat, location_lng
FROM contracts WHERE id = LAST_INSERT_ID();
-- Expected: POINT(-118.2673 34.0430)

-- Verify activity log
SELECT activity_type, description FROM contract_activity_log
WHERE contract_id = LAST_INSERT_ID() AND activity_type = 'contract_created';
```

---

#### Step 2: Brand Publishes Contract
```bash
CONTRACT_ID=1  # Use ID from Step 1

curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/${CONTRACT_ID}/publish" \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" | jq '.'
```

**Validation**:
- ✅ Response: 200 OK
- ✅ Status changed: "draft" → "active"
- ✅ published_at timestamp set
- ✅ Activity log: 'contract_published'

---

#### Step 3: Athlete Discovers Contract via Proximity Search
```bash
# Athlete searches from nearby location (1km away)
curl -X GET "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/nearby?lat=34.0522&lng=-118.2437&radius_km=5&limit=10" \
  -H "X-User-Id: 101" | jq '.'
```

**Validation**:
- ✅ Contract appears in results
- ✅ distance_km calculated correctly (~1.2km)
- ✅ Spatial index improves query performance (<300ms)

**Performance Test**:
```bash
# Test spatial query performance
time curl -s "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/nearby?lat=34.0522&lng=-118.2437&radius_km=10" > /dev/null
# Expected: <300ms with spatial index
```

---

#### Step 4: Athlete Applies to Contract
```bash
curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/${CONTRACT_ID}/apply" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "user_type": "athlete",
    "application_message": "50K Instagram followers, verified athlete, available for event"
  }' | jq '.'
```

**Validation**:
- ✅ Response: 201 Created
- ✅ participant_id returned
- ✅ Status: "pending"
- ✅ Activity log: 'user_applied'
- ✅ Notification sent to brand (async)

**Database Verification**:
```sql
SELECT id, user_id, status, applied_at FROM contract_participants
WHERE contract_id = ${CONTRACT_ID} AND user_id = 101;

SELECT activity_type, user_id, description FROM contract_activity_log
WHERE contract_id = ${CONTRACT_ID} AND activity_type = 'user_applied';
```

---

#### Step 5: Brand Reviews and Accepts Athlete
```bash
PARTICIPANT_ID=1  # From Step 4

curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/accept" \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" | jq '.'
```

**Validation**:
- ✅ Response: 200 OK
- ✅ Participant status: "pending" → "accepted"
- ✅ Contract slots updated: available_slots--, filled_slots++
- ✅ Activity log: 'user_accepted'
- ✅ Notification sent to athlete

**Database Verification**:
```sql
-- Verify participant status
SELECT status, accepted_at FROM contract_participants WHERE id = ${PARTICIPANT_ID};

-- Verify slot count updates
SELECT available_slots, filled_slots FROM contracts WHERE id = ${CONTRACT_ID};
-- Expected: available_slots=1, filled_slots=1

-- Verify activity log
SELECT * FROM contract_activity_log
WHERE contract_id = ${CONTRACT_ID} AND activity_type = 'user_accepted';
```

---

#### Step 6: Athlete Checks In at Event (Geofence Validation)
```bash
# Athlete arrives at venue and checks in
curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/check-in" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "check_in_lat": 34.0431,
    "check_in_lng": -118.2674,
    "photo_url": "https://s3.amazonaws.com/nilbx-photos/checkin-101-event.jpg",
    "device_id": "iPhone-X-101",
    "validation_method": "gps"
  }' | jq '.'
```

**Validation**:
- ✅ Response: 201 Created
- ✅ check_in_id returned
- ✅ within_geofence: true
- ✅ distance_from_target_meters: ~15m
- ✅ Status: "validated"
- ✅ check_in_point auto-populated via trigger
- ✅ Activity log: 'check_in_completed'

**Database Verification**:
```sql
-- Verify check-in record
SELECT
  id,
  status,
  within_geofence,
  distance_from_target_meters,
  ST_AsText(check_in_point),
  validated_at
FROM check_ins
WHERE contract_participant_id = ${PARTICIPANT_ID};

-- Verify spatial distance calculation
SELECT
  ST_Distance_Sphere(
    check_in_point,
    (SELECT location_point FROM contracts WHERE id = ${CONTRACT_ID})
  ) as calculated_distance,
  distance_from_target_meters
FROM check_ins
WHERE contract_participant_id = ${PARTICIPANT_ID};
-- Both values should match (within rounding)

-- Verify participant check-in status updated
SELECT checked_in, checked_in_at FROM contract_participants
WHERE id = ${PARTICIPANT_ID};
```

**Negative Test - Outside Geofence**:
```bash
# Test check-in from Los Angeles Airport (17km away) - should fail
curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/check-in" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "check_in_lat": 33.9416,
    "check_in_lng": -118.4085
  }' | jq '.'
```

**Expected Response**: 422 Unprocessable Entity
```json
{
  "detail": "Check-in location is outside the required geofence",
  "distance_from_target_meters": 17234.5,
  "required_radius_meters": 100,
  "within_geofence": false
}
```

---

#### Step 7: Athlete Submits Completion with Deliverables
```bash
curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/complete" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: 101" \
  -d '{
    "deliverables_urls": [
      "https://instagram.com/p/ABCD123",
      "https://twitter.com/user/status/456789"
    ],
    "completion_notes": "Posted courtside photos and tagged brand. Engagement: 25K likes, 500 comments."
  }' | jq '.'
```

**Validation**:
- ✅ Response: 200 OK
- ✅ Status: "accepted" → "completed"
- ✅ completed_at timestamp set
- ✅ deliverables_urls stored in JSON
- ✅ Activity log: 'completion_submitted'
- ✅ Notification sent to brand

**Database Verification**:
```sql
SELECT
  status,
  completed_at,
  deliverables_urls,
  brand_approved,
  payment_status
FROM contract_participants
WHERE id = ${PARTICIPANT_ID};
-- Expected: status='completed', brand_approved=false, payment_status='pending'
```

---

#### Step 8: Brand Reviews and Approves Deliverables
```bash
curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/api/contracts/${CONTRACT_ID}/participants/${PARTICIPANT_ID}/approve" \
  -H "Content-Type: application/json" \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" \
  -d '{
    "approval_notes": "Great content! Engagement exceeded expectations."
  }' | jq '.'
```

**Validation**:
- ✅ Response: 200 OK
- ✅ brand_approved: false → true
- ✅ brand_approved_at timestamp set
- ✅ Activity log: 'brand_approved'
- ✅ Payment processing triggered
- ✅ Notification sent to athlete

**Database Verification**:
```sql
SELECT
  brand_approved,
  brand_approved_at,
  approval_notes,
  payment_status
FROM contract_participants
WHERE id = ${PARTICIPANT_ID};
-- Expected: brand_approved=true, payment_status='processing'
```

---

#### Step 9: Payment Service Processes Escrow (via Stripe Webhook)
```bash
# Simulate Stripe payment_intent.succeeded webhook
curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/webhooks/stripe" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: ${STRIPE_WEBHOOK_SECRET}" \
  -d '{
    "id": "evt_test123",
    "type": "payment_intent.succeeded",
    "data": {
      "object": {
        "id": "pi_test_escrow_101",
        "amount": 500000,
        "currency": "usd",
        "status": "succeeded",
        "metadata": {
          "contract_id": "'${CONTRACT_ID}'",
          "participant_id": "'${PARTICIPANT_ID}'"
        }
      }
    }
  }' | jq '.'
```

**Validation**:
- ✅ Response: 200 OK
- ✅ Webhook processed successfully
- ✅ Payment status: "processing" → "escrow_funded"
- ✅ escrow_amount set: 5000.00
- ✅ escrow_transaction_id stored
- ✅ Activity log: 'payment_initiated'
- ✅ Notification sent to brand (escrow funded)

**Database Verification**:
```sql
SELECT
  payment_status,
  escrow_funded_at,
  escrow_amount,
  escrow_transaction_id
FROM contract_participants
WHERE id = ${PARTICIPANT_ID};
-- Expected: payment_status='escrow_funded', escrow_amount=5000.00

SELECT * FROM contract_activity_log
WHERE contract_id = ${CONTRACT_ID} AND activity_type = 'payment_initiated';
```

---

#### Step 10: Payout Transfer Completed (via Stripe Webhook)
```bash
# Simulate Stripe transfer.created webhook (payout to athlete)
curl -X POST "http://dev-api-alb-184237217.us-east-1.elb.amazonaws.com/webhooks/stripe" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: ${STRIPE_WEBHOOK_SECRET}" \
  -d '{
    "id": "evt_test456",
    "type": "transfer.created",
    "data": {
      "object": {
        "id": "tr_test_payout_101",
        "amount": 475000,
        "currency": "usd",
        "destination": "acct_athlete_101",
        "metadata": {
          "participant_id": "'${PARTICIPANT_ID}'"
        }
      }
    }
  }' | jq '.'
```

**Validation**:
- ✅ Payment status: "escrow_funded" → "payout_processing"
- ✅ payout_amount set: 4750.00 (after platform fee)
- ✅ payout_transaction_id stored
- ✅ Activity log: 'payout_completed'
- ✅ Notification sent to athlete (payment on the way)

**Database Verification**:
```sql
SELECT
  payment_status,
  payout_amount,
  payout_transaction_id,
  platform_fee,
  payout_initiated_at
FROM contract_participants
WHERE id = ${PARTICIPANT_ID};
-- Expected: payment_status='payout_processing', payout_amount=4750.00

-- Verify complete activity timeline
SELECT activity_type, created_at, description
FROM contract_activity_log
WHERE contract_id = ${CONTRACT_ID}
ORDER BY created_at;
```

---

### Scenario 1: Success Criteria

**All checks must pass**:

- [x] Contract created with spatial point auto-populated
- [x] Contract published and discoverable via proximity search
- [x] Athlete application creates participant record
- [x] Brand acceptance updates contract slots correctly
- [x] Geofence validation passes for valid location
- [x] Geofence validation fails for invalid location
- [x] Check-in triggers auto-populate spatial coordinates
- [x] Completion submission stores deliverables
- [x] Brand approval triggers payment processing
- [x] Stripe webhooks update payment status
- [x] All activity logged in contract_activity_log
- [x] Notifications sent at each step (async)
- [x] Database constraints maintain data integrity

**Performance Criteria**:
- Proximity search: <300ms
- Check-in validation: <200ms
- Webhook processing: <500ms
- End-to-end flow: <30 seconds (excluding event timing)

---

## Service Integration Tests

### API Service ↔ Database Integration

**Test 1**: ORM Model Validation
```python
# Test script: test_orm_models.py
from src.models_contracts import Contract, ContractParticipant, ContractActivityLog
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Create test contract
contract = Contract(
    company_id=1,
    created_by_user_id=1,
    contract_type="public",
    title="ORM Test Contract",
    location_lat=34.0430,
    location_lng=-118.2673
)

# Verify trigger auto-populates location_point
session.add(contract)
session.commit()
session.refresh(contract)

assert contract.location_point is not None
assert "POINT(-118.2673 34.0430)" in str(contract.location_point)
```

**Test 2**: Spatial Query Performance
```sql
-- Benchmark proximity search with spatial index
SET @search_point = ST_GeomFromText('POINT(-118.2437 34.0522)', 4326);
SET @radius_meters = 5000;

EXPLAIN SELECT
  id,
  title,
  ST_Distance_Sphere(location_point, @search_point) / 1000 as distance_km
FROM contracts
WHERE ST_Distance_Sphere(location_point, @search_point) <= @radius_meters
ORDER BY distance_km
LIMIT 10;
-- Verify: "Using index" appears in Extra column
```

---

### API Service ↔ Payment Service Integration

**Test 3**: Webhook Signature Validation
```bash
# Test invalid signature (should reject)
curl -X POST "${API_BASE_URL}/webhooks/stripe" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: invalid_signature" \
  -d '{"type": "test.event"}' -w "\nHTTP: %{http_code}\n"
# Expected: 400 Bad Request
```

**Test 4**: Async Webhook Processing
```bash
# Send webhook and verify async processing
WEBHOOK_START=$(date +%s)

curl -X POST "${API_BASE_URL}/webhooks/stripe" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "payment_intent.succeeded",
    "data": {
      "object": {
        "id": "pi_async_test",
        "amount": 100000,
        "metadata": {"contract_id": "1", "participant_id": "1"}
      }
    }
  }'

WEBHOOK_END=$(date +%s)
WEBHOOK_DURATION=$((WEBHOOK_END - WEBHOOK_START))

echo "Webhook response time: ${WEBHOOK_DURATION}s"
# Expected: <1s (webhook returns immediately, processes async)
```

---

### Checkin Service ↔ Database Integration

**Test 5**: Spatial Trigger Verification
```sql
-- Insert check-in and verify trigger auto-populates point
INSERT INTO check_ins (
  user_id,
  contract_id,
  contract_participant_id,
  check_in_lat,
  check_in_lng,
  status
) VALUES (
  101, 1, 1,
  34.0430, -118.2673,
  'pending'
);

-- Verify trigger populated check_in_point
SELECT
  id,
  check_in_lat,
  check_in_lng,
  ST_AsText(check_in_point)
FROM check_ins
WHERE id = LAST_INSERT_ID();
-- Expected: POINT(-118.2673 34.0430)
```

---

## Data Integrity Validation

### Test 6: Referential Integrity

**Test Foreign Key Constraints**:
```sql
-- Test 1: Cannot create participant for non-existent contract
INSERT INTO contract_participants (contract_id, user_id, user_type, status)
VALUES (99999, 101, 'athlete', 'pending');
-- Expected: ERROR 1452 (23000): Cannot add or update a child row

-- Test 2: Cannot delete contract with participants
DELETE FROM contracts WHERE id = 1;
-- Expected: ERROR 1451 (23000): Cannot delete or update a parent row

-- Test 3: Cascade deletes work correctly
DELETE FROM contracts WHERE id = 1;
-- Verify: contract_participants and contract_activity_log also deleted
SELECT COUNT(*) FROM contract_participants WHERE contract_id = 1;
-- Expected: 0 (if cascade configured)
```

---

### Test 7: Slot Management Integrity

**Test Concurrent Slot Updates**:
```bash
# Terminal 1: Accept participant 1
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/1/accept" \
  -H "X-Company-Id: 1" -H "X-User-Id: 1" &

# Terminal 2: Accept participant 2 (simultaneously)
curl -X POST "${API_BASE_URL}/api/contracts/1/participants/2/accept" \
  -H "X-Company-Id: 1" -H "X-User-Id: 1" &

wait

# Verify slots updated correctly (no race condition)
curl -s "${API_BASE_URL}/api/contracts/1" | jq '.filled_slots, .available_slots'
# Expected: filled_slots=2, available_slots=0 (if total_slots=2)
```

**Database Verification**:
```sql
-- Verify atomic slot updates
SELECT total_slots, available_slots, filled_slots
FROM contracts WHERE id = 1;
-- Expected: available_slots + filled_slots = total_slots
```

---

## Payment Integration

### Test 8: Full Payment Flow

**Step 1**: Create escrow payment intent
```bash
# Simulate payment service creating Stripe PaymentIntent
curl -X POST "https://api.stripe.com/v1/payment_intents" \
  -u "${STRIPE_SECRET_KEY}:" \
  -d amount=500000 \
  -d currency=usd \
  -d "metadata[contract_id]=1" \
  -d "metadata[participant_id]=1" \
  -d description="Escrow for Lakers Game Appearance"
```

**Step 2**: Process webhook (escrow funded)
```bash
# Stripe webhook arrives after payment confirmed
curl -X POST "${API_BASE_URL}/webhooks/stripe" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: ${VALID_SIGNATURE}" \
  -d @stripe_payment_succeeded.json
```

**Step 3**: Verify escrow status
```sql
SELECT
  payment_status,
  escrow_amount,
  escrow_funded_at
FROM contract_participants WHERE id = 1;
-- Expected: payment_status='escrow_funded', escrow_amount=5000.00
```

**Step 4**: Create payout transfer
```bash
# After brand approval, payment service creates transfer
curl -X POST "https://api.stripe.com/v1/transfers" \
  -u "${STRIPE_SECRET_KEY}:" \
  -d amount=475000 \
  -d currency=usd \
  -d destination="${ATHLETE_STRIPE_ACCOUNT}" \
  -d "metadata[participant_id]=1"
```

**Step 5**: Process transfer webhook
```bash
curl -X POST "${API_BASE_URL}/webhooks/stripe" \
  -H "Content-Type: application/json" \
  -H "stripe-signature: ${VALID_SIGNATURE}" \
  -d @stripe_transfer_created.json
```

**Step 6**: Verify payout status
```sql
SELECT
  payment_status,
  payout_amount,
  payout_transaction_id,
  payout_initiated_at
FROM contract_participants WHERE id = 1;
-- Expected: payment_status='payout_processing', payout_amount=4750.00
```

---

## Notification Integration

### Test 9: Async Notification Delivery

**Test notification client connectivity**:
```python
# Test script: test_notifications.py
from src.clients.notification_client import get_notification_client

client = get_notification_client()

# Test async notification
result = await client.send_payment_notification(
    user_id=101,
    event_type='escrow_funded',
    contract_id=1,
    contract_title='Test Contract',
    amount=5000.00
)

assert result['status'] != 'failed'
```

**Monitor notification service logs**:
```bash
# Check if notifications are being sent
aws logs tail /ecs/dev-notification-service --since 5m --region us-east-1 | grep "user_id.*101"
```

---

## Monitoring & Alerts

### Key Metrics to Monitor

**Database Performance**:
```sql
-- Monitor slow queries
SELECT * FROM mysql.slow_log
WHERE query_time > 1.0
ORDER BY start_time DESC LIMIT 10;

-- Monitor spatial index usage
SHOW INDEX FROM contracts WHERE Key_name = 'idx_location_point';
```

**API Performance**:
```bash
# Monitor endpoint response times
curl -w "Time: %{time_total}s\n" -o /dev/null -s \
  "${API_BASE_URL}/api/contracts/nearby?lat=34.0522&lng=-118.2437&radius_km=10"
```

**ECS Service Health**:
```bash
# Monitor service running task count
aws ecs describe-services \
  --cluster dev-nilbx-ops-cluster \
  --services dev-api-service \
  --query 'services[0].runningCount'
```

---

## Final Validation Checklist

### Database Schema
- [x] All tables created with correct column types
- [x] Spatial indexes exist and are being used
- [x] Triggers auto-populate location_point fields
- [x] Foreign key constraints enforce referential integrity
- [x] Slot management maintains consistency

### API Endpoints
- [ ] All CRUD operations return correct status codes
- [ ] Geofence validation works correctly
- [ ] Proximity search uses spatial index
- [ ] Error handling returns meaningful messages
- [ ] Authentication headers enforced

### Integration Points
- [ ] Database connections healthy
- [ ] Stripe webhooks process correctly
- [ ] Notifications sent asynchronously
- [ ] Activity logs track all events
- [ ] Payment flow completes end-to-end

### Performance
- [ ] Proximity search: <300ms
- [ ] Check-in validation: <200ms
- [ ] Webhook processing: <500ms
- [ ] Load testing: >100 req/sec

### Security
- [ ] RDS in private subnet
- [ ] Webhook signatures validated
- [ ] SQL injection prevented (ORM)
- [ ] Input validation on all endpoints

---

**Integration Validation Version**: 1.0
**Last Updated**: December 5, 2025
**Status**: Ready for Testing
**Related Documentation**:
- [CONTRACT_ENDPOINT_TESTING.md](CONTRACT_ENDPOINT_TESTING.md)
- [DEPLOYMENT_COMPLETION_REPORT.md](DEPLOYMENT_COMPLETION_REPORT.md)

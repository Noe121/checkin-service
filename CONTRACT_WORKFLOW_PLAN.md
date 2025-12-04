# Contract Workflow System - Comprehensive Plan

## Executive Summary

This document outlines a complete contract workflow system for the NILBx platform, enabling brands to create location-based contracts that student-athletes and influencers can accept and complete for predetermined payouts. The system supports both private (targeted) and public (open) contracts with geo-fencing validation via the check-in service.

---

## 1. System Architecture

### 1.1 Core Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │ Brand        │  │ Athlete/     │  │ Contract Tracking       │   │
│  │ Dashboard    │  │ Influencer   │  │ Dashboard               │   │
│  └──────────────┘  └──────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ║ HTTPS/REST
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY / ALB                             │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                ┌────────────────┼────────────────┐
                ▼                ▼                ▼
┌───────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│  API Service      │  │ Check-in Service │  │ Payment Service      │
│  (Port 8080)      │  │ (Port 8006)      │  │ (Port 8002)          │
│                   │  │                  │  │                      │
│ - Contract CRUD   │  │ - Geo-validation │  │ - Payout processing  │
│ - Matching Logic  │  │ - Check-ins      │  │ - Escrow management  │
│ - Status Tracking │  │ - Coordinates    │  │ - Transaction logs   │
└───────────────────┘  └──────────────────┘  └──────────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   MySQL DB      │
                        │   (nilbx_db)    │
                        └─────────────────┘
```

### 1.2 Service Responsibilities

**API Service (Primary Contract Management)**
- Contract creation, update, deletion
- Contract matching and discovery
- Eligibility validation
- Status management
- User contract tracking

**Check-in Service (Geo-validation)**
- Location verification
- Check-in/check-out events
- Coordinate validation
- Time tracking
- Proof of attendance

**Payment Service**
- Escrow fund management
- Payout processing
- Transaction records
- Compliance reporting

---

## 2. Data Models

### 2.1 Contracts Table (Extended)

```sql
CREATE TABLE IF NOT EXISTS contracts (
    id INT PRIMARY KEY AUTO_INCREMENT,

    -- Contract ownership
    company_id INT NOT NULL COMMENT 'Brand/sponsor creating contract',
    created_by_user_id INT NOT NULL COMMENT 'User who created contract',

    -- Contract type
    contract_type ENUM('private', 'public') NOT NULL DEFAULT 'public',

    -- Target user (for private contracts)
    target_user_id INT NULL COMMENT 'Specific athlete/influencer (private contracts)',
    target_user_type ENUM('athlete', 'influencer') NULL,

    -- Public contract distribution
    total_slots INT NULL COMMENT 'Total available slots for public contracts',
    filled_slots INT DEFAULT 0 COMMENT 'How many slots are filled',
    max_per_user INT DEFAULT 1 COMMENT 'Max times one user can accept',

    -- Contract details
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    terms_and_conditions TEXT,

    -- Requirements
    required_actions JSON COMMENT '["check_in", "social_post", "photo_upload", "video"]',
    deliverables JSON COMMENT 'Specific deliverable requirements',

    -- Location-based requirements
    requires_checkin BOOLEAN DEFAULT TRUE,
    location_name VARCHAR(255) NOT NULL,
    location_address TEXT,
    location_coordinates JSON NOT NULL COMMENT '{"lat": 40.7128, "lng": -74.0060}',
    geofence_radius_meters INT DEFAULT 100 COMMENT 'Radius for check-in validation',

    -- Time-based requirements
    event_start_datetime DATETIME NOT NULL,
    event_end_datetime DATETIME NOT NULL,
    check_in_window_start DATETIME COMMENT 'When check-ins can begin',
    check_in_window_end DATETIME COMMENT 'Deadline for check-in',
    minimum_duration_minutes INT DEFAULT 0 COMMENT 'Minimum time on-site',

    -- Compensation
    payout_amount DECIMAL(10,2) NOT NULL,
    payout_currency VARCHAR(3) DEFAULT 'USD',
    payment_method ENUM('stripe', 'paypal', 'direct_deposit') DEFAULT 'stripe',

    -- Contract status
    status ENUM(
        'draft',           -- Being created
        'active',          -- Published and accepting
        'paused',          -- Temporarily disabled
        'in_progress',     -- Event happening/users checked in
        'pending_review',  -- Completed, awaiting brand approval
        'completed',       -- Approved and paid
        'cancelled',       -- Cancelled by brand
        'expired'          -- Past event_end_datetime
    ) DEFAULT 'draft',

    -- Approval workflow
    requires_brand_approval BOOLEAN DEFAULT FALSE COMMENT 'Brand must approve completion',
    auto_approve_on_checkin BOOLEAN DEFAULT TRUE COMMENT 'Auto-approve if checked in',

    -- Visibility & Discovery
    is_featured BOOLEAN DEFAULT FALSE,
    visibility ENUM('public', 'private', 'invitation_only') DEFAULT 'public',
    eligible_user_types JSON COMMENT '["athlete", "influencer"]',
    eligible_sports JSON COMMENT 'Filter by sports',
    eligible_tiers JSON COMMENT 'Filter by tier',
    min_follower_count INT DEFAULT 0,

    -- Metadata
    views_count INT DEFAULT 0,
    applicants_count INT DEFAULT 0,
    completed_count INT DEFAULT 0,

    -- Compliance
    compliance_approved BOOLEAN DEFAULT FALSE,
    compliance_notes TEXT,

    -- Audit
    version INT DEFAULT 1,
    deleted_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign Keys (application-level)
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,

    -- Indexes
    INDEX idx_company_id (company_id),
    INDEX idx_contract_type (contract_type),
    INDEX idx_target_user (target_user_id, target_user_type),
    INDEX idx_status (status),
    INDEX idx_event_dates (event_start_datetime, event_end_datetime),
    INDEX idx_visibility (visibility, status),
    INDEX idx_location (location_coordinates(255)),
    INDEX idx_payout (payout_amount),
    INDEX idx_deleted_at (deleted_at),
    INDEX idx_featured (is_featured, status),
    INDEX idx_discovery (status, visibility, event_start_datetime)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Location-based contracts with check-in requirements';
```

### 2.2 Contract Participants Table

```sql
CREATE TABLE IF NOT EXISTS contract_participants (
    id INT PRIMARY KEY AUTO_INCREMENT,

    -- Relationship
    contract_id INT NOT NULL,
    user_id INT NOT NULL,
    user_type ENUM('athlete', 'influencer') NOT NULL,
    athlete_id INT NULL,
    influencer_id INT NULL,

    -- Participation status
    status ENUM(
        'invited',         -- Sent invitation (private contracts)
        'applied',         -- User applied/expressed interest
        'accepted',        -- User accepted contract
        'rejected',        -- User or brand rejected
        'in_progress',     -- Currently fulfilling contract
        'completed',       -- User completed requirements
        'approved',        -- Brand approved completion
        'paid',            -- Payment processed
        'disputed',        -- Dispute raised
        'cancelled'        -- Participation cancelled
    ) DEFAULT 'accepted',

    -- Application/Invitation
    applied_at DATETIME NULL,
    accepted_at DATETIME NULL,
    rejected_at DATETIME NULL,
    rejection_reason TEXT NULL,

    -- Completion tracking
    checked_in BOOLEAN DEFAULT FALSE,
    check_in_id INT NULL COMMENT 'FK to check_ins table',
    checked_in_at DATETIME NULL,
    checked_out_at DATETIME NULL,
    duration_minutes INT NULL,

    deliverables_submitted BOOLEAN DEFAULT FALSE,
    deliverables_data JSON COMMENT 'Uploaded media, links, etc.',
    submitted_at DATETIME NULL,

    completed_at DATETIME NULL,

    -- Approval
    brand_approved BOOLEAN DEFAULT FALSE,
    approved_at DATETIME NULL,
    approved_by_user_id INT NULL,
    approval_notes TEXT NULL,

    -- Payment
    payment_status ENUM('pending', 'processing', 'completed', 'failed', 'disputed') DEFAULT 'pending',
    paid_at DATETIME NULL,
    payment_transaction_id VARCHAR(255) NULL,
    payout_amount DECIMAL(10,2) NULL,

    -- Performance metrics (for brand review)
    performance_rating DECIMAL(3,2) NULL COMMENT '1.00 to 5.00',
    brand_review TEXT NULL,

    -- Audit
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign Keys
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,

    -- Unique constraint: user can only participate once per contract (unless max_per_user > 1)
    UNIQUE KEY uk_contract_user (contract_id, user_id),

    -- Indexes
    INDEX idx_contract_id (contract_id),
    INDEX idx_user (user_id, user_type),
    INDEX idx_status (status),
    INDEX idx_payment_status (payment_status),
    INDEX idx_checked_in (checked_in, checked_in_at),
    INDEX idx_completion (completed_at, brand_approved),
    INDEX idx_user_contracts (user_id, status, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Tracks user participation in contracts';
```

### 2.3 Check-ins Table (Extended)

```sql
CREATE TABLE IF NOT EXISTS check_ins (
    id INT PRIMARY KEY AUTO_INCREMENT,

    -- User info
    user_id INT NOT NULL,
    user_type ENUM('athlete', 'influencer', 'fan') NOT NULL,

    -- Contract relationship
    contract_id INT NULL COMMENT 'FK to contracts table',
    contract_participant_id INT NULL COMMENT 'FK to contract_participants table',

    -- Location data
    location_name VARCHAR(255) NOT NULL,
    location_address TEXT,
    check_in_coordinates JSON NOT NULL COMMENT '{"lat": 40.7128, "lng": -74.0060}',
    target_coordinates JSON NULL COMMENT 'Expected coordinates from contract',
    distance_from_target_meters DECIMAL(10,2) NULL,
    within_geofence BOOLEAN DEFAULT FALSE,

    -- Time tracking
    checked_in_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    checked_out_at DATETIME NULL,
    duration_minutes INT NULL,

    -- Verification
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    device_id VARCHAR(255),
    photo_url VARCHAR(500) NULL COMMENT 'Proof of attendance photo',

    -- Validation
    is_validated BOOLEAN DEFAULT FALSE,
    validated_at DATETIME NULL,
    validation_method ENUM('gps', 'qr_code', 'nfc', 'manual') DEFAULT 'gps',

    -- Status
    status ENUM('active', 'completed', 'cancelled', 'disputed') DEFAULT 'active',

    -- Metadata
    metadata JSON COMMENT 'Additional check-in data',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_user (user_id, user_type),
    INDEX idx_contract (contract_id),
    INDEX idx_participant (contract_participant_id),
    INDEX idx_checked_in_at (checked_in_at),
    INDEX idx_status (status),
    INDEX idx_validation (is_validated, within_geofence),
    INDEX idx_user_checkins (user_id, checked_in_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Location check-ins with contract integration';
```

### 2.4 Contract Activity Log

```sql
CREATE TABLE IF NOT EXISTS contract_activity_log (
    id INT PRIMARY KEY AUTO_INCREMENT,

    contract_id INT NOT NULL,
    contract_participant_id INT NULL,
    user_id INT NOT NULL,

    -- Activity tracking
    activity_type ENUM(
        'contract_created',
        'contract_updated',
        'contract_published',
        'contract_paused',
        'contract_cancelled',
        'user_invited',
        'user_applied',
        'user_accepted',
        'user_rejected',
        'check_in_started',
        'check_in_completed',
        'deliverables_submitted',
        'completion_submitted',
        'brand_approved',
        'brand_rejected',
        'payment_initiated',
        'payment_completed',
        'dispute_raised'
    ) NOT NULL,

    description TEXT,
    metadata JSON COMMENT 'Activity-specific data',

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,

    INDEX idx_contract (contract_id, created_at DESC),
    INDEX idx_participant (contract_participant_id, created_at DESC),
    INDEX idx_activity_type (activity_type),
    INDEX idx_user (user_id, created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Audit log for all contract activities';
```

---

## 3. User Workflows

### 3.1 Brand User Workflow - Create Contract

#### 3.1.1 Private Contract (Targeted to Specific User)

```
1. Brand logs in to dashboard
2. Navigate to "Create Contract" → "Private Contract"
3. Fill out contract form:
   ├─ Search and select target user (athlete/influencer)
   ├─ Set event details (title, description, terms)
   ├─ Define location:
   │  ├─ Use Google Maps autocomplete for address
   │  ├─ Set geofence radius (50m - 1000m)
   │  └─ Save coordinates
   ├─ Set event time window
   ├─ Set check-in requirements:
   │  ├─ Minimum duration on-site
   │  ├─ Required deliverables (photo, video, social post)
   │  └─ Auto-approve vs manual review
   ├─ Set compensation amount
   └─ Review and publish
4. System creates contract with status='active'
5. Target user receives notification
6. Contract appears in target user's "Invitations" tab
```

**API Flow:**
```
POST /api/contracts
{
  "contract_type": "private",
  "target_user_id": 123,
  "target_user_type": "athlete",
  "title": "Appear at Nike Store Grand Opening",
  "description": "Be present at our new flagship store...",
  "location_name": "Nike Flagship Store",
  "location_address": "123 Main St, City, State",
  "location_coordinates": {"lat": 40.7128, "lng": -74.0060},
  "geofence_radius_meters": 100,
  "event_start_datetime": "2025-12-15T10:00:00Z",
  "event_end_datetime": "2025-12-15T14:00:00Z",
  "minimum_duration_minutes": 60,
  "payout_amount": 500.00,
  "required_actions": ["check_in", "photo_upload", "social_post"],
  "requires_brand_approval": true
}

Response 201:
{
  "id": 456,
  "status": "active",
  "contract_type": "private",
  "created_at": "2025-12-04T12:00:00Z"
}
```

#### 3.1.2 Public Contract (Open to Multiple Users)

```
1. Brand logs in to dashboard
2. Navigate to "Create Contract" → "Public Contract"
3. Fill out contract form:
   ├─ Set total available slots (e.g., 10 spots)
   ├─ Set max acceptances per user (usually 1)
   ├─ Define eligibility criteria:
   │  ├─ User types (athletes, influencers, or both)
   │  ├─ Sports filter (basketball, football, etc.)
   │  ├─ Tier filter (medium, high, premium)
   │  ├─ Minimum follower count
   │  └─ Geographic region (optional)
   ├─ Set event details (same as private)
   ├─ Set location and geofence
   ├─ Set compensation per person
   └─ Review and publish
4. System creates contract with status='active'
5. Contract appears in public marketplace
6. Eligible users can browse and accept
```

**API Flow:**
```
POST /api/contracts
{
  "contract_type": "public",
  "total_slots": 10,
  "max_per_user": 1,
  "eligible_user_types": ["athlete", "influencer"],
  "eligible_sports": ["basketball", "football"],
  "eligible_tiers": ["medium", "high", "premium"],
  "min_follower_count": 1000,
  "title": "Grand Opening Event - 10 Spots Available",
  "description": "Join us for our grand opening...",
  "location_name": "Adidas Store Downtown",
  "location_address": "456 Market St, City, State",
  "location_coordinates": {"lat": 40.7580, "lng": -73.9855},
  "geofence_radius_meters": 150,
  "event_start_datetime": "2025-12-20T09:00:00Z",
  "event_end_datetime": "2025-12-20T17:00:00Z",
  "payout_amount": 250.00,
  "required_actions": ["check_in", "photo_upload"],
  "auto_approve_on_checkin": true
}
```

### 3.2 Athlete/Influencer Workflow - Accept & Complete Contract

#### 3.2.1 Discovery & Acceptance

```
User Dashboard:
├─ "Available Contracts" tab
│  ├─ Browse public contracts
│  ├─ Filter by:
│  │  ├─ Location (nearby, city, state)
│  │  ├─ Date range
│  │  ├─ Payout amount
│  │  └─ Requirements
│  └─ Sort by:
│     ├─ Payout (high to low)
│     ├─ Date (upcoming)
│     └─ Distance (nearest)
│
├─ "Invitations" tab (private contracts)
│  ├─ View invitation details
│  ├─ Accept or decline
│  └─ Counter-offer (future feature)
│
└─ Contract Detail View:
   ├─ Full description
   ├─ Location map
   ├─ Date/time
   ├─ Requirements checklist
   ├─ Payout amount
   ├─ Terms & conditions
   └─ "Accept Contract" button
```

**Acceptance Flow:**
```
1. User clicks "Accept Contract"
2. System validates:
   ├─ User eligibility
   ├─ Slots still available (public contracts)
   ├─ No conflicting contracts (same time/location)
   └─ User hasn't reached max_per_user limit
3. Create contract_participant record
4. Increment filled_slots counter
5. Send confirmation to user
6. Add to user's "My Contracts" → "Upcoming" tab
```

**API Flow:**
```
POST /api/contracts/456/accept
{
  "user_id": 123,
  "user_type": "athlete"
}

Response 200:
{
  "participant_id": 789,
  "status": "accepted",
  "contract": {
    "id": 456,
    "title": "Grand Opening Event",
    "event_start": "2025-12-20T09:00:00Z",
    "payout_amount": 250.00,
    "requirements": ["check_in", "photo_upload"]
  },
  "next_steps": [
    "Check in at the event location between 9:00 AM - 5:00 PM on Dec 20",
    "Upload a photo within the app",
    "Stay for at least the minimum duration"
  ]
}
```

#### 3.2.2 Event Day - Check-in Process

```
1. User arrives at event location
2. Opens mobile app
3. Navigate to "My Contracts" → "In Progress"
4. Select active contract
5. Click "Check In Now"
6. System validates:
   ├─ Current time within check-in window
   ├─ GPS coordinates within geofence
   └─ User hasn't already checked in
7. User prompted to:
   ├─ Allow location access
   ├─ Take a photo (if required)
   └─ Confirm check-in
8. Check-in recorded
9. Timer starts for minimum duration
10. User sees "Checked In" status with countdown
```

**API Flow:**
```
POST /api/check-ins
{
  "contract_id": 456,
  "user_id": 123,
  "user_type": "athlete",
  "location_name": "Adidas Store Downtown",
  "check_in_coordinates": {"lat": 40.7581, "lng": -73.9854},
  "photo_url": "https://s3.../check-in-photo.jpg"
}

Response 201:
{
  "check_in_id": 999,
  "status": "active",
  "checked_in_at": "2025-12-20T10:15:00Z",
  "within_geofence": true,
  "distance_from_target_meters": 12.5,
  "minimum_duration_minutes": 60,
  "can_check_out_after": "2025-12-20T11:15:00Z"
}
```

#### 3.2.3 Completion & Check-out

```
1. User has been on-site for minimum duration
2. Completes all required deliverables:
   ├─ Photo uploaded ✓
   ├─ Social media post (if required)
   └─ Any other requirements
3. Click "Check Out & Complete"
4. System validates:
   ├─ Minimum duration met
   ├─ All deliverables submitted
   └─ Within event time window
5. Update participant status to 'completed'
6. If auto-approve enabled:
   ├─ Immediately approve
   ├─ Initiate payment
   └─ Notify user "Payment processing"
7. If manual approval required:
   ├─ Notify brand for review
   └─ User sees "Pending brand approval"
```

**API Flow:**
```
POST /api/check-ins/999/checkout
{
  "deliverables_data": {
    "photo_url": "https://s3.../event-photo.jpg",
    "social_post_url": "https://instagram.com/p/...",
    "notes": "Great event! Had a fantastic time."
  }
}

Response 200:
{
  "check_in_id": 999,
  "status": "completed",
  "checked_out_at": "2025-12-20T12:30:00Z",
  "duration_minutes": 135,
  "participant_status": "completed",
  "payment_status": "processing", // or "pending_approval"
  "estimated_payout_date": "2025-12-22T00:00:00Z"
}
```

### 3.3 Brand Workflow - Review & Approve

#### 3.3.1 Monitor Active Contracts

```
Brand Dashboard:
├─ "Active Contracts" tab
│  ├─ Contract list with live stats:
│  │  ├─ Total slots / filled slots
│  │  ├─ Checked-in count
│  │  ├─ Completed count
│  │  └─ Pending approval count
│  └─ Click contract to view details
│
└─ Contract Detail View:
   ├─ Participant list
   ├─ Real-time check-in status
   ├─ Map view showing checked-in users
   └─ Filter by status
```

#### 3.3.2 Review Completions (Manual Approval)

```
1. Brand receives notification: "5 completions awaiting review"
2. Navigate to "Pending Approvals"
3. For each participant:
   ├─ View deliverables:
   │  ├─ Check-in photo
   │  ├─ Check-out photo
   │  ├─ Social media posts
   │  └─ Duration on-site
   ├─ Review quality
   └─ Decision:
      ├─ Approve → Process payment
      ├─ Request changes → Send back with notes
      └─ Reject → Provide reason (rare)
4. Bulk approve option available
```

**API Flow:**
```
PUT /api/contract-participants/789/approve
{
  "approved": true,
  "approval_notes": "Great photos, thank you!",
  "performance_rating": 5.0
}

Response 200:
{
  "participant_id": 789,
  "status": "approved",
  "payment_status": "processing",
  "payout_amount": 250.00,
  "estimated_payout_date": "2025-12-22"
}
```

---

## 4. User Page Contract Tracking (Privacy-Focused UI/UX)

### 4.1 Design Principles

**Privacy First:**
- Don't show exact earnings to public
- Don't expose all contract details
- Protect brand relationships
- Limit competitive intelligence

**User Experience:**
- Clear status indicators
- Progress tracking
- Actionable next steps
- Performance insights

### 4.2 Athlete/Influencer Dashboard Views

#### 4.2.1 Public Profile View (What Others See)

```
┌─────────────────────────────────────────────────────────────────┐
│  @athlete_username                                    [Follow]   │
│  ──────────────────────────────────────────────────────────────│
│  🏀 Basketball | University of State | Junior                   │
│  📍 City, State | 👥 15.2K followers                            │
│  ──────────────────────────────────────────────────────────────│
│                                                                 │
│  Performance Stats                                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ⭐ 4.8 Average Rating (24 reviews)                       │  │
│  │  ✅ 28 Contracts Completed                                │  │
│  │  📊 95% Completion Rate                                   │  │
│  │  🎯 Top Categories: Events, Appearances, Social Posts    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Badges & Achievements                                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  🏆 Top Performer  |  ⚡ Quick Responder  |  📸 Pro Content│  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ⚠️ Earnings & specific contract details are private           │
└─────────────────────────────────────────────────────────────────┘
```

**Data Shown:**
- Total completed contracts (count only)
- Average rating from brands
- Completion rate %
- Categories/types of work
- Badges earned
- Testimonials (if user enables)

**Data Hidden:**
- Specific contract titles
- Brand names
- Exact earnings
- Upcoming/active contracts
- Pending work

#### 4.2.2 Private Dashboard - "My Contracts" Tab

```
┌─────────────────────────────────────────────────────────────────┐
│  My Contracts                                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  [Upcoming] [In Progress] [Pending] [Completed] [All]    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ── Upcoming (2) ────────────────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  📍 Nike Store Grand Opening               💰 $500.00      ││
│  │  📅 Dec 20, 2025 @ 10:00 AM - 2:00 PM                      ││
│  │  📍 123 Main St, City                                       ││
│  │                                                             ││
│  │  Requirements:                                              ││
│  │  ☐ Check in on-site                                        ││
│  │  ☐ Stay for 60 minutes minimum                             ││
│  │  ☐ Upload 1 photo                                           ││
│  │  ☐ Post on Instagram                                        ││
│  │                                                             ││
│  │  [View Map] [View Details] [Cancel]                        ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  📍 Adidas Popup Event                     💰 $250.00      ││
│  │  📅 Dec 22, 2025 @ 2:00 PM - 6:00 PM                       ││
│  │  📍 456 Market St, City                                     ││
│  │  [View Details]                                             ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ── In Progress (1) ─────────────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  📍 Under Armour Launch Party              💰 $350.00      ││
│  │  ⏱️ Checked In - 45 min ago                                 ││
│  │  ✅ Minimum duration: Met (60/60 min)                       ││
│  │                                                             ││
│  │  Progress:                                                  ││
│  │  ✅ Check in - Completed 10:15 AM                           ││
│  │  ✅ Photo uploaded                                          ││
│  │  ☐ Social post (optional)                                   ││
│  │                                                             ││
│  │  [Upload More] [Check Out & Complete]                      ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ── Pending Approval (3) ────────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  📍 Puma Store Event                       💰 $200.00      ││
│  │  ✅ Completed Dec 18, 2025                                  ││
│  │  ⏳ Awaiting brand review                                   ││
│  │  📊 Est. payment: Dec 20-22                                 ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ── Completed (28) ──────────────────────────────────────────  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  📍 Reebok Meet & Greet                    ✅ Paid $300.00 ││
│  │  📅 Dec 15, 2025 | ⭐ Rating: 5.0                           ││
│  │  💬 "Great work! Very professional"                         ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  [Load More]                                                    │
└─────────────────────────────────────────────────────────────────┘
```

**Status Indicators:**
- 🟢 Upcoming - Accepted, event not started
- 🔵 In Progress - Checked in, completing requirements
- 🟡 Pending - Waiting for brand approval
- ✅ Completed - Approved and paid
- ❌ Cancelled - Contract cancelled
- ⚠️ Action Needed - Missing requirements

#### 4.2.3 Earnings Summary (Private View Only)

```
┌─────────────────────────────────────────────────────────────────┐
│  Earnings Summary                                                │
│  ──────────────────────────────────────────────────────────────│
│                                                                 │
│  This Month (December 2025)                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  💵 $1,450.00 earned                                      │  │
│  │  ⏳ $750.00 pending approval                              │  │
│  │  📊 $500.00 scheduled (upcoming)                          │  │
│  │  ─────────────────────────────────────────────────────── │  │
│  │  Total Potential: $2,700.00                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Year to Date (2025)                                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  💰 $18,350.00 total earnings                             │  │
│  │  📈 +45% vs 2024                                          │  │
│  │  📊 Breakdown:                                            │  │
│  │     Events & Appearances:  $12,400 (68%)                  │  │
│  │     Social Media Posts:    $4,200 (23%)                   │  │
│  │     Content Creation:      $1,750 (9%)                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  [View Detailed Report] [Download Tax Statement]                │
└─────────────────────────────────────────────────────────────────┘
```

**Privacy Controls:**
```
┌─────────────────────────────────────────────────────────────────┐
│  Privacy Settings                                                │
│  ──────────────────────────────────────────────────────────────│
│                                                                 │
│  What others can see:                                           │
│  ☑ Total contracts completed (number only)                      │
│  ☑ Average rating                                               │
│  ☑ Completion rate                                              │
│  ☑ Badges and achievements                                      │
│  ☐ Brand testimonials (requires approval)                       │
│                                                                 │
│  Always private:                                                │
│  🔒 Earnings and payment amounts                                │
│  🔒 Specific contract details                                   │
│  🔒 Brand names (unless testimonial approved)                   │
│  🔒 Upcoming and in-progress contracts                          │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Brand Dashboard Views

#### 4.3.1 Contract Management Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  My Contracts                                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  [Active] [Upcoming] [Completed] [Drafts] [All]          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ── Active Contracts (3) ────────────────────────────────────  │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  📍 Grand Opening Event - Downtown Store                   ││
│  │  📅 Today, Dec 20 @ 9:00 AM - 5:00 PM                      ││
│  │                                                             ││
│  │  Progress:                                                  ││
│  │  ██████████░░░░░░░░░░ 7/10 slots filled                    ││
│  │                                                             ││
│  │  📊 Live Stats:                                             ││
│  │     ✅ 5 checked in                                         ││
│  │     ⏳ 2 not yet arrived                                    ││
│  │     ✓ 2 completed & pending review                          ││
│  │     💰 $2,500.00 total budget | $1,750.00 committed        ││
│  │                                                             ││
│  │  ⚠️ 2 completions awaiting your approval                    ││
│  │                                                             ││
│  │  [View Live Map] [Review Completions] [View Details]       ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐│
│  │  📍 Holiday Popup - Mall Location                          ││
│  │  📅 Dec 22-24 @ All Day                                     ││
│  │  📊 15/20 slots filled                                      ││
│  │  [View Details]                                             ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ── Pending Approvals (8) ───────────────────────────────────  │
│  [Review All] [Bulk Approve Selected]                          │
└─────────────────────────────────────────────────────────────────┘
```

#### 4.3.2 Participant Review Interface

```
┌─────────────────────────────────────────────────────────────────┐
│  Review Completion - Grand Opening Event                         │
│  ──────────────────────────────────────────────────────────────│
│                                                                 │
│  Participant: @athlete_username                                 │
│  Rating: ⭐ 4.8 (24 contracts) | Completion Rate: 95%           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Check-in Details                                         │  │
│  │  ────────────────────────────────────────────────────────│  │
│  │  ✅ Checked in: 10:15 AM (on time)                        │  │
│  │  ✅ Location: Within geofence (12m from target)           │  │
│  │  ✅ Duration: 2h 15min (required: 1h)                     │  │
│  │  ✅ Checked out: 12:30 PM                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Deliverables                                             │  │
│  │  ────────────────────────────────────────────────────────│  │
│  │  📸 Check-in Photo:                                       │  │
│  │     [Image: Athlete at store entrance]                    │  │
│  │                                                           │  │
│  │  📸 Event Photo:                                          │  │
│  │     [Image: Athlete with products]                        │  │
│  │                                                           │  │
│  │  📱 Social Media Post:                                     │  │
│  │     Instagram: https://instagram.com/p/ABC123            │  │
│  │     ❤️ 1,234 likes | 💬 89 comments                       │  │
│  │                                                           │  │
│  │  📝 Notes from participant:                                │  │
│  │     "Amazing event! Customers loved the new products."    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Your Review                                              │  │
│  │  ────────────────────────────────────────────────────────│  │
│  │  Rate Performance: ⭐⭐⭐⭐⭐ 5.0                          │  │
│  │                                                           │  │
│  │  Feedback (optional):                                     │  │
│  │  ┌────────────────────────────────────────────────────┐ │  │
│  │  │ Excellent work! Very professional and engaged with  │ │  │
│  │  │ customers. Great social media content.              │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  │                                                           │  │
│  │  Payout Amount: $500.00                                   │  │
│  │                                                           │  │
│  │  [✅ Approve & Process Payment]  [❌ Request Changes]     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. API Endpoints

### 5.1 Contract Management Endpoints

```
# Create Contract
POST /api/contracts
Headers: Authorization: Bearer <token>
Body: {contract details}
Response: 201 Created

# Get Contract Details
GET /api/contracts/:id
Response: 200 OK

# Update Contract
PUT /api/contracts/:id
Headers: Authorization: Bearer <token>
Body: {updated fields}
Response: 200 OK

# Delete/Cancel Contract
DELETE /api/contracts/:id
Headers: Authorization: Bearer <token>
Response: 204 No Content

# List Contracts (with filters)
GET /api/contracts?status=active&contract_type=public&location=nearby
Response: 200 OK + pagination

# Search/Discover Contracts
GET /api/contracts/discover?user_id=123&lat=40.7128&lng=-74.0060&radius_km=50
Response: 200 OK + matching contracts
```

### 5.2 Contract Participation Endpoints

```
# Accept Contract
POST /api/contracts/:id/accept
Headers: Authorization: Bearer <token>
Body: {user_id, user_type}
Response: 200 OK + participant record

# Decline/Cancel Participation
POST /api/contracts/:id/decline
Headers: Authorization: Bearer <token>
Response: 200 OK

# Get My Contracts
GET /api/users/:user_id/contracts?status=upcoming
Response: 200 OK + user's contracts

# Get Contract Participants (brand view)
GET /api/contracts/:id/participants
Headers: Authorization: Bearer <token>
Response: 200 OK + participants list
```

### 5.3 Check-in Endpoints

```
# Create Check-in
POST /api/check-ins
Headers: Authorization: Bearer <token>
Body: {
  contract_id, user_id, location_coordinates, photo_url
}
Response: 201 Created

# Check-out & Complete
POST /api/check-ins/:id/checkout
Headers: Authorization: Bearer <token>
Body: {deliverables_data}
Response: 200 OK

# Get Check-in Status
GET /api/check-ins/:id
Response: 200 OK

# Validate Location
POST /api/check-ins/validate-location
Body: {contract_id, current_coordinates}
Response: 200 OK + validation result
```

### 5.4 Approval & Payment Endpoints

```
# Approve Completion
PUT /api/contract-participants/:id/approve
Headers: Authorization: Bearer <token>
Body: {approved: true, notes, rating}
Response: 200 OK

# Reject/Request Changes
PUT /api/contract-participants/:id/reject
Headers: Authorization: Bearer <token>
Body: {rejected: true, reason}
Response: 200 OK

# Get Payment Status
GET /api/contract-participants/:id/payment
Response: 200 OK + payment details

# Process Payout (admin/automated)
POST /api/payments/process
Headers: Authorization: Bearer <admin-token>
Body: {participant_id, amount}
Response: 200 OK
```

### 5.5 Analytics & Tracking Endpoints

```
# User Stats (private)
GET /api/users/:user_id/stats
Headers: Authorization: Bearer <token>
Response: {
  total_contracts: 28,
  total_earnings: 18350.00,
  avg_rating: 4.8,
  completion_rate: 0.95
}

# Public Profile Stats
GET /api/users/:user_id/public-stats
Response: {
  total_completed: 28,
  avg_rating: 4.8,
  completion_rate: 0.95,
  badges: [...]
  // No earnings shown
}

# Brand Analytics
GET /api/brands/:brand_id/analytics
Headers: Authorization: Bearer <token>
Response: {
  total_contracts: 15,
  total_participants: 145,
  total_spent: 45000.00,
  avg_participant_rating: 4.6,
  completion_rate: 0.92
}
```

---

## 6. Technical Implementation Notes

### 6.1 Geofence Validation Algorithm

```python
def validate_check_in(contract_id, user_coordinates):
    """
    Validate if user is within contract's geofence
    """
    contract = get_contract(contract_id)
    target = contract.location_coordinates
    radius = contract.geofence_radius_meters

    # Haversine formula for distance calculation
    distance_meters = calculate_distance(
        user_coordinates['lat'],
        user_coordinates['lng'],
        target['lat'],
        target['lng']
    )

    within_geofence = distance_meters <= radius

    return {
        'valid': within_geofence,
        'distance_from_target': distance_meters,
        'geofence_radius': radius
    }
```

### 6.2 Slot Management (Public Contracts)

```python
def accept_public_contract(contract_id, user_id):
    """
    Handle slot management for public contracts
    Uses optimistic locking to prevent race conditions
    """
    contract = get_contract_for_update(contract_id)  # Row-level lock

    # Validate availability
    if contract.filled_slots >= contract.total_slots:
        raise SlotsFilledException("All slots are filled")

    # Check if user already accepted
    existing = get_participant(contract_id, user_id)
    if existing and contract.max_per_user == 1:
        raise AlreadyAcceptedException("Already accepted this contract")

    # Create participant
    participant = create_participant(contract_id, user_id)

    # Increment filled slots (atomic operation)
    contract.filled_slots += 1
    contract.save()

    # If slots now full, update contract status
    if contract.filled_slots >= contract.total_slots:
        contract.status = 'in_progress'
        contract.save()

    return participant
```

### 6.3 Auto-Approval Logic

```python
def process_check_out(check_in_id, deliverables):
    """
    Process check-out and handle auto-approval
    """
    check_in = get_check_in(check_in_id)
    participant = check_in.participant
    contract = participant.contract

    # Update check-in record
    check_in.checked_out_at = now()
    check_in.duration_minutes = calculate_duration(
        check_in.checked_in_at,
        check_in.checked_out_at
    )
    check_in.status = 'completed'
    check_in.save()

    # Update participant deliverables
    participant.deliverables_submitted = True
    participant.deliverables_data = deliverables
    participant.submitted_at = now()
    participant.completed_at = now()
    participant.status = 'completed'
    participant.save()

    # Auto-approval logic
    if contract.auto_approve_on_checkin:
        # Validate all requirements met
        requirements_met = (
            check_in.within_geofence and
            check_in.duration_minutes >= contract.minimum_duration_minutes and
            all_deliverables_submitted(participant, contract)
        )

        if requirements_met:
            # Auto-approve
            participant.brand_approved = True
            participant.approved_at = now()
            participant.status = 'approved'
            participant.save()

            # Initiate payment
            initiate_payout(participant)

            log_activity(contract, 'auto_approved', participant)
        else:
            # Missing requirements, needs manual review
            participant.status = 'pending_review'
            participant.save()
            notify_brand_review_needed(contract, participant)
    else:
        # Manual approval required
        participant.status = 'pending_review'
        participant.save()
        notify_brand_review_needed(contract, participant)

    return participant
```

### 6.4 Payment Processing Flow

```python
async def process_participant_payout(participant_id):
    """
    Process payout for approved participant
    """
    participant = get_participant(participant_id)

    if not participant.brand_approved:
        raise PaymentException("Not approved for payment")

    if participant.payment_status == 'completed':
        raise PaymentException("Already paid")

    contract = participant.contract
    user = get_user(participant.user_id)

    try:
        # Update status
        participant.payment_status = 'processing'
        participant.save()

        # Process via payment service
        result = await payment_service.create_payout({
            'user_id': user.id,
            'amount': contract.payout_amount,
            'currency': contract.payout_currency,
            'method': contract.payment_method,
            'description': f"Contract: {contract.title}",
            'metadata': {
                'contract_id': contract.id,
                'participant_id': participant.id
            }
        })

        # Update participant
        participant.payment_status = 'completed'
        participant.paid_at = now()
        participant.payment_transaction_id = result.transaction_id
        participant.payout_amount = result.amount
        participant.status = 'paid'
        participant.save()

        # Notify user
        send_notification(user, {
            'type': 'payment_completed',
            'amount': result.amount,
            'contract_title': contract.title
        })

        log_activity(contract, 'payment_completed', participant)

        return result

    except PaymentProcessingError as e:
        participant.payment_status = 'failed'
        participant.save()

        notify_admin_payment_failed(participant, e)
        raise
```

---

## 7. Mobile App Integration

### 7.1 Push Notifications

```
Notification Types:
├─ Contract Invitations
│  └─ "You've been invited to {contract_title}"
│
├─ Contract Acceptance
│  └─ "Your contract for {event} has been confirmed"
│
├─ Event Reminders
│  ├─ 24 hours before: "Reminder: {event} tomorrow at {time}"
│  ├─ 1 hour before: "Starting soon: {event} in 1 hour"
│  └─ Event start: "Time to check in for {event}"
│
├─ Check-in Reminders
│  └─ "Don't forget to check in at {location}"
│
├─ Duration Alerts
│  └─ "You've met the minimum duration. Ready to check out?"
│
├─ Approval Notifications
│  ├─ "Your completion is being reviewed"
│  └─ "Approved! Payment processing for {contract}"
│
└─ Payment Notifications
   └─ "${amount} has been deposited to your account"
```

### 7.2 Offline Support

```
Features for limited connectivity:
├─ Cache contract details locally
├─ Queue check-in attempts if offline
├─ Capture GPS coordinates + timestamp
├─ Upload photos when connection restored
└─ Show "Offline Mode" indicator
```

---

## 8. Testing Strategy

### 8.1 Test Scenarios

#### Brand User Tests
```
✓ Create private contract targeting specific athlete
✓ Create public contract with 10 slots
✓ Edit contract before event starts
✓ Cancel contract and refund escrow
✓ Monitor live check-ins on event day
✓ Review and approve completions
✓ Bulk approve multiple participants
✓ Request changes to deliverables
```

#### Athlete/Influencer Tests
```
✓ Discover nearby public contracts
✓ Accept public contract (first-come-first-served)
✓ Accept private invitation
✓ View upcoming contracts
✓ Check in at event location (within geofence)
✓ Attempt check-in outside geofence (should fail)
✓ Upload deliverables
✓ Check out after minimum duration
✓ View payment status
✓ Receive payout
```

#### System Tests
```
✓ Race condition: Multiple users accepting last slot
✓ Geofence validation accuracy
✓ Auto-approval trigger
✓ Payment processing
✓ Notification delivery
✓ Analytics calculation
✓ Privacy controls enforcement
```

### 8.2 Initial Test Contract

```
Test Contract Configuration:
├─ Type: Public
├─ Title: "NILBx Test Event - Beta Testers Only"
├─ Slots: 5 available
├─ Location: {known test location with coordinates}
├─ Geofence: 100 meters
├─ Date: {next week}
├─ Duration: 30 minutes minimum
├─ Payout: $50.00 per person
├─ Requirements:
│  ├─ Check-in on-site
│  ├─ Upload 1 photo
│  └─ Optional social post
├─ Auto-approve: Yes
└─ Test users:
   ├─ test_athlete_1@nilbx.com
   ├─ test_athlete_2@nilbx.com
   └─ test_brand@nilbx.com (creator)
```

---

## 9. Success Metrics

### 9.1 Key Performance Indicators (KPIs)

```
User Engagement:
├─ Contract acceptance rate
├─ Check-in completion rate
├─ Average time from invite to acceptance
└─ User retention (repeat participants)

Brand Satisfaction:
├─ Average participant rating
├─ Contract fill rate (public contracts)
├─ Time to fill all slots
└─ Rebooking rate (brands creating multiple contracts)

Platform Health:
├─ Payment success rate
├─ Dispute rate
├─ No-show rate
└─ Average approval turnaround time
```

### 9.2 Success Criteria for Beta Launch

```
✅ 50+ contracts created by 10+ brands
✅ 200+ successful check-ins
✅ 95%+ geofence validation accuracy
✅ 100% payment processing success
✅ <5% dispute rate
✅ <2% no-show rate
✅ Average user rating >4.5/5.0
✅ Zero critical security issues
```

---

## 10. Future Enhancements

### Phase 2 Features
- Multi-day contracts
- Recurring contracts (weekly/monthly)
- Team/group contracts (multiple participants together)
- QR code check-in (in addition to GPS)
- NFC tag check-in
- Live streaming integration
- Contract templates for brands
- Smart contract suggestions based on past performance

### Phase 3 Features
- AI-powered participant matching
- Dynamic pricing based on demand
- Auction-style contracts (athletes bid)
- Contract negotiation interface
- Advanced analytics dashboard
- White-label solution for enterprises
- International currency support
- Tax document generation (1099, etc.)

---

## 11. Implementation Timeline

### Week 1-2: Database & Backend
- [ ] Create database migrations for new tables
- [ ] Implement contract CRUD endpoints
- [ ] Implement participant management
- [ ] Build geofence validation logic
- [ ] Integrate with payment service

### Week 3-4: Frontend Development
- [ ] Brand dashboard - create contract flow
- [ ] Brand dashboard - manage contracts
- [ ] Athlete dashboard - discover contracts
- [ ] Athlete dashboard - my contracts
- [ ] Check-in interface (mobile-first)

### Week 5: Testing & Refinement
- [ ] End-to-end testing
- [ ] User acceptance testing with beta users
- [ ] Performance optimization
- [ ] Security audit
- [ ] Bug fixes

### Week 6: Beta Launch
- [ ] Deploy to dev environment
- [ ] Create test contracts
- [ ] Onboard beta test users
- [ ] Monitor and iterate
- [ ] Production deployment

---

## 12. Production Readiness - Critical Gaps & Mitigations

### 12.1 Data Model Hardening

#### 12.1.1 Geospatial Indexing (CRITICAL FIX)

**Problem:** JSON columns cannot be efficiently indexed for geofence queries.

**Solution:** Use MySQL spatial data types with proper indexing.

```sql
-- UPDATED contracts table location fields
CREATE TABLE IF NOT EXISTS contracts (
    -- ... other fields ...

    -- Location (CORRECTED for performance)
    location_name VARCHAR(255) NOT NULL,
    location_address TEXT,
    location_lat DECIMAL(10, 8) NOT NULL COMMENT 'Latitude: -90.00000000 to 90.00000000',
    location_lng DECIMAL(11, 8) NOT NULL COMMENT 'Longitude: -180.00000000 to 180.00000000',
    location_point POINT NOT NULL COMMENT 'Spatial point for indexing',
    geofence_radius_meters INT DEFAULT 100,

    -- Spatial index for efficient geofence queries
    SPATIAL INDEX idx_location_point (location_point),
    INDEX idx_location_coords (location_lat, location_lng)
) ENGINE=InnoDB;

-- Create spatial point from lat/lng on insert/update
CREATE TRIGGER before_insert_contract
BEFORE INSERT ON contracts
FOR EACH ROW
SET NEW.location_point = ST_GeomFromText(
    CONCAT('POINT(', NEW.location_lng, ' ', NEW.location_lat, ')'),
    4326  -- WGS84 spatial reference system
);

CREATE TRIGGER before_update_contract
BEFORE UPDATE ON contracts
FOR EACH ROW
SET NEW.location_point = ST_GeomFromText(
    CONCAT('POINT(', NEW.location_lng, ' ', NEW.location_lat, ')'),
    4326
);

-- UPDATED check_ins table
CREATE TABLE IF NOT EXISTS check_ins (
    -- ... other fields ...

    -- Location (CORRECTED)
    check_in_lat DECIMAL(10, 8) NOT NULL,
    check_in_lng DECIMAL(11, 8) NOT NULL,
    check_in_point POINT NOT NULL,

    target_lat DECIMAL(10, 8) NULL,
    target_lng DECIMAL(11, 8) NULL,
    distance_from_target_meters DECIMAL(10, 2) NULL,

    -- Validation
    location_accuracy_meters DECIMAL(10, 2) NULL COMMENT 'GPS accuracy from device',
    within_geofence BOOLEAN DEFAULT FALSE,

    SPATIAL INDEX idx_check_in_point (check_in_point)
) ENGINE=InnoDB;
```

**Query Example:**
```sql
-- Find contracts within 50km of user's current location
SELECT c.*,
       ST_Distance_Sphere(
           c.location_point,
           ST_GeomFromText('POINT(-74.0060 40.7128)', 4326)
       ) AS distance_meters
FROM contracts c
WHERE c.status = 'active'
  AND ST_Distance_Sphere(
      c.location_point,
      ST_GeomFromText('POINT(-74.0060 40.7128)', 4326)
  ) <= 50000
ORDER BY distance_meters ASC;
```

#### 12.1.2 Timezone Handling (CRITICAL)

**Problem:** Event times must be unambiguous across timezones.

**Solution:**

```sql
-- Add timezone fields to contracts
ALTER TABLE contracts ADD COLUMN (
    event_timezone VARCHAR(50) DEFAULT 'UTC' COMMENT 'IANA timezone: America/New_York',

    -- Store all datetimes in UTC
    event_start_datetime DATETIME NOT NULL COMMENT 'UTC timestamp',
    event_end_datetime DATETIME NOT NULL COMMENT 'UTC timestamp',
    check_in_window_start DATETIME COMMENT 'UTC timestamp',
    check_in_window_end DATETIME COMMENT 'UTC timestamp',

    -- Display times in event timezone (generated columns)
    event_start_local AS (
        CONVERT_TZ(event_start_datetime, 'UTC', event_timezone)
    ) VIRTUAL,
    event_end_local AS (
        CONVERT_TZ(event_end_datetime, 'UTC', event_timezone)
    ) VIRTUAL
);

-- Standard for ALL datetime fields across platform
-- Rule: Store in UTC, display in user/event timezone
```

**Application Layer:**
```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def create_contract(event_start_local, event_timezone):
    """
    Convert local event time to UTC for storage
    """
    tz = ZoneInfo(event_timezone)  # e.g., 'America/New_York'
    local_dt = datetime.fromisoformat(event_start_local)
    aware_dt = local_dt.replace(tzinfo=tz)
    utc_dt = aware_dt.astimezone(timezone.utc)

    return {
        'event_start_datetime': utc_dt,
        'event_timezone': event_timezone
    }
```

#### 12.1.3 Unique Constraints & Race Conditions

**Problem:** Multiple acceptance attempts can cause duplicate participants or over-subscription.

**Solution:**

```sql
-- UPDATED contract_participants table
CREATE TABLE IF NOT EXISTS contract_participants (
    -- ... other fields ...

    contract_id INT NOT NULL,
    user_id INT NOT NULL,
    acceptance_attempt_id VARCHAR(36) COMMENT 'UUID for idempotency',

    -- UNIQUE constraint prevents duplicate accepts
    UNIQUE KEY uk_contract_user_attempt (contract_id, user_id, acceptance_attempt_id),

    -- Composite unique for basic duplicate prevention
    UNIQUE KEY uk_contract_user (contract_id, user_id),

    -- Index for slot counting queries
    INDEX idx_status_counting (contract_id, status, created_at)
) ENGINE=InnoDB;

-- Add version field to contracts for optimistic locking
ALTER TABLE contracts ADD COLUMN (
    version INT DEFAULT 1 NOT NULL,
    filled_slots INT DEFAULT 0,

    -- Constraint: filled_slots cannot exceed total_slots
    CONSTRAINT chk_slots CHECK (filled_slots <= total_slots)
);
```

**Application-level atomic slot reservation:**
```python
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

def accept_contract_atomic(contract_id, user_id, attempt_id):
    """
    Atomic slot reservation with optimistic locking
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            # Use SELECT FOR UPDATE to lock row
            contract = db.session.query(Contract).with_for_update()\
                .filter_by(id=contract_id)\
                .one()

            # Validate slots available
            if contract.filled_slots >= contract.total_slots:
                raise SlotsFilledException("No slots available")

            # Create participant with idempotency key
            participant = ContractParticipant(
                contract_id=contract_id,
                user_id=user_id,
                acceptance_attempt_id=attempt_id,  # UUID from client
                status='accepted',
                accepted_at=datetime.utcnow()
            )
            db.session.add(participant)

            # Increment filled_slots with optimistic lock check
            contract.filled_slots += 1
            contract.version += 1

            # Commit transaction
            db.session.commit()

            return participant

        except IntegrityError as e:
            # Duplicate attempt (idempotency - return existing)
            db.session.rollback()
            existing = db.session.query(ContractParticipant)\
                .filter_by(
                    contract_id=contract_id,
                    user_id=user_id
                ).first()
            if existing:
                return existing
            raise

        except StaleDataError:
            # Optimistic lock failed, retry
            db.session.rollback()
            if attempt == max_retries - 1:
                raise ConcurrencyException("Too many concurrent accepts, retry")
            continue
```

### 12.2 State Machine & Consistency

#### 12.2.1 Contract Status State Machine

**Defined States & Transitions:**

```python
from enum import Enum

class ContractStatus(Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    PAUSED = 'paused'
    IN_PROGRESS = 'in_progress'
    PENDING_REVIEW = 'pending_review'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'
    EXPIRED = 'expired'

# Allowed transitions
CONTRACT_TRANSITIONS = {
    'draft': ['active', 'cancelled'],
    'active': ['paused', 'in_progress', 'cancelled', 'expired'],
    'paused': ['active', 'cancelled'],
    'in_progress': ['pending_review', 'completed', 'cancelled'],
    'pending_review': ['completed', 'cancelled'],
    'completed': [],  # Terminal state
    'cancelled': [],  # Terminal state
    'expired': []     # Terminal state
}

def transition_contract_status(contract, new_status):
    """Validate state transitions"""
    current = contract.status

    if new_status not in CONTRACT_TRANSITIONS.get(current, []):
        raise InvalidStateTransition(
            f"Cannot transition from {current} to {new_status}"
        )

    contract.status = new_status
    contract.updated_at = datetime.utcnow()

    # Log state change
    log_activity(contract, f'status_changed_to_{new_status}')
```

#### 12.2.2 Filled Slots Reconciliation

**Problem:** filled_slots can become inconsistent with actual participant count.

**Solution: Single source of truth + scheduled reconciliation**

```python
def reconcile_contract_slots(contract_id):
    """
    Reconcile filled_slots with actual participant count
    Run as scheduled job every 5 minutes
    """
    contract = db.session.query(Contract)\
        .with_for_update()\
        .filter_by(id=contract_id)\
        .one()

    # Count active participants
    actual_count = db.session.query(ContractParticipant)\
        .filter_by(contract_id=contract_id)\
        .filter(ContractParticipant.status.in_([
            'accepted', 'in_progress', 'completed', 'approved', 'paid'
        ]))\
        .count()

    if contract.filled_slots != actual_count:
        # Log discrepancy
        logger.warning(
            f"Slot mismatch for contract {contract_id}: "
            f"filled_slots={contract.filled_slots}, "
            f"actual_count={actual_count}"
        )

        # Reconcile
        contract.filled_slots = actual_count
        db.session.commit()

        # Alert ops team
        send_alert('slot_reconciliation', {
            'contract_id': contract_id,
            'corrected_count': actual_count
        })

# Cron job: */5 * * * * (every 5 minutes)
```

**Cancellation handling:**
```python
def cancel_participation(participant_id, reason):
    """
    Cancel participant and free up slot
    """
    participant = db.session.query(ContractParticipant)\
        .filter_by(id=participant_id)\
        .one()

    contract = db.session.query(Contract)\
        .with_for_update()\
        .filter_by(id=participant.contract_id)\
        .one()

    # Update participant
    participant.status = 'cancelled'
    participant.cancellation_reason = reason
    participant.cancelled_at = datetime.utcnow()

    # Decrement slot count (if previously counted)
    if participant.status in ['accepted', 'in_progress']:
        contract.filled_slots = max(0, contract.filled_slots - 1)

    db.session.commit()

    # Notify waiting list (future feature)
    notify_waitlist(contract)
```

### 12.3 Check-in Integrity & Anti-Fraud

#### 12.3.1 GPS Spoofing Protection

```python
from typing import Dict, Optional

class CheckInValidator:
    """Multi-layer validation for check-ins"""

    def validate_check_in(
        self,
        user_id: int,
        coordinates: Dict[str, float],
        device_info: Dict,
        contract_id: int
    ) -> Dict:
        """
        Comprehensive check-in validation
        """
        validations = []
        risk_score = 0.0

        # 1. GPS Accuracy Check
        accuracy = device_info.get('location_accuracy_meters')
        if accuracy is None or accuracy > 50:
            validations.append({
                'check': 'gps_accuracy',
                'passed': False,
                'message': f'GPS accuracy {accuracy}m exceeds 50m threshold'
            })
            risk_score += 0.3
        else:
            validations.append({
                'check': 'gps_accuracy',
                'passed': True
            })

        # 2. Mock Location Detection (Android)
        is_mock = device_info.get('is_mock_location', False)
        if is_mock:
            validations.append({
                'check': 'mock_location',
                'passed': False,
                'message': 'Mock location detected'
            })
            risk_score += 0.8  # Very suspicious

        # 3. Device Fingerprint Check
        device_id = device_info.get('device_id')
        if device_id:
            # Check if device has history of fraud
            fraud_history = self.check_device_fraud_history(device_id)
            if fraud_history['is_flagged']:
                validations.append({
                    'check': 'device_reputation',
                    'passed': False,
                    'message': 'Device flagged for suspicious activity'
                })
                risk_score += 0.6

        # 4. Velocity Check (impossible travel speed)
        last_checkin = self.get_last_check_in(user_id)
        if last_checkin:
            time_diff = (datetime.utcnow() - last_checkin.checked_in_at).total_seconds()
            distance = calculate_distance(
                coordinates['lat'], coordinates['lng'],
                last_checkin.check_in_lat, last_checkin.check_in_lng
            )

            # Max speed: 1000 km/h (flight speed)
            max_possible_distance = (time_diff / 3600) * 1000 * 1000  # meters

            if distance > max_possible_distance:
                validations.append({
                    'check': 'velocity',
                    'passed': False,
                    'message': f'Impossible travel: {distance}m in {time_diff}s'
                })
                risk_score += 0.9  # Nearly impossible

        # 5. Time-of-day pattern analysis
        hour = datetime.utcnow().hour
        if 2 <= hour <= 5:  # 2-5 AM UTC unusual for events
            risk_score += 0.1

        # 6. IP Address / Network Check
        ip_address = device_info.get('ip_address')
        if ip_address:
            # Check if IP is VPN/proxy/datacenter
            is_vpn = self.check_vpn_ip(ip_address)
            if is_vpn:
                validations.append({
                    'check': 'network',
                    'passed': False,
                    'message': 'VPN/proxy detected'
                })
                risk_score += 0.4

        # Decision logic
        if risk_score >= 0.8:
            decision = 'reject'
            action = 'auto_reject_high_risk'
        elif risk_score >= 0.5:
            decision = 'manual_review'
            action = 'flag_for_review'
        else:
            decision = 'approve'
            action = 'auto_approve'

        return {
            'decision': decision,
            'action': action,
            'risk_score': risk_score,
            'validations': validations,
            'requires_manual_review': risk_score >= 0.5
        }

    def check_device_fraud_history(self, device_id: str) -> Dict:
        """Check device reputation"""
        fraud_count = db.session.query(CheckIn)\
            .filter_by(device_id=device_id)\
            .filter_by(status='disputed')\
            .count()

        return {
            'is_flagged': fraud_count >= 2,
            'fraud_count': fraud_count
        }
```

#### 12.3.2 Clock Skew Handling

```python
def validate_check_in_timing(contract, client_timestamp):
    """
    Handle clock skew between client and server
    """
    server_time = datetime.utcnow()
    client_time = datetime.fromisoformat(client_timestamp)

    # Calculate skew
    skew_seconds = abs((server_time - client_time).total_seconds())

    # Allow up to 5 minutes of clock skew
    MAX_SKEW_SECONDS = 300

    if skew_seconds > MAX_SKEW_SECONDS:
        raise ClockSkewException(
            f"Client clock skew {skew_seconds}s exceeds {MAX_SKEW_SECONDS}s. "
            f"Server: {server_time}, Client: {client_time}"
        )

    # Use server time as authoritative
    return server_time
```

#### 12.3.3 Retry & Backoff Rules

```python
# Client-side retry configuration
CHECK_IN_RETRY_CONFIG = {
    'max_attempts': 3,
    'backoff_multiplier': 2,
    'initial_delay_ms': 1000,
    'max_delay_ms': 10000,
    'retryable_errors': [408, 429, 500, 502, 503, 504]
}

# Server-side idempotency
@app.post("/api/check-ins")
def create_check_in(
    request: CheckInRequest,
    idempotency_key: str = Header(None, alias="Idempotency-Key")
):
    """
    Check-in endpoint with idempotency support
    """
    if not idempotency_key:
        raise ValidationError("Idempotency-Key header required")

    # Check for existing request with same key (24h TTL)
    existing = redis_client.get(f"checkin:idem:{idempotency_key}")
    if existing:
        # Return cached response
        return json.loads(existing)

    # Process check-in
    result = process_check_in(request)

    # Cache result for 24 hours
    redis_client.setex(
        f"checkin:idem:{idempotency_key}",
        86400,  # 24 hours
        json.dumps(result)
    )

    return result
```

### 12.4 Payment State Machine & Idempotency

#### 12.4.1 Complete Payment States

```sql
-- Add comprehensive payment tracking
ALTER TABLE contract_participants ADD COLUMN (
    -- Payment lifecycle
    payment_status ENUM(
        'not_started',      -- Initial state
        'escrow_pending',   -- Awaiting escrow funding
        'escrow_funded',    -- Brand funded escrow
        'escrow_held',      -- Funds held pending completion
        'payout_pending',   -- Completion approved, payout queued
        'payout_processing',-- Payment processor working
        'payout_completed', -- Successfully paid
        'payout_failed',    -- Payment failed (retryable)
        'disputed',         -- Dispute raised
        'refund_pending',   -- Refund requested
        'refund_completed', -- Refunded to brand
        'cancelled'         -- Payment cancelled
    ) DEFAULT 'not_started',

    -- Idempotency
    payment_idempotency_key VARCHAR(64) UNIQUE COMMENT 'Prevent duplicate payouts',
    escrow_idempotency_key VARCHAR(64) UNIQUE COMMENT 'Prevent duplicate escrow',

    -- Tracking
    escrow_transaction_id VARCHAR(255),
    escrow_amount DECIMAL(10,2),
    escrow_funded_at DATETIME,

    payout_transaction_id VARCHAR(255),
    payout_amount DECIMAL(10,2),
    payout_initiated_at DATETIME,
    payout_completed_at DATETIME,
    payout_failed_at DATETIME,
    payout_failure_reason TEXT,
    payout_retry_count INT DEFAULT 0,

    refund_transaction_id VARCHAR(255),
    refund_amount DECIMAL(10,2),
    refund_completed_at DATETIME
);
```

#### 12.4.2 Payment Workflow

**Public Contracts - Pre-fund Strategy:**
```python
def accept_public_contract(contract_id, user_id):
    """
    For public contracts: charge brand on acceptance
    """
    participant = create_participant_atomic(contract_id, user_id)

    # Generate idempotency key
    escrow_key = f"escrow:{contract_id}:{user_id}:{uuid.uuid4()}"

    # Charge brand and hold in escrow
    try:
        escrow_result = payment_service.create_escrow(
            idempotency_key=escrow_key,
            from_company_id=contract.company_id,
            amount=contract.payout_amount,
            currency=contract.payout_currency,
            metadata={
                'contract_id': contract_id,
                'participant_id': participant.id,
                'type': 'contract_escrow'
            }
        )

        participant.payment_status = 'escrow_funded'
        participant.escrow_idempotency_key = escrow_key
        participant.escrow_transaction_id = escrow_result.transaction_id
        participant.escrow_amount = escrow_result.amount
        participant.escrow_funded_at = datetime.utcnow()

        db.session.commit()

    except PaymentException as e:
        # Revert participant acceptance
        participant.status = 'payment_failed'
        participant.payment_failure_reason = str(e)
        db.session.commit()

        # Free up slot
        reconcile_contract_slots(contract_id)

        raise AcceptanceFailedException(
            "Unable to process payment. Please try again."
        )

    return participant
```

**Payout Processing with Idempotency:**
```python
async def process_payout_idempotent(participant_id):
    """
    Process payout with full idempotency guarantees
    """
    participant = db.session.query(ContractParticipant)\
        .with_for_update()\
        .filter_by(id=participant_id)\
        .one()

    # Check if already processed
    if participant.payment_status == 'payout_completed':
        return {
            'status': 'already_processed',
            'transaction_id': participant.payout_transaction_id
        }

    # Generate idempotency key (deterministic)
    payout_key = f"payout:{participant.id}:{participant.contract_id}"

    # Check for in-flight request
    if participant.payment_idempotency_key == payout_key:
        # Already processing
        return {
            'status': 'processing',
            'message': 'Payout already in progress'
        }

    try:
        # Update status
        participant.payment_status = 'payout_processing'
        participant.payment_idempotency_key = payout_key
        participant.payout_initiated_at = datetime.utcnow()
        db.session.commit()

        # Call payment service with idempotency key
        payout_result = await payment_service.create_payout(
            idempotency_key=payout_key,
            to_user_id=participant.user_id,
            amount=participant.contract.payout_amount,
            currency=participant.contract.payout_currency,
            source_transaction_id=participant.escrow_transaction_id,
            metadata={
                'contract_id': participant.contract_id,
                'participant_id': participant.id
            }
        )

        # Success - update record
        participant.payment_status = 'payout_completed'
        participant.payout_transaction_id = payout_result.transaction_id
        participant.payout_amount = payout_result.amount
        participant.payout_completed_at = datetime.utcnow()
        participant.status = 'paid'
        db.session.commit()

        # Send notification
        notify_user_payment_completed(participant)

        return payout_result

    except PaymentProcessingException as e:
        # Retryable error
        participant.payment_status = 'payout_failed'
        participant.payout_failed_at = datetime.utcnow()
        participant.payout_failure_reason = str(e)
        participant.payout_retry_count += 1
        db.session.commit()

        # Schedule retry (exponential backoff)
        if participant.payout_retry_count < 5:
            delay = 2 ** participant.payout_retry_count * 60  # 2, 4, 8, 16, 32 min
            schedule_payout_retry(participant.id, delay_seconds=delay)
        else:
            # Max retries exceeded, alert ops
            alert_payout_failed(participant)

        raise
```

**Webhook Idempotency:**
```python
@app.post("/webhooks/payment")
def payment_webhook(
    event: PaymentWebhookEvent,
    idempotency_key: str = Header(..., alias="X-Idempotency-Key")
):
    """
    Handle payment webhooks with idempotency
    """
    # Check if already processed
    processed = redis_client.get(f"webhook:processed:{idempotency_key}")
    if processed:
        return {"status": "already_processed"}

    # Acquire distributed lock
    lock_key = f"webhook:lock:{idempotency_key}"
    lock = redis_client.lock(lock_key, timeout=30)

    if not lock.acquire(blocking=False):
        # Another instance is processing
        return {"status": "processing"}

    try:
        # Process webhook
        result = process_payment_webhook(event)

        # Mark as processed (TTL 7 days)
        redis_client.setex(
            f"webhook:processed:{idempotency_key}",
            604800,  # 7 days
            json.dumps(result)
        )

        return result

    finally:
        lock.release()
```

### 12.5 Privacy & Compliance

#### 12.5.1 GPS Data Retention Policy

```sql
-- Add retention tracking
ALTER TABLE check_ins ADD COLUMN (
    gps_data_retention_until DATETIME COMMENT 'When to anonymize GPS',
    anonymized BOOLEAN DEFAULT FALSE,
    anonymized_at DATETIME NULL
);

-- Retention policy: 90 days for dispute resolution, then anonymize
CREATE EVENT anonymize_old_gps_data
ON SCHEDULE EVERY 1 DAY
DO
  UPDATE check_ins
  SET check_in_lat = 0,
      check_in_lng = 0,
      check_in_point = ST_GeomFromText('POINT(0 0)', 4326),
      anonymized = TRUE,
      anonymized_at = NOW()
  WHERE checked_in_at < DATE_SUB(NOW(), INTERVAL 90 DAY)
    AND anonymized = FALSE
    AND status NOT IN ('disputed');
```

```python
def create_check_in(data):
    """Set retention timestamp on creation"""
    check_in = CheckIn(**data)

    # GPS data expires after 90 days
    check_in.gps_data_retention_until = datetime.utcnow() + timedelta(days=90)

    db.session.add(check_in)
    db.session.commit()
```

#### 12.5.2 Activity Log Retention

```python
# Retention policies
RETENTION_POLICIES = {
    'activity_log': 365,     # 1 year
    'check_in_photos': 90,   # 90 days
    'gps_coordinates': 90,   # 90 days
    'device_fingerprints': 180,  # 6 months
    'ip_addresses': 90       # 90 days (GDPR requirement)
}

# Scheduled job to purge old data
def purge_expired_data():
    """Daily cleanup job"""
    cutoff_date = datetime.utcnow() - timedelta(days=365)

    # Delete old activity logs
    db.session.query(ContractActivityLog)\
        .filter(ContractActivityLog.created_at < cutoff_date)\
        .delete()

    # Anonymize IP addresses
    ip_cutoff = datetime.utcnow() - timedelta(days=90)
    db.session.query(CheckIn)\
        .filter(CheckIn.checked_in_at < ip_cutoff)\
        .update({'ip_address': '0.0.0.0'})

    db.session.commit()
```

#### 12.5.3 Public Profile Query Protection

```sql
-- Prevent aggregation attacks to deduce earnings
CREATE VIEW user_public_stats AS
SELECT
    user_id,
    COUNT(DISTINCT cp.contract_id) as total_contracts,
    AVG(cp.performance_rating) as avg_rating,
    COUNT(CASE WHEN cp.status = 'paid' THEN 1 END) /
        NULLIF(COUNT(*), 0) as completion_rate,
    -- NO earnings data
    -- NO contract details
    -- NO brand names
    NULL as total_earnings,  -- Always NULL
    NULL as contracts_list   -- Always NULL
FROM contract_participants cp
WHERE cp.status IN ('completed', 'approved', 'paid')
GROUP BY user_id;

-- Query is safe - cannot reverse-engineer earnings
```

```python
def get_public_profile(user_id, requesting_user_id):
    """
    Public profile with privacy controls
    """
    # Prevent own profile exposure
    if user_id == requesting_user_id:
        raise PermissionDenied("Use private stats endpoint for own profile")

    # Get sanitized stats
    stats = db.session.query(UserPublicStats)\
        .filter_by(user_id=user_id)\
        .first()

    return {
        'user_id': user_id,
        'total_completed_contracts': stats.total_contracts,
        'avg_rating': round(stats.avg_rating, 1),  # Round to 1 decimal
        'completion_rate': round(stats.completion_rate, 2),
        # NEVER include:
        # - total_earnings
        # - contract titles
        # - brand names
        # - specific dates
        # - payout amounts
    }
```

### 12.6 Observability & SLOs

#### 12.6.1 Key Metrics & Alerts

```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

# Check-in metrics
checkin_attempts = Counter(
    'checkin_attempts_total',
    'Total check-in attempts',
    ['status', 'contract_type']
)

checkin_geofence_failures = Counter(
    'checkin_geofence_failures_total',
    'Check-ins rejected for geofence violation',
    ['reason']
)

checkin_fraud_score = Histogram(
    'checkin_fraud_score',
    'Distribution of fraud risk scores',
    buckets=[0, 0.2, 0.4, 0.6, 0.8, 1.0]
)

# Slot contention
slot_acceptance_duration = Histogram(
    'slot_acceptance_duration_seconds',
    'Time to accept contract slot',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

slot_contention_retries = Counter(
    'slot_contention_retries_total',
    'Optimistic lock retry attempts'
)

# Payment metrics
payment_payout_status = Counter(
    'payment_payout_status_total',
    'Payout outcomes',
    ['status']  # completed, failed, retrying
)

payment_webhook_latency = Histogram(
    'payment_webhook_latency_seconds',
    'Webhook processing time',
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0]
)

payment_failures = Counter(
    'payment_failures_total',
    'Payment failures',
    ['reason', 'retryable']
)
```

#### 12.6.2 Service Level Objectives (SLOs)

```yaml
# SLO definitions
slos:
  check_in_success_rate:
    target: 99.5%
    description: "Check-ins succeed when user is within geofence"
    measurement: checkin_attempts{status='success'} / checkin_attempts_total
    alert_threshold: 99.0%

  geofence_validation_accuracy:
    target: 99.9%
    description: "Geofence calculations are accurate"
    measurement: Manual audit of disputed check-ins
    alert_threshold: 99.5%

  slot_acceptance_latency:
    target: p95 < 1s
    description: "Slot acceptance completes within 1 second (95th percentile)"
    measurement: slot_acceptance_duration_seconds
    alert_threshold: p95 > 2s

  payment_success_rate:
    target: 99.9%
    description: "Payouts complete successfully"
    measurement: payment_payout_status{status='completed'} / payment_payout_status_total
    alert_threshold: 99.5%

  webhook_processing_time:
    target: p99 < 5s
    description: "Payment webhooks processed within 5 seconds"
    measurement: payment_webhook_latency_seconds
    alert_threshold: p99 > 10s
```

#### 12.6.3 Dashboards

```python
# Grafana dashboard configuration
GRAFANA_DASHBOARDS = {
    'contract_workflow_overview': {
        'panels': [
            {
                'title': 'Check-in Success Rate (24h)',
                'query': 'rate(checkin_attempts{status="success"}[24h]) / rate(checkin_attempts_total[24h])',
                'target': 0.995
            },
            {
                'title': 'Geofence Failures by Reason',
                'query': 'sum by (reason) (rate(checkin_geofence_failures_total[1h]))',
                'type': 'pie_chart'
            },
            {
                'title': 'Slot Contention Errors',
                'query': 'rate(slot_contention_retries_total[5m])',
                'alert': 'value > 10'
            },
            {
                'title': 'Payment Processing Status',
                'query': 'sum by (status) (rate(payment_payout_status_total[1h]))',
                'type': 'stacked_bar'
            },
            {
                'title': 'Webhook Latency p95',
                'query': 'histogram_quantile(0.95, payment_webhook_latency_seconds)',
                'target': 5.0
            }
        ]
    },

    'fraud_detection': {
        'panels': [
            {
                'title': 'Fraud Risk Score Distribution',
                'query': 'histogram_quantile(0.50, checkin_fraud_score)',
            },
            {
                'title': 'Mock Location Detections',
                'query': 'sum(rate(checkin_geofence_failures{reason="mock_location"}[1h]))'
            },
            {
                'title': 'Velocity Check Failures',
                'query': 'sum(rate(checkin_geofence_failures{reason="velocity"}[1h]))'
            }
        ]
    }
}
```

### 12.7 API Hardening

#### 12.7.1 Rate Limiting

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",
    strategy="fixed-window"
)

# Endpoint-specific rate limits
RATE_LIMITS = {
    'contract_create': "10 per hour",      # Prevent spam contracts
    'contract_accept': "20 per minute",    # Allow browsing but limit accepts
    'check_in_create': "5 per minute",     # Prevent check-in spam
    'check_in_validate': "30 per minute",  # Allow location checks
    'payment_webhook': "1000 per minute",  # High throughput for webhooks
    'public_search': "100 per minute",     # Generous for discovery
    'private_dashboard': "300 per minute"  # High limit for own data
}

@app.post("/api/contracts")
@limiter.limit(RATE_LIMITS['contract_create'])
def create_contract():
    pass

@app.post("/api/contracts/<id>/accept")
@limiter.limit(RATE_LIMITS['contract_accept'])
def accept_contract(id):
    pass

@app.post("/api/check-ins")
@limiter.limit(RATE_LIMITS['check_in_create'])
def create_check_in():
    pass
```

#### 12.7.2 Pagination Standards

```python
# Global pagination defaults
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

def paginate_query(query, page=1, per_page=DEFAULT_PAGE_SIZE):
    """Standard pagination"""
    per_page = min(per_page, MAX_PAGE_SIZE)  # Enforce maximum

    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    return {
        'items': [item.to_dict() for item in pagination.items],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total_items': pagination.total,
            'total_pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev,
            'next_page': page + 1 if pagination.has_next else None,
            'prev_page': page - 1 if pagination.has_prev else None
        }
    }

@app.get("/api/contracts")
def list_contracts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    query = db.session.query(Contract).filter_by(status='active')
    return paginate_query(query, page, per_page)
```

#### 12.7.3 Error Codes & Response Standards

```python
# Standardized error codes
ERROR_CODES = {
    # Authentication & Authorization (1xxx)
    1001: "UNAUTHORIZED",
    1002: "FORBIDDEN_RESOURCE",
    1003: "INVALID_TOKEN",
    1004: "TOKEN_EXPIRED",

    # Validation Errors (2xxx)
    2001: "INVALID_INPUT",
    2002: "MISSING_REQUIRED_FIELD",
    2003: "INVALID_COORDINATES",
    2004: "INVALID_DATE_RANGE",

    # Business Logic Errors (3xxx)
    3001: "SLOTS_FILLED",
    3002: "ALREADY_ACCEPTED",
    3003: "CONTRACT_EXPIRED",
    3004: "OUTSIDE_GEOFENCE",
    3005: "OUTSIDE_TIME_WINDOW",
    3006: "INSUFFICIENT_DURATION",
    3007: "MOCK_LOCATION_DETECTED",
    3008: "HIGH_FRAUD_RISK",

    # Payment Errors (4xxx)
    4001: "PAYMENT_FAILED",
    4002: "INSUFFICIENT_FUNDS",
    4003: "PAYOUT_PENDING",
    4004: "ALREADY_PAID",

    # System Errors (5xxx)
    5001: "DATABASE_ERROR",
    5002: "EXTERNAL_SERVICE_ERROR",
    5003: "RATE_LIMIT_EXCEEDED",
    5004: "CONCURRENCY_ERROR"
}

class APIError(Exception):
    def __init__(self, code, message, details=None, http_status=400):
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status

@app.errorhandler(APIError)
def handle_api_error(error):
    return jsonify({
        'error': {
            'code': error.code,
            'error_code': ERROR_CODES.get(error.code, "UNKNOWN_ERROR"),
            'message': error.message,
            'details': error.details
        }
    }), error.http_status

# Usage
@app.post("/api/contracts/<id>/accept")
def accept_contract(id):
    if contract.filled_slots >= contract.total_slots:
        raise APIError(
            code=3001,
            message="All slots for this contract are filled",
            details={'contract_id': id, 'total_slots': contract.total_slots},
            http_status=409
        )
```

#### 12.7.4 Authentication & Authorization Matrix

```python
# Role-based access control per endpoint
AUTHORIZATION_MATRIX = {
    # Contract Management
    'POST /api/contracts': ['brand', 'admin'],
    'GET /api/contracts/:id': ['any'],  # Public info
    'PUT /api/contracts/:id': ['brand:owner', 'admin'],
    'DELETE /api/contracts/:id': ['brand:owner', 'admin'],

    # Participation
    'POST /api/contracts/:id/accept': ['athlete', 'influencer'],
    'GET /api/users/:user_id/contracts': ['user:self', 'admin'],

    # Check-ins
    'POST /api/check-ins': ['athlete', 'influencer'],
    'GET /api/check-ins/:id': ['user:owner', 'brand:contract_owner', 'admin'],

    # Approval
    'PUT /api/contract-participants/:id/approve': ['brand:contract_owner', 'admin'],

    # Payments
    'POST /api/payments/process': ['system', 'admin'],
    'GET /api/contract-participants/:id/payment': ['user:owner', 'brand:contract_owner', 'admin'],

    # Analytics
    'GET /api/users/:user_id/stats': ['user:self', 'admin'],  # Private
    'GET /api/users/:user_id/public-stats': ['any'],          # Public
}

def check_authorization(endpoint, user, resource=None):
    """
    Check if user is authorized for endpoint
    """
    required_roles = AUTHORIZATION_MATRIX.get(endpoint, [])

    for role_spec in required_roles:
        if ':' in role_spec:
            # Conditional role (e.g., 'user:self', 'brand:owner')
            role, condition = role_spec.split(':')

            if user.role != role:
                continue

            if condition == 'self' and resource.user_id == user.id:
                return True
            elif condition == 'owner' and resource.created_by_user_id == user.id:
                return True
            elif condition == 'contract_owner' and resource.contract.company_id == user.company_id:
                return True
        else:
            # Simple role check
            if role_spec == 'any' or user.role == role_spec:
                return True

    raise APIError(
        code=1002,
        message="You do not have permission to access this resource",
        http_status=403
    )
```

## 13. Conclusion

This contract workflow system enables the core value proposition of NILBx: connecting brands with athletes/influencers for location-based promotional opportunities. The geo-fencing via check-in service ensures accountability, while the privacy-focused UI/UX protects user earnings and relationships. The system balances brand control (approval workflows) with user autonomy (public marketplace), creating a win-win platform for all parties.

**Production Readiness Checklist:**
- ✅ Geospatial indexing with MySQL POINT types
- ✅ Timezone-aware datetime handling (UTC storage, local display)
- ✅ Race condition protection with optimistic locking
- ✅ Complete state machines for contracts and payments
- ✅ GPS spoofing detection (6-layer validation)
- ✅ Payment idempotency (escrow, payout, webhooks)
- ✅ Data retention and privacy compliance (GDPR-ready)
- ✅ Comprehensive observability (metrics, SLOs, dashboards)
- ✅ API hardening (rate limits, pagination, error codes, RBAC)

**Next Steps:**
1. Review and approve this hardened plan
2. Create database migrations with production schema
3. Implement API with full error handling
4. Set up monitoring and alerting
5. Security audit and penetration testing
6. Load testing (slot contention, concurrent check-ins)
7. Beta testing with real users

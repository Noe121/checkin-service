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

## 12. Conclusion

This contract workflow system enables the core value proposition of NILBx: connecting brands with athletes/influencers for location-based promotional opportunities. The geo-fencing via check-in service ensures accountability, while the privacy-focused UI/UX protects user earnings and relationships. The system balances brand control (approval workflows) with user autonomy (public marketplace), creating a win-win platform for all parties.

**Next Steps:**
1. Review and approve this plan
2. Create database migrations
3. Begin API implementation
4. Parallel frontend development
5. Beta testing with real users

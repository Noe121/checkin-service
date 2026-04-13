# Check-in Service

FastAPI microservice for events, RSVPs, QR / NFC / geofence check-ins, and event invitations. Multi-tenant via `school_id`, with PII-hashed audit trail and HMAC-signed QR tokens. Connects to `nilbx_db` (NOT a separate `checkin_db`).

## 🚀 Phase 10 features (Apr 2026)

- **Non-fan event creators** — creators / brands / agencies / coaches / school admins / governing-body roles can all author events. Fans and guardians cannot. Event ownership flows to the caller via `events.owner_user_id`.
- **4-tier visibility** —
  - `public` — anyone signed in can discover + RSVP
  - `school_only` — only authors with a real school binding can create; only same-school users can discover + RSVP
  - `unlisted` — not in discover, but anyone with the link can RSVP
  - `invite_only` — RSVP requires an accepted `event_invitations` row
- **Event invitations** — organizer batch-sends invites; invitee accepts / declines via /me/invitations; idempotent on `(event_id, invitee_user_id)`.
- **Phone-to-phone NFC tap** — explicit per-event `allow_nfc_checkin` opt-in; the existing /checkin endpoint accepts `checkin_method: "nfc"` once enabled. iOS CoreNFC reader / Android NfcAdapter HCE land in Phase 10.B.
- **Public discovery feed** — `GET /api/checkin/events/discover` returns public + same-school events, paginated, with `event_type` filter. PII guard: omits raw lat/lon and owner_user_id.
- **Owner-or-admin gate** — PATCH/DELETE event accepts the original organizer OR a same-school admin. Cross-tenant non-owners get 404 (existence-leak guard).

## 🚀 Inherited Phase 2 features

- **Capacity + waitlist** — `events.max_capacity` enforced on POST /register; overflow → `status='waitlisted'` with `waitlist_position`
- **Idempotency-Key** — replay-safe POST /events + POST /register via per-tenant unique constraints
- **HMAC-signed QR tokens** — two-phase verify (peek → geofence → consume) so a single-use token is NEVER burned by a failed geofence check. Token mint via POST /events/{id}/qr-tokens (admin only)
- **Geofence verification** — Haversine distance with bounds checks; raw lat/lon NEVER persisted (rounded to ~100m + HMAC-hashed before write)
- **PII hashing** — every API response with attendee data uses SHA-256[:8] hashed user IDs; raw IDs only echoed to admin-bypass roles
- **Cross-tenant 404** — never 403; existence is never leaked to other schools
- **CSRF middleware** — cookie-authed mutations require X-CSRF-Token (bearer-only callers bypass)

## 🏗️ Architecture

### Service Overview
- **Framework**: FastAPI with async support
- **Database**: MySQL 8.0 with InnoDB engine
- **Port**: 8006 (internal and container)
- **Health Checks**: Integrated with feature flag service
- **Containerized**: Docker with multi-stage builds

### Data flow

  Owner POST /events                       (creator/brand/coach/admin)
       └→ event row in `events`
  Owner POST /events/{id}/invitations      (optional, invite_only events)
       └→ rows in `event_invitations`
  Invitee POST /events/{id}/invitations/{iid}/respond
       └→ status flips to accepted/declined
  Attendee POST /events/{id}/register      (RSVP)
       └→ row in `event_registrations`, capacity → waitlist
  Attendee POST /events/{id}/checkin       (manual / qr / geo / qr_geo / nfc)
       └→ row in `event_checkins`, lat/lon hashed to ~100m
       └→ registration.status flipped to attended

### Phase 10 API surface

  POST   /api/checkin/events                              (event_creator)
  GET    /api/checkin/events                              (admin only)
  GET    /api/checkin/events/discover                     (any bearer)
  GET    /api/checkin/events/{id}                         (admin only)
  PATCH  /api/checkin/events/{id}                         (owner-or-admin)
  DELETE /api/checkin/events/{id}                         (owner-or-admin)
  POST   /api/checkin/events/{id}/qr-tokens               (admin only)
  GET    /api/checkin/events/{id}/qr-tokens               (admin only)
  POST   /api/checkin/events/{id}/register                (any bearer + visibility gate)
  GET    /api/checkin/events/{id}/registrations           (admin only)
  DELETE /api/checkin/events/{id}/registrations/{uid}     (self-or-admin)
  POST   /api/checkin/events/{id}/checkin                 (self-or-admin + nfc opt-in)
  POST   /api/checkin/events/{id}/invitations             (owner-or-admin)
  GET    /api/checkin/events/{id}/invitations             (owner-or-admin)
  POST   /api/checkin/events/{id}/invitations/{iid}/respond  (invitee only)
  GET    /api/checkin/me/invitations                      (any bearer; own rows only)

## 📡 API Endpoints

### Core Endpoints

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "checkin-service",
  "feature_flags": {
    "geo_checkins": true,
    "social_verification": true,
    "auto_payout": true
  },
  "timestamp": "2025-10-23T10:30:00Z"
}
```

#### `POST /checkins`
Create a new check-in with geo-fence verification.

**Request:**
```json
{
  "deal_id": 1,
  "athlete_id": 456,
  "location": {
    "lat": 40.712776,
    "lng": -74.005974
  }
}
```

**Response:**
```json
{
  "id": 123,
  "geo_verified": true,
  "distance_meters": 25,
  "payout": 500,
  "status": "pending",
  "message": "Geo-verified! Post on social media to complete check-in."
}
```

#### `POST /checkins/{checkin_id}/social-verify`
Complete check-in with social media verification.

**Request:**
```json
{
  "social_url": "https://twitter.com/user/status/123?text=@nilbx+hotspot"
}
```

**Response:**
```json
{
  "verified": true,
  "status": "verified",
  "auto_payout_triggered": true
}
```

### Geo-fence Management

#### `POST /geo-fences`
Create a new geo-fence for a hotspot.

**Request:**
```json
{
  "hotspot_name": "Starbucks Downtown",
  "deal_id": 1,
  "lat_center": 40.712776,
  "lng_center": -74.005974,
  "radius_meters": 100,
  "address": "123 Main St, New York, NY"
}
```

#### `GET /geo-fences/{deal_id}`
Get all geo-fences for a specific deal.

**Response:**
```json
{
  "geo_fences": [
    {
      "id": 1,
      "hotspot_name": "Starbucks Downtown",
      "deal_id": 1,
      "lat_center": 40.712776,
      "lng_center": -74.005974,
      "radius_meters": 100,
      "address": "123 Main St, New York, NY",
      "active": true
    }
  ]
}
```

## 🗄️ Database Schema

### Tables

#### `checkins`
```sql
CREATE TABLE checkins (
    id INT PRIMARY KEY AUTO_INCREMENT,
    deal_id INT NOT NULL,
    athlete_id INT NOT NULL,
    location_lat DECIMAL(10, 8),
    location_lng DECIMAL(11, 8),
    geo_verified BOOLEAN DEFAULT FALSE,
    social_post_url VARCHAR(500),
    social_verified BOOLEAN DEFAULT FALSE,
    photo_url VARCHAR(500),
    status ENUM('pending', 'verified', 'rejected') DEFAULT 'pending',
    checkin_time DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE CASCADE,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id) ON DELETE CASCADE,

    INDEX idx_deal_id (deal_id),
    INDEX idx_athlete_id (athlete_id),
    INDEX idx_status (status),
    INDEX idx_checkin_time (checkin_time)
);
```

#### `geo_fences`
```sql
CREATE TABLE geo_fences (
    id INT PRIMARY KEY AUTO_INCREMENT,
    hotspot_name VARCHAR(255) NOT NULL,
    deal_id INT,
    lat_center DECIMAL(10, 8) NOT NULL,
    lng_center DECIMAL(11, 8) NOT NULL,
    radius_meters INT NOT NULL DEFAULT 100,
    address VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE SET NULL,

    INDEX idx_hotspot_name (hotspot_name),
    INDEX idx_active (active)
);
```

## 🚀 Setup and Installation

### Prerequisites
- Python 3.11+
- MySQL 8.4+
- Docker & Docker Compose (for containerized setup)

### Local Development Setup (service-isolated DB)

1. **Clone and navigate:**
   ```bash
   cd checkin-service
   ```

2. **Run via Docker Compose (recommended):**
   ```bash
   docker-compose -f docker-compose.per-service.yml up --build
   ```
   - MySQL 8.4 starts with `checkin_db` on host port `3307`, seeded by `migrations/0001_init_checkin_schema.sql`.
   - Service starts on `http://localhost:8006` after DB health passes.
   - Health check: `curl http://localhost:8006/health`

3. **Manual venv (optional):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   export DB_HOST=localhost DB_PORT=3307 DB_NAME=checkin_db DB_USER=checkin_user DB_PASSWORD=checkin_pass
   uvicorn main:app --reload --host 0.0.0.0 --port 8006
   ```

### Docker Setup

1. **Build and run with Docker Compose:**
   ```bash
   docker-compose up --build
   ```

2. **Access the service:**
   - API: http://localhost:8006
   - MySQL: localhost:3307

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DB_HOST` | MySQL host | `checkin-db` (docker) / `localhost` | Yes |
| `DB_PORT` | MySQL port | `3306` (in container) / `3307` (host) | Yes |
| `DB_NAME` | Database name | `checkin_db` | Yes |
| `DB_USER` | Database user | `checkin_user` | Yes |
| `DB_PASSWORD` | Database password | `checkin_pass` | Yes |
| `GOOGLE_MAPS_API_KEY` | Google Maps API key | - | No |
| `TWITTER_API_KEY` | Twitter API key | - | No |
| `FEATURE_FLAG_URL` | Feature flag service URL | `http://localhost:8004` | No |

### Feature Flags

The service integrates with a feature flag service to enable/disable features:

- `geo_checkins`: Enable/disable GPS-based check-ins
- `social_verification`: Enable/disable social media verification
- `auto_payout`: Enable/disable automatic payout processing

## 🧪 Testing

### Run Tests

```bash
# Run all tests
./run_tests.sh

# Or run directly with pytest
python -m pytest tests/ -v
```

### Test Coverage

The test suite includes:
- ✅ Health check endpoint testing
- ✅ Geo-fence verification logic
- ✅ Social media URL validation
- ✅ Database integration tests
- ✅ Error handling scenarios
- ✅ Haversine distance calculations

### Test Structure

```
tests/
├── test_checkin_service.py    # Main test suite
└── __pycache__/
```

## 🚢 Deployment

### Container Deployment

The service is designed to run in Docker containers with the following configuration:

- **Base Image**: `python:3.11-slim`
- **Port Mapping**: `8006:8006` (external:internal)
- **Health Checks**: Integrated with container orchestration
- **Database Dependencies**: Requires MySQL service

### Kubernetes Deployment

For production deployment, use the provided ECS Fargate configuration in the main NILbx infrastructure.

### CI/CD Integration

The service integrates with Jenkins for automated:
- Container building and ECR push
- ECS deployment updates
- Database migrations
- Health checks and rollbacks

## 🔧 Development

### Code Structure

```
checkin-service/
├── src/
│   └── main.py              # FastAPI application
├── tests/
│   └── test_checkin_service.py
├── Dockerfile               # Container definition
├── docker-compose.yml       # Local development setup
├── requirements.txt         # Python dependencies
├── init_checkin_db.sql      # Database schema
├── run_tests.sh            # Test runner script
└── README.md               # This file
```

### Key Components

- **main.py**: Core FastAPI application with all endpoints
- **Database Models**: Check-in and geo-fence data structures
- **Haversine Algorithm**: GPS distance calculations
- **Social Verification**: URL pattern matching for social proof
- **Feature Flags**: Dynamic feature toggling

### Adding New Features

1. **Database Changes**: Update `init_checkin_db.sql`
2. **API Endpoints**: Add to `main.py` with proper validation
3. **Tests**: Add comprehensive test cases
4. **Documentation**: Update this README

### Code Quality

- **Type Hints**: Full type annotation support
- **Linting**: Pylance integration for static analysis
- **Testing**: 100% test coverage target
- **Documentation**: OpenAPI/Swagger auto-generation

## 🤝 Integration

### Service Dependencies

- **MySQL Database**: Shared `nilbx_db` with other services
- **Feature Flag Service**: Dynamic configuration management
- **Payment Service**: Automatic payout processing
- **ALB**: Request routing and authentication (fronted by CloudFront)

### ALB / Edge Configuration

The service is configured behind the ALB (via CloudFront) with:
- **Path**: `/checkin`
- **Authentication**: JWT token validation
- **Rate Limiting**: Handled at ALB/WAF layer
- **CORS**: Single layer (ALB)

## 📊 Monitoring

### Health Checks

- **Endpoint**: `GET /health`
- **Metrics**: Response time, error rates, feature flag status
- **Dependencies**: Database connectivity, external service health

### Logging

- **Format**: Structured JSON logging
- **Levels**: INFO, WARNING, ERROR
- **Integration**: AWS CloudWatch for containerized deployments

## 🐛 Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Check MySQL service is running
   - Verify connection credentials
   - Ensure database exists

2. **Geo-fence Not Found**
   - Verify deal has active geo-fences
   - Check coordinate accuracy
   - Review radius settings

3. **Social Verification Failed**
   - Check URL format and platform support
   - Verify @nilbx tag presence
   - Review API key configuration

### Debug Mode

Enable debug logging:
```bash
export PYTHONPATH=/app
uvicorn main:app --reload --log-level debug
```

## 📝 License

This service is part of the NILbx platform. See main project license for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

For questions or issues, please contact the development team.

# Check-in Service

A FastAPI-based microservice for geo-fencing and social verification check-ins in the NILbx platform. This service enables users to check into sponsored deals at physical locations with GPS verification and social media proof-of-visit.

## 🚀 Features

- **Geo-fencing Check-ins**: GPS-based location verification for sponsored deals
- **Social Media Verification**: Instagram/Twitter post validation for proof-of-visit
- **Real-time Payouts**: Automatic payment processing for verified check-ins
- **Hotspot Management**: Dynamic geo-fence creation and management
- **Feature Flags**: Configurable feature toggles via external service
- **Health Monitoring**: Comprehensive health checks and metrics
- **Database Integration**: MySQL integration with the main NILbx database

## 🏗️ Architecture

### Service Overview
- **Framework**: FastAPI with async support
- **Database**: MySQL 8.0 with InnoDB engine
- **Port**: 8006 (internal and container)
- **Health Checks**: Integrated with feature flag service
- **Containerized**: Docker with multi-stage builds

### Data Flow
1. **Check-in Creation**: Athlete submits location + deal ID
2. **Geo Verification**: Haversine distance calculation against geo-fences
3. **Social Proof**: URL validation for social media posts
4. **Payout Trigger**: Automatic payment processing for verified check-ins

## 📡 API Endpoints

### Core Endpoints

#### `GET /health`
Health check endpoint with feature flag status.

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
- MySQL 8.0+
- Docker & Docker Compose (for containerized setup)

### Local Development Setup

1. **Clone and navigate:**
   ```bash
   cd checkin-service
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   export DB_HOST=localhost
   export DB_PORT=3306
   export DB_NAME=nilbx_db
   export DB_USER=root
   export DB_PASSWORD=rootpassword
   export GOOGLE_MAPS_API_KEY=your_api_key
   export TWITTER_API_KEY=your_api_key
   export FEATURE_FLAG_URL=http://localhost:8004
   ```

5. **Run the service:**
   ```bash
   cd src
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
| `DB_HOST` | MySQL host | `localhost` | Yes |
| `DB_PORT` | MySQL port | `3306` | Yes |
| `DB_NAME` | Database name | `nilbx_db` | Yes |
| `DB_USER` | Database user | `root` | Yes |
| `DB_PASSWORD` | Database password | `rootpassword` | Yes |
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
- **API Gateway**: Request routing and authentication

### API Gateway Configuration

The service is configured behind an API Gateway with:
- **Base Path**: `/checkin`
- **Authentication**: JWT token validation
- **Rate Limiting**: 1000 requests/minute burst
- **CORS**: Cross-origin request support

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

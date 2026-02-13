# Database Schema Migration

## ⚠️ Schema Moved to Centralized Management

All database schemas for NILbx are now managed centrally in:

```
NILbx-env/modules/db/mysql/migrations/
```

### Checkin & Admin Database Schema Location

The checkin and admin tables are part of notifications_db:
```
NILbx-env/modules/db/mysql/migrations/notifications_db/V001__initial_schema.sql
```

Tables included:
- `checkins` - Check-in records for geofencing
- `geo_fences` - Geofence definitions
- `admin_audit_log` - Admin action audit trail
- `system_alerts` - System alerts and monitoring
- `report_schedules` - Scheduled report configurations
- `dashboard_metrics` - Dashboard metric tracking

### For Local Development

To run checkin-service with the centralized schema:

```bash
# Option 1: Set environment variable
export NILBX_SCHEMA_PATH=../NILbx-env/modules/db/mysql/migrations/notifications_db/V001__initial_schema.sql
docker-compose up

# Option 2: Use centralized database
cd ../NILbx-env
./scripts/migrate.sh --environment dev notifications_db
```

### Running Migrations

```bash
cd NILbx-env
./scripts/migrate.sh --environment <env> notifications_db
```

For more information, see:
- `NILbx-env/modules/db/mysql/migrations/README.md`
- `NILbx-env/MIGRATION_VALIDATION_REPORT.md`

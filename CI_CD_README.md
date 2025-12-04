# Check-in Service CI/CD Documentation

This document describes the CI/CD pipeline configurations for the check-in service across multiple platforms.

## Overview

The check-in service supports CI/CD pipelines on:
- **Jenkins** - Self-hosted CI/CD
- **GitHub Actions** - GitHub native CI/CD
- **GitLab CI** - GitLab native CI/CD
- **AWS CodePipeline/CodeBuild** - AWS native CI/CD

All pipelines follow the same workflow:
1. **Test** - Run unit tests
2. **Build** - Build Docker image
3. **Smoke Test** - Run smoke tests against running service
4. **Deploy** - Deploy to development/production environments

## Pipeline Files

| Platform | File | Description |
|----------|------|-------------|
| Jenkins | `Jenkinsfile` | Jenkins declarative pipeline |
| GitHub Actions | `.github/workflows/ci-cd.yml` | GitHub Actions workflow |
| GitLab CI | `.gitlab-ci.yml` | GitLab CI configuration |
| AWS CodeBuild | `buildspec.yml` | AWS CodeBuild build specification |

## Common Pipeline Stages

### 1. Test Stage
- Sets up Python 3.11 environment
- Installs dependencies from `requirements.txt`
- Runs MySQL database in container
- Executes unit tests via `run_tests.sh`
- Generates JUnit test reports

### 2. Build Stage
- Builds Docker image
- Tags image with:
  - Commit SHA
  - Branch name
  - `latest` (for main branch only)

### 3. Smoke Test Stage
- Starts service and database containers
- Waits for service to be ready
- Runs `smoke_checkin.sh` script
- Tests `/health` and `/db-health` endpoints
- Fails fast on any non-200 response

### 4. Deploy Stage
- **Development**: Auto-deploys on `develop` branch
- **Production**: Auto-deploys on `main` branch (with approval for some platforms)
- Pushes image to ECR
- Updates ECS service with new image
- Waits for deployment to stabilize

## Platform-Specific Setup

### Jenkins

**Prerequisites:**
- Jenkins with Docker support
- AWS CLI installed
- Required plugins: Docker Pipeline, AWS Steps

**Required Credentials:**
- `ecr-registry-url` - ECR registry URL
- `db-password` - Database password
- `aws-credentials` - AWS access credentials

**Configuration:**
```groovy
// Jenkinsfile is configured for:
// - Docker builds
// - ECS deployments
// - Manual approval for production
```

**Usage:**
1. Create new Pipeline job in Jenkins
2. Point to repository with Jenkinsfile
3. Configure credentials in Jenkins
4. Run pipeline

### GitHub Actions

**Prerequisites:**
- GitHub repository
- AWS account with ECR and ECS

**Required Secrets:**
Configure in repository Settings → Secrets and variables → Actions:
- `AWS_ACCESS_KEY_ID` - AWS access key
- `AWS_SECRET_ACCESS_KEY` - AWS secret key

**Environment Configuration:**
- `development` environment for dev deployments
- `production` environment for prod deployments (with approval)

**Workflow Features:**
- Runs on push to `main`/`develop` and pull requests
- MySQL service container for tests
- Parallel job execution
- Automatic ECR login
- ECS deployment with stability wait

**Manual Approval:**
Production deploys require manual approval via GitHub Environments.

### GitLab CI

**Prerequisites:**
- GitLab repository
- GitLab Runner with Docker executor
- AWS account

**Required Variables:**
Configure in Settings → CI/CD → Variables:
- `AWS_ACCESS_KEY_ID` - AWS access key
- `AWS_SECRET_ACCESS_KEY` - AWS secret key
- `ECR_REGISTRY` - ECR registry URL
- `CI_REGISTRY` - GitLab container registry (auto-set)
- `CI_REGISTRY_USER` - GitLab registry user (auto-set)
- `CI_REGISTRY_PASSWORD` - GitLab registry password (auto-set)

**Environment Configuration:**
- `development` - Auto-deploy from `develop` branch
- `production` - Manual deploy from `main` branch

**Pipeline Features:**
- Multi-stage pipeline with dependencies
- Extends base configurations for DRY
- MySQL service integration
- Artifact and report handling
- Manual production deployment

### AWS CodePipeline/CodeBuild

**Prerequisites:**
- AWS CodePipeline
- AWS CodeBuild project
- ECR repository
- ECS cluster and service

**Required Parameters:**
Configure in Systems Manager Parameter Store:
- `/nilbx/db/password` - Database password

Configure in Secrets Manager:
- `nilbx/aws:account_id` - AWS account ID

**Environment Variables:**
Set in CodeBuild project:
- `AWS_REGION` - AWS region (default: us-east-1)
- `ECR_REPOSITORY` - ECR repository name
- `ECS_SERVICE` - ECS service name

**Pipeline Setup:**
1. Create CodeBuild project using `buildspec.yml`
2. Create CodePipeline with stages:
   - Source (GitHub/CodeCommit)
   - Build (CodeBuild)
   - Deploy (ECS)
3. Configure IAM roles with necessary permissions

**Buildspec Features:**
- Uses parameter store and secrets manager
- Caches pip dependencies
- Generates imagedefinitions.json for ECS
- JUnit test reporting
- Artifact management

## Smoke Tests

All pipelines run the `smoke_checkin.sh` script to verify service health.

**Tests Performed:**
- `GET /health` - Basic service availability
- `GET /db-health` - Database connectivity

**Configuration:**
```bash
BASE_URL=http://localhost:8006 ./smoke_checkin.sh
```

**Exit Codes:**
- `0` - All tests passed
- `1` - At least one test failed

## Environment Variables

All pipelines use consistent environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `3306` |
| `DB_USER` | Database user | `root` |
| `DB_PASSWORD` | Database password | (from secrets) |
| `DB_NAME` | Database name | `nilbx_db` |
| `AWS_REGION` | AWS region | `us-east-1` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Deployment Strategy

### Branch Strategy
- `develop` → Development environment
- `main` → Production environment
- Pull requests → Test only (no deploy)

### Rollback
If deployment fails or issues are detected:

**ECS Rollback:**
```bash
# Revert to previous task definition
aws ecs update-service \
  --cluster <cluster-name> \
  --service checkin-service \
  --task-definition checkin-service:<previous-revision>
```

**Docker Image Rollback:**
```bash
# Use previous image tag
docker pull <ecr-registry>/checkin-service:<previous-tag>
```

## Monitoring

After deployment, monitor:
- ECS service health
- CloudWatch logs for errors
- Application metrics
- Smoke test endpoints

**Quick Health Check:**
```bash
curl https://dev.nilbx.com/health
curl https://dev.nilbx.com/db-health
```

## Troubleshooting

### Tests Failing
- Check database connectivity
- Verify environment variables
- Review test logs in artifacts

### Build Failing
- Verify Docker daemon is running
- Check disk space
- Review build logs

### Smoke Tests Failing
- Ensure service has time to start (increase sleep time)
- Check database container health
- Verify port mappings
- Review service logs

### Deployment Failing
- Verify AWS credentials
- Check ECS service exists
- Review task definition
- Ensure ECR image exists

## Best Practices

1. **Always run smoke tests** before deploying
2. **Use tagged images** instead of `latest` for production
3. **Monitor deployments** until stable
4. **Keep secrets secure** using platform-specific secret management
5. **Test locally** before pushing to CI/CD
6. **Review logs** for any warnings or errors

## Local Testing

Test the smoke test script locally:

```bash
# Start local environment
docker-compose up -d

# Wait for services
sleep 10

# Run smoke tests
./smoke_checkin.sh

# Cleanup
docker-compose down
```

## Contributing

When modifying CI/CD pipelines:
1. Test changes in a feature branch first
2. Update this documentation
3. Verify all platforms still work
4. Get approval before merging to main

## Support

For CI/CD issues:
- Check platform-specific logs
- Review this documentation
- Contact DevOps team

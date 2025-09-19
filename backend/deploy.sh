# deploy.sh
#!/bin/bash
set -e

echo "🚀 Deploying TimeTracker Pro..."

# Pull latest code
git pull origin main

# Build Docker images
docker-compose build

# Run database migrations
docker-compose run --rm app alembic upgrade head

# Restart services with zero downtime
docker-compose up -d --no-deps app

# Clean up old images
docker image prune -f

echo "✅ Deployment complete!"

# Run health checks
sleep 10
curl -f http://localhost:8000/health || exit 1

echo "🎉 TimeTracker Pro is running successfully!"

## Database Migration (alembic.ini)
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = driver://user:pass@localhost/dbname

## Health Check Endpoint (add to main.py)
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "database": "connected",
        "redis": "connected"
    }
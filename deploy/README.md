# Deployment

The production compose example separates the schema migration job from the
long-running API container:

```bash
cp production.env.example .env.production
# Fill secrets and create keys/private.pem + keys/public.pem.
docker compose -f deploy/docker-compose.production.yml up --build
```

Set `PG_HOST` to a PostgreSQL host reachable from the Compose network. The
example does not bundle a database because production should use a separately
managed database.

The `migrate` service runs once. The API starts in production mode through
Gunicorn with Uvicorn workers and exposes `/livez` for liveness and `/readyz`
for dependency-aware readiness. Do not set `RUN_MIGRATIONS` on every API
replica: concurrent migrations create startup races.

The example is intentionally one API container. For multiple replicas, use an
external gateway or Redis-backed quota/rate-limit service; the in-process
request limits are safe defaults for one process only. Share secrets through a
secret manager rather than committed files.

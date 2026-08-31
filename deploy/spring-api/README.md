# Spring API deployment

Spring owns accounts, authentication, boards, notifications, inquiries, tiers,
and saved places. It shares the Django-owned PostgreSQL schema and JWT secret.

The runtime database and storage must be running first. From this directory:

```bash
docker compose \
  --env-file ../db/.env \
  --env-file ../../backend/.env \
  --env-file .env \
  config --quiet

docker compose \
  --env-file ../db/.env \
  --env-file ../../backend/.env \
  --env-file .env \
  up -d --build
```

Keep `JWT_SECRET` identical to Django. Bind to the Tailscale address for private
remote access and do not expose port 8081 publicly without TLS termination.

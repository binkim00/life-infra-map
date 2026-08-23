# Django API deployment

The API shares the existing PostgreSQL Docker network and binds to loopback by
default. Set `API_BIND_IP` to the server's Tailscale address for private remote
access; do not bind publicly until a domain, TLS termination, and allowed origin
policy are configured.

`API_AI_PROVIDER` defaults to `rule`, the tested deterministic conversational
planner. Change it only after the external model endpoint has a passing live
smoke test; server-side conversation state does not depend on a proprietary or
self-hosted model.

Create `deploy/api/.env` from `.env.example`, keep it mode `600`, and use the
runtime database env file together with it:

```bash
docker compose \
  --env-file /home/ubuntu/life-infra-map/deploy/db/.env \
  --env-file .env \
  -f docker-compose.yml config --quiet

docker compose \
  --env-file /home/ubuntu/life-infra-map/deploy/db/.env \
  --env-file .env \
  -f docker-compose.yml up -d --build
```

Verify from the server with
`curl --fail http://127.0.0.1:8000/api/recommendations/health/`, or replace the
address with the configured private bind address.

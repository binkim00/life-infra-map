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
The default deployment limits Gradle to one worker and the Spring container to
512 MB (`-Xmx384m`) so it can coexist with the database and collection workers
on a small EC2 host.

## Public login rate limits

The filter trusts `X-Real-IP` only when the TCP peer matches `TRUSTED_GATEWAY_CIDR`.
Set this to the exact gateway container IPv4 address (a `/32`) on the shared
`life-infra-map-runtime-db_default` network. Leave it empty if the gateway
address cannot be verified; the filter then uses the TCP peer. Recheck this
address after recreating the gateway container. Do not trust the entire Docker
subnet, because another container could forge the header.

The gateway must have `TRUSTED_EDGE_IP` set to the exact host bridge address
seen by Nginx for the host-network Caddy connection. Confirm both addresses
with `docker inspect` on the server before changing the containers. Test two
separate client IPs, a forged `X-Forwarded-For` request, and direct private
access before calling this effective in production. Rollback is the previous
gateway image and Spring image plus their saved environment files.

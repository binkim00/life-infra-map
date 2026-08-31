# Persistent media storage

This deploys private MinIO on the shared runtime network. The object API can be
bound to the server's Tailscale address; the admin console remains loopback-only.
The init job creates the shared bucket and grants download-only anonymous access
for profile and board images.

Use the same `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_BUCKET` values in
`backend/.env`, Django, and Spring.

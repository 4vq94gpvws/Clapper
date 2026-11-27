# HTTP mode

Run the server as a service (see `docker-compose.yml`), then point any client that speaks
MCP over streamable HTTP at it:

    URL:     http://127.0.0.1:8770/mcp
    Header:  Authorization: Bearer <CLAPPER_TOKEN>

Check that it is up (no token needed): `curl http://127.0.0.1:8770/healthz` -> `ok`.

The server listens on loopback only in the compose file. If you expose it beyond your own
machine, put a TLS reverse proxy in front of it; the bearer token alone is not transport
security.

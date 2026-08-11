# Services

This folder contains the deployable microservices for LR Platform.

- `api-gateway`: public entrypoint that proxies requests to internal services.
- `auth-service`: authentication API.
- `user-service`: user and role management API.
- `web-backend`: web application APIs, local license state, and validation
  against the configured external Super Admin license API.

Each service owns its FastAPI application entrypoint and is wired in
`../docker-compose.yml`.

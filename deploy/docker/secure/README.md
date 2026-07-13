# Secure Docker stack for Mehreagan ERP (Windows Server + Docker Desktop)

## Architecture

```text
Internet
   │
   ▼
:80 (Caddy)  ──only public port──
   ├── /backend/*  → backend:8000
   ├── /ws*        → backend:8000
   ├── /uploads/*  → backend:8000
   └── /*          → frontend:3000

Internal Docker network (no host ports):
   postgres:5432
   rabbitmq:5672

Loopback only (admin on the server):
   127.0.0.1:8000 → backend
   127.0.0.1:3000 → frontend
```

This matches the hard requirement: **app containers are not published on 0.0.0.0**; only Caddy on **80** (and later **443**).

ASP.NET sites on **80 / 1396 / 1398**: if **Default Web Site already owns port 80**, either:
- stop/rebind Default Web Site, **or**
- change Caddy publish to `"8080:80"` and port-forward **8080** on the modem (less ideal than true :80).

---

## Files in this folder

| File | Role |
|------|------|
| `docker-compose.yml` | Hardened compose |
| `Dockerfile.backend` | Multi-stage Python, UID 10001 |
| `Dockerfile.frontend` | Multi-stage Next.js standalone, UID 10001 |
| `Caddyfile` | Edge reverse proxy + security headers |
| `.env.example` | Secrets template |
| `.dockerignore.backend` / `.dockerignore.frontend` | Build context hygiene |
| `up.ps1` | Build & start |
| `security-check.ps1` | Inspect privileges / ports |

**PostgreSQL:** no custom Dockerfile — official `postgres:16-alpine` + `cap_drop` / `no-new-privileges` is the secure default.

---

## Security controls applied

| Control | Applied |
|---------|---------|
| Non-root app containers | `user: 10001:10001` |
| `privileged: false` | All services |
| `no-new-privileges:true` | All services |
| `cap_drop: ALL` | All (+ minimal `cap_add` for postgres/rabbitmq/caddy) |
| `read_only: true` | backend, consumer, frontend, caddy |
| Host ports | Caddy `:80` only; API/UI on `127.0.0.1` |
| Internal DB/MQ | `internal: true` network, no publish |
| Resource limits | `deploy.resources` |
| Healthchecks | All critical services |
| Restart | `unless-stopped` |
| Secrets | Only via `.env` / compose interpolation |

**Windows / Docker Desktop caveat:** full Linux `userns-remap` is limited on Desktop. Controls above still apply inside the Linux VM.

---

## First-time setup

```powershell
cd E:\ERP\Backend2

# 1) Secrets
Copy-Item deploy\docker\secure\.env.example .env
notepad .env
# Set: POSTGRES_PASSWORD, RABBITMQ_PASSWORD, SECRET_KEY, JWT_SERVER_SECRET
# Set: SERVER_IP in NEXT_PUBLIC_API_URL / ALLOWED_ORIGINS / API_PUBLIC_BASE_URL

# 2) Frontend dockerignore
Copy-Item deploy\docker\secure\.dockerignore.frontend ..\Frontend-Next3\.dockerignore -Force

# 3) Backend dockerignore (optional merge)
Copy-Item deploy\docker\secure\.dockerignore.backend .dockerignore -Force

# 4) Free port 80 if Default Web Site uses it (IIS)
#    IIS Manager → Default Web Site → Stop
#    OR change compose caddy ports to "8080:80"

# 5) Firewall (public HTTP only)
New-NetFirewallRule -DisplayName "ERP-Caddy-80" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow

# 6) Start
.\deploy\docker\secure\up.ps1

# 7) Verify
curl http://127.0.0.1/healthz
curl http://127.0.0.1/backend/health
.\deploy\docker\secure\security-check.ps1
```

Modem port-forward: **WAN 80 → LAN server IP:80** (not 8080/8081).

---

## Commands

```powershell
# Start
docker compose -f deploy/docker/secure/docker-compose.yml --env-file .env up -d --build

# Logs
docker compose -f deploy/docker/secure/docker-compose.yml logs -f caddy backend frontend

# Stop
docker compose -f deploy/docker/secure/docker-compose.yml down

# Rebuild one service
docker compose -f deploy/docker/secure/docker-compose.yml up -d --build backend

# Exec as same non-root user
docker compose -f deploy/docker/secure/docker-compose.yml exec backend whoami
```

---

## Security check commands

```powershell
.\deploy\docker\secure\security-check.ps1

# Manual inspect
docker inspect mehragan-erp-secure-backend-1 --format "User={{.Config.User}} Priv={{.HostConfig.Privileged}} RO={{.HostConfig.ReadonlyRootfs}}"

# No docker.sock mounts
docker inspect $(docker ps -aq) --format "{{.Name}} {{range .Mounts}}{{.Source}}{{end}}" | findstr docker.sock

# Listening ports on host
netstat -ano | findstr "LISTENING" | findstr ":80 :443 :8000 :3000 :5432"
```

Expect:
- `:80` listening (Caddy)
- `:8000` / `:3000` only on `127.0.0.1` if published
- **no** `:5432` / `:5672` on host

---

## Windows Server hardening (checklist)

1. **Windows Update** — keep OS patched.
2. **Firewall**
   - Allow inbound **80** (and **443** later).
   - Allow **3389** only from admin IPs if RDP needed.
   - Do **not** open 5432, 5672, 8000, 3000, Docker engine port.
3. **IIS coexistence**
   - Mehregan ASP.NET on **1396/1398** — leave alone.
   - If Default Web Site holds **80**, stop it or move ERP Caddy to another external port.
4. **Docker Desktop**
   - Disable “Expose daemon on tcp without TLS”.
   - Do not add users to `docker-users` lightly (docker group ≈ root).
5. **Secrets**
   - Strong `POSTGRES_PASSWORD`, `SECRET_KEY`, `JWT_SERVER_SECRET`.
   - Change CEO password away from `123456`.
   - Never commit `.env`.
6. **Backups**
   - Schedule `pg_dump` of `task_management`.
7. **Later: TLS**
   - Domain + win-acme on IIS **or** Caddy `auto_https` with DNS.
   - Then publish `443:443` and set `https://` URLs in `.env`.

---

## Migration from current 8080/8081 stack

```powershell
cd E:\ERP\Backend2
docker compose down
# Update .env URLs to http://SERVER_IP/backend and ALLOWED_ORIGINS=http://SERVER_IP
.\deploy\docker\secure\up.ps1
# Rebuild frontend so NEXT_PUBLIC_API_URL is baked correctly
```

Users open: `http://SERVER_IP/` (via Caddy), not `:8080`.

---

## Known trade-offs

| Item | Note |
|------|------|
| `read_only` + uploads | Writable named volume `uploads_data` |
| Postgres/RabbitMQ user | Official images manage their own UID; still non-privileged |
| Path-based API `/backend` | Caddy `handle_path` strips `/backend` before proxy |
| Docker Hub 403 | Set `*_IMAGE` mirrors in `.env` |

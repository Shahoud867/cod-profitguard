# Local installation and optional hosting

## Guaranteed zero-fee path

Use an existing laptop with Python 3.11+ and Node.js 22.12+ (or Node.js 24+). Package installation requires internet, disk space and ordinary computing resources; there are no mandatory paid subscriptions, API keys or external accounts. Runtime workflows can operate offline; the interface uses system fallback fonts if optional Google Fonts cannot load.

```bash
python scripts/launch.py
```

First run creates `.venv`, installs the exact Python versions in `services/api/requirements.txt`, runs `npm ci` using the committed lockfile, applies SQL migration 001 and seeds 8,000 orders. Open `http://localhost:5173`. Python API docs: `http://localhost:8000/docs`.

Use `python3` instead of `python` on systems where that is the installed Python command. On Windows, Python 3.11+ should be on PATH and Node/npm installed normally. The launcher resolves `Scripts/python.exe` and `npm.cmd`.

## Separate processes

```bash
python -m venv .venv
# Linux/macOS
.venv/bin/pip install -r services/api/requirements.txt
# Windows alternative: .venv\Scripts\python -m pip install -r services/api/requirements.txt
npm --prefix apps/web ci
.venv/bin/python scripts/migrate.py
.venv/bin/python scripts/seed.py
.venv/bin/python -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
# Second terminal
npm --prefix apps/web run dev
```

The frontend proxies `/api` to the local Python API. Database: `data/profitguard.db`, WAL mode with foreign keys and indexes. Money is integer paisa. UTC timestamps are shown in Asia/Karachi. Only one local API worker is intended. No background worker or Redis is necessary: durable connector jobs run when virtual time advances.

The bundled database, if present, is a clean seed. Deleting it **while all processes are stopped** causes automatic reseeding on startup. For a different reproducible seed, set `PROFITGUARD_DB` to a new file and run `scripts/seed.py --seed 12345 --count 8000`. Seed is non-destructive when a tenant already exists. UI reset is explicit and tenant-scoped.

## Configuration

`.env.example` documents process variables. The launcher does not implicitly parse `.env`; export variables in your shell, IDE or process manager. `PROFITGUARD_DB` chooses a local persistent file; `AUTO_SEED=false` disables automatic initial seeding; `CORS_ORIGINS` is a comma-separated explicit origin allowlist; `COOKIE_SECURE=true` is necessary behind HTTPS. The local HTTP default intentionally uses non-Secure cookies; they are still HttpOnly and SameSite=Strict. Session tokens have 320 bits of entropy and are stored only as SHA-256 hashes in SQLite, with eight-hour expiry.

## Reproduce the checks

```bash
.venv/bin/python -m pytest services/api/tests -q
npm --prefix apps/web test
npm --prefix apps/web run build
cd apps/web
npx playwright install chromium
npm run test:e2e
```

A system Chromium can be selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`. Stop the running dev app before E2E. The browser harness uses a fresh temporary database by default. You may explicitly set `PROFITGUARD_DB` to an absolute scratch path to retain test data. The tests’ server automatically seeds a new database. `scripts/benchmark.py` separately creates and removes a 10,000-order benchmark database.

## Optional hosting (guidance, not a deployed deliverable)

The tested deliverable is local. No public service was created. The managed Sites preview relay in this session was unavailable; local Playwright testing is recorded separately in TEST_REPORT.md.

A static Vite build alone cannot execute the Python API or persist SQLite. Sites’ Cloudflare Workers runtime does not run this FastAPI backend unchanged. Publishing only the interface would break the requested workflows, so no partial static deployment was substituted.

For a supervised private pilot, use an existing persistent server or an available free VM with durable disk, HTTPS reverse proxy, same-origin frontend/API and backup storage. Verify current provider limits yourself. Free ephemeral Python hosts are unsuitable for persistent SQLite; free plans may sleep and delete local files. Cloudflare Pages can serve only the frontend if paired with a separately configured durable API and same-origin routing. No free always-on production claim is made.

Before live deployment replace public demo accounts and the demo login UI, add real identity provisioning, secret management, backups, monitoring and dependency/security maintenance. Use PostgreSQL and a durable job queue for multi-worker or commercial operation. Real courier/messaging/payment contracts and costs are separate; see FUTURE_INTEGRATIONS.md.

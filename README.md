# 🏛 GLOBAL TASK EARN

Production-grade Telegram Task & Earning Platform.  
Users complete Telegram tasks → earn real USDT on BSC.

---

## Architecture

```
Bot (python-telegram-bot v21)
  ├─ Handlers       — user interface & conversation flows
  ├─ Services       — business logic (task, reward, ledger, fraud, blockchain)
  ├─ Models         — SQLAlchemy ORM (PostgreSQL)
  └─ Middlewares    — maintenance, ban, force-join, rate-limit, auth

Worker (APScheduler)
  ├─ expire_campaigns     — every 5 min
  ├─ process_withdrawals  — every 2 min
  ├─ monitor_deposits     — every 3 min
  ├─ retry_failed_payouts — every 15 min
  ├─ fraud_monitor        — every 10 min
  ├─ wallet_balance check — every 30 min
  └─ cleanup              — daily

Infrastructure
  ├─ PostgreSQL 15   — primary database (NUMERIC(18,8) for all money)
  └─ Redis 7         — rate limiting, distributed locks, idempotency
```

---

## Quick Start (Docker)

### 1. Clone and configure

```bash
git clone <repo>
cd global_task_earn
cp .env.example .env
# Edit .env — fill in BOT_TOKEN, ADMIN_IDS, PAYOUT_PRIVATE_KEY, etc.
nano .env
```

### 2. Start all services

```bash
docker-compose up -d
```

This will:
- Start PostgreSQL and Redis
- Run `alembic upgrade head` automatically
- Start the bot in polling mode
- Start the background worker

### 3. Check logs

```bash
docker-compose logs -f bot
docker-compose logs -f worker
```

---

## Production Deployment (Ubuntu 24.04 VPS)

### Prerequisites

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv postgresql-15 redis-server nginx
```

### Setup

```bash
# Create app user
sudo useradd -r -m -s /bin/bash gte
sudo su - gte

# Clone
git clone <repo> /opt/global_task_earn
cd /opt/global_task_earn

# Virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Environment
cp .env.example .env
nano .env  # Fill in all values

# Database
sudo -u postgres psql -c "CREATE DATABASE global_task_earn;"
sudo -u postgres psql -c "CREATE USER gte_user WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE global_task_earn TO gte_user;"

# Run migrations
alembic upgrade head
```

### systemd Services

```bash
sudo cp systemd/global-task-earn-bot.service /etc/systemd/system/
sudo cp systemd/global-task-earn-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable global-task-earn-bot global-task-earn-worker
sudo systemctl start global-task-earn-bot global-task-earn-worker
sudo systemctl status global-task-earn-bot
```

### Webhook Mode (recommended for production)

Set in `.env`:
```
WEBHOOK_URL=https://yourdomain.com
WEBHOOK_SECRET=random_secret_here
```

nginx config:
```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location /BOT_TOKEN {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Railway Deployment

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and init
railway login
railway init

# Set environment variables (all from .env)
railway variables set BOT_TOKEN=xxx ADMIN_IDS=xxx ...

# Deploy
railway up
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | From @BotFather |
| `BOT_USERNAME` | ✅ | Without @ |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://...` |
| `REDIS_URL` | ✅ | `redis://...` |
| `ADMIN_IDS` | ✅ | Comma-separated Telegram IDs |
| `PAYOUT_WALLET_ADDRESS` | ✅ | Your BSC hot wallet |
| `PAYOUT_PRIVATE_KEY` | ✅ | Private key — **never commit!** |
| `SECRET_SALT` | ✅ | Random hex string for idempotency |
| `BSC_RPC_URL` | ✅ | BSC RPC endpoint |
| `WEBHOOK_URL` | ❌ | Leave blank for polling |

---

## Financial Safety

- All monetary values: `NUMERIC(18,8)` — never `float`
- Every balance mutation creates a `transactions` ledger row
- `SELECT FOR UPDATE NOWAIT` on all balance rows
- Idempotency keys prevent duplicate rewards/payouts
- Failed payouts **always** refund user balance atomically
- 12+ BSC confirmations required before crediting deposits
- Private key never logged or stored in DB

---

## Anti-Fraud System

Fraud scores (0–100) are recalculated every 10 minutes.

| Score | Status | Actions |
|---|---|---|
| 0–25 | Normal | None |
| 26–50 | Flagged | Admin notified |
| 51–75 | Restricted | Withdrawals blocked |
| 76–100 | Banned | Full ban |

Signals: duplicate wallets, rapid task completion, early withdrawal, suspicious referral chains, bot behavior patterns.

---

## Admin Commands

Access via `/admin` in bot (admin Telegram IDs only).

- **Users** — search, ban, unban, adjust balance
- **Campaigns** — approve, reject, pause, resume
- **Withdrawals** — view queue, approve, reject (with auto-refund)
- **Sponsors** — approve/suspend accounts
- **Fraud Monitor** — review flags, override scores
- **Broadcast** — message all users
- **Settings** — view platform configuration
- **Audit Logs** — all admin actions logged

---

## Sponsor Flow

1. User applies via bot → Admin approves
2. Sponsor deposits USDT via BSC → submits TX hash
3. System verifies TX (12+ confirmations) → credits balance
4. Sponsor creates campaign → Admin approves
5. Sponsor funds campaign from balance → goes ACTIVE
6. Users complete tasks → campaign budget decrements
7. Unused budget released when campaign expires/completes

---

## Development

```bash
# Local dev without Docker
cp .env.example .env
# Start postgres and redis locally, then:
alembic upgrade head
python bot.py          # terminal 1
python worker.py       # terminal 2
```

```bash
# Run with pgAdmin (dev profile)
docker-compose --profile dev up -d
# pgAdmin at http://localhost:5050
```

---

## Project Structure

```
global_task_earn/
├── bot.py              # Entry point
├── config.py           # Pydantic settings
├── database.py         # Async SQLAlchemy + Redis
├── worker.py           # APScheduler background jobs
├── models/             # SQLAlchemy ORM models
├── services/           # Business logic
│   ├── ledger_service.py       # Double-entry financials
│   ├── verification_service.py # Telegram membership checks
│   ├── reward_service.py       # Atomic task rewards
│   ├── blockchain_service.py   # BSC/web3 integration
│   ├── withdrawal_service.py   # Payout lifecycle
│   ├── fraud_service.py        # Anti-fraud engine
│   └── ...
├── handlers/           # Telegram message handlers
├── admin/              # Admin panel
├── sponsor/            # Sponsor panel
├── middlewares/        # Rate limiting, auth, ban, maintenance
├── keyboards/          # Inline & reply keyboards
├── utils/              # Decimal, wallet, time helpers
├── migrations/         # Alembic migrations
├── systemd/            # Linux service files
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
└── railway.toml
```

---

## License

Private / Commercial use. Do not redistribute without permission.

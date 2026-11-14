# Jotly (NEXUS Meeting Intelligence) — Simple Deployment Guide

You do **not** need to write any code for this guide. You will create 4 free/low-cost
accounts, copy some values into 2 places, and run 1 command on your server.
Do the steps **in order**. Each step tells you exactly what to click and where the
value you copy ends up.

---

## Step 1 — Supabase (accounts & login)

1. Go to **https://supabase.com** → **Start your project** → sign in with GitHub.
2. Click **New project**. Name it `jotly`. Choose a region near your users (e.g. eu-west / eu-central). Set a **database password** — save it somewhere safe.
3. Wait ~2 minutes for the project to be ready.
4. In the left sidebar click the **⚙ Project Settings → API** page. You will see three values:
   - **Project URL** — looks like `https://abcd1234.supabase.co`
   - **anon public key** — a long `eyJ...` string
   - **secret / JWT secret** — on the same page or under *Settings → API → JWT Settings* (a long random string)
5. **Keep this browser tab open.** You will paste these values in Step 3 and Step 4.

---

## Step 2 — Vercel (the website frontend)

1. Go to **https://vercel.com** → sign up / sign in **with GitHub** (use the same GitHub account that owns the repo).
2. Click **Add New… → Project**, find the `jotly` repository, click **Import**.
3. On the configuration screen:
   - **Root Directory**: click **Edit** and set it to `apps/web`
   - **Framework Preset**: it should auto-detect **Next.js** (leave as is)
4. Open **Environment Variables** and add these **4 rows** (Name / Value):

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | *(leave as `http://localhost:8000/api/v1` for now — you will update it in Step 4 after the backend has a public address)* |
   | `NEXT_PUBLIC_SUPABASE_URL` | the **Project URL** from Step 1 |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the **anon public key** from Step 1 |
   | `NEXT_PUBLIC_APP_ENV` | `production` |

5. Click **Deploy**. After ~2 minutes you get a website address like `https://jotly-xxxx.vercel.app`. **Copy this address** — it is your `NEXUS_ALLOWED_ORIGINS` value for Step 3.

---

## Step 3 — Hostinger (the backend brain)

You need a VPS. On Hostinger order **VPS → KVM 2** (or larger; more RAM is better for the AI features later).

1. In the Hostinger panel, choose OS **Ubuntu 24.04** and set a root password.
2. Open the **Browser terminal** in the Hostinger panel (button in the VPS dashboard). Run these commands one at a time:

   ```bash
   apt update && apt -y upgrade && apt -y install docker.io docker-compose-v2 git
   git clone https://github.com/scholarsuite25-netizen/jotly.git /opt/jotly
   cd /opt/jotly
   ```

3. Create the settings file:

   ```bash
   cp .env.example .env
   nano .env
   ```

   Edit these lines (press Ctrl+O then Enter to save, Ctrl+X to exit):

   | Line | Put in |
   |---|---|
   | `NEXUS_ALLOWED_ORIGINS=` | your Vercel address from Step 2 (e.g. `https://jotly-xxxx.vercel.app`) |
   | `DATABASE_URL=` | `postgresql+psycopg://nexus_admin:` **DB-PASSWORD-BELOW** `@postgres:5432/nexus_meeting` |
   | `DATABASE_ADMIN_URL=` | same but user `nexus_admin` |
   | `SUPABASE_URL=` | Project URL from Step 1 |
   | `SUPABASE_ANON_KEY=` | anon key from Step 1 |
   | `SUPABASE_JWT_SECRET=` | JWT secret from Step 1 |
   | `EMAIL_DRY_RUN=` | `true` (emails are simulated until you add provider keys) |

   Also choose **one new strong password** for the database and use it in both `DATABASE_URL` lines. Then set it in the compose override:

   ```bash
   nano infra/hostinger/docker-compose.hostinger.yml
   ```

   In the `postgres:` service, replace `${POSTGRES_USER}` / `${POSTGRES_PASSWORD}` defaults by putting the same values at the bottom of your `.env` file instead:

   ```bash
   echo 'POSTGRES_USER=nexus_admin' >> .env
   echo 'POSTGRES_PASSWORD='your-chosen-db-password >> .env
   ```

4. **Start everything** (this is the 1 command that runs the whole backend):

   ```bash
   docker compose -f infra/hostinger/docker-compose.hostinger.yml --env-file .env up -d --build
   ```

5. Wait ~2 minutes, then verify it is alive:

   ```bash
   curl http://localhost:8000/api/v1/health
   ```

   You should see JSON containing `"status":"ok"`. If you see it — the backend is running.

6. **Create the database tables** (one-time):

   ```bash
   docker compose -f infra/hostinger/docker-compose.hostinger.yml exec -T api sh -c "cd /app && python -m alembic upgrade head"
   ```

   This applies all 8 migrations **including the security (Row-Level Security) policies** and locks in the final security verification.

---

## Step 4 — Cloudflare (public address & protection)

1. Go to **https://dash.cloudflare.com** → create a free account → add your **domain** (buy one in Cloudflare or transfer one you own; e.g. `yourcompany.com`).
2. In the Zero Trust section (left sidebar → **Networks → Tunnels**) click **Create a tunnel** → choose **Cloudflared** → name it `jotly-backend`.
3. Cloudflare shows you a long **tunnel token**. Copy it. Then on the Hostinger terminal:

   ```bash
   docker run -d --name cloudflared --restart always cloudflare/cloudflared:latest tunnel --no-autoupdate run --token PASTE-TOKEN-HERE
   ```

4. Back in the Cloudflare tunnel page, add a **Public Hostname**:
   - Subdomain: `api` · Domain: your domain · Service: `http://api:8000`
   - Save. Your backend now has a public address like `https://api.yourcompany.com`.
5. **Update the two places that point to the backend:**
   - Vercel → your project → Settings → Environment Variables → change `NEXT_PUBLIC_API_BASE_URL` to `https://api.yourcompany.com/api/v1` → **Redeploy**.
   - Hostinger `.env` → `NEXUS_ALLOWED_ORIGINS=https://jotly-xxxx.vercel.app` (already done in Step 3).

---

## Step 5 — Try it!

1. First, create a user in Supabase: Supabase dashboard → **Authentication → Users → Add user** → enter your email and a password (min 8 characters). Confirm the user if needed.
2. Open your Vercel website → sign in with that email/password.
3. Click through: create an organisation → create a meeting → confirm the recording notice → use the recorder → see the transcript → export.

Every important action is recorded in a tamper-evident audit log automatically.

---

## When you're done: flip the repo back to Private

GitHub → `scholarsuite25-netizen/jotly` → **Settings → General → Danger Zone → Change visibility → Private**.
CI keeps running on private repos — nothing breaks.

---

## Quick problem solver

| Problem | Fix |
|---|---|
| Vercel build fails | Check Root Directory is exactly `apps/web` |
| `curl localhost:8000/...` fails on VPS | `docker compose -f infra/hostinger/docker-compose.hostinger.yml logs api --tail 50` |
| Sign-in says invalid token | The `SUPABASE_JWT_SECRET` in `.env` doesn't match the Supabase project — re-copy it |
| Website shows CORS error | `NEXUS_ALLOWED_ORIGINS` in Hostinger `.env` must be the exact Vercel URL, then `docker compose ... restart api` |
| Email not received | Expected: `EMAIL_DRY_RUN=true` simulates emails. Add Resend/Emailbump/Unipost API keys to `.env` and set `EMAIL_DRY_RUN=false` when ready |

# Deployment

Two things get deployed, to two different hosts, because they are two different kinds of thing.

| What | Host | Why there |
|---|---|---|
| `console/streamlit_app.py` — the interactive console | **Streamlit Community Cloud** | Streamlit needs a long-lived stateful process. This is the host built for it. |
| `site/` — the landing page | **Vercel** | A static page on a CDN: instant, no cold start, nothing to wake up. |

---

## Why the console is not on Vercel

This is worth understanding, because "just put it on Vercel" is the obvious first instinct and it
does not survive contact with how Streamlit works.

Vercel [added native WebSocket support to Functions in June 2026](https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections),
so the old blanket answer — "Vercel can't do WebSockets" — is out of date. The blockers that remain
are about **state and duration**, and they are worse for a live demo than a flat refusal:

1. **Sessions outlive the function.** Vercel's own guidance is that "established connections are
   only pinned to a Function for its maximum duration". That maximum is
   [300 seconds on Hobby](https://vercel.com/docs/functions/limitations). A Streamlit session lasts
   as long as the browser tab is open. The socket would be torn down roughly every five minutes —
   which, during a pitch, means the demo dies mid-sentence.
2. **Reconnects are not sticky.** "Future connections aren't guaranteed to connect to the same
   Function instance." Streamlit keeps all session state in the process's memory. A reconnect to a
   cold instance loses the cached engine, the calibration, and the ledger connection, then pays the
   full re-calibration cost.
3. **The filesystem is effectively read-only.** Only `/tmp` is writable, and it is per-instance and
   ephemeral. `data/audit.db` is a SQLite hash chain that is *supposed* to accumulate — a ledger
   that silently resets is worse than no ledger.

None of that applies to Streamlit Community Cloud, which runs a persistent container with a
writable disk. So the console goes there and Vercel gets the landing page, which is what a CDN host
is genuinely good at.

---

## Deploying the console (Streamlit Community Cloud)

Everything in the repository is already set up for this. `requirements.txt` at the root ends with a
bare `.`, which installs the repository itself — without it the hosted app fails at import, because
only `console/` lands on `sys.path`.

1. Go to <https://share.streamlit.io> and sign in with the GitHub account that owns the repository.
2. **New app → Deploy a public app from GitHub.**
3. Fill in:
   - **Repository:** `Advait-Pathak9222/BurningShadows`
   - **Branch:** `main`
   - **Main file path:** `console/streamlit_app.py`
   - **App URL:** `controlplane-ai` → gives `https://controlplane-ai.streamlit.app`
4. **Advanced settings → Python version → 3.11** (or newer; `pyproject.toml` requires ≥ 3.11).
5. Deploy. First build takes a few minutes while it installs the application dependencies.

> **Claim the `controlplane-ai` subdomain exactly.** The landing page in `site/index.html` links to
> `https://controlplane-ai.streamlit.app`. If you pick a different name, update the two `href`s in
> that file and redeploy the site.

### On repository visibility

Community Cloud [deploys from private repositories](https://docs.streamlit.io/deploy/streamlit-community-cloud/status)
as well as public ones, so either works. Two things follow from staying private:

- The free tier allows **one private app**; public apps are unlimited.
- Streamlit authenticates by adding a **read-only deploy key**, which needs admin on the repository.
  That is satisfied — `BurningShadows` is owned by the deploying account.

**Making it public is still worth doing before judging.** Judges need to read the code, and while
the repository is private the GitHub links on the landing page and in this README return a 404 to
everyone except collaborators.

### Three things to know about the hosted console

- **It sleeps after about 12 hours without traffic**, and waking it takes 30–60 seconds.
  **Open it five minutes before you present.** This is the single most likely thing to go wrong on
  the day.
- **Memory is roughly 1 GB.** Measured locally, the console holds about 147 MB resident with the
  engine calibrated and cached, so there is a wide margin — but avoid opening six browser tabs
  against it during a demo, because each session holds its own state.
- **The audit ledger starts empty.** `data/audit.db` is gitignored, so it does not travel with the
  repository. Run one check in the Decision lab and the chain appears. For a demo this is better
  than a pre-populated ledger — the record is created in front of the audience.

---

## Deploying the landing page (Vercel)

The page is static: `site/index.html` plus four PNGs in `site/assets/`. No build step.

```bash
npm install -g vercel
cd site
vercel login            # one-time, opens a browser
vercel --prod
```

When prompted, name the project `controlplane` so the URL reads
`https://controlplane.vercel.app` rather than the directory name.

### Optional: deploy on every push

```bash
cd site
vercel git connect
```

Vercel then rebuilds whenever `main` moves. Set the project's **Root Directory** to `site` in the
dashboard, otherwise it will try to build the whole repository.

### A note on anonymous deploys

`vercel deploy --temporary` publishes without logging in, which is useful for a quick check, but the
resulting deployment sits behind Vercel's SSO protection and returns a `302` to anyone who is not
signed in. It is not usable as a link you hand to a judge. Log in and deploy properly.

---

## Verifying a deployment

**Do not check the bare Streamlit hostname for a 200.** It returns `303` — and so does a hostname
that does not exist at all:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://controlplane-ai.streamlit.app
# 303 -- and the control below returns 303 too, so this check proves nothing
curl -s -o /dev/null -w "%{http_code}\n" https://a-name-nobody-registered.streamlit.app
# 303
```

An earlier version of this page asked for a 200 there. It reads as a login wall or a redirect loop
when it is neither, and it cost a reviewer time. The checks that actually discriminate are the
served app and its health endpoint:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://controlplane-ai.streamlit.app/~/+/         # 200
curl -s -o /dev/null -w "%{http_code}\n" https://controlplane-ai.streamlit.app/~/+/healthz  # 200
```

Streamlit Community Cloud suspends an app that has been idle, and the first request then serves a
wake-up page while the container starts. That is not an outage, but it does mean **the console
should be opened once shortly before any demo** so a reviewer never meets a cold start.

Whatever the hosted state, the console runs locally with no key, no network and no GPU:

```bash
make console      # http://localhost:8501
```

### The Vercel host is not ours, and the link has been removed

`controlplane.vercel.app` returns 200 but serves an unrelated "SaaS Template" belonging to someone
else — the name was already taken. Recorded here so nobody re-adds it after seeing a 200:

```bash
curl -s https://controlplane.vercel.app | grep -c "0.9879"    # 0 -- not our page
```

A static mirror of the results pages can be published to any Vercel project from `site/`, but it
must be verified by grepping for a number only our page carries, never by status code alone.

---

## What is deliberately not deployed

The FastAPI gateway (`controlplane/gateway/app.py`) runs locally via `make api` and is not hosted.
It writes to the same SQLite ledger and holds a calibrated engine in memory, so it has the same
statefulness problem as the console, and nothing in the pitch depends on it being reachable over the
internet.

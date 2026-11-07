# IrisClick online backup on Vercel

A second copy of IrisClick on the internet, for when the PC's server is off or broken.
It uses the **same Supabase database** as the PC, so users, settings, messages, SOS
contacts and reports are the same in both.

| Works online | Only on the IrisClick PC |
|---|---|
| Sign-in (admin password, user name tiles) | Controlling other apps and websites with the eyes |
| **Eye tracking inside the IrisClick website** (browser webcam) | Opening PC apps from the Apps tiles |
| Home, Voice Communication (natural voice), SOS email | Camera choice, tray, PC control bar, on-screen Windows keyboard |
| Settings, Edit Apps, word filter | |
| Admin: users, settings, logs, reports (PDF) | |

**Online eye tracking** (`site/src/online-gaze/`): the browser runs Google MediaPipe
(tasks-vision 1.1.1, loaded from jsDelivr) on the webcam; camera pictures stay on the device.
Same rules as the PC: 13-dot calibration, the eye-midpoint gaze formula, left wink = click,
right wink = back, dwell click, edge scroll and button snapping follow the user's Accessibility
Settings. Calibrations are saved as "Online (browser)" rows in `calibration_profiles` (counted in
reports; the PC ignores them). Browsers only let it control the IrisClick tab itself, and the tab
must stay open and visible. Math tests: `cd site && node --test tests/`.

**Access code.** On the PC, users sign in by choosing their name with no password. Online,
anyone could do that, so the online copy first asks for an **access code** (kept only in
Vercel's settings). Give it to PDAO staff and caregivers only. A device remembers it for
180 days. Changing the code in Vercel signs every device out. Each wrong code waits 1 s,
and ten wrong codes from one address pause it for 15 minutes (counted per running Vercel
server copy, so a long random code is the real protection).

This is **not a data backup**: if Supabase is down, both copies are down.

## How it is built (for the team)

- `vercel.json`: builds the site (`site/`, with `VITE_IRISCLICK_ONLINE=1`) and sends
  every `/api/...` request to `api/index.py`.
- `api/index.py` → `server/app/cloud/`: the online server. `server/app/api/main.py` (the PC
  server) is unchanged.
- `requirements.txt` (repo root): Python packages for Vercel only. `server/requirements.txt`
  is still the PC's list.
- `.vercelignore`: `server/.env`, local storage and calibration profiles are never uploaded.
- Site: `online-access-gate.tsx` (code screen and banner), `pc-only-notice.tsx` (shown on
  `/calibration`), and small hooks in `app.tsx` and `user-select-page.tsx` (online: choosing
  your name goes straight to Home). The PC build does not include any of it.

## Set it up (about 15 minutes)

1. **Create a Vercel account** at vercel.com with "Continue with GitHub", using the GitHub
   account that owns `knoxvillesuazolatribe-bit/Iris-Click`.
   Vercel's free Hobby plan is for personal, non-commercial use; if PDAO's use counts as
   organisational, Vercel expects the Pro plan.
2. **Push the branch** `feature/vercel-fallback` to GitHub (or merge it first).
3. In Vercel: **Add New → Project → Import** `Iris-Click`.
   - Root Directory: leave it as the repository root (`./`).
   - Framework Preset: **Vite** (`vercel.json` sets the build; leave the build fields empty).
4. Still on the import screen, open **Environment Variables** and add the names below.
   Copy each value from `server/.env` on the PC yourself (never paste them in chat or commit them).

   | Name | Value |
   |---|---|
   | `IRISCLICK_ACCESS_CODE` | A new code, **at least 8 characters** (12+ recommended, e.g. three random words). Shorter = the site stays closed. |
   | `DB_HOST` | Same as `server/.env` (the Supabase **pooler** host) |
   | `DB_PORT` | `6543` (Supabase's transaction pooler, best for Vercel). `5432` also works. |
   | `DB_NAME` | Same as `server/.env` |
   | `DB_USER` | Same as `server/.env` |
   | `DB_PASSWORD` | Same as `server/.env` |
   | `DB_SSLMODE` | `require` |
   | `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Same as `server/.env`, so SOS emails work online. Without them SOS says email is not set up. |

   Camera, tracking and `ADMIN_*` settings are not needed online.
5. **Deploy.** Vercel builds and gives an address like `iris-click-xxxx.vercel.app`.
   A branch other than the production branch gets a *Preview* address; Vercel may ask you to
   log in to Vercel to open preview addresses (that is Vercel's own protection, on top of the code).

## Check it after each deploy

1. Open `https://<your address>/api/cloud/status`. Expect
   `{"online_copy":true,"ready":true,"access":false}`.
   `"ready":false` means `IRISCLICK_ACCESS_CODE` is missing or shorter than 8 characters.
2. Open `https://<your address>/`. The **IrisClick online** code screen appears. Enter the code.
3. The welcome screen shows the grey "Online backup" banner. Sign in as an admin, open
   Users: the same users as on the PC.
4. Open `https://<your address>/api/health/database`. Expect `"status":"ok"`.
5. As a user: choose a name → **Go to Home** → Voice Communication → press a Quick Phrase.
   It speaks with the natural voice.
6. If a page says the database cannot be reached: check the `DB_*` values in Vercel,
   then **Deployments → ⋯ → Redeploy** (new values only apply after a redeploy).
   Vercel's **Logs** tab shows the server's messages.

## Good to know

- **Natural voice is a bit slower online.** Saved voice audio lasts only while a Vercel
  server copy is running, so phrases are created again more often (about 1–2 s).
- **SOS online** sends during the request, so the SOS page may wait up to about a minute
  if the email server needs retries (2 retries, after 5 s and 15 s; the PC waits 10/30/60 s).
  SMS is not set up on either copy.
- **Database connections:** the online copy opens one connection per request and closes it,
  so many Vercel copies never use up Supabase's connection limit.
- **Migrations** are never run from Vercel. Apply them from the PC as before; both copies
  then use the new tables.
- **Changing the code:** Vercel → Project → Settings → Environment Variables → edit
  `IRISCLICK_ACCESS_CODE` → Redeploy. Every device must enter the new code.

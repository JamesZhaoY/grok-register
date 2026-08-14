# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Automated xAI / Grok account registration. A FastAPI backend drives a Camoufox (anti-detect Firefox)
browser through the `accounts.x.ai` signup flow, pulls the OTP from one of seven temp-mail providers,
exchanges the resulting `sso` cookie for downstream tokens (CPA / Grok2API), and records every attempt
in SQLite. A React + Vite SPA under `front/` is the only UI. Logs, docs and most user-facing strings
are Chinese — keep that convention when adding to them.

## Commands

Local setup (`.venv` here is Python 3.12; README claims 3.10+). The one-click launchers under `scripts/`
do all of this idempotently and are the documented entry point — read `scripts/_lib.sh` before changing
any of it:

```bash
scripts/start-linux.sh --check              # environment triage only, no server
scripts/start-macos.sh                      # venv + deps + camoufox + config.json + front/dist, then serve
scripts/start-linux.sh --xvfb               # headless server: wrap itself in xvfb-run
powershell -File scripts\start-windows.ps1   # Windows (or scripts\start-windows.bat)
```

Equivalent manual steps:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m camoufox fetch          # one-time browser engine download
cp config.example.json config.json
cd front && npm install && npm run build    # SPA must be built, else "/" returns 503 "Web UI 未构建"
```

Run the server (defaults come from `GROK_WEB_HOST` / `GROK_WEB_PORT`; uvicorn factory mode, `workers=1`):

```bash
./start-web.sh                                                    # legacy macOS/Linux wrapper, kept as-is
.venv/bin/python -m backend.web.cli --host 127.0.0.1 --port 8787  # direct
cd front && npm run dev                                           # Vite dev server, proxies /api -> 127.0.0.1:8787
```

Tests are plain `unittest` (no pytest, no conftest); 114 tests across 20 modules in `backend/tests/`:

```bash
.venv/bin/python -m unittest discover -s backend/tests -v         # full suite
.venv/bin/python -m unittest backend.tests.test_signup_flow       # single module — dotted path only
.venv/bin/python -m unittest discover -s backend/tests -k proxy   # name filter
```

`python -m unittest test_signup_flow` (bare module name) fails with `ModuleNotFoundError`; always use the
`backend.tests.*` dotted path. Four of the 114 do not pass on macOS and that is expected, not a
regression: three path-equality assertions in `test_auth_artifact_loading.py` and
`test_failure_screenshots.py` break because `Path.resolve()` rewrites `/var/folders/...` to
`/private/var/folders/...`, and `test_browser_lifecycle.CamoufoxProcessMatchTests` errors because
`kill_all_camoufox_processes()` refuses to run without `/proc`. A clean macOS run is "110 ok + those 4".

The runtime Python is whatever the launcher's `PYTHON_CANDIDATES` finds first, which on a fresh box can be
3.14 — so the source must stay **PEP 765 clean**: no `break` / `continue` / `return` that exits a `finally`
block (3.14 warns, and the jump silently discards an exception that was propagating through the `finally`).
`backend/tests/test_finally_control_flow.py` AST-scans `backend/`, `scripts/` and `docker/` to pin that;
`python3.14 -W error::SyntaxWarning -m compileall -q -f backend scripts docker` is the same check as a
hard error. Compute a flag inside the `finally` and jump after the `try` statement instead — that is what
`run_registration()`'s per-account loop does with `stop_after_round`.

There is no linter, formatter or type-checker configured, and `front/package.json` defines only
`dev` / `build` / `preview` — there are no frontend tests. Don't invent a lint command.

Docker is the supported deployment path (details in DEPLOYMENT.md):

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose --profile outlookemail up -d    # also start the bundled outlook-email service
docker compose run --rm grok-register python /app/docker/camoufox_smoke.py   # in-container browser check
```

### Launcher / container scripts

`scripts/_lib.sh` is the whole bash implementation; `start-linux.sh` and `start-macos.sh` are thin wrappers
that set `GROK_SCRIPT_DIR`, `SCRIPT_NAME`, `PLATFORM_LABEL`, `PYTHON_CANDIDATES` (a space-separated string,
not an array) and optional `EXTRA_USAGE`, then call `grok_main "$@"`. It must stay **bash 3.2 clean** for
macOS's system bash: no `mapfile`, no `declare -A`, use `${ARR[@]+"${ARR[@]}"}` for possibly-empty arrays,
and never write `test && cmd` as a bare statement (it exits the script under `set -e`). `--xvfb` is
Linux-only and re-execs the script under `xvfb-run`, guarded by `GROK_XVFB_WRAPPED`.
`ensure_frontend()` rebuilds when `front/dist/index.html` is missing **or** older than any file under
`front/` outside `node_modules`/`dist` (`frontend_sources_changed()`, mirrored as `Test-FrontendStale` in
the PowerShell launcher) — existence alone would keep serving a stale bundle after every `git pull`.

`scripts/seed_config.py` is the single config-preparation implementation, shared by `docker/entrypoint.sh`
and all three launchers: create from template, additively merge template-only keys without overwriting user
values, back up a corrupt `config.json` to `config.json.broken-<UTC>` and rebuild. The container calls it
plainly (so `browser_headless=false` + `data/`-relative auth dirs + `http://outlook-email:5000` get forced
on first creation); the local launchers pass `--no-container-defaults` so those never leak into the
repo-root `config.json`. `backend/tests/test_docker_config_seed.py` pins that split, and loads the script
through `importlib.util.spec_from_file_location` because it is not inside a package.

`scripts/start-windows.ps1` (+ a `start-windows.bat` double-click wrapper) mirrors the bash flow with
`-BindHost -Port -Docker -WithOutlookEmail -SkipInstall -RebuildWeb -Open -Check -Help`. Two hard rules,
both pinned by the same test module: the file keeps a **UTF-8 BOM** (Windows PowerShell 5.1 decodes a
BOM-less file with the ANSI codepage and mangles every Chinese string), and no parameter may be named
`-Host` (`$Host` is a reserved automatic variable).

`docker/entrypoint.sh` runs prepare-dirs → optional PUID/PGID remap → seed config → conditional `chown`
(skipped when the dir is already owned correctly; `GROK_SKIP_CHOWN` / `GROK_FORCE_CHOWN` override) →
writability assertion → `logs/container-<UTC>.log` + `container-latest.log` symlink + pruning to
`GROK_LOG_KEEP` → `gosu app xvfb-run …`. Other knobs: `GROK_LOG_TO_FILE=0`, `GROK_DISABLE_XVFB=1`,
`GROK_CONFIG_TEMPLATE`, `GROK_RUN_USER`.

## Architecture

Layer flow, one direction only:

```
backend.web           HTTP routes, cookie session, job coordinators
  -> backend.registration   engine (orchestrator), signup_flow (page steps), store (SQLite), artifacts
       -> backend.automation     session (Camoufox lifecycle), page_adapter (selector translation)
       -> backend.integrations   proxy, network_checks, auth_exchange (OIDC), grok2api_client
       -> backend.mailbox        one adapter per provider + shared utilities
            -> backend.shared.paths   PROJECT_ROOT / DATA_ROOT / STATIC_ROOT
```

`backend/registration/engine.py` (~2950 lines) is the hub — config, failure taxonomy, provider dispatch,
the SSO→auth pipeline and `run_registration()`. `backend/web/application.py` imports it lazily through
`_gr()` so that starting the web server doesn't pay the browser-stack import cost.

### Runtime dependency injection (the main seam)

`engine._wire_runtime_modules()` is what makes the one-directional layering possible: instead of the
lower layers importing `engine`, engine pushes callables *into* them at startup.

- `automation.session.configure(get_proxies=, is_debug=, is_headless=, get_locale=, extension_path=)`
- `registration.signup_flow.configure(get_email_and_token=, get_oai_code=, raise_if_cancelled=,
  sleep_with_cancel=, RegistrationCancelled=, EmailDomainRejected=, AccountRetryNeeded=, email_unavailable=)`

Both modules hold a module-level `_deps: Dict[str, Any]` that `configure(**kwargs)` updates. Anything
that runs registration must call `_wire_runtime_modules()` first — the web startup hook, the relogin
coordinator, and any new entry point all do. Tests inject through the same dict:
`mock.patch.dict(signup_flow._deps, {"get_oai_code": mock.Mock(return_value="123456")})`.

### The registration flow, and the duplication trap

Happy path per account, all in `engine.run_registration()`:

```
open_signup_page -> fill_email_and_submit -> fill_code_and_submit -> fill_profile_and_submit
-> wait_for_sso_cookie -> ensure_sso_oauth_eligible -> enable_nsfw_for_token
-> write data/accounts/<email>.txt  ("email----password----sso") -> add_sso_to_cpa
```

**`run_registration()` contains this flow twice** — once inside the `worker()` closure taken when
`workers > 1`, once inline for the single-worker case. Any change to the per-account sequence must be
applied to both branches or concurrency and serial runs will silently diverge.

Success is *not* just "signup completed": `registration_counts_as_success(cpa_detail)` gates it, so a
failed CPA/Grok2API import is persisted as a failure with `failure_type=FAIL_CPA`. Failure kinds live in
`engine` as `FAIL_DOMAIN / ALREADY_REGISTERED / RISK / CODE / BROWSER / CPA / STUCK / SSO / OTHER` with
`FAIL_LABELS` for display and `classify_failure(exc)` mapping exceptions; add new exception types there,
not at call sites. `_persist_result()` attaches `exception_traceback` / `exception_type` to `extra` and
captures a failure screenshot for everything except `FAIL_CPA`.

Before any account is attempted, `run_registration` runs `_cleanup_stale_profiles()` and
`network_checks.run_connectivity_checks()`, and aborts the whole batch if `has_blocking_xai_failure()`
sees Cloudflare blocking the signup page. Concurrency and batch size are clamped against two shared
constants in `engine` — `MAX_REGISTER_WORKERS = 10` and `MAX_REGISTER_COUNT = 100000`: engine computes
`max(1, min(register_workers, MAX_REGISTER_WORKERS, count))`, `web/jobs.start()` clamps both, and
`application._apply_config_updates()` clamps the persisted config values. Changing a limit means editing
the constant in `engine.py` and the mirrored pair in `front/src/pages/Register.tsx`, nothing else.

### Job coordination — progress is parsed out of log strings

`web/jobs.RegistrationJobCoordinator` is single-flight: it monkey-patches `gr.registration_log` and
`gr.RegistrationStopController` with a web shim + `WebStopController`, runs `gr.run_registration(count)`
in a daemon thread, and restores the originals in `finally`. Logs go to a ring buffer (`deque`, 2000).

`_update_progress_from_log()` derives `current_stage`, `current_email`, and the success/failure counters
by regex-matching the **Chinese log text** (`"[+] 注册成功"`, `"注册未计成功 [CPA失败]"`,
`r"(\d+)\s*个任务均记为失败"`, …). Rewording a `registration_log(...)` call in `engine.py` breaks the UI
progress display. Register jobs and `web/relogin_jobs.ReloginJobCoordinator` are mutually exclusive —
routes return 409 if the other is running.

### Browser layer

`automation/session.py` keeps browser state in `threading.local()` behind a `_SessionProxy`, so the
module-level names `browser` / `page` resolve per worker thread — that is what lets `workers > 1` run
independent browsers. `IsolatedCamoufox` subclasses Camoufox and overrides `__enter__` to install a fresh
`asyncio.new_event_loop()`, which is what bypasses Playwright's "Sync API inside the asyncio loop" error.
There is a kill switch (`block_browser_launches()` / `allow_browser_launches()`, a `threading.Event`) plus
`kill_all_camoufox_processes()` (Linux-only, walks `/proc`) and `cleanup_stale_profiles()` for temp profile
dirs tagged `grok-register-camoufox`.

`automation/page_adapter.py` translates DrissionPage-style selectors — `tag:button`, `@id=x`, `text:x`,
`xpath=//x` — into Playwright/CSS and exposes `CamoufoxPage` / `CamoufoxElement` / `_ElementStates` /
`_ShadowRootAdapter`. Flow code in `signup_flow.py` must keep using this adapter API; don't reach for
Playwright objects directly. `signup_flow` also has `_native_*` helpers that type/click through real DOM
events (Turnstile and the x.ai form reject synthetic `run_js` input), and `_native_type_element` only
reports success when it reads the value back — an empty read is a failure, not a pass.

### Token exchange

`integrations/auth_exchange.py` turns the browser `sso` cookie into downstream credentials against the
xAI OIDC issuer `https://auth.x.ai`, with three modes selected by `cpa_token_mode`:
`device_protocol` (default), `device_browser`, `auth_code`. Constraints encoded there and worth respecting:
the scope string is fixed (adding `conversations:read`/`write` breaks the grant — there's a comment saying
so), requests must carry `referrer=grok-build`, and the Next.js server-action id is discovered at runtime
and cached in `data/.next_action_id.cache`. Writers produce `cpa_auth/xai-<email>.json` and
`grok2api_auth/g2a-<email>.json`; `grok2api_client.import_auth_file()` consumes an SSE response stream.

### Mailbox providers

Seven providers (`duckmail`, `cloudflare`, `cloudmail`, `outlookemail`, `yyds`, `vmail`, `mailnest`) are
dispatched by two `if provider == ...` chains in `engine.get_email_and_token()` and `engine.get_oai_code()`
keyed off `config["email_provider"]`. Adding a provider means a `backend/mailbox/<name>.py` adapter plus a
branch in *both* chains plus its config keys in `DEFAULT_CONFIG`. Shared parsing lives in
`mailbox/utilities.py`: `pick_list_payload` normalises the `results`/`hydra:member`/`data`/`messages`
response shapes, and `strip_html` must drop script/style/comments before text extraction or CSS class
names like `.sm-w-per-100` false-match the OTP pattern (`[A-Z0-9]{3}-[A-Z0-9]{3}`, subject checked first).

## Config

`engine.DEFAULT_CONFIG` (55 keys) is the schema of record; `load_config()` merges `config.json` over it.
The file path is `$GROK_CONFIG_FILE` or `<repo>/config.json` — **in Docker it is `/app/data/config.json`,
seeded and additively merged from `config.example.json` by `scripts/seed_config.py`** (called from
`docker/entrypoint.sh` on every boot, and from the launchers with `--no-container-defaults`), so editing
the repo-root `config.json` has no effect on a container. Adding a key to `config.example.json` therefore
reaches existing deployments on their next restart. The two key sets have drifted apart in both directions:
`vmail_*` exists only in `DEFAULT_CONFIG`, `yyds_api_key` / `yyds_jwt` only in `config.example.json`.
Treat `DEFAULT_CONFIG` as authoritative and update the example file alongside it.

`load_config()` runs at engine **import** time, so merely importing `backend.registration.engine` reads
config.json and mutates the module-level `config` dict.

The web API can only write keys listed in `application.CONFIG_PUBLIC_KEYS`, each with its own coercion /
enum clamping in `_apply_config_updates()`; keys in `SENSITIVE_HINT_KEYS` are returned masked. A new
user-editable setting needs an entry in `DEFAULT_CONFIG` **and** in `CONFIG_PUBLIC_KEYS`, or the UI will
silently drop it.

Environment overrides worth knowing: `GROK_FORCE_HEADED=1` beats `browser_headless` in config (the Docker
image sets it and runs headed Camoufox under Xvfb), `GROK_DOCKER_PROXY_HOST` rewrites loopback proxy hosts
via `integrations/proxy.resolve_proxy_url`, `GROK_WEB_COOKIE_SECURE` forces the session-cookie `Secure`
flag on (`1/true/yes/on`) or off (`0/false/no/off`) — anything else, including unset, means **auto**:
`_session_cookie_secure()` sets it only when the request is HTTPS, reading `X-Forwarded-Proto` first (its
leading entry) and falling back to `request.url.scheme`. Auto is the required default; a hardcoded `Secure`
makes the browser silently drop the session cookie on any plain-HTTP origin other than loopback, which
surfaces as "created the admin, then the console 401s straight back to the login page". Both
`/api/auth/setup` and `/api/auth/login` must issue the cookie through `_set_session_cookie()`, and
`front/src/pages/Login.tsx` re-checks `/api/auth/me` after a successful login so a dropped cookie shows a
real message instead of a silent bounce. `backend/tests/test_console_authentication.py` pins all of it.

## Data, persistence, safety guards

Everything runtime lives under `data/` (gitignored) and is anchored by `backend/shared/paths.py`.
`backend/tests/test_runtime_paths.py` pins the exact layout — `data/accounts/`, `data/cpa_auth/`,
`data/grok2api_auth/`, `data/web_auth.json`, `front/dist` — so moving a path means updating that test
deliberately, not incidentally.

`registration/store.RegistrationRepository` is one SQLite table, `registration_results` (35 columns in
`RESULT_COLUMNS`), WAL + `busy_timeout=15000`, a connection per operation. Schema changes are additive
in-code migrations (`PRAGMA table_info` → `ALTER TABLE`, `PRAGMA user_version`), not migration files, and
`IN (...)` queries chunk at `SQLITE_IN_BATCH_SIZE = 900`.

Two guards exist deliberately and should not be bypassed: `application._path_within()` confines auth-JSON
reads/downloads to the configured auth dirs and screenshots to `data/screenshots/{registration,relogin}-failures`,
and `artifacts._PROTECTED_BASENAMES` stops account deletion from removing the SQLite DB or the shared side
files (`mail_credentials.txt`, `sso_pending.txt`, `sso_risk_rejected.txt`).

Web auth is a single admin created on first visit (PBKDF2-HMAC-SHA256, 240k iterations, record at
`data/web_auth.json` mode 0600) plus an HMAC-signed `grok_register_session` cookie; the `require_web_login`
middleware guards every `/api/*` route except health/login/setup/me/logout.

`data/accounts/*.txt`, `data/web_auth.json`, `config.json` and `.env` hold live credentials — don't read
them to answer questions and don't echo their values; reference keys by name.

# DeepSeek Playwright Button Automation

## Objective

Create a small Python application that attaches to a Chrome remote-debugging
session with Playwright, reuses an existing tab for the specified DeepSeek chat
or opens one if needed, allows manual login, and repeatedly clicks each
appearance of the first visible and enabled button whose text, after trimming
and case folding, is exactly “Continue”. Stop the application after five
minutes without a click.

## Repository findings

- The workspace contains an empty `app.py`; no existing application structure,
  tests, dependency manifest, or project documentation were found.
- The directory is not a Git repository and GitHub CLI is unavailable.
- Use direct edits; no branch, PR, or CI workflow applies.

## Dependency graph and delivery

This is one direct-mode delivery. Steps are serial because they all contribute
to one usable app; no independent workstream is justified.

### Step 1 — Implement Playwright CDP automation and dependencies

**Context brief:** Attach to a local Chrome DevTools Protocol endpoint (default
`http://127.0.0.1:9222`). If it is unavailable and the local port is free,
launch Chrome with a dedicated profile and that debugging endpoint. Use a new
tab so existing user tabs are not navigated. Navigate to the supplied DeepSeek
chat. The user performs login in Chrome; the app waits for an exact, visible,
enabled “Continue” button and clicks it once with Playwright. Limit chat URLs
to `https://chat.deepseek.com` and CDP URLs to loopback HTTP endpoints.

**Tasks**

- Add the Playwright dependency manifest so the app's environment is
  reproducible.
- Store target URL, CDP endpoint, timeouts, Chrome executable, and profile
  directory in project-local configuration; let CLI options override the
  target URL, endpoint, and button timeout.
- Attach to an existing local CDP session, or start Chrome with a dedicated
  profile and debugging port when the endpoint is unavailable and the port is
  free.
- Reuse an existing browser context when available, otherwise report a clear
  error; create and navigate a new page.
- Poll visible/enabled exact-text button candidates and use Playwright's click
  operation; print waiting and success messages and surface errors explicitly.
- Disconnect cleanly without closing the user's Chrome session.

**Verification**

- `python -m compileall -q app.py`
- Run focused unit tests for target-button selection/waiting using a local
  Playwright page or mock objects, without logging in to DeepSeek.
- Install dependencies with `python -m pip install -r requirements.txt`.

**Exit criteria:** The app starts against a Chrome CDP endpoint, leaves login
to the user, watches continuously, clicks each appearance once without
repeatedly clicking the same visible button, and exits after the configured
inactivity timeout. It reuses a matching tab and does not create duplicates.
Non-DeepSeek chat URLs and non-loopback CDP endpoints are rejected.

### Step 2 — Document setup and operation

**Context brief:** A fresh user needs Python dependencies, a Chrome instance
with remote debugging enabled, and instructions to log in manually before the
app clicks. Do not include credentials or automate login.

**Tasks**

- Document dependency installation, starting Chrome with a dedicated
  user-data directory and loopback remote-debugging port, manual login,
  command usage, and common connection or timeout failures.

**Verification**

- Check documented commands against the implemented CLI and dependency
  manifest.
- Confirm setup instructions do not ask users to expose the debugging port to
  untrusted networks.

**Exit criteria:** A new user can install the dependency, start a local Chrome
debug session, log in manually, and run the app using documented commands.

### Step 3 — Verify end-to-end behavior and safety boundaries

**Context brief:** The target site requires manual authentication and must not
be accessed with stored or supplied credentials. The app should interact only
with the configured page and click once.

**Tasks**

- Add focused tests for matching, visibility/enabled state, button re-arming,
  inactivity timeout, existing-tab reuse, and URL restrictions without
  external network access.
- Run the test suite and compile check; inspect final files for unintended
  credential handling or broad browser actions.
- When a local Chrome environment is available, run a manual smoke test with a
  disposable profile; confirm the app can start Chrome when the CDP endpoint is
  down, reuses the configured chat tab if present, and leaves Chrome open after
  the app exits.

**Verification**

- `python -m unittest discover -s tests -v`
- `python -m compileall -q app.py`

**Exit criteria:** Focused checks pass; no external login or live site is
required for tests; user Chrome remains open after the app exits. The app does
not store credentials; clicking may trigger the site's normal button behavior.

## Rollback

Remove the newly added app, dependency manifest, tests, and this plan if the
automation is abandoned. The app does not store credentials or alter existing
Chrome tabs; the requested click may trigger the site's normal behavior and
cannot necessarily be undone by the app. The dedicated Chrome profile is
persistent and contains browser login state; it remains under the configured
user-data directory unless the user removes it.

## Plan mutation protocol

If implementation reveals that the Chrome endpoint or button text differs,
update the affected step and tests before broadening selectors.
Any expanded click behavior (for example repeated clicks or non-exact matching)
requires explicit user approval; do not silently change the one-click boundary.

# DeepSeek Playwright button clicker

This app connects to a locally running Chrome session using Chrome DevTools
Protocol (CDP), reuses an existing tab for the configured chat or opens one if
needed, and clicks the first visible and enabled button whose text is exactly
`Continue` (ignoring case and surrounding whitespace). It keeps monitoring,
clicking each appearance once. It exits after five minutes without a click and
never enters login credentials.

## Requirements

- Python 3.10+
- Google Chrome

Create a project-local Python environment and install Playwright into it:

```powershell
.\setup.ps1
```

Dependencies are installed under this project's `.venv`; the app launcher uses
that interpreter so it does not depend on packages installed globally or in
another project.

Edit [config.json](./config.json) to change the chat URL, local Chrome CDP
endpoint, inactivity timeout, Chrome startup timeout, executable path, or
dedicated Chrome profile directory. Leave the executable and profile values
empty to let the app discover Chrome and use
`%LOCALAPPDATA%\DeepSeekPlaywright\ChromeProfile` (Windows). Settings are
loaded from the project directory, not the current working directory.
Command-line options override URL, CDP endpoint, and inactivity timeout.

## Chrome and login

When you run the app, it starts Chrome automatically if the configured local
debugging endpoint is not already active. The app uses a dedicated profile at
`%LOCALAPPDATA%\DeepSeekPlaywright\ChromeProfile` by default; sign in manually
in the Chrome window it opens.

To start that same profile manually instead, use a loopback-only debugging
port:

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-address=127.0.0.1 `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:LOCALAPPDATA\DeepSeekPlaywright\ChromeProfile"
```

If Chrome is installed in a different location, substitute its `chrome.exe`
path. Sign in to DeepSeek manually in this Chrome window if prompted. Do not
expose the debugging port to other machines or use a profile containing
unrelated sensitive sessions.

## Run

From this project directory, after setup:

```powershell
.\run.ps1
```

The app first attaches to the configured Chrome debugging endpoint. If no CDP
session is available and the local port is free, it starts Chrome with the
dedicated profile and configured debugging port, then waits for CDP. It reuses
an already-open tab for the configured chat; otherwise, it opens a new tab.
The watcher clicks once when the button appears, waits for that button to
disappear before clicking a later appearance, and exits after five minutes
without a click. Use `Ctrl+C` to stop it sooner.

Options:

```powershell
.\run.ps1 --cdp-url http://127.0.0.1:9222 --inactivity-timeout 120
.\run.ps1 --url "https://chat.deepseek.com/a/chat/s/782f2f38-e31c-4310-ae8b-1c1744087630"
```

The inactivity timeout is in seconds; the default is 300. `--timeout` remains
available as an alias. When the app exits, the Chrome window stays open.

## Troubleshooting

- **Cannot connect:** Confirm Chrome is running with the same CDP port, and
  that `--cdp-url` matches it.
- **Button not found:** Complete login manually and confirm the page presents a
  button whose text is exactly `Continue`. The app exits after five minutes
  without a click by default; adjust `inactivity_timeout_seconds` in
  `config.json` or use `--inactivity-timeout`.
- **Chrome executable not found:** Update the startup command with the
  installation path for Chrome on your machine.
- **Project environment missing:** Run `.\setup.ps1` to create `.venv` and
  install the project's dependencies.
- **Chrome startup fails:** Confirm Chrome is installed and the configured CDP
  port is free. If Chrome is installed outside standard locations, set
  `chrome_executable` in `config.json`.

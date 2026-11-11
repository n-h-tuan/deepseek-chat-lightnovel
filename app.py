"""Click an exact, visible, enabled Continue button in an attached Chrome tab."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Sequence
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Locator, Page, Playwright


DEFAULT_CHAT_URL = "https://chat.deepseek.com/a/chat/s/782f2f38-e31c-4310-ae8b-1c1744087630"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.json"
POLL_INTERVAL_SECONDS = 0.1


class ConfigError(ValueError):
    """Raised when the project-local configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    chat_url: str
    cdp_url: str
    inactivity_timeout_seconds: float
    startup_timeout_seconds: float
    chrome_executable: str
    chrome_user_data_dir: str


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or CONFIG_PATH
    try:
        with config_path.open(encoding="utf-8") as config_file:
            data = json.load(config_file)
    except OSError as error:
        raise ConfigError(
            f"Cannot read project config at {config_path}: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"Invalid JSON in project config at {config_path}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise ConfigError("Project config must be a JSON object.")

    required_keys = {
        "chat_url",
        "cdp_url",
        "inactivity_timeout_seconds",
        "startup_timeout_seconds",
        "chrome_executable",
        "chrome_user_data_dir",
    }
    missing_keys = required_keys - data.keys()
    extra_keys = data.keys() - required_keys
    if missing_keys or extra_keys:
        details = []
        if missing_keys:
            details.append(f"missing keys: {', '.join(sorted(missing_keys))}")
        if extra_keys:
            details.append(f"unknown keys: {', '.join(sorted(extra_keys))}")
        raise ConfigError(f"Invalid project config ({'; '.join(details)}).")

    chat_url = data["chat_url"]
    cdp_url = data["cdp_url"]
    inactivity_timeout_seconds = data["inactivity_timeout_seconds"]
    startup_timeout_seconds = data["startup_timeout_seconds"]
    chrome_executable = data["chrome_executable"]
    chrome_user_data_dir = data["chrome_user_data_dir"]
    if not isinstance(chat_url, str):
        raise ConfigError("Project config 'chat_url' must be a string.")
    if not isinstance(cdp_url, str):
        raise ConfigError("Project config 'cdp_url' must be a string.")
    for key, value in (
        ("inactivity_timeout_seconds", inactivity_timeout_seconds),
        ("startup_timeout_seconds", startup_timeout_seconds),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"Project config '{key}' must be a number.")
        if not math.isfinite(value) or value < 0:
            raise ConfigError(
                f"Project config '{key}' must be a finite number zero or greater."
            )
    if startup_timeout_seconds == 0:
        raise ConfigError(
            "Project config 'startup_timeout_seconds' must be greater than zero."
        )
    if not isinstance(chrome_executable, str):
        raise ConfigError("Project config 'chrome_executable' must be a string.")
    if not isinstance(chrome_user_data_dir, str):
        raise ConfigError("Project config 'chrome_user_data_dir' must be a string.")

    try:
        validate_chat_url(chat_url)
    except argparse.ArgumentTypeError as error:
        raise ConfigError(f"Invalid project config 'chat_url': {error}") from error
    try:
        validate_cdp_url(cdp_url)
    except argparse.ArgumentTypeError as error:
        raise ConfigError(f"Invalid project config 'cdp_url': {error}") from error
    return AppConfig(
        chat_url=chat_url,
        cdp_url=cdp_url,
        inactivity_timeout_seconds=float(inactivity_timeout_seconds),
        startup_timeout_seconds=float(startup_timeout_seconds),
        chrome_executable=chrome_executable,
        chrome_user_data_dir=chrome_user_data_dir,
    )


def find_continue_button(page: Page) -> Locator | None:
    """Return the first button matching the original script's visibility rules."""
    buttons = page.locator('button, [role="button"]')
    for index in range(buttons.count()):
        button = buttons.nth(index)
        if not button.is_visible() or not button.is_enabled():
            continue
        text = button.text_content()
        if text is not None and text.strip().casefold() == "continue":
            return button
    return None


def wait_for_continue_button(page: Page, timeout_seconds: float = 0) -> Locator:
    """Wait for a matching button; timeout 0 means wait until it appears."""
    deadline = time.monotonic() + timeout_seconds if timeout_seconds else None
    while True:
        button = find_continue_button(page)
        if button is not None:
            return button
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError(
                f"No visible, enabled Continue button appeared within "
                f"{timeout_seconds:g} seconds."
            )
        time.sleep(POLL_INTERVAL_SECONDS)


def click_continue_once(page: Page, timeout_seconds: float = 0) -> None:
    button = wait_for_continue_button(page, timeout_seconds)
    button.click()


def watch_continue_button(
    page: Page,
    inactivity_timeout_seconds: float,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> int:
    """Click each appearance once and stop after the configured idle interval."""
    last_click_at = time.monotonic()
    button_is_armed = True
    click_count = 0

    while True:
        if time.monotonic() - last_click_at >= inactivity_timeout_seconds:
            return click_count

        button = find_continue_button(page)
        if button is None:
            button_is_armed = True
        elif button_is_armed:
            button.click()
            click_count += 1
            last_click_at = time.monotonic()
            button_is_armed = False

        time.sleep(poll_interval_seconds)


def find_existing_chat_tab(browser: Browser, chat_url: str) -> Page | None:
    target = urlsplit(chat_url)
    target_path = target.path.rstrip("/")
    target_port = target.port or 443
    for context in browser.contexts:
        for page in context.pages:
            current = urlsplit(page.url)
            try:
                current_port = current.port or 443
            except ValueError:
                continue
            if (
                current.scheme == target.scheme
                and current.hostname == target.hostname
                and current_port == target_port
                and current.path.rstrip("/") == target_path
            ):
                return page
    return None


def validate_chat_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid chat URL: {error}") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != "chat.deepseek.com"
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise argparse.ArgumentTypeError(
            "chat URL must use HTTPS on chat.deepseek.com"
        )
    return value


def validate_cdp_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
        host = parsed.hostname
        is_loopback = host == "localhost" or (
            host is not None and ipaddress.ip_address(host).is_loopback
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid CDP URL: {error}") from error
    if (
        parsed.scheme != "http"
        or port is None
        or not is_loopback
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise argparse.ArgumentTypeError(
            "CDP URL must be a local HTTP endpoint, such as "
            "http://127.0.0.1:9222"
        )
    return value


def non_negative_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number of seconds") from error
    if not math.isfinite(seconds) or seconds < 0:
        raise argparse.ArgumentTypeError("must be a finite number zero or greater")
    return seconds


def resolve_chrome_executable(configured_path: str = "") -> Path:
    if configured_path:
        expanded_path = Path(os.path.expandvars(os.path.expanduser(configured_path)))
        if expanded_path.is_file():
            return expanded_path.resolve()
        executable = shutil.which(configured_path)
        if executable:
            return Path(executable).resolve()
        raise RuntimeError(
            f"Configured Chrome executable was not found: {configured_path}"
        )

    executable = shutil.which("chrome.exe") or shutil.which("chrome")
    if executable:
        return Path(executable).resolve()

    candidate_roots = (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    )
    for root in candidate_roots:
        if root:
            candidate = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if candidate.is_file():
                return candidate.resolve()
    raise RuntimeError(
        "Chrome executable was not found. Set 'chrome_executable' in config.json."
    )


def resolve_chrome_user_data_dir(configured_path: str = "") -> Path:
    if configured_path:
        path = Path(os.path.expandvars(os.path.expanduser(configured_path)))
        if not path.is_absolute():
            path = PROJECT_DIR / path
        return path.resolve()

    local_app_data = os.environ.get("LOCALAPPDATA")
    base_dir = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / ".local" / "share"
    )
    return base_dir / "DeepSeekPlaywright" / "ChromeProfile"


def is_cdp_port_in_use(cdp_url: str) -> bool:
    parsed = urlsplit(cdp_url)
    host = parsed.hostname or "127.0.0.1"
    if host == "localhost":
        host = "127.0.0.1"
    address_family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(address_family, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.3)
        address = (
            (host, parsed.port, 0, 0)
            if address_family == socket.AF_INET6
            else (host, parsed.port)
        )
        return connection.connect_ex(address) == 0


def connect_or_start_chrome(playwright: Playwright, config: AppConfig) -> Browser:
    from playwright.sync_api import Error as PlaywrightError

    chromium = playwright.chromium
    try:
        return chromium.connect_over_cdp(config.cdp_url, timeout=1000)
    except PlaywrightError as connection_error:
        if is_cdp_port_in_use(config.cdp_url):
            raise RuntimeError(
                f"CDP endpoint {config.cdp_url} is already in use but is not "
                "accepting Chrome DevTools connections. Stop the other service "
                "or configure a different port."
            ) from connection_error

    chrome_executable = resolve_chrome_executable(config.chrome_executable)
    user_data_dir = resolve_chrome_user_data_dir(config.chrome_user_data_dir)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    parsed_cdp_url = urlsplit(config.cdp_url)
    host = parsed_cdp_url.hostname or "127.0.0.1"
    debug_address = "127.0.0.1" if host == "localhost" else host
    command = [
        str(chrome_executable),
        f"--remote-debugging-address={debug_address}",
        f"--remote-debugging-port={parsed_cdp_url.port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
    ]

    print(
        f"Chrome CDP is unavailable; starting Chrome with profile {user_data_dir}.",
        flush=True,
    )
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise RuntimeError(f"Could not start Chrome: {error}") from error

    deadline = time.monotonic() + config.startup_timeout_seconds
    last_connection_error: PlaywrightError | None = None
    while True:
        if process.poll() is not None:
            raise RuntimeError(
                f"Chrome exited before its CDP endpoint became ready "
                f"(exit code {process.returncode}). Check the Chrome path and "
                "profile directory in config.json."
            )
        try:
            return chromium.connect_over_cdp(config.cdp_url, timeout=1000)
        except PlaywrightError as error:
            last_connection_error = error
        if time.monotonic() >= deadline:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    raise RuntimeError(
        f"Chrome started but its CDP endpoint {config.cdp_url} did not become "
        f"ready within {config.startup_timeout_seconds:g} seconds: "
        f"{last_connection_error}"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Attach to Chrome over its local DevTools endpoint, open the DeepSeek "
            "chat, and monitor it for visible enabled Continue buttons."
        )
    )
    try:
        config = load_config()
    except ConfigError as error:
        parser.error(str(error))
    parser.set_defaults(
        startup_timeout_seconds=config.startup_timeout_seconds,
        chrome_executable=config.chrome_executable,
        chrome_user_data_dir=config.chrome_user_data_dir,
    )
    parser.add_argument(
        "--url",
        type=validate_chat_url,
        default=config.chat_url,
        help="DeepSeek chat URL to open",
    )
    parser.add_argument(
        "--cdp-url",
        type=validate_cdp_url,
        default=config.cdp_url,
        help=f"Chrome DevTools Protocol endpoint (default: {DEFAULT_CDP_URL})",
    )
    parser.add_argument(
        "--inactivity-timeout",
        "--timeout",
        dest="inactivity_timeout_seconds",
        type=non_negative_seconds,
        default=config.inactivity_timeout_seconds,
        metavar="SECONDS",
        help="exit after this many seconds without a click (default: 300)",
    )
    return parser.parse_args(argv)


def run(config: AppConfig) -> None:
    validate_chat_url(config.chat_url)
    validate_cdp_url(config.cdp_url)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = connect_or_start_chrome(playwright, config)
        if not browser.contexts:
            raise RuntimeError(
                "Chrome has no available browser context. Start Chrome with "
                "remote debugging enabled and try again."
            )
        page = find_existing_chat_tab(browser, config.chat_url)
        if page is None:
            page = browser.contexts[0].new_page()
            page.goto(config.chat_url, wait_until="domcontentloaded")
        else:
            print("Reusing the existing DeepSeek chat tab.", flush=True)
        print(
            "If needed, log in to DeepSeek in the Chrome tab. "
            "Watching for visible, enabled Continue buttons...",
            flush=True,
        )
        click_count = watch_continue_button(
            page, config.inactivity_timeout_seconds
        )
        print(
            f"No Continue button was clicked for "
            f"{config.inactivity_timeout_seconds:g} seconds. "
            f"Stopping after {click_count} click(s)."
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run(
        AppConfig(
            chat_url=args.url,
            cdp_url=args.cdp_url,
            inactivity_timeout_seconds=args.inactivity_timeout_seconds,
            startup_timeout_seconds=args.startup_timeout_seconds,
            chrome_executable=args.chrome_executable,
            chrome_user_data_dir=args.chrome_user_data_dir,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
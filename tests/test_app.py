import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app
from playwright.sync_api import Error as PlaywrightError


class FakeButton:
    def __init__(
        self,
        text: str,
        *,
        visible: bool = True,
        enabled: bool = True,
    ) -> None:
        self.text = text
        self.visible = visible
        self.enabled = enabled
        self.click = Mock()

    def is_visible(self) -> bool:
        return self.visible

    def is_enabled(self) -> bool:
        return self.enabled

    def text_content(self) -> str:
        return self.text


class FakeButtons:
    def __init__(self, buttons: list[FakeButton]) -> None:
        self.buttons = buttons

    def count(self) -> int:
        return len(self.buttons)

    def nth(self, index: int) -> FakeButton:
        return self.buttons[index]


class FakePage:
    def __init__(self, buttons: list[FakeButton]) -> None:
        self.buttons = FakeButtons(buttons)

    def locator(self, selector: str) -> FakeButtons:
        self.asserted_selector = selector
        return self.buttons


class FindContinueButtonTests(unittest.TestCase):
    def test_selects_first_visible_enabled_exact_text_match(self) -> None:
        hidden = FakeButton("Continue", visible=False)
        disabled = FakeButton("Continue", enabled=False)
        wrong_text = FakeButton("Continue now")
        matching = FakeButton("  CONTINUE \n")
        page = FakePage([hidden, disabled, wrong_text, matching])

        self.assertIs(app.find_continue_button(page), matching)

    def test_returns_none_when_no_candidate_matches(self) -> None:
        page = FakePage([FakeButton("Continue", enabled=False), FakeButton("Next")])

        self.assertIsNone(app.find_continue_button(page))


class ClickContinueTests(unittest.TestCase):
    def test_waits_for_a_match_and_clicks_only_once(self) -> None:
        matching = FakeButton("Continue")
        page = FakePage([matching])

        app.click_continue_once(page, timeout_seconds=0.1)

        matching.click.assert_called_once_with()

    def test_raises_after_timeout(self) -> None:
        page = FakePage([FakeButton("Continue", visible=False)])

        with self.assertRaisesRegex(TimeoutError, "No visible, enabled Continue"):
            app.wait_for_continue_button(page, timeout_seconds=0.01)


class WatchContinueButtonTests(unittest.TestCase):
    def test_clicks_each_button_appearance_and_exits_after_inactivity(self) -> None:
        button = FakeButton("Continue")
        page = FakePage([button])
        monotonic_values = iter([0.0, 0.0, 0.0, 100.0, 300.0])

        with (
            patch.object(app.time, "monotonic", side_effect=lambda: next(monotonic_values)),
            patch.object(app.time, "sleep"),
            patch.object(
                app,
                "find_continue_button",
                side_effect=[button, button, None],
            ),
        ):
            click_count = app.watch_continue_button(
                page,
                inactivity_timeout_seconds=300,
                poll_interval_seconds=0.1,
            )

        self.assertEqual(click_count, 1)
        button.click.assert_called_once_with()

    def test_rearms_after_button_disappears_and_clicks_again(self) -> None:
        first_button = FakeButton("Continue")
        second_button = FakeButton("Continue")
        page = FakePage([first_button])
        monotonic_values = iter(
            [0.0, 0.0, 0.0, 100.0, 200.0, 250.0, 250.0, 300.0, 400.0, 550.0]
        )

        with (
            patch.object(app.time, "monotonic", side_effect=lambda: next(monotonic_values)),
            patch.object(app.time, "sleep"),
            patch.object(
                app,
                "find_continue_button",
                side_effect=[
                    first_button,
                    first_button,
                    None,
                    second_button,
                    second_button,
                    None,
                ],
            ),
        ):
            click_count = app.watch_continue_button(
                page,
                inactivity_timeout_seconds=300,
                poll_interval_seconds=0.1,
            )

        self.assertEqual(click_count, 2)
        first_button.click.assert_called_once_with()
        second_button.click.assert_called_once_with()

    def test_waits_thirty_minutes_when_clicks_are_under_one_second_apart(self) -> None:
        first_button = FakeButton("Continue")
        second_button = FakeButton("Continue")
        resumed_button = FakeButton("Continue")
        page = FakePage([first_button])
        monotonic_values = iter(
            [0.0, 0.0, 0.0, 0.1, 0.2, 0.2, 300.2, 300.2, 300.2, 600.2]
        )

        with (
            patch.object(app.time, "monotonic", side_effect=lambda: next(monotonic_values)),
            patch.object(app.time, "sleep") as sleep,
            patch.object(
                app,
                "find_continue_button",
                side_effect=[
                    first_button,
                    None,
                    second_button,
                    resumed_button,
                    None,
                ],
            ),
            patch("builtins.print") as print_log,
        ):
            click_count = app.watch_continue_button(
                page,
                inactivity_timeout_seconds=300,
                poll_interval_seconds=0.1,
            )

        self.assertEqual(click_count, 3)
        first_button.click.assert_called_once_with()
        second_button.click.assert_called_once_with()
        resumed_button.click.assert_called_once_with()
        sleep.assert_any_call(app.RATE_LIMIT_COOLDOWN_SECONDS)
        self.assertTrue(
            any(
                "rate limit" in str(call).casefold()
                and "30 minutes" in str(call).casefold()
                for call in print_log.call_args_list
            )
        )


class ExistingChatTabTests(unittest.TestCase):
    def test_reuses_existing_tab_for_same_chat(self) -> None:
        existing_page = Mock(url=app.DEFAULT_CHAT_URL)
        browser = Mock()
        browser.contexts = [Mock(pages=[existing_page])]

        page = app.find_existing_chat_tab(browser, app.DEFAULT_CHAT_URL)

        self.assertIs(page, existing_page)

    def test_reuses_tab_when_config_url_has_explicit_default_port(self) -> None:
        existing_page = Mock(url=app.DEFAULT_CHAT_URL)
        browser = Mock()
        browser.contexts = [Mock(pages=[existing_page])]
        configured_url = app.DEFAULT_CHAT_URL.replace(
            "https://chat.deepseek.com", "https://chat.deepseek.com:443", 1
        )

        page = app.find_existing_chat_tab(browser, configured_url)

        self.assertIs(page, existing_page)

    def test_ignores_tabs_for_other_chats(self) -> None:
        other_page = Mock(url="https://chat.deepseek.com/a/chat/s/other-chat")
        browser = Mock()
        browser.contexts = [Mock(pages=[other_page])]

        page = app.find_existing_chat_tab(browser, app.DEFAULT_CHAT_URL)

        self.assertIsNone(page)


class UrlValidationTests(unittest.TestCase):
    def test_accepts_chat_url_and_local_cdp_endpoint(self) -> None:
        self.assertEqual(app.validate_chat_url(app.DEFAULT_CHAT_URL), app.DEFAULT_CHAT_URL)
        self.assertEqual(
            app.validate_cdp_url(app.DEFAULT_CDP_URL), app.DEFAULT_CDP_URL
        )
        self.assertEqual(
            app.validate_cdp_url("http://[::1]:9222"), "http://[::1]:9222"
        )

    def test_rejects_non_deepseek_chat_url(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            app.validate_chat_url("https://example.com/")
        with self.assertRaises(argparse.ArgumentTypeError):
            app.validate_chat_url("http://chat.deepseek.com/")

    def test_rejects_non_loopback_cdp_endpoint(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            app.validate_cdp_url("http://192.0.2.1:9222")
        with self.assertRaises(argparse.ArgumentTypeError):
            app.validate_cdp_url("https://localhost:9222")

    def test_rejects_invalid_timeouts(self) -> None:
        for value in ("-1", "nan", "inf"):
            with self.subTest(value=value), self.assertRaises(
                argparse.ArgumentTypeError
            ):
                app.non_negative_seconds(value)


class ProjectConfigTests(unittest.TestCase):
    def test_loads_project_config(self) -> None:
        config_data = {
            "chat_url": app.DEFAULT_CHAT_URL,
            "cdp_url": app.DEFAULT_CDP_URL,
            "inactivity_timeout_seconds": 30,
            "startup_timeout_seconds": 15,
            "chrome_executable": "",
            "chrome_user_data_dir": "",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            config_path.write_text(json.dumps(config_data), encoding="utf-8")

            config = app.load_config(config_path)

        self.assertEqual(config.chat_url, app.DEFAULT_CHAT_URL)
        self.assertEqual(config.cdp_url, app.DEFAULT_CDP_URL)
        self.assertEqual(config.inactivity_timeout_seconds, 30)
        self.assertEqual(config.startup_timeout_seconds, 15)

    def test_cli_options_override_project_config(self) -> None:
        with patch.object(
            app,
            "load_config",
            return_value=app.AppConfig(
                chat_url=app.DEFAULT_CHAT_URL,
                cdp_url=app.DEFAULT_CDP_URL,
                inactivity_timeout_seconds=30,
                startup_timeout_seconds=15,
                chrome_executable="",
                chrome_user_data_dir="",
            ),
        ):
            args = app.parse_args(["--inactivity-timeout", "60"])

        self.assertEqual(args.inactivity_timeout_seconds, 60)
        self.assertEqual(args.url, app.DEFAULT_CHAT_URL)
        self.assertEqual(args.cdp_url, app.DEFAULT_CDP_URL)

    def test_rejects_invalid_config_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "chat_url": "https://example.com/",
                        "cdp_url": app.DEFAULT_CDP_URL,
                        "inactivity_timeout_seconds": 0,
                        "startup_timeout_seconds": 15,
                        "chrome_executable": "",
                        "chrome_user_data_dir": "",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(app.ConfigError, "chat_url"):
                app.load_config(config_path)


class ChromeStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = app.AppConfig(
            chat_url=app.DEFAULT_CHAT_URL,
            cdp_url=app.DEFAULT_CDP_URL,
            inactivity_timeout_seconds=0,
            startup_timeout_seconds=5,
            chrome_executable="",
            chrome_user_data_dir="",
        )

    def test_uses_existing_cdp_session_without_starting_chrome(self) -> None:
        browser = object()
        chromium = Mock()
        chromium.connect_over_cdp.return_value = browser
        playwright = Mock(chromium=chromium)

        with patch.object(app.subprocess, "Popen") as popen:
            result = app.connect_or_start_chrome(playwright, self.config)

        self.assertIs(result, browser)
        popen.assert_not_called()

    def test_starts_chrome_when_cdp_is_not_available(self) -> None:
        browser = object()
        chromium = unittest.mock.Mock()
        chromium.connect_over_cdp.side_effect = [PlaywrightError("not ready"), browser]
        playwright = unittest.mock.Mock(chromium=chromium)

        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "profile"
            with (
                patch.object(app, "is_cdp_port_in_use", return_value=False),
                patch.object(
                    app, "resolve_chrome_executable", return_value=Path("chrome.exe")
                ),
                patch.object(
                    app, "resolve_chrome_user_data_dir", return_value=profile_path
                ),
                patch.object(app.subprocess, "Popen") as popen,
                patch.object(app.time, "sleep"),
            ):
                popen.return_value.poll.return_value = None
                result = app.connect_or_start_chrome(playwright, self.config)

        self.assertIs(result, browser)
        popen.assert_called_once()
        arguments = popen.call_args.args[0]
        self.assertIn("--remote-debugging-port=9222", arguments)
        self.assertIn("--remote-debugging-address=127.0.0.1", arguments)
        self.assertIn(f"--user-data-dir={profile_path}", arguments)

    def test_does_not_start_chrome_when_port_is_already_in_use(self) -> None:
        chromium = unittest.mock.Mock()
        chromium.connect_over_cdp.side_effect = PlaywrightError("not a CDP endpoint")
        playwright = unittest.mock.Mock(chromium=chromium)

        with (
            patch.object(app, "is_cdp_port_in_use", return_value=True),
            patch.object(app.subprocess, "Popen") as popen,
            self.assertRaisesRegex(RuntimeError, "already in use"),
        ):
            app.connect_or_start_chrome(playwright, self.config)

        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()

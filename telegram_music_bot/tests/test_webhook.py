from __future__ import annotations

import unittest
from typing import Any

from music_bot.webhook import (
    WEBHOOK_SECRET_HEADER,
    _resolve_secret_token,
    _validate_webhook_url,
    create_flask_app,
)


class FakeRuntime:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def process_update(self, payload: dict[str, Any]) -> None:
        self.updates.append(payload)


class WebhookAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = FakeRuntime()
        self.app = create_flask_app(self.runtime, "test_secret_123")
        self.client = self.app.test_client()

    def test_health_check(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])

    def test_valid_webhook_update_is_dispatched(self) -> None:
        payload = {"update_id": 23, "message": {"text": "hello"}}

        response = self.client.post(
            "/",
            json=payload,
            headers={WEBHOOK_SECRET_HEADER: "test_secret_123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.runtime.updates, [payload])

    def test_invalid_webhook_secret_is_rejected(self) -> None:
        response = self.client.post(
            "/",
            json={"update_id": 1},
            headers={WEBHOOK_SECRET_HEADER: "wrong"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.runtime.updates, [])

    def test_non_json_request_is_rejected(self) -> None:
        response = self.client.post(
            "/",
            data="not-json",
            content_type="text/plain",
            headers={WEBHOOK_SECRET_HEADER: "test_secret_123"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.runtime.updates, [])

    def test_unconfigured_preview_does_not_accept_webhook_updates(self) -> None:
        app = create_flask_app(None, "")
        client = app.test_client()

        health = client.get("/")
        response = client.post("/", json={"update_id": 1})

        self.assertTrue(health.json["ok"])
        self.assertFalse(health.json["webhook_configured"])
        self.assertEqual(response.status_code, 503)


class WebhookConfigurationTests(unittest.TestCase):
    def test_webhook_url_must_use_https(self) -> None:
        with self.assertRaises(ValueError):
            _validate_webhook_url("http://example.com/")

    def test_render_external_url_is_accepted(self) -> None:
        url = "https://music-bot.onrender.com"

        self.assertEqual(_validate_webhook_url(url), url)

    def test_webhook_secret_is_derived_when_not_configured(self) -> None:
        secret = _resolve_secret_token("example-token", None)

        self.assertEqual(len(secret), 64)
        self.assertNotEqual(secret, "example-token")

    def test_configured_webhook_secret_must_use_telegram_safe_characters(self) -> None:
        with self.assertRaises(ValueError):
            _resolve_secret_token("example-token", "not safe!")


if __name__ == "__main__":
    unittest.main()

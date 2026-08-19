import unittest
from unittest import mock

from backend.mailbox import vmail


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or str(payload)

    def json(self):
        return self._payload


class VmailAdapterTests(unittest.TestCase):
    def test_normalize_base(self):
        self.assertEqual(vmail.normalize_base("https://mail.22y.uk"), "https://mail.22y.uk/api/v1")
        self.assertEqual(vmail.normalize_base("https://mail.22y.uk/"), "https://mail.22y.uk/api/v1")
        self.assertEqual(vmail.normalize_base("https://mail.22y.uk/api"), "https://mail.22y.uk/api/v1")
        self.assertEqual(vmail.normalize_base("https://mail.22y.uk/api/v1"), "https://mail.22y.uk/api/v1")
        self.assertEqual(vmail.normalize_base(""), "https://mail.22y.uk/api/v1")

    def test_create_mailbox(self):
        captured = {}

        def http_post(url, json=None, headers=None, **_kwargs):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp(
                201,
                {
                    "data": {
                        "id": "box1",
                        "address": "abc@example.com",
                        "domain": "example.com",
                    }
                },
            )

        address, token = vmail.create_mailbox(
            http_post,
            "https://mail.22y.uk",
            "test-key",
            domain="example.com",
            local_part="abc",
            expires_in=3600,
        )
        self.assertEqual(address, "abc@example.com")
        self.assertEqual(token, "box1")
        self.assertEqual(captured["url"], "https://mail.22y.uk/api/v1/mailboxes")
        self.assertEqual(captured["headers"]["X-API-Key"], "test-key")
        self.assertEqual(captured["json"]["domain"], "example.com")
        self.assertEqual(captured["json"]["localPart"], "abc")
        self.assertEqual(captured["json"]["expiresIn"], 3600)

    def test_wait_for_code(self):
        calls = {"list": 0, "detail": 0}

        def http_get(url, params=None, headers=None, **_kwargs):
            if url.endswith("/messages"):
                calls["list"] += 1
                return _Resp(200, {"data": [{"id": "m1", "subject": "Verify", "preview": "code"}]})
            if url.endswith("/messages/m1"):
                calls["detail"] += 1
                return _Resp(
                    200,
                    {
                        "data": {
                            "id": "m1",
                            "subject": "Your code",
                            "text": "Your verification code: 123456",
                            "html": "<p>verification code: 123456</p>",
                        }
                    },
                )
            raise AssertionError(url)

        code = vmail.wait_for_code(
            http_get,
            "https://mail.22y.uk",
            "test-key",
            "box1",
            "abc@example.com",
            timeout=5,
            poll_interval=0,
            raise_if_cancelled=lambda _cb: None,
            sleep_with_cancel=lambda _s, _cb: None,
        )
        self.assertEqual(code, "123456")
        self.assertGreaterEqual(calls["list"], 1)
        self.assertEqual(calls["detail"], 1)

    def test_wait_for_code_all_digit_subject(self):
        # 复现 2026-08-19 事故：验证码只在主题里且为纯数字，曾导致无限轮询
        def http_get(url, params=None, headers=None, **_kwargs):
            if url.endswith("/messages"):
                return _Resp(200, {"data": [{"id": "m1", "subject": "SpaceXAI confirmation code: 688-106"}]})
            if url.endswith("/messages/m1"):
                return _Resp(
                    200,
                    {
                        "data": {
                            "id": "m1",
                            "subject": "SpaceXAI confirmation code: 688-106",
                            "text": "Enter this code to finish signing up.",
                            "html": "<style>.sm-w-per-100{width:100%}</style><p>Enter this code to finish signing up.</p>",
                        }
                    },
                )
            raise AssertionError(url)

        code = vmail.wait_for_code(
            http_get,
            "https://mail.22y.uk",
            "test-key",
            "box1",
            "abc@example.com",
            timeout=5,
            poll_interval=0,
            raise_if_cancelled=lambda _cb: None,
            sleep_with_cancel=lambda _s, _cb: None,
        )
        self.assertEqual(code, "688-106")

    def test_create_requires_api_key(self):
        with self.assertRaises(Exception):
            vmail.create_mailbox(mock.Mock(), "https://mail.22y.uk", "")


if __name__ == "__main__":
    unittest.main()

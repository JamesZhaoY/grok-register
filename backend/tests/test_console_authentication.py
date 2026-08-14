import os
import tempfile
import time
import unittest
from unittest import mock

from starlette.requests import Request

from backend.web import application as web_app
from backend.web.application import _create_auth_record, _sign_session, _valid_session


def _make_request(scheme: str = "http", headers: dict | None = None) -> Request:
    raw = [(key.lower().encode("ascii"), value.encode("ascii")) for key, value in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "scheme": scheme,
            "server": ("192.168.1.20", 8787),
            "headers": raw,
            "query_string": b"",
        }
    )


class WebAuthTests(unittest.TestCase):
    def setUp(self):
        self.auth_file = tempfile.NamedTemporaryFile(delete=False)
        self.auth_file.close()
        self.original_auth_file = web_app.WEB_AUTH_FILE
        web_app.WEB_AUTH_FILE = web_app.Path(self.auth_file.name)

    def tearDown(self):
        web_app.WEB_AUTH_FILE = self.original_auth_file
        try:
            os.unlink(self.auth_file.name)
        except FileNotFoundError:
            pass

    def test_signed_session_validates_and_rejects_tampering(self):
        expires = int(time.time()) + 60
        record = _create_auth_record("admin", "password")
        web_app._save_auth_record(record)
        token = _sign_session("admin", expires, record["session_secret"])
        self.assertTrue(_valid_session(token))
        self.assertFalse(_valid_session(token[:-1] + ("0" if token[-1] != "0" else "1")))
        self.assertFalse(_valid_session(_sign_session("other", expires, record["session_secret"])))

    def test_expired_session_is_rejected(self):
        record = _create_auth_record("admin", "password")
        web_app._save_auth_record(record)
        token = _sign_session("admin", int(time.time()) - 1, record["session_secret"])
        self.assertFalse(_valid_session(token))


class SessionCookieSecureTests(unittest.TestCase):
    """纯 HTTP 部署不能发带 Secure 的会话 Cookie，否则浏览器丢弃后表现为登录即 401。"""

    def test_defaults_to_request_scheme(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROK_WEB_COOKIE_SECURE", None)
            self.assertFalse(web_app._session_cookie_secure(_make_request("http")))
            self.assertTrue(web_app._session_cookie_secure(_make_request("https")))

    def test_defaults_follow_forwarded_proto_from_reverse_proxy(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROK_WEB_COOKIE_SECURE", None)
            forwarded = _make_request("http", {"X-Forwarded-Proto": "https"})
            self.assertTrue(web_app._session_cookie_secure(forwarded))
            # 多级代理会拼成 "https, http"，取最外层
            chained = _make_request("http", {"X-Forwarded-Proto": "https, http"})
            self.assertTrue(web_app._session_cookie_secure(chained))
            plain = _make_request("https", {"X-Forwarded-Proto": "http"})
            self.assertFalse(web_app._session_cookie_secure(plain))

    def test_environment_override_wins_both_ways(self):
        with mock.patch.dict(os.environ, {"GROK_WEB_COOKIE_SECURE": "1"}):
            self.assertTrue(web_app._session_cookie_secure(_make_request("http")))
        with mock.patch.dict(os.environ, {"GROK_WEB_COOKIE_SECURE": "0"}):
            self.assertFalse(web_app._session_cookie_secure(_make_request("https")))
        with mock.patch.dict(os.environ, {"GROK_WEB_COOKIE_SECURE": "auto"}):
            self.assertFalse(web_app._session_cookie_secure(_make_request("http")))
            self.assertTrue(web_app._session_cookie_secure(_make_request("https")))


class SessionCookieEndpointTests(unittest.TestCase):
    """守住 /api/auth/setup 与 /api/auth/login 真正下发的 Set-Cookie。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_auth_file = web_app.WEB_AUTH_FILE
        web_app.WEB_AUTH_FILE = web_app.Path(self.tmp.name) / "web_auth.json"
        self.app = web_app.create_app()

    def tearDown(self):
        web_app.WEB_AUTH_FILE = self.original_auth_file
        self.tmp.cleanup()

    def _endpoint(self, path: str):
        return next(route for route in self.app.routes if getattr(route, "path", "") == path).endpoint

    @staticmethod
    def _set_cookie(response) -> str:
        for key, value in response.raw_headers:
            if key.lower() == b"set-cookie":
                return value.decode("latin-1")
        return ""

    def test_plain_http_setup_then_login_issues_usable_cookie(self):
        body = web_app.LoginBody(username="admin", password="password123", confirm_password="password123")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROK_WEB_COOKIE_SECURE", None)
            created = self._set_cookie(self._endpoint("/api/auth/setup")(body, _make_request("http")))
            signed_in = self._set_cookie(
                self._endpoint("/api/auth/login")(
                    web_app.LoginBody(username="admin", password="password123"), _make_request("http")
                )
            )

        for cookie in (created, signed_in):
            self.assertIn(web_app.WEB_SESSION_COOKIE, cookie)
            self.assertNotIn("Secure", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=lax", cookie)
            token = cookie.split(";", 1)[0].split("=", 1)[1]
            self.assertTrue(_valid_session(token))

    def test_https_setup_keeps_secure_flag(self):
        body = web_app.LoginBody(username="admin", password="password123", confirm_password="password123")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROK_WEB_COOKIE_SECURE", None)
            cookie = self._set_cookie(self._endpoint("/api/auth/setup")(body, _make_request("https")))
        self.assertIn("Secure", cookie)


if __name__ == "__main__":
    unittest.main()

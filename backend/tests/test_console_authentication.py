import os
import tempfile
import time
import unittest
from unittest import mock

from backend.web import application as web_app
from backend.web.application import _create_auth_record, _sign_session, _valid_session


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


if __name__ == "__main__":
    unittest.main()

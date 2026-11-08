import asyncio
import copy
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import auth
from app import activities, app


class ASGIClient:
    def __init__(self):
        self.cookies = {}

    def request(self, method, path, body=None, query=None):
        body_bytes = json.dumps(body).encode() if body is not None else b""
        encoded_path, _, existing_query = path.partition("?")
        request_path = unquote(encoded_path)
        query_string = query or existing_query
        headers = [(b"host", b"testserver")]
        if body is not None:
            headers.append((b"content-type", b"application/json"))
        if self.cookies:
            cookie = "; ".join(f"{key}={value}" for key, value in self.cookies.items())
            headers.append((b"cookie", cookie.encode()))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": request_path,
            "raw_path": encoded_path.encode(),
            "query_string": query_string.encode(),
            "root_path": "",
            "headers": headers,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "state": {},
        }
        request_sent = False
        messages = []

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        asyncio.run(app(scope, receive, send))
        response_start = next(message for message in messages if message["type"] == "http.response.start")
        response_body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        response_headers = dict(response_start["headers"])
        set_cookie = response_headers.get(b"set-cookie", b"").decode()
        if set_cookie.startswith("session="):
            cookie_pair = set_cookie.split(";", 1)[0]
            key, value = cookie_pair.split("=", 1)
            if "max-age=0" in set_cookie.lower():
                self.cookies.pop(key, None)
            else:
                self.cookies[key] = value
        data = json.loads(response_body) if response_body else None
        return response_start["status"], response_headers, data


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.users = [
            {
                "username": "student",
                "email": "student@mergington.edu",
                "role": "student",
                "password_hash": auth.hash_password("student-password-123"),
            },
            {
                "username": "parent",
                "email": "parent@mergington.edu",
                "role": "parent",
                "password_hash": auth.hash_password("parent-password-123"),
            },
            {
                "username": "teacher",
                "email": "teacher@mergington.edu",
                "role": "staff",
                "password_hash": auth.hash_password("teacher-password-123"),
            },
        ]

    def setUp(self):
        self.original_users_file = auth.USERS_FILE
        self.original_activities = copy.deepcopy(activities)
        self.temp_dir = tempfile.TemporaryDirectory()
        auth.USERS_FILE = Path(self.temp_dir.name) / "users.json"
        auth.USERS_FILE.write_text(
            json.dumps({"users": self.users}), encoding="utf-8"
        )
        auth._sessions.clear()
        self.client = ASGIClient()

    def tearDown(self):
        activities.clear()
        activities.update(self.original_activities)
        auth._sessions.clear()
        auth.USERS_FILE = self.original_users_file
        self.temp_dir.cleanup()

    def login(self, username, password):
        return self.client.request(
            "POST",
            "/auth/login",
            {"username": username, "password": password},
        )

    def test_password_hashes_and_login_cookie(self):
        status, _, error = self.login("student", "wrong-password-123")
        self.assertEqual(status, 401)
        self.assertEqual(error["detail"], "Invalid username or password")

        status, headers, user = self.login("student", "student-password-123")
        self.assertEqual(status, 200)
        self.assertEqual(user["role"], "student")
        cookie = headers[b"set-cookie"].decode().lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertNotIn("password_hash", user)

        status, _, current_user = self.client.request("GET", "/auth/me")
        self.assertEqual(status, 200)
        self.assertEqual(current_user["email"], "student@mergington.edu")

    def test_signup_requires_student_identity_and_ignores_submitted_email(self):
        status, _, _ = self.client.request(
            "POST",
            "/activities/Chess%20Club/signup?email=someone-else@example.com",
        )
        self.assertEqual(status, 401)

        self.login("student", "student-password-123")
        status, _, _ = self.client.request(
            "POST",
            "/activities/Chess%20Club/signup?email=someone-else@example.com",
        )
        self.assertEqual(status, 200)
        self.assertIn("student@mergington.edu", activities["Chess Club"]["participants"])
        self.assertNotIn("someone-else@example.com", activities["Chess Club"]["participants"])

        self.client = ASGIClient()
        self.login("parent", "parent-password-123")
        status, _, _ = self.client.request("POST", "/activities/Chess%20Club/signup")
        self.assertEqual(status, 403)

    def test_student_cannot_remove_another_participant(self):
        self.login("student", "student-password-123")
        status, _, _ = self.client.request(
            "DELETE",
            "/activities/Chess%20Club/unregister?email=michael%40mergington.edu",
        )
        self.assertEqual(status, 403)
        self.assertIn("michael@mergington.edu", activities["Chess Club"]["participants"])

    def test_student_can_unregister_their_own_signup(self):
        activities["Chess Club"]["participants"].append("student@mergington.edu")
        self.login("student", "student-password-123")
        status, _, _ = self.client.request(
            "DELETE", "/activities/Chess%20Club/unregister"
        )
        self.assertEqual(status, 200)
        self.assertNotIn("student@mergington.edu", activities["Chess Club"]["participants"])

    def test_parent_is_read_only_and_staff_can_manage_roster(self):
        self.login("parent", "parent-password-123")
        status, _, _ = self.client.request(
            "DELETE",
            "/activities/Chess%20Club/unregister?email=michael%40mergington.edu",
        )
        self.assertEqual(status, 403)

        self.client = ASGIClient()
        self.login("teacher", "teacher-password-123")
        status, _, _ = self.client.request(
            "DELETE",
            "/activities/Chess%20Club/unregister?email=michael%40mergington.edu",
        )
        self.assertEqual(status, 200)
        self.assertNotIn("michael@mergington.edu", activities["Chess Club"]["participants"])

    def test_logout_invalidates_session(self):
        self.login("student", "student-password-123")
        status, _, _ = self.client.request("POST", "/auth/logout")
        self.assertEqual(status, 200)
        status, _, _ = self.client.request("GET", "/auth/me")
        self.assertEqual(status, 401)

    def test_account_tool_writes_hashed_private_user_file(self):
        user_file = Path(self.temp_dir.name) / "new-users.json"
        environment = os.environ.copy()
        environment["USERS_FILE"] = str(user_file)
        password = "new-student-password-123"
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "src" / "manage_users.py"),
                "new-student",
                "new-student@mergington.edu",
                "student",
            ],
            input=f"{password}\n{password}\n",
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        user_data = json.loads(user_file.read_text(encoding="utf-8"))
        user = user_data["users"][0]
        self.assertTrue(user["password_hash"].startswith("pbkdf2_sha256$"))
        self.assertNotIn(password, user_file.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(user_file.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()

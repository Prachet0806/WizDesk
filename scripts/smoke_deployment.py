"""Read-only endpoint checks for a running WizDesk deployment."""

import argparse
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


def fetch(base_url, path, *, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = Request(urljoin(base_url + "/", path.lstrip("/")), data=data, headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, response.headers, response.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--allow-http-local", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    parsed = urlparse(base_url)
    local_http = (
        args.allow_http_local
        and parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
    )
    require(parsed.scheme == "https" or local_http, "Deployment URL must use HTTPS")
    require(parsed.hostname is not None and not parsed.username and not parsed.password, "Invalid deployment URL")
    require(parsed.path in ("", "/") and not parsed.query and not parsed.fragment, "Use the service origin without a path or query")

    for path, expected in (
        ("/health/", "alive"),
        ("/ready/", "healthy"),
    ):
        status, headers, body = fetch(base_url, path)
        require(status == 200, f"{path} returned {status}")
        require(json.loads(body)["status"] == expected, f"{path} reported an unhealthy state")
        if not local_http:
            hsts = headers.get("Strict-Transport-Security", "")
            max_age = re.search(r"(?:^|;)\s*max-age=(\d+)(?:;|$)", hsts)
            require(max_age is not None and int(max_age.group(1)) > 0, f"{path} lacks an active HSTS policy")

    for path in ("/static/css/auth.css", "/static/js/api.js"):
        status, _, body = fetch(base_url, path)
        require(status == 200 and body, f"{path} is unavailable")

    status, _, body = fetch(
        base_url,
        "/api/auth/login/",
        payload={"email": "nonexistent-smoke@example.invalid", "password": "wrong"},
    )
    require(status == 401, f"Invalid login returned {status}, expected 401")
    require("Invalid credentials" in body.decode(), "Invalid login response changed")
    checks = "health, database, static assets, invalid login"
    if not local_http:
        checks += ", HSTS"
    print(f"Deployment smoke passed: {checks}")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, ValueError, URLError) as error:
        print(f"Deployment smoke failed: {error}", file=sys.stderr)
        sys.exit(1)

"""Read-only endpoint checks for a running WizDesk deployment."""

import argparse
import http.cookiejar
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = build_opener(HTTPCookieProcessor(COOKIE_JAR))


def fetch(base_url, path, *, payload=None, headers=None, forwarded_proto=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Content-Type": "application/json"} if data is not None else {}
    if forwarded_proto:
        request_headers["X-Forwarded-Proto"] = forwarded_proto
    request_headers.update(headers or {})
    request = Request(urljoin(base_url + "/", path.lstrip("/")), data=data, headers=request_headers)
    try:
        with OPENER.open(request, timeout=10) as response:
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
    parser.add_argument("--forwarded-proto", choices=("http", "https"))
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    parsed = urlparse(base_url)
    local_http = (
        args.allow_http_local
        and parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
    )
    if local_http and args.forwarded_proto == "https":
        # CI sends plain HTTP to localhost while emulating Render's HTTPS
        # proxy header. Permit the secure CSRF cookie on this local-only URL.
        COOKIE_JAR.set_policy(
            http.cookiejar.DefaultCookiePolicy(secure_protocols=("https", "http"))
        )
    require(parsed.scheme == "https" or local_http, "Deployment URL must use HTTPS")
    require(parsed.hostname is not None and not parsed.username and not parsed.password, "Invalid deployment URL")
    require(parsed.path in ("", "/") and not parsed.query and not parsed.fragment, "Use the service origin without a path or query")

    for path, expected in (
        ("/health/", "alive"),
        ("/ready/", "healthy"),
    ):
        status, headers, body = fetch(
            base_url, path, forwarded_proto=args.forwarded_proto
        )
        require(status == 200, f"{path} returned {status}")
        require(json.loads(body)["status"] == expected, f"{path} reported an unhealthy state")
        if not local_http:
            hsts = headers.get("Strict-Transport-Security", "")
            max_age = re.search(r"(?:^|;)\s*max-age=(\d+)(?:;|$)", hsts)
            require(max_age is not None and int(max_age.group(1)) > 0, f"{path} lacks an active HSTS policy")

    for path in ("/static/css/auth.css", "/static/js/api.js"):
        status, _, body = fetch(base_url, path, forwarded_proto=args.forwarded_proto)
        require(status == 200 and body, f"{path} is unavailable")

    csrf_status, _, csrf_body = fetch(
        base_url, "/api/auth/csrf/", forwarded_proto=args.forwarded_proto
    )
    require(csrf_status == 200, f"CSRF bootstrap returned {csrf_status}")
    csrf_token = json.loads(csrf_body)["csrfToken"]
    request_origin = f"{args.forwarded_proto or parsed.scheme}://{parsed.netloc}"
    status, _, body = fetch(
        base_url,
        "/api/auth/login/",
        payload={"email": "nonexistent-smoke@example.invalid", "password": "wrong"},
        headers={"X-CSRFToken": csrf_token, "Origin": request_origin},
        forwarded_proto=args.forwarded_proto,
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

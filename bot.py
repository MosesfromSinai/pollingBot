"""
Smart PollEverywhere Bot (Cookie-based auth for UCR SSO)
========================================================
Monitors a PollEverywhere host for active polls and uses Claude
to reason through the question and select the best answer.

Since UCR uses SSO, this bot uses cookies exported from your browser
session rather than direct login.

SETUP:
1. pip install requests anthropic browser-cookie3
2. Log into PollEverywhere via UCR SSO in Chrome
3. Run this script while Chrome is open (it grabs your session cookies)
"""

import re
import json
import time
import random
import logging
import sys

import requests
import anthropic

try:
    import browser_cookie3
except ImportError:
    print("Missing dependency. Run: pip install browser-cookie3")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── PollEverywhere API URLs ──────────────────────────────────────────

CSRF_URL = "https://pollev.com/proxy/api/csrf_token?_={ts}"
REG_URL = "https://pollev.com/proxy/api/users/{host}/registration_info?_={ts}"
FIREHOSE_URL = (
    "https://firehose-production.polleverywhere.com"
    "/users/{host}/activity/current.json"
    "?{token_param}last_message_sequence=0&_={ts}"
)
POLL_URL = (
    "https://pollev.com/proxy/api/participant"
    "/multiple_choice_polls/{uid}?include=collection"
)
ANSWER_URL = (
    "https://pollev.com/proxy/api/participant"
    "/multiple_choice_polls/{uid}/results"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _ts():
    return str(round(time.time() * 1000))


class SmartPollBot:
    """
    PollEverywhere bot that uses Claude to pick the best answer.
    Authenticates by borrowing cookies from your Chrome browser session.
    """

    def __init__(
        self,
        host: str,
        anthropic_api_key: str,
        model: str = "claude-sonnet-4-20250514",
        subject_hint: str = "",
        closed_wait: float = 5.0,
        open_wait: float = 5.0,
    ):
        self.host = host
        self.model = model
        self.subject_hint = subject_hint
        self.closed_wait = closed_wait
        self.open_wait = open_wait
        self.answered: set[str] = set()

        # Set up HTTP session with browser cookies
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._load_browser_cookies()

        # Set up Claude client
        self.claude = anthropic.Anthropic(api_key=anthropic_api_key)

    def _load_browser_cookies(self):
        """Load PollEverywhere cookies from Chrome."""
        log.info("Loading cookies from Chrome...")
        try:
            cookies = browser_cookie3.chrome(domain_name=".polleverywhere.com")
            self.session.cookies.update(cookies)
            log.info("Loaded PollEverywhere cookies from Chrome.")
        except Exception as e:
            log.error("Failed to load Chrome cookies: %s", e)
            log.error(
                "Make sure you're logged into PollEverywhere in Chrome "
                "and Chrome is closed or allows cookie access."
            )
            sys.exit(1)

        # Also grab pollev.com cookies
        try:
            cookies2 = browser_cookie3.chrome(domain_name=".pollev.com")
            self.session.cookies.update(cookies2)
        except Exception:
            pass  # Not all cookies may be under this domain

    # ── CSRF ─────────────────────────────────────────────────────────

    def _csrf(self) -> str:
        r = self.session.get(CSRF_URL.format(ts=_ts()))
        r.raise_for_status()
        token = r.json()["token"]
        self.session.headers["x-csrf-token"] = token
        return token

    # ── Firehose / poll detection ────────────────────────────────────

    def _firehose_token(self) -> str | None:
        r = self.session.get(REG_URL.format(host=self.host, ts=_ts()))
        r.raise_for_status()
        data = r.json()
        token = data.get("firehose_token")
        if token:
            log.info("Got firehose token for host '%s'.", self.host)
        else:
            log.info("No firehose token (will poll without one).")
        return token

    def _poll_id(self, firehose_token: str | None) -> str | None:
        token_param = (
            f"firehose_token={firehose_token}&" if firehose_token else ""
        )
        url = FIREHOSE_URL.format(
            host=self.host, token_param=token_param, ts=_ts()
        )
        try:
            r = self.session.get(url, timeout=10)
            r.raise_for_status()
            msg = json.loads(r.json()["message"])
            uid = msg["uid"]
            if uid not in self.answered:
                return uid
        except (requests.Timeout, KeyError, json.JSONDecodeError):
            pass
        return None

    # ── Fetch poll details ───────────────────────────────────────────

    def _fetch_poll(self, uid: str) -> dict:
        self._csrf()
        r = self.session.get(POLL_URL.format(uid=uid))
        r.raise_for_status()
        return r.json()

    # ── Ask Claude ───────────────────────────────────────────────────

    def _ask_claude(self, question: str, options: list[dict]) -> str:
        choices_text = "\n".join(
            f"  {i+1}. {opt.get('value') or opt.get('keyword') or opt.get('description', '(no text)')}"
            for i, opt in enumerate(options)
        )

        subject_line = ""
        if self.subject_hint:
            subject_line = f"This is a {self.subject_hint} class. "

        prompt = (
            f"{subject_line}"
            f"A multiple-choice poll question was just asked in class.\n\n"
            f"Question: {question}\n\n"
            f"Options:\n{choices_text}\n\n"
            f"Which option number (1-{len(options)}) is most likely correct? "
            f"Be brief. Respond with ONLY the option number."
        )

        log.info("Asking Claude: %s", question)

        response = self.claude.messages.create(
            model=self.model,
            max_tokens=128,
            messages=[{"role": "user", "content": prompt}],
        )

        reply = response.content[0].text.strip()
        log.info("Claude's reasoning:\n%s", reply)

        # Extract the last number in the response
        numbers = re.findall(r"\d+", reply)
        if not numbers:
            log.warning("Could not parse Claude's answer, picking randomly.")
            return random.choice(options)["id"]

        choice = int(numbers[-1])
        if 1 <= choice <= len(options):
            selected = options[choice - 1]
            log.info(
                "Selected option %d: %s",
                choice,
                selected.get("value") or selected.get("description", ""),
            )
            return selected["id"]

        log.warning("Claude returned out-of-range %d, picking randomly.", choice)
        return random.choice(options)["id"]

    # ── Submit answer ────────────────────────────────────────────────

    def _submit(self, uid: str, option_id: str):
        self._csrf()
        r = self.session.post(
            ANSWER_URL.format(uid=uid),
            data={
                "option_id": option_id,
                "isPending": True,
                "source": "pollev_page",
            },
        )
        r.raise_for_status()
        log.info("Answer submitted! (HTTP %d)", r.status_code)
        return r.json() if r.text else {}

    # ── Main loop ────────────────────────────────────────────────────

    def run(self):
        """Start monitoring for polls."""
        log.info("Verifying session...")
        self._csrf()
        firehose_token = self._firehose_token()
        log.info(
            "Monitoring host '%s' for polls... (Ctrl+C to stop)", self.host
        )

        while True:
            try:
                log.info("Checking for polls...")
                uid = self._poll_id(firehose_token)
                if uid is None:
                    log.info("No active poll. Next check in %ds.", self.closed_wait)
                    time.sleep(self.closed_wait)
                    continue

                log.info(">>> New poll detected: %s", uid)
                time.sleep(self.open_wait)

                poll = self._fetch_poll(uid)
                options = poll.get("options", [])
                question = (
                    poll.get("title")
                    or poll.get("question")
                    or poll.get("prompt")
                    or "(no question text found)"
                )

                if not options:
                    log.warning("Poll has no options, skipping.")
                    self.answered.add(uid)
                    continue

                log.info("Question: %s", question)
                log.info("Options: %s", [o.get("value") or o.get("description") for o in options])

                option_id = self._ask_claude(question, options)
                self._submit(uid, option_id)
                self.answered.add(uid)

                log.info(">>> Done! Waiting for next poll...\n")

            except KeyboardInterrupt:
                log.info("Stopped by user.")
                break
            except Exception as e:
                log.error("Error: %s", e, exc_info=True)
                time.sleep(self.closed_wait)


# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    if not ANTHROPIC_API_KEY:
        print("Set your Anthropic API key:")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        print("Then run this script again.")
        sys.exit(1)

    bot = SmartPollBot(
        host="elaheh",                     # your professor's PollEv username
        anthropic_api_key=ANTHROPIC_API_KEY,
        subject_hint="computer science",   # helps Claude answer better
        closed_wait=30,                    # seconds between checks
        open_wait=0,                       # no delay before answering
    )
    bot.run()
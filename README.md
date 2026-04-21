# PollingBot

An automated PollEverywhere bot that uses Claude AI to answer multiple-choice poll questions. It monitors a professor's PollEverywhere host, detects new polls, sends the question to Claude, and submits the best answer — all within seconds.

Built for UCR SSO authentication. The bot borrows your Chrome session cookies so you don't need to handle SSO login in code.

## Requirements

- **Python 3.10+**
- **Google Chrome** (logged into PollEverywhere via UCR SSO)
- **Anthropic API key** ([get one here](https://console.anthropic.com))

## Setup

### 1. Install Python

Check if you have it:

```bash
python3 --version
```

If not installed or below 3.10, download from [python.org/downloads](https://www.python.org/downloads/). On macOS you can also use Homebrew:

```bash
brew install python
```

### 2. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/PollingBot.git
cd PollingBot
```

### 3. Install dependencies

```bash
pip install requests anthropic browser-cookie3
```

If `pip` doesn't work, try `pip3`. If you're using conda:

```bash
pip install requests anthropic browser-cookie3
```

### 4. Log into PollEverywhere in Chrome

1. Open Chrome
2. Go to [pollev.com](https://www.polleverywhere.com/login)
3. Log in with your UCR SSO credentials
4. Complete the Duo/MFA prompt on your phone
5. You should see your PollEverywhere home page

**Keep Chrome open** — the bot reads cookies from Chrome's storage.

### 5. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY='sk-ant-your-key-here'
```

To avoid setting this every time, add it to your shell profile:

```bash
# For zsh (default on macOS):
echo "export ANTHROPIC_API_KEY='sk-ant-your-key-here'" >> ~/.zshrc
source ~/.zshrc

# For bash:
echo "export ANTHROPIC_API_KEY='sk-ant-your-key-here'" >> ~/.bashrc
source ~/.bashrc
```

Or create a `.env` file in the project directory:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

(Requires `python-dotenv` — `pip install python-dotenv` — and loading it in the script.)

### 6. Run the bot

```bash
cd PollingBot
python3 bot.py
```

You should see:

```
2026-04-21 11:57:29 [INFO] Loading cookies from Chrome...
2026-04-21 11:57:36 [INFO] Loaded PollEverywhere cookies from Chrome.
2026-04-21 11:57:36 [INFO] Verifying session...
2026-04-21 11:57:36 [INFO] Monitoring host 'elaheh' for polls... (Ctrl+C to stop)
```

Press `Ctrl+C` to stop.

## Configuration

Edit the bottom of `bot.py` to change settings:

```python
bot = SmartPollBot(
    host="elaheh",                     # professor's PollEv username
    anthropic_api_key=ANTHROPIC_API_KEY,
    subject_hint="computer science",   # helps Claude answer accurately
    closed_wait=30,                    # seconds between poll checks
    open_wait=0,                       # seconds to wait before answering
)
```

| Setting | Default | Description |
|---|---|---|
| `host` | `"elaheh"` | Your professor's PollEverywhere username (from their poll URL: `pollev.com/username`) |
| `subject_hint` | `"computer science"` | Tell Claude what class this is for — be specific (e.g., `"data structures"`, `"operating systems"`) for better answers |
| `closed_wait` | `30` | How often (in seconds) to check for new polls |
| `open_wait` | `0` | Delay before submitting an answer after detecting a poll |
| `model` | `"claude-sonnet-4-20250514"` | Claude model to use. Sonnet is fast (~3-5s). Opus is smarter but slower (~10-15s). |

## macOS Keychain Prompt

The first time you run the bot, macOS will ask for your **Mac login password** to allow access to Chrome's cookie storage. Enter your password and click **"Always Allow"** so it doesn't ask again.

## Troubleshooting

**"Login failed" or 401 error**
You're running an old version of the script that tries email/password login. Make sure you have the cookie-based version.

**"Failed to load Chrome cookies"**
- Make sure you're logged into PollEverywhere in Chrome
- Try closing Chrome completely, then rerun the bot
- Make sure you clicked "Always Allow" on the Keychain prompt

**"Set your Anthropic API key"**
Run `export ANTHROPIC_API_KEY='your-key'` before running the bot, or add it to your shell profile (see step 5).

**"No firehose token"**
This is normal — the bot will still work, it just polls differently. No action needed.

**Session expired**
If the bot stops detecting polls or gets errors, your Chrome session may have expired. Log into PollEverywhere in Chrome again and restart the bot.

## How it works

1. Reads your PollEverywhere session cookies from Chrome
2. Polls the PollEverywhere firehose API every 30 seconds for active polls
3. When a poll is detected, fetches the question and answer options
4. Sends the question to Claude (Sonnet) and asks for the best answer
5. Submits the answer via the PollEverywhere API
6. Waits for the next poll

## Cost

Each poll question costs roughly **$0.002–$0.005** in API usage (a fraction of a cent). A full quarter of daily polls would cost well under $1 total.

## Disclaimer

This tool is for educational purposes only. Use at your own risk.
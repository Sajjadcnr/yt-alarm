# YouTube Analytics Telegram Bot

Serverless YouTube channel monitor. Runs entirely inside **GitHub Actions**,
polls **YouTube Data API v3** once per hour, compares the results against the
previous run (stored in `data/stats.json` in this repo), and sends a report
to a **Telegram** chat. No server, no `while True: sleep()` loop — every run
starts cold and exits when done.

## Project structure

```text
youtube-telegram-monitor/
├── .github/workflows/youtube-monitor.yml   # hourly cron + manual trigger
├── src/
│   ├── main.py         # orchestrates one run: fetch -> compare -> notify -> save
│   ├── youtube.py      # YouTube Data API v3 client (quota-efficient)
│   ├── telegram.py     # Telegram Bot API client + command handling
│   ├── storage.py      # stats.json read/write + growth calculation
│   ├── formatter.py    # builds the Telegram report text
│   └── config.py       # env var / secrets loading
├── data/stats.json     # persisted state, committed back by the workflow
├── tests/               # pytest unit tests
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── .gitignore
```

## How it avoids burning YouTube API quota

```text
channels.list        (1 unit)  -> subscriber/view/video counts + uploads playlist id
playlistItems.list   (1 unit/page, 50 items/page) -> every video id, paginated
videos.list           (1 unit/call, up to 50 ids/call, batched) -> stats for all videos
```

`search.list` is never used (it's far more expensive and unnecessary — the
uploads playlist already lists every public video on the channel).

With the default 10,000 units/day quota, a channel with a few hundred videos
costs only a handful of units per hourly run.

## Required GitHub Secrets

Go to **Repository → Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Description |
|---|---|
| `YOUTUBE_API_KEY` | API key from Google Cloud Console |
| `YOUTUBE_CHANNEL_ID` | The channel's `UC...` id |
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather |
| `TELEGRAM_CHAT_ID` | The chat that should receive reports |

Optional repository **variable** (Settings → Secrets and variables → Actions → Variables):

| Variable | Default | Description |
|---|---|---|
| `MAX_VIDEOS_IN_REPORT` | `20` | Max videos shown in the Telegram report (all videos are still checked) |

None of these are ever printed to logs.

## How to get a YouTube API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or reuse one).
3. Go to **APIs & Services → Library**, search for **YouTube Data API v3**, click **Enable**.
4. Go to **APIs & Services → Credentials → Create Credentials → API key**.
5. (Recommended) Restrict the key to the YouTube Data API v3.
6. Copy the key — this is `YOUTUBE_API_KEY`.

## How to get your Channel ID

1. Go to your channel on YouTube.
2. Click **Customize channel → Basic info**, or open `https://www.youtube.com/channel/UC.../about` — the `UC...` segment is the channel id.
3. Alternatively use [commentpicker.com/youtube-channel-id.php](https://commentpicker.com/youtube-channel-id.php) with your handle/URL.

This is `YOUTUBE_CHANNEL_ID`.

## How to create a Telegram Bot

1. Open Telegram, search for **@BotFather**.
2. Send `/newbot` and follow the prompts (choose a name and a username ending in `bot`).
3. BotFather replies with a token like `123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.

This is `TELEGRAM_BOT_TOKEN`.

## How to get your Telegram Chat ID

1. Send any message to your new bot (or add it to a group/channel).
2. Open in a browser: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Look for `"chat":{"id": ...}` in the JSON response — that number is your `TELEGRAM_CHAT_ID`.

For a private chat, this is a positive number. For groups it's usually negative.

## Setting up the repository

1. Push this project to a new GitHub repository.
2. Add the four secrets above (Settings → Secrets and variables → Actions → Secrets).
3. Optionally add the `MAX_VIDEOS_IN_REPORT` variable.
4. Go to the **Actions** tab and enable workflows if prompted.
5. Open the **YouTube Monitor** workflow and click **Run workflow** to trigger the first run manually.
6. Check your Telegram chat for the first report — it will show `N/A` for growth (there's no previous data to compare against yet).
7. From then on, it runs automatically every hour.

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt

cp .env.example .env
# edit .env with your real values

PYTHONPATH=src python src/main.py
```

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## How GitHub Actions runs it

The workflow at `.github/workflows/youtube-monitor.yml`:

1. Triggers on a schedule (`17 * * * *` — hourly, at minute 17 to avoid the
   top-of-hour congestion GitHub warns scheduled workflows can hit) and on
   `workflow_dispatch` (manual trigger).
2. Uses a `concurrency` group so overlapping runs never execute at the same time.
3. Checks out the repo, installs dependencies, runs `src/main.py` with the
   secrets as environment variables.
4. If `data/stats.json` changed, commits and pushes it, rebasing onto the
   latest remote state first and retrying on conflict — so two close-together
   runs can't crash each other's commit.

## Manually triggering a run

**Actions tab → YouTube Monitor → Run workflow → Run workflow** button.

## Changing the interval

Edit the `cron` expression in `.github/workflows/youtube-monitor.yml`:

```yaml
on:
  schedule:
    - cron: "17 * * * *"   # every hour at minute 17
```

Examples:
- Every 30 minutes: `"17,47 * * * *"`
- Every 6 hours: `"17 */6 * * *"`
- Once a day at 09:17 UTC: `"17 9 * * *"`

GitHub Actions cron times are always in UTC regardless of the `TIMEZONE`
setting used for displaying the report time.

## Telegram commands

Since there's no always-on server, commands are answered once per scheduled
run (a `getUpdates` poll happens right after the report is sent):

- `/start` — welcome message + command list
- `/stats` — last saved channel stats (subscribers, views, video count)
- `/videos` — all tracked videos ranked by views
- `/help` — command list

Only messages from `TELEGRAM_CHAT_ID` are answered.

## Data persistence & edge cases

- **First run**: no `data/stats.json` history yet → growth is reported as `N/A`, never a fabricated number.
- **New video**: flagged with a `🆕 New Video` section; growth is calculated starting the *next* run.
- **Video disappears from the channel** (private/deleted/API hiccup): it's kept in `stats.json` with `"status": "missing"` instead of being deleted immediately. After 3 consecutive missing runs it's marked `"status": "archived"` and excluded from future reports.
- **YouTube API error / quota exceeded**: the run fails loudly in the workflow log, a best-effort Telegram error message is sent, and `stats.json` is left untouched (no bad data is written).
- **Telegram send failure**: retried up to 3 times with backoff; if it still fails, the run exits non-zero without corrupting `stats.json`.

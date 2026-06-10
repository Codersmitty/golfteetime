# golfteetime

Polls public golf courses every 5 minutes for available tee times matching the
criteria in [`watches.json`](./watches.json), and emails when a new slot opens.

Supported courses (selectable in the control panel):
Baylands Golf Links, Sharp Park, Shoreline Golf Links, Crystal Springs (all via
GolfNow), and Poppy Ridge (via ForeUp).

## Control panel (web UI)

A point-and-click control panel lives at:

**https://codersmitty.github.io/golfteetime/**

From there you can edit watches, turn the bot on/off, trigger a run, and send a
test email — from any phone or computer. It's served by GitHub Pages from the
[`docs/`](./docs) folder. The first time you use it, you paste a GitHub token
(saved only in your browser) so it can write changes back to this repo.

## Changing what's monitored

Open [`watches.json`](./watches.json) on GitHub, click the pencil (edit) icon,
edit the `watches` list, and click **Commit changes**. Each entry has:

| Field | What it means |
| --- | --- |
| `course` | Must match a key in the `courses` object (case-sensitive) |
| `date` | `YYYY-MM-DD` |
| `time_start` / `time_end` | 24-hour `HH:MM`, inclusive window |
| `players` | Minimum spots needed |
| `max_price` | Skip if price per player exceeds this. `0` = no limit |

You can have multiple watches for the same course (e.g. different dates).
The next scheduled run picks up the new file automatically.

## Required GitHub Secrets

| Name | Value |
| --- | --- |
| `ALERT_EMAIL_FROM` | Gmail address sending the alert |
| `ALERT_EMAIL_PASSWORD` | Gmail [app password](https://myaccount.google.com/apppasswords) (NOT the account password) |
| `ALERT_EMAIL_TO` | Recipient address |

Set these at: **Settings → Secrets and variables → Actions → New repository secret**.

## Notes

- Cache of already-alerted slots is committed back to `cache/alerted.json` to
  prevent duplicate alerts across runs. Entries auto-prune once the date passes.
- Poppy Hills is intentionally not polled: ForeUp booking classes for it are
  NCGA member-only. Adding it requires storing NCGA credentials and a
  Playwright-driven login flow.
- GitHub Actions cron is best-effort — actual run cadence can drift to
  10–20 minutes during peak load.

## Local run

```sh
pip install -r requirements.txt
python -m playwright install chromium
ALERT_EMAIL_FROM=... ALERT_EMAIL_PASSWORD=... ALERT_EMAIL_TO=... \
  python tee_time_monitor.py
```

# golfteetime

Polls Baylands Golf Links (via GolfNow) and Poppy Ridge (via ForeUp) every
5 minutes for available tee times matching the criteria in
`tee_time_monitor.py`, and emails when a new slot opens.

Schedules and filters are defined in the `WATCHES` list at the top of
`tee_time_monitor.py`. Edit it and commit to change what's monitored.

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

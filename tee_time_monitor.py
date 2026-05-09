"""
Tee Time Monitor — Baylands (GolfNow), Poppy Ridge (ForeUp).

Polls each course's actual booking backend and emails when a matching slot
opens up. Designed to run on a schedule (GitHub Actions or local cron).
"""

import json
import os
import smtplib
import sys
import time as _time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent
CACHE_FILE = REPO_ROOT / "cache" / "alerted.json"

WATCHES = [
    {
        "course": "Baylands Golf Links",
        "platform": "golfnow",
        "facility_id": 9259,
        "lat": 37.44936,
        "lon": -122.12526,
        "date": "2026-05-16",
        "time_start": "06:00",
        "time_end": "12:00",
        "players": 4,
        "max_price": 120,
    },
    {
        "course": "Poppy Ridge",
        "platform": "foreup",
        "course_id": 20938,
        "schedule_id": 11715,
        "booking_class": 50613,
        "date": "2026-05-16",
        "time_start": "06:00",
        "time_end": "12:00",
        "players": 4,
        "max_price": 0,
    },
    # Poppy Hills is intentionally not included: ForeUp booking classes for
    # Poppy Hills are NCGA member-only (online_booking_protected=1). A reliable
    # poller requires NCGA member credentials. Add it back once we have those.
]

ALERT_FROM = os.getenv("ALERT_EMAIL_FROM", "")
ALERT_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "")
ALERT_TO = os.getenv("ALERT_EMAIL_TO", "")


def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True))


def prune_cache(cache):
    today = datetime.now().date().isoformat()
    return {k: v for k, v in cache.items() if k.split("|")[1] >= today}


def time_in_window(hhmm, start_str, end_str):
    t = datetime.strptime(hhmm, "%H:%M").time()
    s = datetime.strptime(start_str, "%H:%M").time()
    e = datetime.strptime(end_str, "%H:%M").time()
    return s <= t <= e


def send_alert(subject, body):
    if not (ALERT_FROM and ALERT_PASSWORD and ALERT_TO):
        print(f"[ALERT — no email configured]\n{subject}\n{body}")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = ALERT_FROM
    msg["To"] = ALERT_TO
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(ALERT_FROM, ALERT_PASSWORD)
        server.sendmail(ALERT_FROM, ALERT_TO, msg.as_string())
    print(f"[EMAIL SENT] {subject}")


# --- Poppy Ridge / ForeUp ----------------------------------------------------

FOREUP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://foreupsoftware.com/",
}


def check_foreup(watch):
    date_obj = datetime.strptime(watch["date"], "%Y-%m-%d")
    params = {
        "time": "all",
        "date": date_obj.strftime("%m-%d-%Y"),
        "holes": "all",
        "players": "0",
        "booking_class": str(watch["booking_class"]),
        "schedule_id": str(watch["schedule_id"]),
        "schedule_ids[]": str(watch["schedule_id"]),
        "specials_only": "0",
        "api_key": "no_limits",
    }
    referer = f"https://foreupsoftware.com/index.php/booking/{watch['course_id']}"
    headers = {**FOREUP_HEADERS, "Referer": referer}
    url = "https://foreupsoftware.com/index.php/api/booking/times"

    resp = requests.get(url, params=params, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        print(f"  [ForeUp] unexpected response: {data!r}")
        return []

    slots = []
    for tt in data:
        try:
            tee_dt = datetime.strptime(tt["time"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            continue
        if tee_dt.date() != date_obj.date():
            continue
        hhmm = tee_dt.strftime("%H:%M")
        if not time_in_window(hhmm, watch["time_start"], watch["time_end"]):
            continue
        avail = int(tt.get("available_spots", 0) or 0)
        if avail < watch["players"]:
            continue
        # ForeUp doesn't return a price field on this endpoint; treat as 0/TBD.
        price = 0.0
        slots.append({
            "time": hhmm,
            "price": price,
            "available": avail,
            "url": referer,
        })
    return slots


# --- Baylands / GolfNow ------------------------------------------------------

def _hhmm_to_halfhours(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 2 + (1 if int(m) >= 30 else 0)


def check_golfnow(watch):
    """Drive GolfNow's SPA via Playwright and capture the tee-time JSON XHR.

    GolfNow's `/api/tee-times/tee-time-search-results` POST endpoint is gated
    by browser-side session/CSRF state and refuses bare HTTP calls. Loading
    the search page and intercepting the response is the most reliable path.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [GolfNow] playwright not installed")
        return []

    date_obj = datetime.strptime(watch["date"], "%Y-%m-%d")
    slug = watch["course"].lower().replace(" ", "-")
    page_url = (
        f"https://www.golfnow.com/tee-times/facility/{watch['facility_id']}-{slug}/search"
        f"?Date={date_obj.strftime('%Y-%m-%d')}"
        f"&Players={watch['players']}"
        f"&Holes=18"
    )

    captured = []

    def on_response(resp):
        if "tee-time-search-results" in resp.url and resp.status == 200:
            try:
                captured.append(resp.json())
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = ctx.new_page()
        page.on("response", on_response)
        try:
            page.goto(page_url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
        except Exception as e:
            print(f"  [GolfNow] navigation error: {e}")
        browser.close()

    if not captured:
        print("  [GolfNow] no search-results response captured")
        return []

    payload = captured[-1]
    tee_times = (payload.get("ttResults") or {}).get("teeTimes") or payload.get("results") or []

    slots = []
    for tt in tee_times:
        if tt.get("facilityId") and tt["facilityId"] != watch["facility_id"]:
            continue
        rates = tt.get("rates") or []
        if not rates:
            continue
        rate = rates[0]
        raw_time = rate.get("teeTime") or tt.get("teeOffTime") or tt.get("date")
        if not raw_time:
            continue
        try:
            if isinstance(raw_time, str) and "T" in raw_time:
                tee_dt = datetime.fromisoformat(raw_time.split(".")[0].replace("Z", ""))
            elif isinstance(raw_time, str):
                tee_dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
            else:
                continue
        except ValueError:
            continue
        if tee_dt.date() != date_obj.date():
            continue
        hhmm = tee_dt.strftime("%H:%M")
        if not time_in_window(hhmm, watch["time_start"], watch["time_end"]):
            continue

        avail = int(rate.get("playerCount", tt.get("maxPlayers", 0)) or 0)
        if avail and avail < watch["players"]:
            continue

        price_obj = rate.get("greenFeeRate") or rate.get("greenFee") or {}
        price = float(price_obj.get("value", 0) or 0)
        if watch["max_price"] and price > watch["max_price"]:
            continue

        slots.append({
            "time": hhmm,
            "price": price,
            "available": avail or watch["players"],
            "url": page_url,
        })
    return slots


# --- Driver ------------------------------------------------------------------

def check_all():
    cache = prune_cache(load_cache())
    new_finds = []

    for watch in WATCHES:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {watch['course']} on {watch['date']} ({watch['players']}p, {watch['time_start']}–{watch['time_end']})")
        try:
            if watch["platform"] == "foreup":
                slots = check_foreup(watch)
            elif watch["platform"] == "golfnow":
                slots = check_golfnow(watch)
            else:
                slots = []
        except Exception as e:
            print(f"  [error] {e}")
            slots = []

        if not slots:
            print("  no matching times")
            continue

        for slot in slots:
            cache_key = f"{watch['course']}|{watch['date']}|{slot['time']}"
            if cache_key in cache:
                continue
            print(f"  ✓ FOUND {slot['time']} (avail={slot['available']}, ${slot['price']:.0f})")
            new_finds.append({**watch, **slot})
            cache[cache_key] = datetime.now().isoformat()

    if new_finds:
        lines = []
        for f in new_finds:
            price_str = f"${f['price']:.0f}/player" if f["price"] else "price TBD"
            lines.append(
                f"• {f['course']} — {f['date']} at {f['time']} ({price_str})\n"
                f"  Book: {f['url']}"
            )
        body = "Tee times opened up:\n\n" + "\n\n".join(lines)
        send_alert("⛳ Tee time alert", body)

    save_cache(cache)
    return new_finds


if __name__ == "__main__":
    check_all()

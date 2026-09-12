"""Fetch a Dexcom Share reading, store it, and send a useful alert."""

import os
import requests
from datetime import datetime, timezone

from pydexcom import Dexcom
from pydexcom.const import Region

DEXCOM_USERNAME = os.environ.get("DEXCOM_SHARE_USERNAME")
DEXCOM_ACCOUNT_ID = os.environ.get("DEXCOM_ACCOUNT_ID")
DEXCOM_PASSWORD = os.environ["DEXCOM_SHARE_PASSWORD"]
DEXCOM_REGION = Region(os.environ.get("DEXCOM_REGION", "us").lower())
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
ONESIGNAL_APP_ID = os.environ["ONESIGNAL_APP_ID"]
ONESIGNAL_API_KEY = os.environ["ONESIGNAL_API_KEY"]

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


# ---------- Dexcom Share ----------

def fetch_latest_reading() -> tuple[int, str]:
    if DEXCOM_ACCOUNT_ID:
        dexcom = Dexcom(account_id=DEXCOM_ACCOUNT_ID, password=DEXCOM_PASSWORD, region=DEXCOM_REGION)
    elif DEXCOM_USERNAME:
        dexcom = Dexcom(username=DEXCOM_USERNAME, password=DEXCOM_PASSWORD, region=DEXCOM_REGION)
    else:
        raise RuntimeError("Set DEXCOM_ACCOUNT_ID or DEXCOM_SHARE_USERNAME")
    reading = dexcom.get_current_glucose_reading()
    if reading is None:
        raise RuntimeError("Dexcom Share returned no current glucose reading")

    glucose = int(reading.value)
    trend = getattr(reading, "trend_arrow", None) or getattr(reading, "trend", "→")
    return glucose, normalize_trend(trend)


def normalize_trend(trend: object) -> str:
    value = str(trend)
    arrows = {
        "DoubleUp": "↑↑",
        "SingleUp": "↑",
        "FortyFiveUp": "↗",
        "Flat": "→",
        "FortyFiveDown": "↘",
        "SingleDown": "↓",
        "DoubleDown": "↓↓",
    }
    if value in arrows:
        return arrows[value]
    return value if value in {"↑↑", "↑", "↗", "→", "↘", "↓", "↓↓"} else "→"


# ---------- Supabase (readings + de-dupe state) ----------

def store_reading(glucose: int, trend_arrow: str) -> None:
    requests.post(
        f"{SUPABASE_URL}/rest/v1/readings",
        headers=SUPABASE_HEADERS,
        json={"glucose": glucose, "trend_arrow": trend_arrow},
        timeout=15,
    ).raise_for_status()


def get_last_notify_key() -> str | None:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/notify_state?id=eq.last",
        headers=SUPABASE_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0]["value"] if rows else None


def set_last_notify_key(value: str) -> None:
    requests.post(
        f"{SUPABASE_URL}/rest/v1/notify_state",
        headers={**SUPABASE_HEADERS, "Prefer": "resolution=merge-duplicates"},
        json={"id": "last", "value": value},
        timeout=15,
    ).raise_for_status()


# ---------- classification ----------

def classify(glucose: int) -> str:
    if glucose < 70:
        return "low"
    if glucose <= 160:
        return "range"
    if glucose <= 220:
        return "high"
    return "very-high"


def meal_window(now: datetime) -> str | None:
    h = now.hour
    if 7 <= h < 9:
        return "breakfast"
    if 12 <= h < 13:
        return "lunch"
    if 17 <= h < 19:
        return "dinner"
    return None


# ---------- Grok message generation ----------

def generate_message(kind: str, glucose: int, trend_arrow: str, meal: str | None = None) -> str:
    if kind == "alert":
        prompt = (
            f"The user's glucose reading is {glucose} mg/dL with a {trend_arrow} trend, "
            f"which is a notable low, high, or fast-moving event. Write a short (under 25 words), dry and "
            f"slightly sarcastic but caring push-notification message about it. "
            f"No medical dosing advice, no exclamation points."
        )
    else:
        prompt = (
            f"It's {meal} time and the user's glucose is {glucose} mg/dL. "
            f"Write a short (under 25 words), dry and slightly sarcastic "
            f"push-notification nudge suggesting they check the app for a meal idea."
        )

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 60,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ---------- OneSignal ----------

def send_push(title: str, message: str) -> None:
    requests.post(
        "https://onesignal.com/api/v1/notifications",
        headers={
            "Authorization": f"Basic {ONESIGNAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "app_id": ONESIGNAL_APP_ID,
            "included_segments": ["Subscribed Users"],
            "headings": {"en": title},
            "contents": {"en": message},
        },
        timeout=15,
    ).raise_for_status()


# ---------- main ----------

def main() -> None:
    glucose, trend_arrow = fetch_latest_reading()

    store_reading(glucose, trend_arrow)

    state = classify(glucose)
    now = datetime.now(timezone.utc)
    meal = meal_window(now)
    last_key = get_last_notify_key()

    event_key = None
    fast_trend = trend_arrow in ("↑↑", "↓↓")
    alert_event = state in ("low", "very-high") or (fast_trend and state in ("low-ish", "high"))
    if alert_event:
        event_key = f"{state}-{trend_arrow}"
    elif meal:
        event_key = f"meal-{meal}-{now.date()}"  # one nudge per meal window per day

    if event_key and event_key != last_key:
        if alert_event:
            msg = generate_message("alert", glucose, trend_arrow)
            send_push("Sugar Buddy", msg)
        elif meal:
            msg = generate_message("meal", glucose, trend_arrow, meal)
            send_push(f"baseline — {meal.title()} time", msg)
        set_last_notify_key(event_key)


if __name__ == "__main__":
    main()

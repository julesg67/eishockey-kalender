
import calendar
import re
import requests

from datetime import date, datetime, timezone
from html import unescape
from zoneinfo import ZoneInfo
from icalendar import Calendar, Event


# --------------------------------------------------
# Einstellungen
# --------------------------------------------------

URL = "https://booking.locaboo.com/calendar/load_events"

TEAMS = {
    "Royal Bavarians": "Royal_Bavarians.ics",
    "Tigers Roßhaupten": "Tigers_Rosshaupten.ics",
}
CABIN_NAMES = {
    "23090": "ARENA - K1",
    "23091": "ARENA - K2",
    "23092": "ARENA - K3",
    "23093": "ARENA - K4",
    "23094": "ARENA - A",
    "23095": "ARENA - B",
    "23096": "ARENA - Links",
    "23097": "ARENA - Rechts",
    "23176": "ARENA - EK 1",
    "23177": "ARENA - EK 2",
    "58126": "ARENA - SR",

    "23109": "H1 - Kabine 1",
    "23110": "H1 - Kabine 2",
    "23111": "H1 - Kabine 3",
    "23112": "H1 - Kabine 4",
    "23113": "H1 - Gymnastikumkleide",
    "23755": "H1 - Allgemeiner Lauf",
    "60719": "H1 - Mehrzweckkabine",
    "83262": "H1 - Schiedsrichterkabine",
    "93286": "DEB Profikabine",
}

TZ = ZoneInfo("Europe/Berlin")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": (
        "https://booking.locaboo.com/de/"
        "bundesstuetzpunkt-fuer-eishockey-und-curling-stadt-fuessen/"
        "belegungsplan"
    ),
}


# --------------------------------------------------
# Zeitraum: aktueller Monat + zwei Folgemonate
# --------------------------------------------------

today = date.today()
start_date = today.replace(day=1)

end_month = today.month + 2
end_year = today.year + (end_month - 1) // 12
end_month = (end_month - 1) % 12 + 1

last_day = calendar.monthrange(end_year, end_month)[1]
end_date = date(end_year, end_month, last_day)

date_from = start_date.isoformat()
date_to = end_date.isoformat()


# --------------------------------------------------
# Locaboo-Daten abrufen
# --------------------------------------------------

def load_events(locations, widget_id, referer):

    payload = [
        ("from", date_from),
        ("to", date_to),
        ("mode", "Month"),
        ("date", date_from),
        ("manager_id", "49798"),
        ("season_mode", "live"),
        ("widget", "true"),
    ]

    for location in locations:
        payload.append(("locations[]", location))

    payload.append(("platform_widget_id", widget_id))

    headers = HEADERS.copy()
    headers["Referer"] = referer

    response = requests.post(
        URL,
        data=payload,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if "events" not in result:
        raise ValueError("Locaboo-Antwort enthält keine Events.")

    return result["events"]


ice_events = load_events(
    ["23121", "23071", "23072"],
    "694",
    HEADERS["Referer"]
)

cabin_events = load_events(
    ["23089", "23073", "23098", "23108"],
    "696",
    "https://booking.locaboo.com/de/"
    "bundesstuetzpunkt-fuer-eishockey-und-curling-stadt-fuessen/"
    "kabinenbelegung"
)


# --------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------

def get_hall(event_text):

    text = re.sub(
        r"<br\s*/?>",
        "\n",
        event_text or "",
        flags=re.IGNORECASE
    )

    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)

    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]

    return lines[0] if lines else "Unbekannt"


def to_datetime(value):

    return datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=TZ)


# --------------------------------------------------
# Mannschafts-Eiszeiten filtern
# --------------------------------------------------

ice_events = [
    event for event in ice_events
    if event.get("customer_name") in TEAMS
    and event.get("status") == "live"
]


# --------------------------------------------------
# Kabinen zuordnen
# --------------------------------------------------

for event in ice_events:

    matching_cabins = [
        cabin for cabin in cabin_events
        if cabin.get("customer_name") == event.get("customer_name")
        and cabin.get("start") == event.get("start")
        and cabin.get("end") == event.get("end")
        and cabin.get("status") == "live"
    ]

    event["cabin_resource"] = (
        matching_cabins[0].get("resource")
        if matching_cabins else None
    )


# --------------------------------------------------
# Zwei getrennte Kalender erstellen
# --------------------------------------------------

for team, filename in TEAMS.items():

    cal = Calendar()
    cal.add("prodid", "-//Locaboo Eishockey Fuessen//DE")
    cal.add("version", "2.0")
    cal.add("name", team)
    cal.add("X-WR-CALNAME", team)
    cal.add("X-WR-TIMEZONE", "Europe/Berlin")

    team_events = [
        event for event in ice_events
        if event["customer_name"] == team
    ]

    for event_data in team_events:

        calendar_event = Event()

        start = to_datetime(event_data["start"])
        end = to_datetime(event_data["end"])

        calendar_event.add("summary", team)
        calendar_event.add("dtstart", start)
        calendar_event.add("dtend", end)

        hall = get_hall(event_data.get("text", ""))
        calendar_event.add("location", hall)

        cabin_id = event_data.get("cabin_resource")

        if cabin_id:
            description = (
                f"Kabinen-Ressourcen-ID: {cabin_id}"
            )
        else:
            description = "Kabine noch nicht zugeteilt"

        calendar_event.add("description", description)

        uid = (
            f'{event_data["id"]}-'
            f'{event_data["instance"]}-'
            f'{event_data["resource"]}@locaboo-fuessen'
        )

        calendar_event.add("uid", uid)
        calendar_event.add(
            "dtstamp",
            datetime.now(timezone.utc)
        )

        cal.add_component(calendar_event)

    with open(filename, "wb") as file:
        file.write(cal.to_ical())

    print(f"{team}: {len(team_events)} Termine erstellt.")

print(f"Zeitraum: {date_from} bis {date_to}")
print("Beide Kalender wurden erfolgreich erstellt.")


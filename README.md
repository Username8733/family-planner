# Family Planner

A touch-friendly family calendar for wall displays, tablets and computers. See the whole month at once: one row per day and one column per person.

A fresh installation is empty, with **Shared** and **Person 1–5** columns. No accounts, locations or events are included.

![Family Planner month view showing fictional events, shared activities and multi-day plans](docs/images/family-planner-example.png)

*Example with fictional events and weather. A fresh installation starts empty.*

## Quick start

Requires Python 3.11 or newer.

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python serve.py --port 8086

Open http://127.0.0.1:8086/. Local-only mode also works by opening dist/index.html directly.
On Windows, use .venv\Scripts\python.exe instead of .venv/bin/python.

## Features

- Rename, color and reorder columns.
- Side-by-side activities, multi-day events with stable widths and multiple participants.
- Tap a date or a dense day’s “+” button for an enlarged, paged day view instead of scrolling inside cells.
- Connect iCloud, Google Calendar, Home Assistant, CalDAV and ICS feeds. Display multiple sources together.
- English by default, with optional Swedish. ISO dates (YYYY-MM-DD), 24-hour or AM/PM time.
- Swedish public holidays, observances and flag days, with localized names.
- Eight themes with light and dark modes, including e-ink and an Apple-inspired Liquid Glass theme.
- Today's forecast and outdoor temperature, with optional Home Assistant temperature sensors.
- Import and export local events and settings.

## Calendar connections and data

See [ONLINE-CALENDAR.md](ONLINE-CALENDAR.md) for provider setup, Google OAuth and editing capabilities.

Enter credentials in Settings. They are stored only in private server-side files outside the repository, normally under ~/.local/share/hemma-calendar/. Credentials are excluded from Git and JSON exports. Google requires your own OAuth client ID and client secret. No working credentials are included.

Local events and preferences are stored in the browser. Online events are fetched from their providers. Resetting the local calendar does not delete online events.

## Home Assistant

See [home-assistant/README.md](home-assistant/README.md). Online calendars require the Python server; local mode can be served as static files. Nothing is installed in Home Assistant automatically.

## Tests

    .venv/bin/python -m pip install -r requirements-test.txt
    .venv/bin/python test_online_backend.py
    .venv/bin/python test_calendar_sources.py
    .venv/bin/python test_ha_websocket.py
    .venv/bin/python qa-clean-template.py
    .venv/bin/python qa-multiple-calendars.py
    .venv/bin/python qa-settings-layout.py

Browser checks use a separate temporary Brave profile and synthetic calendar data. Set BRAVE_BINARY when Brave is not installed in its default macOS location.

## Translations and fonts

English is the source and default language. The optional Swedish catalog is maintained in i18n.js. Run python3 sync_i18n.py after editing it to embed the catalog in dist/index.html. No external scripts are required.

The bundled Inter font is licensed under the SIL Open Font License; see [licenses/Inter-LICENSE.txt](licenses/Inter-LICENSE.txt).

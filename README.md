# Family Planner

En familjeplanerare för touchskärm, iPad och dator. Hela månaden visas med en rad per dag och en kolumn per person.

En ny installation är tom och har kolumnerna **Gemensamt** och **Person 1–5**. Inga konton, platser eller kalenderhändelser följer med.

## Starta

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python serve.py --port 8086

Öppna http://127.0.0.1:8086/. Enbart lokal kalender kan även öppnas direkt via dist/index.html.

## Funktioner

- Egna kolumnnamn, färger och dragordning.
- Aktiviteter bredvid varandra, flerdagarsaktiviteter och flera deltagare.
- iCloud, Google Calendar, Home Assistant, CalDAV och ICS. Flera källor samtidigt.
- Svenska och engelska. Datum: YYYY-MM-DD. Tid: 24 timmar eller AM/PM.
- Svenska helgdagar och flaggdagar.
- Åtta teman, inklusive e-ink och Liquid Glass, med mörkerläge.
- Dagens väder, utetemperatur och stöd för HA-givare.
- Export/import av lokala aktiviteter och inställningar.

## Anslutningar och lagring

Se [ONLINE-CALENDAR.md](ONLINE-CALENDAR.md) för anslutning, Google OAuth och källornas behörigheter.

Anslutningsuppgifter matas in i Inställningar och sparas enbart i privata filer utanför projektet, normalt under ~/.local/share/hemma-calendar/. De ingår inte i Git eller exporten. Google behöver ett eget OAuth Client ID och Client secret. Inga färdiga kontouppgifter medföljer.

Lokala aktiviteter och inställningar sparas i webbläsaren. Onlinehändelser hämtas från respektive leverantör. Lokal återställning raderar inga onlinehändelser.

## Home Assistant

Se [home-assistant/README.md](home-assistant/README.md). Onlinekalendrar kräver Python-servern; lokal kalender kan köras statiskt. Ingen automatisk installation i HA görs.

## Tester

    .venv/bin/python -m pip install -r requirements-test.txt
    .venv/bin/python test_online_backend.py
    .venv/bin/python test_calendar_sources.py
    .venv/bin/python test_ha_websocket.py
    .venv/bin/python qa-clean-template.py
    .venv/bin/python qa-multiple-calendars.py
    .venv/bin/python qa-settings-layout.py

Webbläsartester använder en separat Brave-profil och syntetiska kalenderdata. Ställ in BRAVE_BINARY om Brave ligger på en annan plats än macOS-standardplatsen.

## Språk och typsnitt

Översättningar underhålls i i18n.js. Kör python3 sync_i18n.py för att bädda in dem i dist/index.html. Appen kräver inga externa skript.
Inter-typsnittets licens finns i [licenses/Inter-LICENSE.txt](licenses/Inter-LICENSE.txt).

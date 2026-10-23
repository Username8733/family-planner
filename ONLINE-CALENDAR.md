# Online calendars

Start the application using its virtual environment:

    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python serve.py --port 8086

Open http://127.0.0.1:8086/. Local events also work directly from dist/index.html. Online connections require the server. Nothing is installed in HA automatically.

## Provider capabilities

| Provider | View | Create | Edit / delete |
| --- | --- | --- | --- |
| iCloud | Yes | Yes | Yes; one selected recurrence |
| Google Calendar | Yes | With write access | With write access; one recurrence |
| CalDAV, including Nextcloud and Fastmail | Yes | If allowed by the server | If allowed; one recurrence |
| Home Assistant | Yes | If supported by the entity | If supported and the event has a UID |
| ICS / iCalendar subscription | Yes | No | No |

Multiple sources and calendars can be selected together. Each event belongs to one source. Choosing another target does not migrate existing events. For new events, select the target using **Save to**.

Saving a new online event from the local-only view switches to mixed view so that the saved event is visible.

In **Settings → Calendar view**, choose local, online or mixed mode. Select calendars under **Online calendars**, then save settings. Connecting and disconnecting take effect immediately on the server; calendar selection is applied when settings are saved.

The iCloud panel selects one calendar for the connected Apple account. Its Apple ID is shown in the connection list. Additional CalDAV sources can be added separately.

## iCloud

Connect using an Apple ID and an Apple app-specific password, not the normal account password. Select the iCloud calendar and save settings.

Reading uses the discovered calendar server, which may have a different hostname from the iCloud sign-in endpoint.

## Google Calendar

1. Enable **Google Calendar API** in a Google Cloud project.
2. Configure the OAuth consent screen. Add your account as a test user if the app is in testing.
3. Create a **Desktop app** OAuth client for local use on the same computer.
4. In Family Planner, open **Settings → Online calendars → Add calendar source → Google Calendar**.
5. Enter the client ID and client secret, then choose **Connect calendar source**.
6. Choose **Continue to Google**, grant calendar access, and return to the app.
7. Select calendars and save settings.

The flow uses state, PKCE and a callback to the application server. The redirect URI is displayed in Settings. For remote access or a hosted HTTPS service, use a **Web application** OAuth client with that exact URI registered.

You must create your own OAuth client; no shared client credentials are included. Requested scopes are calendar.calendarlist.readonly and calendar.events. Refresh tokens are stored on the server and renew access. Restart the flow if sign-in expires or is cancelled.

Disconnecting removes the local connection. You can also revoke the app's access in your Google account.

## Home Assistant

Enter HA's base URL and a long-lived access token from your HA profile. The token is used only by the Python server and is never returned to the browser.

Select the calendar entities to display. The entity's supported_features determines which actions are available.

Reads and creation use REST. Updates and deletion use calendar/event/update and calendar/event/delete through HA's WebSocket API. Existing events require a UID; events without one are read-only. Recurrence IDs are passed through to edit only the selected occurrence. Descriptions and locations are preserved.

The event is re-read and checked before modification. HA does not support atomic If-Match conditions for these commands, so a concurrent change immediately after the check cannot be ruled out.

HA creation has no server-side idempotency key. Confirmed retries are protected for the current server process. If creation is interrupted or times out, refresh before trying again.

This also works standalone. A static HA /local/ copy does not provide the Python API. For online functions, embed the running service's HTTPS URL, with a same-origin proxy if you also use the temperature adapter.

## Other services

**CalDAV:** enter the provider's CalDAV base URL, username and password/app password. Calendars are discovered automatically.

**ICS:** enter a direct http/https or webcal URL for an iCalendar feed. Private subscription links are treated as credentials. Feeds are read-only, for example a published Outlook calendar.

Native Microsoft Graph/Exchange OAuth is not included; use ICS or an existing HA integration. Token-based API and ICS redirects are not followed. Use the final URL so that private links or tokens are not forwarded to another host.

## Names, dates and refresh

- Person 1 - Dance appears in Person 1's column.
- Person 1, Person 2 - Cinema is one shared event shown in both columns.
- Names match column names without case sensitivity. Renaming a column preserves the previous name as an alias.
- If any participant name cannot be matched, the original title is placed in the configured fallback column.
- All-day end dates are inclusive in the UI and exclusive in provider APIs.
- Times use each source's time zone, with daylight-saving validation.
- Events refresh every three minutes, when changing month, when the tab becomes visible, and after changes.
- If one source fails, its last events for that month remain visible but read-only. Other sources continue to work.
- Connecting the same underlying calendar directly and through HA may show duplicate events. Select only one connection.

## Language

English is the default. Choose **Settings → Language → English / Swedish** and save to change it. With the server, the choice is shared across devices and included in JSON exports. A static installation keeps it in the current browser.

Interface labels, months, weekdays, weather descriptions and holiday names are translated. Personal column names, provider calendar names and event titles are not translated. Dates remain YYYY-MM-DD. Time format and temperature units are separate preferences.

The observances remain Swedish holidays when the interface is English.

## Private data and network access

Private files normally live under ~/.local/share/hemma-calendar/:

- icloud.json: Apple connection.
- sources.json: other connections, selected calendars, Google OAuth tokens and a signing key.

Files are written with mode 0600 outside dist/. Passwords, tokens, private subscription links and fetched online events are excluded from browser localStorage and JSON exports.

The Apple ID is intentionally shown to an authenticated/localhost user so that the connected account can be identified. Do not put private configuration under HA's www, dist/ or Git.

The default server listens on localhost only. Network access requires HEMMA_HTTP_USERNAME and HEMMA_HTTP_PASSWORD plus TLS, or --behind-https-proxy and --public-host. Host, origin and CSRF checks apply. Google OAuth codes are not logged.

Anyone who can sign into the calendar service can use its connected sources according to their permissions.

## Validation

- test_online_backend.py: real local CalDAV server, CRUD, recurrence exceptions, conflicts and time zones.
- test_calendar_sources.py: isolated Google/HA/ICS contracts, OAuth/PKCE, refresh, pagination, CRUD, privacy and failures.
- test_ha_websocket.py: real local HTTP/WebSocket fixture using the HA protocol.
- qa-multiple-calendars.py: real browser and CalDAV server, source selection, shared events, language and stale-data behavior.
- qa-settings-layout.py: internal scrolling, rounded corners, footer and city selection on desktop/tablet.

Google is tested using isolated API responses. Connect a real Google account to verify your OAuth client configuration.

## References

- https://developers.google.com/identity/protocols/oauth2/native-app
- https://developers.google.com/workspace/calendar/api/v3/reference/events/list
- https://developers.google.com/workspace/calendar/api/v3/reference/events/patch
- https://developers.home-assistant.io/docs/api/rest/
- https://github.com/home-assistant/core/blob/dev/homeassistant/components/calendar/__init__.py
\n## Event notes and location\n\nNotes and location can be viewed, edited and cleared in the event form. iCloud/CalDAV, Google and writable HA calendars synchronize these fields with their provider; ICS feeds display them read-only. Changes to a recurring occurrence only affect that occurrence. A client that omits these fields preserves existing values.\n\nLocal event details are included in shared server settings and JSON backups. Notes use plain text with line breaks. The editor accepts up to 10000 characters of notes and 1000 characters for location; longer existing provider values are retained when unchanged. No address lookup or geocoding is performed.\n
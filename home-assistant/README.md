# Family Planner in Home Assistant

Family Planner can run as a Home Assistant OS app and a separate dashboard, or as a static local calendar.

## HA OS app with online calendars

The local app runs the Python service in HA, starts automatically, and uses HA ingress authentication without exposing a host port. It needs no Home Assistant API token or privileged container access. Calendar provider credentials are stored in the app's private /data directory and included in HA app backups.

1. From the repository root, run: python3 home-assistant/prepare-addon.py build/family_planner
2. Copy the generated build/family_planner/ folder to /addons/family_planner/ on HA. Refresh the app store, install the local **Family Planner** app, and start it.
3. Copy dist/hemma-calendar-card.js to /config/www/family-planner/hemma-calendar-card.js. Register /local/family-planner/hemma-calendar-card.js as a JavaScript module in dashboard resources. Add a version query when updating this file.
4. Create a separate dashboard at dashboard-family-planner, titled **Family Planner**, with icon mdi:calendar-month, visible in the sidebar. Use the panel configuration below.
5. In the card's url, use the app's own ingress_url followed by index.html. The URL is returned by the Supervisor app info endpoint or: ha apps info local_family_planner --raw-json. It is installation-specific; do not put an actual ingress URL into a public repository.

Panel configuration:

    title: Family Planner
    views:
      - title: Family Planner
        path: calendar
        type: panel
        cards:
          - type: custom:hemma-calendar-card
            url: /api/hassio_ingress/REPLACE_WITH_APP_PATH/index.html

The card establishes an HA ingress session before loading the app and renews it while the dashboard is open. Temperature sensors are passed through the adapter described below. Online calendar connections are configured in the calendar's Settings.

For Google OAuth, the app's dashboard_path option must match the dashboard's path (default /dashboard-family-planner/calendar). Register your public HTTPS HA origin plus that path as the Google Web application client's redirect URI. Google returns to the HA dashboard; the card then forwards the one-time code to the app after creating an authenticated ingress session. This preserves HA authentication during the return from Google. A real Google connection still requires your own OAuth client configuration.

To update, prepare and copy the build context again, rebuild or update the local HA app, and refresh the card module's resource URL. App data remains in /data. Local browser events/settings remain in browser storage; use Export JSON and Import JSON when moving from a standalone origin to HA or between devices.

To remove the integration, remove its dashboard and module resource and uninstall the app. Export local events and back up the app first if its data should be retained.

## Static embedding: local calendar

1. Export existing local data using Settings → Export JSON.
2. Copy dist/ into /config/www/familjekalender/ on the HA server. Restart HA if www was created for the first time.
3. Open /local/familjekalender/index.html through your usual HA address.
4. In HA, add a Webpage dashboard named Family Planner with icon mdi:calendar-month and URL /local/familjekalender/index.html.
5. Open the calendar's Settings and import the JSON backup. Import replaces this browser's local calendar after confirmation.
6. Keep the same URL for future updates so that local storage stays associated with the calendar.

The same dist/index.html works standalone. Static local mode does not require an HA token or HACS. It adapts to the frame's available height.

## Data and online calendars

Local activities, columns, themes and preferences use browser localStorage. They do not synchronize automatically across devices. Changing the scheme, hostname or port creates a separate storage origin; export before moving or clearing browser data.

Online events come from connected providers, including HA calendar entities. This requires the running Python service; see [ONLINE-CALENDAR.md](../ONLINE-CALENDAR.md). A static /local/ copy has no Python API.

For online mode, embed the running service's HTTPS address as a Webpage dashboard. A same-origin proxy is needed when combining it with the included temperature adapter.

Weather is fetched directly from Open-Meteo. The selected city's name/coordinates are sent to the weather service; activity data is not sent. The forecast always covers today in the city's time zone, regardless of the displayed calendar month.

HA's /local/ endpoint serves static files without separate authentication. Place only generic dist files under www. Keep credentials, personal backups and calendar exports elsewhere.

## Optional HA temperature adapter

A normal Webpage dashboard does not send HA sensor values to the frame. To select an outdoor sensor, use the included custom card:

1. Copy dist/ into /config/www/familjekalender/, including hemma-calendar-card.js.
2. Add /local/familjekalender/hemma-calendar-card.js as a JavaScript module resource in HA's dashboard resources.
3. Create a separate dashboard using dashboard.yaml as its raw configuration.
4. In the calendar's Settings, choose Home Assistant temperature sensor as the outdoor temperature source.
5. Select the actual outdoor sensor and save. Only temperature sensors with °C or °F units are listed; a sensor is never guessed.
6. Optionally restrict the list using temperature_entities in the card configuration. This is a display filter, not a user permission boundary.

The adapter receives HA's hass object and sends only temperature sensor IDs, names, values, units and update times to the calendar. It does not send or store credentials or other entities. The frame and adapter must have the same origin. Messages are checked against both origin and sender window.

The adapter uses a 30-second heartbeat. After 90 seconds without messages, the calendar reports a lost HA connection. Unknown/unavailable values and missing sensors are shown explicitly, without silently replacing them with modelled weather temperatures. An old reading is not automatically considered invalid; its update time remains visible.

Standalone mode can use the weather service's modelled current temperature. Selecting an HA sensor without the adapter shows no connection.

## References

- https://www.home-assistant.io/dashboards/dashboards/#webpage-dashboard
- https://www.home-assistant.io/dashboards/iframe/
- https://www.home-assistant.io/integrations/http/#hosting-files
- https://contributors.home-assistant.io/frontend/custom-ui/card/
- https://www.home-assistant.io/dashboards/panel/

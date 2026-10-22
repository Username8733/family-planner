# Family Planner in Home Assistant

Family Planner can be embedded in Home Assistant. These instructions do not install anything automatically.

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

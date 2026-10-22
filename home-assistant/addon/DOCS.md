# Family Planner app

Start the app and use its dedicated dashboard with the included hemma-calendar-card module. This module creates the HA ingress session and provides the temperature sensor adapter.

The dashboard_path option must match the dashboard URL path for Google OAuth returns. Its default is /dashboard-family-planner/calendar. Use the public HTTPS Home Assistant address when configuring Google.

Provider credentials are stored privately in /data and survive updates. They are excluded from browser exports and are never placed in /config/www. Local calendar events and display settings remain in browser storage. Export/import them when changing the browser or origin. Home Assistant app backups contain the private provider configuration.

The app exposes no host port and only accepts HTTP requests from Supervisor ingress. Do not add direct port mappings.

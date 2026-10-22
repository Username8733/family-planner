# Running Family Planner

See README.md for installation and ONLINE-CALENDAR.md for calendar connections.

Default address: http://127.0.0.1:8086/.

Network access requires HTTPS, HTTP authentication and an explicitly allowed hostname. Run serve.py --help for details. No account credentials are included.

A fresh installation has no events, connected accounts, weather location or HA sensor. Its columns are Shared and Person 1–5. English is the default interface language.

Legacy proposal data is removed when the clean template is first loaded. New data saved in the current version is retained. Upgrading older settings to the English-first release preserves events and custom columns; only the initial interface language and the untouched generic shared-column label are migrated.

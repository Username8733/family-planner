# Verification 2026-10-29

The event overview frontend and i18n catalog match the deployed HA app. Live HA ingress checks verified an existing event, the overview/edit separation, day-view navigation and Surface wallboard compatibility without changing live calendar data.

Isolated checks passed on Chromium on the Surface Go:

- `qa-event-overview.py`: overview/read-first behavior, explicit editing, provider capability restrictions, participant/time/location/notes display, mobile long notes, Escape, English/Swedish and safe text rendering.
- `qa-event-details.py`: create/read/update/clear notes and location against a temporary CalDAV server; local event persistence; responsive editor in light/dark modes. All accounts/events are temporary fixtures.
- `qa-event-entry.py`: occupied/dense day entry, default duration, time pickers, all-day and multi-day events across themes/formats/screen sizes.
- `qa-new-themes.py`: light/dark themes, layout, persistence and explicit event editing.
- `qa-daily-event-width.py`: dense/paged day view, shared events, editing/adding, responsive layouts and all events reachable.

The existing backend checks also passed via `python -m unittest discover -q`, including shared state/cache, provider adapters, CalDAV CRUD/conflicts, HA ingress authorization and private-file isolation.

The Chromium test harness selects a page target instead of a background extension, waits for frontend readiness and allows a longer protocol timeout for slower machines. Local Mac headless browser startup is unavailable in the current execution environment, so the browser checks above were run on the Surface against isolated fixtures.

The broader `qa-multiple-calendars.py` check did not pass in this run: it timed out while waiting for a source-selection/cache refresh before the event-edit step. This is outside the overview change; no provider/backend runtime code changed. The dedicated CalDAV notes/editor check, live HA overview check and backend provider checks passed. This broader scenario remains unverified in this environment.

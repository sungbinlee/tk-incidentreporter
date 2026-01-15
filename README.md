# tk-incidentreporter (MVP)

FPTR Toolkit (`sgtk`) Desktop app that implements a simple idea:

> If something breaks on the client, detect it from `tk-*.log` and automatically file a Ticket to FPTR with the log attached.

This is an MVP built to validate the end-to-end flow, not a production-ready app!

## What it does

- Watches `tk-*.log` on the client machine
- Detects incident lines via regex: `ERROR|CRITICAL`
- Creates a **Ticket** and attaches the log file
- Prevents ticket flooding by **title signature de-dup**
  - Title format: `"<user_login> - <ErrorName or short message>"`
  - If the same title already exists → skip creation

## Test it (SGTK config)

### 1) Add app location

Edit: `<your_config>/env/include/app_locations.yml`

```yml
# location descriptors for apps used in this configuration
# --- Site apps
apps.tk-incidentreporter.location:
  type: dev
  name: tk-incidentreporter
  path: D:/<your_path>/tk-incidentreporter  # <yourpath>
````

### 2) Enable the app in tk-desktop site settings

Edit: `<your_config>/env/includes/settings/tk-desktop.yml`

```yml
# site
settings.tk-desktop.site:
  apps:
    tk-incidentreporter:
      location: "@apps.tk-incidentreporter.location"
      shotgun_project_id: 190
  location: "@engines.tk-desktop.location"
```

* `shotgun_project_id` is the **Project ID** where Tickets should be created(Should enable Ticket entity)

## What a Ticket contains

* Matched line (trigger line)
* Detected timestamp
* Client User
* Log path + matched byte offset
* Attached log file (e.g. `tk-desktop.log`)

## Contributing
Any opinions or contributions are welcome!

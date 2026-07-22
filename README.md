# Gmonitor

A simple, lightweight dashboard for monitoring diverse hosts in a non-security-critical environment. Hosts (or scripts running on them) push status reports to Gmonitor over HTTP; Gmonitor displays them as a grid of cards with grouped, color-coded paramter values, and flags any host that hasn't reported in recently. Users can access the data with a pre-shared password.

## Features

- Simple push-based reporting with a single `POST` request.
- Configurable staleness detection: hosts that stop reporting are automatically flagged, and eventually removed, based on two timeouts.
- Two access levels: an admin password (full access) and a separate dashboard view-only password.
- A settings page for the grid layout, visible fields, timeouts, and access keys.
- Optional shared-key authentication for incoming reports.

## Requirements

- Python 3.6 or newer
- The Python `venv` module (`python3-venv` / `python3-devel` depending on distro — see below)
- A systemd-based Linux distribution, if using the provided `install.sh` and unit file (tested on AlmaLinux). Otherwise, you must install and run this application based on your service managemant system.
- Either:
  - A C compiler and Python development headers, to build `pyuwsgi` into the app's virtual environment (default), **or**
  - A system-wide `uwsgi` installation with its Python 3 plugin (see [Using a system uwsgi installation](#using-a-system-uwsgi-installation))
  - A different option to run Flask applications in development. In this case, you can not use the automated installer. Running the application in Python is possible but not recommended. In this case, remove the debug feature (Gmonitor.py, line 291).

## Project layout

```
.
├── install.sh               # Installer script (run this)
├── gmonitor.service         # systemd unit template
└── src/
    ├── Gmonitor.py          # Flask application
    ├── Gmonitor.ini         # Startup configuration file
    ├── requirements.txt     # Pinned Python dependencies
    ├── start_uwsgi.sh       # Startup script invoked by systemd
    ├── static/
    │   ├── style.css
    │   └── favicon.svg
    └── templates/
        ├── dashboard.html
        ├── login.html
        └── setting.html
```

`install.sh` expects to be run from the directory containing `install.sh`, `gmonitor.service`, and the `src/` folder shown above.

## Installation

By default the application listens on port 8080. To change the port, edit `src/Gmonitor.ini` before running the installation script.

```bash
sudo ./install.sh [/optional/absolute/install/path]
```

If no path is given, Gmonitor is installed to `/srv/Gmonitor`. The target folder must not already exist or must be empty.

What the script does:

1. Verifies Python ≥ 3.6, the `venv` module, and (depending on your `requirements.txt`, see below) either a C toolchain or a system `uwsgi`.
2. Copies everything under `src/` into the install folder.
3. Generates a random `SECRET_KEY` and stores it in `.secret_key` (root-readable only) in the install folder, used to sign session cookies.
4. Creates a Python virtual environment in the install folder and installs `requirements.txt` into it.
5. Reads the configured port from `Gmonitor.ini` and opens it in the firewall, if `firewalld` is present.
6. Installs and starts a systemd service (`gmonitor.service`), enabling it to start on boot.

After installation, check the service status with:

```bash
systemctl status gmonitor
journalctl -u gmonitor -f
```

### Using a system uwsgi installation

By default, `requirements.txt` includes `pyuwsgi`, which is compiled into the app's virtual environment during install — this requires a C compiler and Python development headers (`install.sh` checks for both and tells you how to install them if missing).

If you'd rather use your distribution's packaged `uwsgi` instead of building one:

1. Remove the `pyuwsgi`/`uwsgi` line from `requirements.txt`.
2. Install `uwsgi` and its Python 3 plugin system-wide, e.g. `dnf install uwsgi uwsgi-plugin-python3` (RHEL/Alma/Rocky), `apt install uwsgi uwsgi-plugin-python3` (Debian/Ubuntu), or `zypper install uwsgi uwsgi-python3` (SUSE).
3. Run `install.sh` as normal — it detects the missing `pyuwsgi` entry, skips the compiler checks, and verifies the system `uwsgi` command is available instead.

`start_uwsgi.sh` automatically detects which of the two is in play at startup and adjusts its invocation accordingly (using `--virtualenv` to point a system-wide `uwsgi` at the app's venv). Note that the Python plugin name (`--plugin python3` in the script) can vary slightly between distributions — if `uwsgi` reports a missing plugin, check what's available under your system's uwsgi plugin directory.

## Configuration

### `Gmonitor.ini`

```ini
[Server]
port = 8080

[Files]
settings = settings.json
inventory = inventory.json
```

| Key | Section | Description |
|---|---|---|
| `port` | `Server` | TCP port the app listens on. |
| `settings` | `Files` | Path (relative to the install folder) where dashboard settings are persisted. |
| `inventory` | `Files` | Path (relative to the install folder) where reported host data is persisted. |

### The Settings page (`/settings`, admin only)

| Setting | Description |
|---|---|
| Max columns | Number of columns in the dashboard grid. |
| Show name / description / last seen | Toggle which fields are displayed on each host card. |
| Require key on incoming reports | If enabled, `POST /report` requests must include one of the accepted keys below. |
| Accepted keys | One key per line; used only when "Require key" is enabled. |
| Time to stale | Seconds since a host's last report before it's flagged stale/offline. |
| Time to remove | Seconds since a host's last report before it's dropped from the dashboard entirely. |
| User password | Grants dashboard-only access. |
| Admin password | Grants dashboard, settings, and cleanup access. |

### Timeouts

All timeouts are set in seconds.

The first timeout controls the time after which a host is marked as stale. The default value after installation is 3900 seconds (1 hour + 5 min grace period). It can be changed in the configuration page. After this time, the host will be marked as stale (red border and warning that the timelimit has been exceeded).

The second timeout controls the time after which a host is removed from the dashboard. The default value after installation is 2764800 seconds (1 month + 1 day grace period).

Each host can oweride both times for its own card.

### Logging in

No usernames. Two passwords control access:

- **User password** — view the dashboard only.
- **Admin password** — dashboard, plus `/settings` and `/cleanup`.

Log out at any time via the logout link on the dashboard or settings page.

## Reporting host status

Hosts report their status with a `POST` request to `/report`:

```bash
curl -X POST http://your-server:8080/report \
     -H "Content-Type: application/json" \
     -d '{
           "name": "web01",
           "description": "Primary web server",
           "key": "key123",
           "metrics": {
             "Disk": {
               "status": "GREEN",
               "used": "42%"
             },
             "Services": {
               "nginx": { "status": "GREEN", "uptime": "14d" },
               "postgres": { "status": "YELLOW", "note": "high load" }
             }
           }
         }'
```

Notes on the payload:

- `name` — the hostname; used as the unique key in the dashboard. Defaults to `"Unknown"` if omitted. **Important**: hostnames should be unique. Gmonitor does not check if two POST requests with the same name came from the same device. In such cases, requests will overwrite the previus data.
- `key` — required only if "Require key on incoming reports" is enabled in Settings; must match one of the accepted keys. It is stripped before storage.
- `timeStamp` — optional ISO-8601-ish timestamp; if omitted, the server records the time the report was received. If in different timezones, it is recommended to ommit this entry but be aware that displayed times on the dashboard are for the monitors timezone.
- `description` — optional free-text field shown on the dashboard.
- `metrics` — optional nested structure. While this is technically optional, the main data shall be in here. Each top-level key is a section title. Its value is either:
  - a flat object with a `status` (`GREEN`/`YELLOW`/`RED`/`BLUE`/`WHITE`) and arbitrary key/value pairs shown as a single badge, or
  - a nested object of named items, each with their own `status` and key/value pairs, shown as one badge per item.
- `timeoutError` / `timeoutDelete` — optional per-host overrides (in seconds) for the stale/removal timeouts, taking precedence over the global settings for that host only.

Any host that stops reporting is marked offline once "Time to stale" elapses, and removed from the dashboard once "Time to remove" elapses.

## Development notes

- Dependencies are pinned in `requirements.txt` for reproducibility, targeting Python 3.6 compatibility (see the [project layout](#project-layout) above for where it lives). If you regenerate it, do so from a venv built with the oldest Python version you intend to support, e.g.:

  ```bash
  python3.6 -m venv venv36
  source venv36/bin/activate
  pip install "Flask==2.0.3"
  pip freeze > requirements.txt
  ```

- The app expects to run behind at most one reverse proxy (see `ProxyFix` configuration in `Gmonitor.py`); if you add a TLS-terminating proxy (nginx, etc.) in front of Gmonitor, make sure it's the only hop or adjust the `ProxyFix` parameters accordingly.
- If the reverese proxy is on the same machine as this application, the only firewall rule that is needed is to the reverse proxy. You can close the firewall for this applications port.
- Passwords are stored and compared in plaintext in `settings.json`. This is an intentional simplification for non-security-critical internal deployments — do not expose this service directly to the internet without additional hardening.

## Uninstalling

```bash
sudo systemctl disable --now gmonitor
sudo rm /etc/systemd/system/gmonitor.service
sudo systemctl daemon-reload
sudo rm -rf /srv/Gmonitor   # or your chosen install path
```

Remember to also close the firewall port you opened during installation, if it's no longer needed.

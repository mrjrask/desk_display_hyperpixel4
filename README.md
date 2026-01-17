# Desk Scoreboard & Info Display (HyperPixel 4.0 / 4.0 Square)

A Raspberry Pi-powered, always‑on desk display for a Pimoroni HyperPixel 4.0 panel. It cycles through time, weather, travel, sensors, and sports dashboards with smooth transitions and a web admin interface.

**Highlights**
- HyperPixel 4.0 Square (720×720) and standard HyperPixel 4.0 (800×480) support with portrait/landscape profiles.
- Sports coverage for MLB, NHL, NBA, and NFL with live/last/next game screens.
- Playlist-based screen scheduler with rules, conditions, and an admin UI editor.
- Auto screenshots + batch archiving, optional H.264 video output.
- GitHub update indicator and RGB LED status helpers.

---

## Table of contents

- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Scheduler & playlists](#scheduler--playlists)
- [Secrets & environment variables](#secrets--environment-variables)
- [Images & fonts](#images--fonts)
- [Running](#running)
- [Admin UI](#admin-ui)
- [Systemd service](#systemd-service)
- [Screenshots & archiving](#screenshots--archiving)
- [GitHub update indicator](#github-update-indicator)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Requirements

- Raspberry Pi (tested on Pi Zero/Zero 2 W, Pi 4, Pi 5)
- Raspberry Pi OS **Bookworm** (64‑bit). Wayland is supported; X11 is auto-detected when needed.
  - Raspberry Pi OS **Trixie** currently has multiple issues; stick with Bookworm for now.
- Pimoroni HyperPixel 4.0 Square (720×720) or HyperPixel 4.0 (800×480) wired to SPI0
- Python 3.11+ (Bookworm ships 3.11)

Install OS packages:

```bash
sudo apt-get update
sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg-dev libopenblas0 libopenblas-dev liblgpio-dev \
    libopenjp2-7-dev libtiff5-dev libcairo2-dev libpango1.0-dev \
    libgdk-pixbuf2.0-dev libffi-dev network-manager wireless-tools \
    i2c-tools fonts-dejavu-core fonts-noto-color-emoji libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1-mesa libgles2-mesa libdrm2
```

Create a virtual environment and install Python dependencies:

```bash
python -m venv venv && source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note:** On recent Raspberry Pi OS builds, Pillow typically ships with WebP support. If animated WebP flags do not render, upgrade Pillow: `pip install --upgrade pillow`.

Additional sensor libraries (install only if you have the hardware):

- `bme68x` for the bundled BME688 helper.
- `adafruit-circuitpython-sht4x` for the Adafruit SHT41 (STEMMA QT).
- `pimoroni-bme280` for the Pimoroni Multi-Sensor Stick’s BME280 breakout.

---

## Quick start

```bash
cd ~/desk_display_hyperpixel4
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

> **Tip:** Run `pip install -r requirements.txt` from the repository root. Pip 25.3 resolves editable paths against your current working directory, so installing from elsewhere can break the vendored `./vendor/bme68x` dependency.

### Raspberry Pi OS Bookworm (Pi 4 & Pi 5)

1. Flash Raspberry Pi OS **Bookworm** (64‑bit) and enable desktop auto-login.
2. Run `sudo raspi-config`, enable **SPI**, **I²C**, and the **GL (Full KMS)** driver, then reboot.
3. Install the HyperPixel overlay (`curl https://get.pimoroni.com/hyperpixel4 | bash`) or add `dtoverlay=hyperpixel4` to `/boot/firmware/config.txt`.
4. Install the apt packages above, clone this repository, and create the virtual environment.
5. If you need to force X11 instead of Wayland, set `DESK_DISPLAY_FORCE_X11=1` in `/home/pi/desk_display_hyperpixel4/.env`.

---

## Project layout

```
.
├─ main.py
├─ config.py
├─ data_fetch.py
├─ screens_catalog.py
├─ screens_config.json
├─ utils.py
├─ tools/
│  ├─ scripts_2_text.py
│  ├─ test_screens.py
│  └─ maintenance/
│     ├─ cleanup.sh
│     ├─ diagnose_apt.sh
│     ├─ diagnose_weather.py
│     ├─ fix_apt_sources.sh
│     ├─ render_all_screens.py
│     └─ reset_screenshots.sh
├─ services/
│  ├─ __init__.py
│  ├─ http_client.py
│  ├─ network.py
│  └─ wifi_utils.py
├─ screens/
│  ├─ draw_date_time.py
│  ├─ draw_weather.py
│  ├─ draw_travel_time.py
│  ├─ draw_inside.py
│  ├─ mlb_scoreboard.py
│  ├─ mlb_standings.py
│  ├─ nhl_scoreboard.py
│  ├─ nhl_standings.py
│  ├─ nba_scoreboard.py
│  ├─ nfl_scoreboard.py
│  └─ nfl_standings.py
├─ images/
├─ fonts/
└─ services/
```

---

## Configuration

Most runtime behavior is controlled in `config.py`:

- **Display:** `DISPLAY_PROFILE`, `DISPLAY_WIDTH`, `DISPLAY_HEIGHT`
- **Intervals:** `SCREEN_DELAY`, `TEAM_STANDINGS_DISPLAY_SECONDS`, `SCHEDULE_UPDATE_INTERVAL`
- **Feature flags:** `ENABLE_SCREENSHOTS`, `ENABLE_VIDEO`, `ENABLE_WIFI_MONITOR`
- **Weather:** `ENABLE_WEATHER`, `LATITUDE`, `LONGITUDE`, `WEATHER_REFRESH_MINUTES`
- **Travel:** `TRAVEL_MODE` (`to_home` or `to_work`)
- **Fonts:** set `FONT_SCALE_FACTOR` or ensure `fonts/` contains the required TTFs

### Display profiles

Set `DISPLAY_PROFILE` (defaults to `hyperpixel4_square`):

- `hyperpixel4_square` – 720×720
- `hyperpixel4_square_portrait` – 720×720 rotated
- `hyperpixel4` / `hyperpixel4_landscape` – 800×480
- `hyperpixel4_portrait` – 480×800

Aliases like `hp4`, `hp4_landscape`, `square`, and `portrait` also work. You can override dimensions directly with `DISPLAY_WIDTH` / `DISPLAY_HEIGHT`.

Example:

```bash
DISPLAY_PROFILE=hyperpixel4_landscape python main.py
```

---

## Scheduler & playlists

Screen sequencing uses a **playlist‑centric schema (v2)** in `screens_config.json`. Playlists can contain screen steps, nested playlists, or rules (`variants`, `cycle`, `every`) and optional conditions.

Minimal example:

```json
{
  "version": 2,
  "catalog": {"presets": {}},
  "metadata": {"ui": {"playlist_admin_enabled": true}},
  "playlists": {
    "weather": {
      "label": "Weather",
      "steps": [
        {"screen": "date"},
        {"screen": "weather1"},
        {"rule": {"type": "variants", "options": ["travel", "inside"]}}
      ]
    },
    "main": {
      "label": "Primary loop",
      "steps": [
        {"playlist": "weather"},
        {"rule": {"type": "every", "frequency": 3, "item": {"screen": "inside"}}},
        {"rule": {"type": "cycle", "items": [{"screen": "time"}, {"screen": "date"}]}}
      ]
    }
  },
  "sequence": [
    {"playlist": "main"}
  ]
}
```

Add conditions to playlists or steps:

```json
{
  "conditions": {
    "days_of_week": ["mon", "wed", "fri"],
    "time_of_day": [{"start": "08:00", "end": "12:00"}]
  },
  "playlist": "weather"
}
```

### Migrating legacy configs

Convert older v1 `sequence` arrays with:

```bash
python schedule_migrations.py migrate --input screens_config.json --output screens_config.v2.json
```

---

## Secrets & environment variables

API keys live in environment variables (not `config.py`). Define them in your shell or via a `.env` file:

- `WEATHERKIT_TEAM_ID`, `WEATHERKIT_KEY_ID`, `WEATHERKIT_SERVICE_ID`, and either `WEATHERKIT_PRIVATE_KEY`
  or `WEATHERKIT_PRIVATE_KEY_PATH`.
- `GOOGLE_MAPS_API_KEY` (leave unset to disable travel time).
- `TRAVEL_TO_HOME_ORIGIN`, `TRAVEL_TO_HOME_DESTINATION`, `TRAVEL_TO_WORK_ORIGIN`,
  `TRAVEL_TO_WORK_DESTINATION`.

Example shell exports:

```bash
export WEATHERKIT_TEAM_ID="YOUR_APPLE_TEAM_ID"
export WEATHERKIT_KEY_ID="YOUR_WEATHERKIT_KEY_ID"
export WEATHERKIT_SERVICE_ID="com.example.service"
export WEATHERKIT_PRIVATE_KEY_PATH="/home/pi/AuthKey.p8"
export GOOGLE_MAPS_API_KEY="your-google-maps-key"
```

**WeatherKit PEM tips:** If you store the `.p8` key directly in an environment variable, preserve the real newlines between `-----BEGIN` / `-----END`. Converting newlines to `\n` or providing a CRLF file can cause PEM parsing errors.

---

## Images & fonts

- **MLB logos:** `images/mlb/<ABBR>.png` (e.g., `CUBS.png`, `MIL.png`).
- **NFL logos:** `images/nfl/<abbr>.png` (e.g., `gb.png`, `min.png`).
- **Cubs W/L flag:** `images/W_flag.webp` and `images/L_flag.webp` (animated). PNG fallback in `images/mlb/W.png` / `images/mlb/L.png`.
- **Fonts:** copy `TimesSquare-m105.ttf`, `DejaVuSans.ttf`, and `DejaVuSans-Bold.ttf` into `fonts/`.
- **Travel font:** `HWYGNRRW.TTF` (Highway Gothic) must be present in `fonts/` or the app exits at startup.
- **Emoji font:** `NotoColorEmoji.ttf` is preferred. Install `fonts-noto-color-emoji` or place `Symbola.ttf` on the system if needed.

---

## Running

Run the display directly:

```bash
python3 main.py
```

Render all available screens (useful for validation):

```bash
python3 tools/maintenance/render_all_screens.py --all
```

Flags:

- `-a`, `--all`: ignore `screens_config.json` and render every screen.
- `--no-archive`: skip ZIP creation.
- `--no-images`: skip image‑based screens and logos.

---

## Admin UI

The Flask admin interface runs on port **5001** and provides:

- Live screenshot gallery.
- Drag‑and‑drop playlist editor with rule wizards.
- Condition editors for time/day windows.
- Version history and rollback (backed by an SQLite ledger).
- Per‑screen tuning overrides stored in `screen_overrides.json`.

To enable it, set `metadata.ui.playlist_admin_enabled` to `true` in `screens_config.json`.

**Helper scripts** in `scripts/`:

- `./scripts/install_admin_service.sh`
- `./scripts/update_admin_service.sh`
- `./scripts/uninstall_admin_service.sh`

Override defaults with environment variables such as `INSTALL_USER`, `INSTALL_DIR`, `VENV_PATH`, `SERVICE_NAME`, `ADMIN_HOST`, and `ADMIN_PORT`.

---

## Systemd service

Create `/etc/systemd/system/desk_display.service`:

```ini
[Unit]
Description=Desk Display (user) - main
After=graphical-session.target network-online.target
Wants=graphical-session.target

[Service]
User=pi
WorkingDirectory=/home/pi/desk_display_hyperpixel4
Environment=DISPLAY_PROFILE=hyperpixel4_square
EnvironmentFile=-/home/pi/desk_display_hyperpixel4/.env
EnvironmentFile=-/run/user/%U/desk_display.env
Environment=INSIDE_SENSOR_I2C_BUS=15
SupplementaryGroups=video render input gpio i2c spi
ExecStartPre=/home/pi/desk_display_hyperpixel4/scripts/wait_and_export_display_env.sh
ExecStart=/home/pi/desk_display_hyperpixel4/venv/bin/python /home/pi/desk_display_hyperpixel4/main.py
ExecStop=/bin/bash -lc '/home/pi/desk_display_hyperpixel4/tools/maintenance/cleanup.sh'
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

Enable & start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable desk_display.service
sudo systemctl start desk_display.service
journalctl -u desk_display.service -f
```

The unit assumes a venv at `/home/pi/desk_display_hyperpixel4/venv`. Ensure `cleanup.sh` is executable:

```bash
python -m venv /home/pi/desk_display_hyperpixel4/venv
/home/pi/desk_display_hyperpixel4/venv/bin/pip install -r /home/pi/desk_display_hyperpixel4/requirements.txt
chmod +x /home/pi/desk_display_hyperpixel4/tools/maintenance/cleanup.sh
```

**Sensor selection:**

- Use `INSIDE_SENSOR_I2C_BUS` to pin the I2C bus (HyperPixel 4.0 Square uses bus `15`, standard boards often use `13`).
- Set `INSIDE_SENSOR` to `pimoroni_bme280`, `adafruit_bme280`, `pimoroni_bme680`, `pimoroni_bme68x`, `adafruit_bme680`, or `adafruit_sht41` to lock the sensor type.

---

## Screenshots & archiving

- Screenshots are saved to `~/.local/share/desk_display_hyperpixel4/screenshots/` when `ENABLE_SCREENSHOTS=True`.
- Override with `DESK_DISPLAY_SCREENSHOT_DIR` or edit `storage_overrides.py`.
- When the live folder reaches **500** images, the entire batch moves to `screenshot_archive/<screen>/` to mirror the live layout.
- Videos (if enabled) are written to `screenshots/display_output.mp4` and are not archived.

---

## GitHub update indicator

`utils.check_github_updates()` compares `HEAD` with `origin/HEAD`. When they diverge, a red dot appears on date/time screens and the logger prints the changed file list via `git diff --name-only HEAD..origin/HEAD`.

---

## Troubleshooting

- **Too‑dark colors on date/time:** the project forces high‑brightness random RGB values for legibility.
- **lgpio wheel fails to link on Trixie:** install `liblgpio-dev` (`sudo apt-get install -y liblgpio-dev`).
- **Missing logos:** watch for `Logo file missing: CUBS.png` and add assets to `images/mlb/` or `images/nfl/`.
- **No WebP animation:** ensure Pillow is built with WebP (`pip3 show pillow`); PNG fallback will still work.
- **Network/API errors:** MLB/WeatherKit requests are bounded and failures are logged; screens are skipped gracefully.
- **NHL statsapi DNS warning:** run `python3 nhl_scoreboard.py --diagnose-dns` for resolver details and attach JSON output in bug reports.
- **Font not found:** the app falls back to `ImageFont.load_default()`; install missing TTFs for proper rendering.

---

## License

Personal / hobby project. Use at your own risk. Team names and logos belong to their respective owners.

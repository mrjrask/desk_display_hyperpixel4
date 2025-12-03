# Desk Scoreboard & Info Display (Pimoroni HyperPixel 4.0 / 4.0 Square)

A tiny, always‑on scoreboard and info display that runs on a Raspberry Pi and a Pimoroni HyperPixel 4.0 panel (Square 720×720 or standard 800×480). It cycles through date/time, weather, travel time, indoor sensors, stocks, Blackhawks, Bulls & Bears screens, MLB standings, and Cubs/White Sox game views (last/live/next).

> **Highlights**
> - Smooth animations: scroll and fade‑in
> - Rich MLB views: last/live/next game, standings (divisions, overview, wild card)
> - **Cubs W/L result** full‑screen flag (animated WebP supported; PNG fallback)
> - **Smart screenshots** auto‑archived in batches when the live folder reaches 500 images
> - **GitHub update dot** on date/time screens when new commits are available
> - Screen sequencing via `screens_config.json`

---

## Features

### Display & Hardware Support
- **HyperPixel 4.0 Square (720×720)** and **HyperPixel 4.0 (800×480)** with portrait/landscape modes
- **Wayland and X11** backend support with auto-detection
- **Touch Navigation** - Tap right side of screen to skip to next screen
- **Physical Button Controls** (Display HAT Mini):
  - X Button: Skip to next screen
  - Y Button: Restart display service
  - A/B Buttons: Reserved for custom shortcuts
- **Environmental Sensors** via I2C (auto-detected across 6 buses):
  - BME280/BME680/BME688: Temperature, humidity, pressure, air quality
  - SHT4x/SHT41: Temperature and humidity
  - LTR559: Ambient light and proximity
  - LSM6DS3: 6-axis IMU (accelerometer + gyroscope)
- **RGB LED Status Indicator** for stock movements and GitHub updates
- **Video Output** capability (H.264 MP4 at 30 FPS)

### Sports Coverage
- **MLB (Baseball)**:
  - Cubs & White Sox: Last/Live/Next/Next Home games
  - Division Standings: All 6 divisions (NL/AL East/Central/West)
  - League Overviews: NL/AL complete standings
  - Wild Card Standings: NL/AL wild card races
  - Scoreboard: Live scores across all games
  - **Animated W/L Flags**: WebP animations for Cubs results

- **NHL (Hockey)**:
  - Blackhawks: Last/Live/Next/Next Home games
  - Division Standings: East/West with wild card
  - League Overview: Complete NHL standings
  - Scoreboard: Live scores across all games

- **NBA (Basketball)**:
  - Bulls: Last/Live/Next/Next Home games
  - Scoreboard: Live scores across all games

- **NFL (Football)**:
  - Bears: Next game with opponent logos
  - Conference Overviews: NFC/AFC complete standings
  - Division Standings: All 8 divisions
  - Scoreboard: Live scores across all games

### Information Screens
- **Date/Time Displays**:
  - Standard date screen with weekday/month/day
  - **Phone-style Clock** with persistent time in upper left corner
  - Nixie tube retro digital clock display
  - **GitHub Update Indicator**: Red dot when new commits available
- **Weather** (OpenWeatherMap + Open-Meteo):
  - Current conditions with temperature, wind, and emoji icons
  - Daily forecasts with high/low and sunrise/sunset
  - Rate-limit handling with automatic fallback
- **Travel Time** (Google Maps):
  - Real-time traffic-aware commute estimates
  - Configurable to_home/to_work modes based on WiFi SSID
  - Active time window scheduling (morning/evening commutes)
  - Multi-route analysis with smart selection
- **Indoor Sensors**:
  - Temperature, humidity, pressure, air quality
  - Multi-sensor display with automatic I2C detection
  - Lux and proximity readings
- **Stock Ticker** (VRNOF):
  - Real-time price with change percentage
  - All-time profit/loss calculations
  - LED color indication (green/red)

### Animations & Transitions
- **Smooth Fade-In**: 15-step fade transitions with configurable easing
- **Scrolling Animations**: Vertical scrolling for standings and long lists
- **Logo Animations**: Team logo transitions and movements
- **Drop-In Animation**: Standings overview with animated team drops
- **LED Pulse**: Background thread animations for update indicators

### Admin & Configuration
- **Web Admin Interface** (Flask, port 5001):
  - Real-time screenshot gallery
  - Screen frequency configuration
  - Auto-render on startup
  - Drag-and-drop playlist editor
- **Advanced Scheduling**:
  - **Playlist-Centric Schema (v2)** with reusable definitions
  - **Rule Types**: variants (random), cycle (sequential), every (frequency)
  - **Conditional Scheduling**: days-of-week and time-of-day windows
  - **Nested Playlists**: Modular playlist composition
  - **Version History**: Rollback capability with SQLite ledger
  - **Auto-Migration**: Legacy v1 to v2 config conversion
- **Display Profiles**:
  - Multiple preconfigured profiles (square, landscape, portrait)
  - Custom dimensions via environment variables
  - Rotation support (0°, 90°, 180°, 270°)
- **Environment Variables**: API keys, travel addresses, feature toggles
- **WiFi-Based Configuration**: Auto-detect location based on SSID

### Data Management
- **Smart Screenshot Archiving**:
  - Auto-capture PNG screenshots of every screen
  - Batch archiving when folder reaches 500 images
  - Organized by `<screen>/` to mirror the live screenshots/ structure
  - XDG Base Directory compliance
- **Data Caching**:
  - 10-minute background refresh for sports/weather data
  - Resilient API retry logic with exponential backoff
  - Shared requests.Session for connection pooling
- **Video Recording**: Optional H.264 MP4 output (30 FPS)
- **Monitoring**:
  - Background Wi-Fi connection monitor
  - Wi-Fi triage screens during outages
  - Comprehensive logging with timestamps
  - I2C bus scanning and sensor diagnostics

### Customization
- **Color Schemes**: Custom palettes per league/team
- **Font Scaling**: Dynamic sizing via `FONT_SCALE_FACTOR` (1.15x default)
- **Score Colors**: Different colors for in-progress, winning, and losing scores
- **Emoji Support**: NotoColorEmoji with automatic Symbola fallback
- **Team Logos**: Configurable MLB/NFL team logo directories
- **Background Colors**: Customizable scoreboard backgrounds

### System Integration
- **systemd Service**: Auto-start on boot with restart capability
- **Graceful Shutdown**: Cleanup script blanks display on exit
- **SIGTERM Handling**: Clean shutdown on signals
- **GPIO Permissions**: Proper group access for hardware (video, render, input, gpio, i2c, spi)
- **X11/Wayland Auto-Detection**: Seamless backend selection with manual override
- **Performance Optimizations**: Garbage collection, image caching, batch operations

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Install](#install)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Images & Fonts](#images--fonts)
- [Screens](#screens)
- [Running](#running)
- [Systemd unit](#systemd-unit)
- [Screenshots & archiving](#screenshots--archiving)
- [GitHub update indicator](#github-update-indicator)
- [Troubleshooting](#troubleshooting)

---

## Requirements

- Raspberry Pi (tested on Pi Zero/Zero 2 W, Pi 4, and Pi 5)
- Raspberry Pi OS **Bookworm** (64-bit) with Wayland enabled – legacy X11 sessions continue to work via the service gate.
  - Raspberry Pi OS **Trixie** currently runs into multiple issues; stick with Bookworm for now and watch this space for a future Trixie-ready update.
- Pimoroni **HyperPixel 4.0 Square (720×720 LCD)** or **HyperPixel 4.0 (800×480 LCD)** wired to SPI0
- Python 3.11+ (Bookworm ships 3.11)
- Packages (install via apt / pip):
  ```bash
  sudo apt-get update
  sudo apt-get install -y \
      python3-venv python3-pip python3-dev python3-opencv \
      build-essential libjpeg-dev libopenblas0 libopenblas-dev liblgpio-dev \
      libopenjp2-7-dev libtiff5-dev libcairo2-dev libpango1.0-dev \
      libgdk-pixbuf2.0-dev libffi-dev network-manager wireless-tools \
      i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
      libatlas-base-dev libegl1-mesa libgles2-mesa libdrm2
  ```

  Create and activate a virtual environment before installing the Python dependencies:

  ```bash
  python -m venv venv && source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  ```
  Pillow on current Raspberry Pi OS builds usually includes **WebP** support. If animated WebP is not rendering, upgrade Pillow:
  ```bash
  pip install --upgrade pillow
  ```
  The `bme68x` package is required when using the bundled BME688 air quality sensor helper.
  Install `adafruit-circuitpython-sht4x` when wiring an Adafruit SHT41 (STEMMA QT).
  Install `pimoroni-bme280` for the Pimoroni Multi-Sensor Stick's BME280 breakout (shares a board with the LTR559 and LSM6DS3).

---

## Install

If you've already cloned this repository (for example into `~/desk_display_hyperpixel4`), switch into that directory to install dependencies and configure the app.

```bash
cd ~/desk_display_hyperpixel4
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

> **Tip:** Run `pip install -r requirements.txt` from the project root. Pip 25.3
> resolves editable paths against your current working directory, so installing
> from elsewhere will fail to find the vendored `./vendor/bme68x` dependency.

The `venv` directory is ignored by Git. Re-run `source venv/bin/activate` whenever you start a new shell session to ensure the project uses the isolated Python environment.

### Raspberry Pi OS Bookworm quickstart (Pi 4 & Pi 5)

1. Flash the 64-bit edition of Raspberry Pi OS **Bookworm** and enable desktop autologin so a graphical session starts at boot.
2. Run `sudo raspi-config`, enable **SPI**, **I²C**, and the **GL (Full KMS)** driver, then reboot.
3. Install Pimoroni’s HyperPixel overlay (`curl https://get.pimoroni.com/hyperpixel4 | bash`) or manually add `dtoverlay=hyperpixel4` to `/boot/firmware/config.txt` and reboot.
4. Install the apt packages listed above, clone this repository, and create the virtual environment (`python -m venv venv && source venv/bin/activate`).
5. For Pi 5 systems running Wayland, no additional tweaks are required; the included service gate script auto-detects Wayland and X11 sessions. To force legacy X11, set `DESK_DISPLAY_FORCE_X11=1` in `/home/pi/desk_display_hyperpixel4/.env`.

---

## Project layout

```
desk_display_hyperpixel4/
├─ main.py
├─ config.py
├─ data_fetch.py
├─ screens_catalog.py
├─ screens_config.json
├─ utils.py
├─ scripts_2_text.py
├─ services/
│  ├─ __init__.py
│  ├─ http_client.py              # shared requests.Session + NHL headers
│  ├─ network.py                  # background Wi-Fi / internet monitor
│  └─ wifi_utils.py               # Wi-Fi triage exposed to the main loop
├─ screens/
│  ├─ __init__.py
│  ├─ color_palettes.py
│  ├─ draw_bears_schedule.py
│  ├─ draw_bulls_schedule.py
│  ├─ draw_date_time.py
│  ├─ draw_hawks_schedule.py
│  ├─ draw_inside.py
│  ├─ draw_travel_time.py
│  ├─ draw_vrnof.py
│  ├─ draw_weather.py
│  ├─ mlb_schedule.py
│  ├─ mlb_scoreboard.py
│  ├─ mlb_standings.py
│  ├─ mlb_team_standings.py
│  ├─ nba_scoreboard.py
│  ├─ nhl_scoreboard.py
│  ├─ nhl_standings.py
│  └─ nfl_scoreboard.py / nfl_standings.py
├─ images/
│  ├─ mlb/<ABBR>.png              # MLB team logos (e.g., CUBS.png)
│  ├─ nfl/<ABBR>.png              # NFL logos used by Bears screen
│  ├─ W_flag.webp / L_flag.webp   # animated WebP flags (preferred)
│  ├─ W.png / L.png               # fallback PNG flags
│  ├─ cubs.jpg, sox.jpg, hawks.jpg, mlb.jpg, weather.jpg, verano.jpg, bears.png
└─ fonts/
   ├─ TimesSquare-m105.ttf
   ├─ DejaVuSans.ttf
   ├─ DejaVuSans-Bold.ttf
   └─ NotoColorEmoji.ttf
```

---

## Configuration

Most runtime behavior is controlled in `config.py`:

- **Display:** `DISPLAY_PROFILE`, `DISPLAY_WIDTH`, `DISPLAY_HEIGHT`
- **Intervals:** `SCREEN_DELAY`, `TEAM_STANDINGS_DISPLAY_SECONDS`, `SCHEDULE_UPDATE_INTERVAL`
- **Feature flags:** `ENABLE_SCREENSHOTS`, `ENABLE_VIDEO`, `ENABLE_WIFI_MONITOR`
- **Weather:** `ENABLE_WEATHER`, `LATITUDE/LONGITUDE`
- **Travel:** `TRAVEL_MODE` (`to_home` or `to_work`)
- **MLB:** constants and timezone `CENTRAL_TIME`
- **Fonts:** make sure `fonts/` contains the TTFs above

### Display profiles

Select the panel geometry with `DISPLAY_PROFILE` (defaults to `hyperpixel4_square`). Available options:

- `hyperpixel4_square` – 720×720 (square)
- `hyperpixel4_square_portrait` – 720×720 rotated for portrait mounting
- `hyperpixel4` / `hyperpixel4_landscape` – 800×480 (rectangular landscape)
- `hyperpixel4_portrait` – 480×800 (rectangular portrait)

Short aliases such as `hp4`, `hp4_landscape`, `hp4_portrait`, `square`, and `portrait` are also accepted. Override pixel
dimensions explicitly with `DISPLAY_WIDTH` / `DISPLAY_HEIGHT` when experimenting with other panels.

Example:

```bash
DISPLAY_PROFILE=hyperpixel4_landscape python main.py
```

### Screen sequencing

The scheduler now uses a **playlist-centric schema (v2)** that supports reusable playlists, nested playlists, rule descriptors, and optional conditions. A minimal configuration looks like this:

```json
{
  "version": 2,
  "catalog": {"presets": {}},
  "metadata": {
    "ui": {"playlist_admin_enabled": true}
  },
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

Key points:

- **`catalog`** holds reusable building blocks (e.g., preset playlists exposed in the admin UI sidebar).
- **`playlists`** is a dictionary of playlist IDs → definitions. Each playlist contains an ordered `steps` list. Steps may be screen descriptors, nested playlist references, or rule descriptors (`variants`, `cycle`, `every`).
- **`sequence`** is the top-level playlist order for the display loop. Entries can reference playlists or inline descriptors.
- Optional **conditions** may be attached to playlists or individual steps:

  ```json
  {
    "conditions": {
      "days_of_week": ["mon", "wed", "fri"],
      "time_of_day": [{"start": "08:00", "end": "12:00"}]
    },
    "playlist": "weather"
  }
  ```

  The scheduler automatically skips a step when its conditions are not met.

#### Migrating existing configs

Legacy `sequence` arrays are migrated to v2 automatically on startup. For manual conversions or batch jobs run:

```bash
python schedule_migrations.py migrate --input screens_config.json --output screens_config.v2.json
```

This writes a playlist-aware config and validates it using the scheduler parser. The original file is left untouched when `--output` is provided.

#### Admin workflow

- The refreshed admin UI (enabled when `metadata.ui.playlist_admin_enabled` is `true`) provides:
  - Drag-and-drop sequence editing with playlist cards.
  - Rule wizards for **frequency**, **cycle**, and **variants** patterns.
  - Condition editors for days-of-week and time-of-day windows.
  - A preview drawer that simulates the next N screens via the live scheduler.
  - Version history with rollback, backed by `config_versions/` plus an SQLite ledger.
- Set `metadata.ui.playlist_admin_enabled` to `false` (or append `?legacy=1` to the URL) to fall back to the JSON editor.
- Every save records an audit entry (actor, summary, diff summary) and prunes historical versions beyond the configured retention window.

#### Screen tuning overrides

The admin UI also exposes per-screen tuning controls backed by `screen_overrides.json`. The file accepts a `screens` mapping whose values combine shared defaults with optional profile-specific overrides:

```json
{
  "screens": {
    "travel": {
      "defaults": {
        "font_scale": 1.1,
        "image_scale": 0.95
      },
      "profiles": {
        "hyperpixel4": {"image_scale": 0.9},
        "hyperpixel4_square": {"font_scale": 1.2}
      }
    }
  }
}
```

- The **shared defaults** block applies to every display profile unless a targeted override is provided.
- A profile entry replaces only the specified keys when the display reports that profile; any missing values fall back to the shared defaults.
- The runtime resolves overrides through `screen_overrides.py`, so both the live service and the batch renderer automatically pick the correct values for the active `DISPLAY_PROFILE`.

### Default playlist reference

The repository ships with a ready-to-run `screens_config.json` that exposes the **Default loop** playlist shown in the admin UI. The playlist executes the following steps in order (rules are evaluated on each pass through the loop):

1. `date`
2. `weather1`
3. Every third pass, show `weather2`.
4. Every third pass, show `inside` (indoor sensors).
5. `travel`
6. Every fourth pass, show `vrnof` (Verano office status).
7. Every other pass, cycle through the Blackhawks cards: `hawks logo`, `hawks last`, `hawks live`, `hawks next`, `hawks next home`.
8. Every fifth pass, show `NHL Scoreboard`.
9. Every sixth pass, cycle through `NHL Standings Overview`, `NHL Standings Overview`, `NHL Standings West`.
10. Every eighteenth pass (starting at phase 12), show `NHL Standings East`.
11. Every fourth pass, show `bears logo`.
12. Every fourth pass, show `bears next`.
13. Every fifth pass, show `NFL Scoreboard`.
14. Every sixth pass, cycle through `NFL Overview NFC`, `NFL Overview NFC`, `NFL Standings NFC`.
15. Every sixth pass, cycle through `NFL Overview AFC`, `NFL Overview AFC`, `NFL Standings AFC`.
16. Every seventh pass, show `NBA Scoreboard`.
17. Every third pass, show `MLB Scoreboard`.

Each step above maps directly to the JSON structure under `playlists.default.steps`, so any edits made through the admin UI will keep the document and the on-device rotation in sync.

---

### Secrets & environment variables

API keys are no longer stored directly in `config.py`. Set them as environment variables before running any of the
scripts:

- `OWM_API_KEY_VERANO`, `OWM_API_KEY_WIFFY`, or `OWM_API_KEY_DEFAULT` (fallback); the code also accepts a generic
  `OWM_API_KEY` value if you only have a single OpenWeatherMap key.
- `GOOGLE_MAPS_API_KEY` for travel-time requests (leave unset to disable that screen).
- `TRAVEL_TO_HOME_ORIGIN`, `TRAVEL_TO_HOME_DESTINATION`, `TRAVEL_TO_WORK_ORIGIN`,
  and `TRAVEL_TO_WORK_DESTINATION` to override the default travel addresses.

You can export the variables in your shell session:

```bash
export OWM_API_KEY="your-open-weather-map-key"
export GOOGLE_MAPS_API_KEY="your-google-maps-key"
```

Or copy `.env.example` to `.env` and load it with your preferred process manager or a tool such as
[`python-dotenv`](https://github.com/theskumar/python-dotenv).

---

## Images & Fonts

- **MLB logos:** put team PNGs into `images/mlb/` named with your abbreviations (e.g., `CUBS.png`, `MIL.png`).
- **NFL logos:** for the Bears screen, `images/nfl/<abbr>.png` (e.g., `gb.png`, `min.png`).
- **Cubs W/L flag:** use `images/W_flag.webp` and `images/L_flag.webp` (animated). If missing, the code falls back to `images/W.png` / `images/L.png`.
- **Fonts:** copy `TimesSquare-m105.ttf`, `DejaVuSans.ttf`, `DejaVuSans-Bold.ttf`, and `NotoColorEmoji.ttf` into `fonts/`.
- **Travel font:** the Google Maps travel screen loads `HWYGNRRW.TTF` (Highway Gothic) directly from `fonts/`. Without this
  file the app will exit on startup, so copy your licensed copy into that folder alongside the other fonts.
- **Emoji font:** `NotoColorEmoji.ttf` is used by default; if unavailable, install the Symbola font (package `ttf-ancient-fonts` on Debian/Ubuntu) or place `Symbola.ttf` in your system font directory so precipitation/cloud icons render correctly.

---

## Screens

- **Date/Time:** both screens display date & time in bright/legible colors with a red dot when updates are available.
- **Weather (1/2):** Open‑Meteo + OWM configuration.
- **Inside:** BME sensor summary (labels/values) if wired.
- **VRNOF:** stock mini‑panel.
- **Travel:** Maps ETA using your configured mode.
- **Bears Next:** opponent and logos row, formatted bottom line.
- **Blackhawks:** last/live/next based on schedule feed, logos included.
- **Bulls:** last/live/next/home powered by the NBA live scoreboard feed with team logos.
- **MLB (Cubs/Sox):**
  - **Last Game:** box score with **bold W/L** in the title.
  - **Live Game:** box score with inning/state as the bottom label.
  - **Next Game:** AWAY @ HOME logos row with day/date/time label using **Today / Tonight / Tomorrow / Yesterday** logic.
  - **Cubs Result:** full‑screen **W/L flag** (animated WebP 100×100 centered; PNG fallback).

- **MLB Standings:**
  - **Overview (AL/NL):** 3 columns of division logos (East/Central/West) with **drop‑in** animation (last place drops first).
  - **Divisions (AL/NL East/Central/West):** scrolling list with W‑L, GB.
  - **Wild Card (AL/NL):** bottom→top scroll with WCGB formatting and separator line.

---

## Running

Run directly:

```bash
python3 main.py
```

Or install the included systemd service (see below).

---

## Systemd unit

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
ExecStop=/bin/bash -lc '/home/pi/desk_display_hyperpixel4/cleanup.sh'
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

The service definition above assumes the project’s virtual environment lives at `/home/pi/desk_display_hyperpixel4/venv` and that the
cleanup helper is executable. Make sure to create the venv first and grant execute permissions to the script:

```bash
python -m venv /home/pi/desk_display_hyperpixel4/venv
/home/pi/desk_display_hyperpixel4/venv/bin/pip install -r /home/pi/desk_display_hyperpixel4/requirements.txt
chmod +x /home/pi/desk_display_hyperpixel4/cleanup.sh
```

`INSIDE_SENSOR_I2C_BUS` is optional; set it to match the `/dev/i2c-*` bus number
that your hardware exposes. HyperPixel 4.0 Square hats usually use bus `15`, while
the standard rectangular HyperPixel boards commonly appear on bus `13`. If you
omit the variable entirely the app will scan every detected bus but still prefer
the HyperPixel candidates first.

`ExecStop` runs `cleanup.sh` on every shutdown so the LCD blanks immediately and any lingering screenshots or videos are swept
into the archive folders. The service is marked `Restart=always`, so crashes or manual restarts via `systemctl restart` will
trigger a fresh boot after cleanup completes.

If the unit refuses to start, check the logs with `journalctl -u desk_display.service -b` or `systemctl status desk_display.service`. The `wait_and_export_display_env.sh` gate emits verbose logs showing which display backend (Wayland or X11) was selected, the `XDG_RUNTIME_DIR` it discovered, and any failures while probing DRM connectors. When running under X11, the gate now exports `XAUTHORITY` automatically so pygame can authenticate with the display server.

Systemd stops when a referenced `EnvironmentFile` is missing; either create the `.env` file or keep the dashed form shown above so the service can boot without it. The dynamically generated `/run/user/%U/desk_display.env` file is produced by the gate script before every launch.

### Display HAT Mini controls

- **X button:** skips the remainder of the current screen and moves on immediately.
- **Y button:** requests a `systemctl restart desk_display.service`, which stops the service, runs `cleanup.sh`, and starts a
  fresh process.
- **A/B buttons:** currently unused but logged when pressed so you can build new shortcuts.

---

## Screenshots & archiving

- Screenshots land in a writable XDG-style data directory (by default `~/.local/share/desk_display_hyperpixel4/screenshots/`) when `ENABLE_SCREENSHOTS=True`. Set `DESK_DISPLAY_SCREENSHOT_DIR` or edit `storage_overrides.py` to override the location explicitly.
- **Batch archiving:** once the live folder reaches **500** images, the program moves the **entire batch** into `screenshot_archive/<screen>/` beside the screenshots directory (images only) so the archive mirrors the folder layout under the live folder.
- You will **not** see per‑image pruning logs; instead you’ll see a single archive log like: `🗃️ Archived 500 screenshot(s) → …`

> Tip: videos (if enabled) are written to `screenshots/display_output.mp4` and aren’t moved by the archiver.

---

## GitHub update indicator

`utils.check_github_updates()` compares local HEAD with `origin/HEAD`. If they differ, a **red dot** appears at the lower‑left of date/time screens.

The checker now logs **which files have diverged** when updates exist, for easier review (uses `git diff --name-only HEAD..origin/HEAD`).

---

## Troubleshooting

- **Too‑dark colors on date/time:** this project forces high‑brightness random RGB values to ensure legibility on the LCD.
- **lgpio wheel fails to link on Trixie:** install `liblgpio-dev` so the `lgpio` Python package can find `liblgpio.so` during
  the build: `sudo apt-get install -y liblgpio-dev`.
- **Missing logos:** you’ll see a warning like `Logo file missing: CUBS.png`. Add the correct file into `images/mlb/`.
- **No WebP animation:** ensure your Pillow build supports WebP (`pip3 show pillow`). PNG fallback will still work.
- **Network/API errors:** MLB/OWM requests are time‑bounded; transient timeouts are logged and screens are skipped gracefully.
- **NHL statsapi DNS warning:** run `python3 nhl_scoreboard.py --diagnose-dns` to print resolver details, `/etc/resolv.conf`, and
  quick HTTP checks for both the statsapi and api-web fallbacks. Attach the JSON output when filing an issue.
- **Font not found:** the code falls back to `ImageFont.load_default()` so the app keeps running; install the missing TTFs to restore look.

---

## License

Personal / hobby project. Use at your own risk. Team names and logos belong to their respective owners.

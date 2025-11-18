# Requirements Section for README.md

Replace the current "Requirements" section in your README.md with this updated version:

---

## Requirements

- **Raspberry Pi** (tested on Pi Zero/Zero 2 W, Pi 4, and Pi 5)
- **Raspberry Pi OS Bookworm or Trixie** (64-bit) with Wayland enabled – legacy X11 sessions continue to work via the service gate
- **Pimoroni HyperPixel 4.0** Square (720×720 LCD) or HyperPixel 4.0 (800×480 LCD) wired to SPI0
- **Python 3.11+** (Bookworm ships 3.11; Trixie ships 3.12)

### System Packages

#### For Debian Trixie (13.x - Current Stable)

```bash
sudo apt-get update
sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg62-turbo-dev libopenblas-pthread-dev \
    libopenjp2-7 libtiff6 libcairo2-dev libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi8 network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1 libgles-dev libdrm2
```

#### For Debian Bookworm (12.x - Oldstable)

```bash
sudo apt-get update
sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg-dev libopenblas0 libopenblas-dev \
    libopenjp2-7-dev libtiff5-dev libcairo2-dev libpango1.0-dev \
    libgdk-pixbuf2.0-dev libffi-dev network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1-mesa libgles2-mesa libdrm2
```

**Note:** Package names changed between Bookworm and Trixie. Check your version with `cat /etc/debian_version` (12.x = Bookworm, 13.x = Trixie).

### Python Environment Setup

Create and activate a virtual environment before installing the Python dependencies:

```bash
python3 -m venv venv && source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Optional Pillow WebP Support

Pillow on current Raspberry Pi OS builds usually includes WebP support. If animated WebP is not rendering, upgrade Pillow:

```bash
pip install --upgrade pillow
```

### Sensor-Specific Packages

The `bme68x` package is required when using the bundled BME688 air quality sensor helper. Install `adafruit-circuitpython-sht4x` when wiring an Adafruit SHT41 (STEMMA QT). Install `pimoroni-bme280` for the Pimoroni Multi-Sensor Stick's BME280 breakout (shares a board with the LTR559 and LSM6DS3).

---

## Key Package Changes Between Versions

For reference, here are the main package name changes from Bookworm to Trixie:

| Bookworm (12.x)          | Trixie (13.x)              | Notes                           |
|--------------------------|----------------------------|---------------------------------|
| `libjpeg-dev`            | `libjpeg62-turbo-dev`      | JPEG library development files  |
| `libopenblas0`           | `libopenblas-pthread-dev`  | Combined runtime + dev package  |
| `libopenblas-dev`        | `libopenblas-pthread-dev`  | Now single package              |
| `libopenjp2-7-dev`       | `libopenjp2-7`             | Runtime lib sufficient          |
| `libtiff5-dev`           | `libtiff6`                 | Version bump, runtime lib       |
| `libpango1.0-dev`        | `libpango-1.0-0`           | Runtime lib sufficient          |
| `libgdk-pixbuf2.0-dev`   | `libgdk-pixbuf-2.0-0`      | Runtime lib sufficient          |
| `libffi-dev`             | `libffi8`                  | Runtime lib sufficient          |
| `libegl1-mesa`           | `libegl1`                  | Vendor-neutral version          |
| `libgles2-mesa`          | `libgles-dev`              | Consolidated GLES package       |

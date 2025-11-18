# Updated Dependencies for Debian Bookworm and Trixie

## For Debian Trixie (Testing/Stable - Current)

Many package names have changed in Debian Trixie. Use this command instead:

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

### Key Package Changes in Trixie:
- `libjpeg-dev` → `libjpeg62-turbo-dev`
- `libopenblas0` + `libopenblas-dev` → `libopenblas-pthread-dev` (combines both)
- `libopenjp2-7-dev` → `libopenjp2-7` (runtime lib; dev package not needed)
- `libtiff5-dev` → `libtiff6` (version bump)
- `libpango1.0-dev` → `libpango-1.0-0` (runtime lib)
- `libgdk-pixbuf2.0-dev` → `libgdk-pixbuf-2.0-0` (runtime lib)
- `libffi-dev` → `libffi8` (runtime lib)
- `libegl1-mesa` → `libegl1` (vendor-neutral version)
- `libgles2-mesa` → `libgles-dev` (consolidated package)

## For Debian Bookworm (Oldstable)

If you're still on Debian Bookworm, use the original command:

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

## Verifying Your Debian Version

To check which version you're running:

```bash
cat /etc/debian_version
# Bookworm = 12.x
# Trixie = 13.x (currently stable as of June 2025)
```

Or use:

```bash
lsb_release -a
```

## After Installing Dependencies

Once the appropriate packages are installed, continue with creating the virtual environment:

```bash
cd ~/desk_display_hyperpixel4
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

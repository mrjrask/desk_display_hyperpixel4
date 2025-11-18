# Quick Command Reference Card

## Check Your Debian Version
```bash
cat /etc/debian_version
# 12.x = Bookworm
# 13.x = Trixie
```

---

## DEBIAN TRIXIE (13.x) - Use This Command:

```bash
sudo apt-get update && sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg62-turbo-dev libopenblas-pthread-dev \
    libopenjp2-7 libtiff6 libcairo2-dev libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi8 network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1 libgles-dev libdrm2
```

---

## DEBIAN BOOKWORM (12.x) - Use This Command:

```bash
sudo apt-get update && sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg-dev libopenblas0 libopenblas-dev \
    libopenjp2-7-dev libtiff5-dev libcairo2-dev libpango1.0-dev \
    libgdk-pixbuf2.0-dev libffi-dev network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1-mesa libgles2-mesa libdrm2
```

---

## After Installing Dependencies:

```bash
cd ~/desk_display_hyperpixel4
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Package Changes Cheat Sheet:

**Trixie replaces:**
- libjpeg-dev → libjpeg62-turbo-dev
- libopenblas0 + libopenblas-dev → libopenblas-pthread-dev
- libopenjp2-7-dev → libopenjp2-7
- libtiff5-dev → libtiff6
- libpango1.0-dev → libpango-1.0-0
- libgdk-pixbuf2.0-dev → libgdk-pixbuf-2.0-0
- libffi-dev → libffi8
- libegl1-mesa → libegl1
- libgles2-mesa → libgles-dev

# APT Repository Issues - Troubleshooting Guide

## Problem
Packages cannot be located even after running `apt-get update`, with errors like:
```
E: Unable to locate package python3-opencv
E: Unable to locate package libjpeg62-turbo-dev
```

## Root Cause
This happens when your APT sources are not properly configured. Raspberry Pi OS needs **both** Debian repositories AND Raspberry Pi specific repositories.

## Solution Steps

### Step 1: Run Diagnostics

First, let's see what's wrong:

```bash
# Download and run the diagnostic script
chmod +x diagnose_apt.sh
sudo ./diagnose_apt.sh
```

Share the output so we can see exactly what's misconfigured.

### Step 2: Fix APT Sources (if needed)

If your sources are misconfigured, run:

```bash
# This will backup your current sources and set up correct ones
chmod +x fix_apt_sources.sh
sudo ./fix_apt_sources.sh
```

### Step 3: Verify Package Availability

After fixing sources, test if packages are now available:

```bash
apt-cache policy python3-opencv
apt-cache policy libopenblas-pthread-dev
apt-cache policy libjpeg62-turbo-dev
```

You should see output with version numbers and sources.

### Step 4: Install Dependencies

Once packages are available, run the appropriate installation command:

**For Trixie (13.x):**
```bash
sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg62-turbo-dev libopenblas-pthread-dev \
    libopenjp2-7 libtiff6 libcairo2-dev libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi8 network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1 libgles-dev libdrm2
```

**For Bookworm (12.x):**
```bash
sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg-dev libopenblas0 libopenblas-dev \
    libopenjp2-7-dev libtiff5-dev libcairo2-dev libpango1.0-dev \
    libgdk-pixbuf2.0-dev libffi-dev network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1-mesa libgles2-mesa libdrm2
```

## Common Issues & Fixes

### Issue 1: Missing `contrib` and `non-free` sections

**Symptom:** Some packages can't be found
**Fix:** Your sources.list needs these sections enabled:
```
deb http://deb.debian.org/debian trixie main contrib non-free non-free-firmware
```

### Issue 2: Missing Raspberry Pi repository

**Symptom:** Raspberry Pi specific packages missing
**Fix:** Add this line to sources.list:
```
deb http://archive.raspberrypi.org/debian/ trixie main
```

### Issue 3: Wrong Debian version in sources.list

**Symptom:** Running Trixie but sources.list says `bookworm`
**Fix:** Update all instances of `bookworm` to `trixie` in /etc/apt/sources.list

### Issue 4: Outdated package lists

**Symptom:** Packages not found after fixing sources
**Fix:** 
```bash
sudo apt-get clean
sudo apt-get update
```

## Manual APT Sources Configuration

If the automated scripts don't work, manually edit your sources:

```bash
sudo nano /etc/apt/sources.list
```

**For Raspberry Pi OS Trixie, use:**
```
deb http://deb.debian.org/debian trixie main contrib non-free non-free-firmware
deb http://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware
deb http://archive.raspberrypi.org/debian/ trixie main
```

**For Raspberry Pi OS Bookworm, use:**
```
deb http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware
deb http://deb.debian.org/debian bookworm-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware
deb http://archive.raspberrypi.org/debian/ bookworm main
```

After editing, save (Ctrl+X, Y, Enter) and run:
```bash
sudo apt-get update
```

## Checking Your Configuration

Verify your setup is correct:

```bash
# Check Debian version
cat /etc/debian_version

# Check OS info
cat /etc/os-release

# View current sources
cat /etc/apt/sources.list

# Test package availability
apt-cache search python3-opencv
apt-cache policy python3-opencv
```

## Still Having Issues?

If packages still can't be found after these steps:

1. **Check your internet connection:**
   ```bash
   ping -c 3 deb.debian.org
   ```

2. **Check for conflicting sources:**
   ```bash
   ls -la /etc/apt/sources.list.d/
   ```
   Remove or comment out any conflicting .list files

3. **Clear apt cache completely:**
   ```bash
   sudo rm -rf /var/lib/apt/lists/*
   sudo apt-get clean
   sudo apt-get update
   ```

4. **Verify architecture:**
   ```bash
   dpkg --print-architecture
   ```
   Should show `arm64` or `armhf` on Raspberry Pi

5. **Share diagnostic output:**
   Run the `diagnose_apt.sh` script and share the complete output

## Emergency Fallback: Use Bookworm

If Trixie repositories are consistently problematic, you can:

1. Check if you're actually running Bookworm:
   ```bash
   cat /etc/debian_version
   ```

2. If showing 12.x, use Bookworm packages instead (different command - see above)

3. Consider staying on Bookworm until Raspberry Pi OS Trixie is more stable

# IMMEDIATE ACTION REQUIRED - APT Sources Issue

Your APT sources are not configured correctly. Packages exist but your system can't find them.

## Quick Fix - Run These Commands:

```bash
# 1. First, let's diagnose the problem
wget https://raw.githubusercontent.com/mrjrask/desk_display_hyperpixel4/main/diagnose_apt.sh
chmod +x diagnose_apt.sh
sudo ./diagnose_apt.sh
```

**OR if you have the file locally:**

```bash
chmod +x diagnose_apt.sh
sudo ./diagnose_apt.sh > apt_diagnosis.txt
cat apt_diagnosis.txt
```

## Look for these RED FLAGS in the output:

1. **Missing repositories in /etc/apt/sources.list:**
   - Should have `deb http://deb.debian.org/debian trixie main contrib non-free`
   - Should have `deb http://archive.raspberrypi.org/debian/ trixie main`

2. **Version mismatch:**
   - Debian version says 13.x (Trixie) but sources.list says "bookworm"
   - OR Debian version says 12.x (Bookworm) but you're using Trixie commands

3. **Missing sections:**
   - Only has "main", missing "contrib non-free non-free-firmware"

## Most Likely Issue: Wrong/Missing Sources

Run this to fix (it will backup your current config):

```bash
sudo bash fix_apt_sources.sh
```

This will:
- ✓ Detect your Debian version automatically
- ✓ Backup your current sources.list
- ✓ Set up correct repositories
- ✓ Run apt-get update

## After Fixing Sources:

Test if packages are now available:

```bash
apt-cache policy python3-opencv
```

Should show something like:
```
python3-opencv:
  Installed: (none)
  Candidate: 4.10.0+dfsg-5
  Version table:
     4.10.0+dfsg-5 500
        500 http://deb.debian.org/debian trixie/main arm64 Packages
```

## Then Install Dependencies:

**If you're on Trixie (13.x):**
```bash
sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg62-turbo-dev libopenblas-pthread-dev \
    libopenjp2-7 libtiff6 libcairo2-dev libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi8 network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1 libgles-dev libdrm2
```

**If you're on Bookworm (12.x):**
```bash
sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg-dev libopenblas0 libopenblas-dev \
    libopenjp2-7-dev libtiff5-dev libcairo2-dev libpango1.0-dev \
    libgdk-pixbuf2.0-dev libffi-dev network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1-mesa libgles2-mesa libdrm2
```

## What Went Wrong?

The packages DO exist in Debian repositories, but your system doesn't know where to look for them. This usually happens when:

1. **Fresh install** - Sources not fully configured
2. **Upgraded** - Sources still point to old version (bookworm → trixie)
3. **Missing sections** - `contrib` and `non-free` not enabled
4. **No Raspberry Pi repo** - Some packages are in Pi-specific repos

## Files You Need:

All diagnostic and fix scripts are in your outputs folder:
- `diagnose_apt.sh` - Find out what's wrong
- `fix_apt_sources.sh` - Automatically fix your sources
- `TROUBLESHOOTING_APT.md` - Complete troubleshooting guide

## Quick Self-Check:

```bash
# What version are you running?
cat /etc/debian_version

# What do your sources say?
grep "^deb" /etc/apt/sources.list | grep -v "^#"

# Are packages available?
apt-cache search python3-opencv | grep "^python3-opencv "
```

If the search returns nothing, your sources are definitely misconfigured.

## Need More Help?

Run the diagnostic script and share the **complete output**. That will show exactly what needs to be fixed.

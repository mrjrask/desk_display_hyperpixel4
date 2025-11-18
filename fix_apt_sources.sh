#!/bin/bash
# Fix APT sources for Raspberry Pi OS (Debian Trixie base)

echo "================================================"
echo "Raspberry Pi OS APT Sources Fix for Trixie/Bookworm"
echo "================================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Detect Debian version
if [ -f /etc/debian_version ]; then
    DEBIAN_VERSION=$(cat /etc/debian_version)
    MAJOR_VERSION=$(echo $DEBIAN_VERSION | cut -d. -f1)
    echo "Detected Debian version: $DEBIAN_VERSION (major: $MAJOR_VERSION)"
else
    echo "Cannot detect Debian version"
    exit 1
fi

# Check if Raspberry Pi OS
if [ ! -f /etc/rpi-issue ]; then
    echo "Warning: This doesn't appear to be Raspberry Pi OS"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Backing up current sources..."
cp /etc/apt/sources.list /etc/apt/sources.list.backup.$(date +%Y%m%d_%H%M%S)
echo "✓ Backup created"

echo ""
echo "Determining correct sources..."

# For Bookworm (12.x)
if [ "$MAJOR_VERSION" = "12" ]; then
    echo "Setting up sources for Bookworm..."
    cat > /etc/apt/sources.list << 'EOF'
deb http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware
deb http://deb.debian.org/debian bookworm-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware

# Raspberry Pi OS specific
deb http://archive.raspberrypi.org/debian/ bookworm main
EOF

# For Trixie (13.x)
elif [ "$MAJOR_VERSION" = "13" ]; then
    echo "Setting up sources for Trixie..."
    cat > /etc/apt/sources.list << 'EOF'
deb http://deb.debian.org/debian trixie main contrib non-free non-free-firmware
deb http://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware

# Raspberry Pi OS specific (if available)
deb http://archive.raspberrypi.org/debian/ trixie main
EOF
else
    echo "Unsupported Debian version: $DEBIAN_VERSION"
    exit 1
fi

echo "✓ Sources file updated"

echo ""
echo "Updating package lists..."
apt-get update

echo ""
echo "================================================"
echo "Sources fixed! Now try installing packages again."
echo "================================================"
echo ""
echo "Your old sources.list has been backed up to:"
echo "/etc/apt/sources.list.backup.*"

#!/bin/bash
# Test script to verify all dependencies for desk_display_hyperpixel4
# This script checks which Debian version you're running and tests the installation

set -e

echo "=================================================="
echo "Desk Display HyperPixel4 - Dependency Test Script"
echo "=================================================="
echo ""

# Detect Debian version
if [ -f /etc/debian_version ]; then
    DEBIAN_VERSION=$(cat /etc/debian_version)
    echo "Detected Debian version: $DEBIAN_VERSION"
    
    # Extract major version
    MAJOR_VERSION=$(echo $DEBIAN_VERSION | cut -d. -f1)
    
    if [ "$MAJOR_VERSION" = "12" ]; then
        echo "✓ Running Debian Bookworm (12.x)"
        PACKAGES="python3-venv python3-pip python3-dev python3-opencv \
                  build-essential libjpeg-dev libopenblas0 libopenblas-dev \
                  libopenjp2-7-dev libtiff5-dev libcairo2-dev libpango1.0-dev liblgpio-dev \
                  libgdk-pixbuf2.0-dev libffi-dev network-manager wireless-tools \
                  i2c-tools fonts-dejavu-core fonts-noto-color-emoji libgl1 libx264-dev ffmpeg git \
                  libatlas-base-dev libegl1-mesa libgles2-mesa libdrm2"
    elif [ "$MAJOR_VERSION" = "13" ]; then
        echo "✓ Running Debian Trixie (13.x)"
        PACKAGES="python3-venv python3-pip python3-dev python3-opencv \
                  build-essential libjpeg62-turbo-dev libopenblas-pthread-dev \
                  libopenjp2-7 libtiff6 libcairo2-dev libpango-1.0-0 liblgpio-dev \
                  libgdk-pixbuf-2.0-0 libffi8 network-manager wireless-tools \
                  i2c-tools fonts-dejavu-core fonts-noto-color-emoji libgl1 libx264-dev ffmpeg git \
                  libatlas-base-dev libegl1 libgles-dev libdrm2"
    else
        echo "⚠ Warning: Unrecognized Debian version: $DEBIAN_VERSION"
        echo "This script supports Bookworm (12.x) and Trixie (13.x)"
        exit 1
    fi
else
    echo "✗ Error: Cannot detect Debian version"
    exit 1
fi

echo ""
echo "Testing package availability..."
echo "================================"
echo ""

# Update package list
echo "Updating package list..."
sudo apt-get update -qq

# Test if all packages are available
MISSING_PACKAGES=""
for package in $PACKAGES; do
    if apt-cache show "$package" &>/dev/null; then
        echo "✓ $package"
    else
        echo "✗ $package - NOT FOUND"
        MISSING_PACKAGES="$MISSING_PACKAGES $package"
    fi
done

echo ""
echo "================================"
echo ""

if [ -z "$MISSING_PACKAGES" ]; then
    echo "✓ All packages are available!"
    echo ""
    echo "To install all dependencies, run:"
    echo ""
    echo "sudo apt-get install -y \\"
    echo "$PACKAGES" | fmt -w 70 | sed 's/^/    /'
    echo ""
else
    echo "✗ The following packages are not available:"
    echo "$MISSING_PACKAGES"
    echo ""
    echo "Please check your apt sources or Debian version."
    exit 1
fi

echo ""
echo "Test completed successfully!"

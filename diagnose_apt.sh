#!/bin/bash
# Diagnostic script for apt repository issues on Debian Trixie

echo "=========================================="
echo "Debian Trixie APT Repository Diagnostics"
echo "=========================================="
echo ""

echo "1. Checking Debian Version:"
echo "----------------------------"
cat /etc/debian_version
cat /etc/os-release | grep -E "PRETTY_NAME|VERSION_CODENAME"
echo ""

echo "2. Checking APT Sources:"
echo "------------------------"
echo "=== /etc/apt/sources.list ==="
cat /etc/apt/sources.list
echo ""

echo "=== Files in /etc/apt/sources.list.d/ ==="
ls -la /etc/apt/sources.list.d/
echo ""

for file in /etc/apt/sources.list.d/*.list; do
    if [ -f "$file" ]; then
        echo "=== Content of $file ==="
        cat "$file"
        echo ""
    fi
done

echo "3. Testing package availability:"
echo "--------------------------------"
echo "Testing key packages..."
apt-cache policy python3-opencv 2>/dev/null | head -5
apt-cache policy libopenblas-pthread-dev 2>/dev/null | head -5
apt-cache policy libjpeg62-turbo-dev 2>/dev/null | head -5
echo ""

echo "4. Checking if this is Raspberry Pi OS:"
echo "---------------------------------------"
if [ -f /etc/rpi-issue ]; then
    echo "✓ Raspberry Pi OS detected"
    cat /etc/rpi-issue
else
    echo "⚠ Not Raspberry Pi OS or /etc/rpi-issue missing"
fi
echo ""

echo "5. Architecture:"
echo "----------------"
dpkg --print-architecture
echo ""

echo "=========================================="
echo "Diagnostic Complete"
echo "=========================================="
echo ""
echo "Please share this output for further troubleshooting."

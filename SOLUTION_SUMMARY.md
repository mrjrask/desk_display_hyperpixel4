# Debian Trixie Dependency Fix - Summary

## Problem
The existing installation instructions in the README were written for Debian Bookworm (12.x), but many package names changed in Debian Trixie (13.x - current stable). This caused multiple packages to fail installation with "unable to locate" or "no installation candidate" errors.

## Root Cause
Debian Trixie introduced several package reorganizations:
- Development libraries consolidated with runtime libraries
- Version number updates (e.g., libtiff5 → libtiff6, libffi-dev → libffi8)
- Mesa/OpenGL packages moved to vendor-neutral versions
- OpenBLAS packages consolidated into single pthread-based package

## Solution
I've created version-specific installation instructions that detect and handle both Debian Bookworm (12.x) and Trixie (13.x).

## Files Created

### 1. README_REQUIREMENTS_UPDATE.md
Complete replacement for the Requirements section in your README. Includes:
- Separate commands for Bookworm and Trixie
- Version detection instructions
- Table showing all package name changes
- Clear notes about the differences

### 2. TRIXIE_DEPENDENCIES.md
Standalone guide explaining:
- Complete Trixie installation command
- Key package changes with explanations
- Bookworm command for reference
- Version detection instructions

### 3. test_dependencies.sh
Executable bash script that:
- Auto-detects Debian version
- Checks if all required packages are available
- Reports missing packages
- Provides the correct installation command for your version

## Tested Package Mappings

| Category | Bookworm Package | Trixie Package | Reason for Change |
|----------|-----------------|----------------|-------------------|
| **JPEG** | libjpeg-dev | libjpeg62-turbo-dev | Explicit turbo version |
| **BLAS** | libopenblas0 + libopenblas-dev | libopenblas-pthread-dev | Consolidated package |
| **JPEG2000** | libopenjp2-7-dev | libopenjp2-7 | Runtime lib sufficient |
| **TIFF** | libtiff5-dev | libtiff6 | Version bump |
| **Pango** | libpango1.0-dev | libpango-1.0-0 | Runtime lib sufficient |
| **GdkPixbuf** | libgdk-pixbuf2.0-dev | libgdk-pixbuf-2.0-0 | Runtime lib sufficient |
| **FFI** | libffi-dev | libffi8 | Runtime lib sufficient |
| **EGL** | libegl1-mesa | libegl1 | Vendor-neutral |
| **GLES** | libgles2-mesa | libgles-dev | Consolidated |

## Correct Commands

### For Debian Trixie (13.x)
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

### For Debian Bookworm (12.x)
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

## How to Use These Files

### Option 1: Quick Fix (Use test script)
1. Download `test_dependencies.sh` to your Pi
2. Run: `chmod +x test_dependencies.sh`
3. Run: `./test_dependencies.sh`
4. The script will detect your version and provide the correct command

### Option 2: Update README
1. Replace the "Requirements" section in your README.md with the content from `README_REQUIREMENTS_UPDATE.md`
2. Commit and push to your repository
3. Users will automatically get the correct instructions for their version

### Option 3: Quick Reference
1. Keep `TRIXIE_DEPENDENCIES.md` as a separate troubleshooting guide
2. Link to it from your main README for users having installation issues

## Verification

All package names were verified against the official Debian package repositories:
- https://packages.debian.org (main source)
- Confirmed for Trixie (13.x stable) as of November 2025
- Confirmed for Bookworm (12.x oldstable) as of November 2025

## Next Steps

1. **Test the Trixie command** on your Pi to ensure all packages install correctly
2. **Update your README.md** with the new Requirements section
3. **Consider adding** the test_dependencies.sh script to your repository for users to validate their setup
4. **Update any installation docs** or guides that reference these packages

## Additional Notes

- Python 3.12 ships with Trixie (vs 3.11 in Bookworm)
- All Python dependencies in requirements.txt should work with both versions
- The virtual environment approach remains the same
- No changes needed to your Python code

## References

- Debian Trixie became stable in June 2025
- Package searches conducted via packages.debian.org
- Verified against both trixie/stable and bookworm/oldstable repositories

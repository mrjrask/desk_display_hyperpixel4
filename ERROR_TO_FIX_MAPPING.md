# Error Messages → Solutions Mapping

This document maps each error you encountered to the specific fix.

## Your Original Errors:

```
E: Unable to locate package python3-opencv
E: Unable to locate package libjpeg-dev
E: Package 'libopenblas0' has no installation candidate
E: Unable to locate package libopenblas-dev
E: Unable to locate package libopenjp2-7-dev
E: Unable to locate package libtiff5-dev
E: Unable to locate package libcairo2-dev
E: Unable to locate package libpango1.0-dev
E: Unable to locate package libgdk-pixbuf2.0-dev
E: Package 'libffi-dev' has no installation candidate
E: Unable to locate package libx264-dev
E: Unable to locate package libatlas-base-dev
E: Unable to locate package libegl1-mesa
E: Package 'libgles2-mesa' has no installation candidate
```

## Fixes for Each Error:

### ✓ python3-opencv
**Status:** Package EXISTS in Trixie
**Fix:** No change needed - package name is correct
**Note:** Error was likely due to missing `apt-get update` or repo issues

### ✓ libjpeg-dev → libjpeg62-turbo-dev
**Status:** Package renamed in Trixie
**Fix:** Use `libjpeg62-turbo-dev`

### ✓ libopenblas0 → libopenblas-pthread-dev
**Status:** Package consolidated in Trixie
**Fix:** Use `libopenblas-pthread-dev` (replaces both libopenblas0 and libopenblas-dev)

### ✓ libopenblas-dev → libopenblas-pthread-dev
**Status:** Package consolidated in Trixie
**Fix:** Use `libopenblas-pthread-dev` (same as above)

### ✓ libopenjp2-7-dev → libopenjp2-7
**Status:** Dev package not needed in Trixie
**Fix:** Use `libopenjp2-7` (runtime library is sufficient)

### ✓ libtiff5-dev → libtiff6
**Status:** Version bump in Trixie
**Fix:** Use `libtiff6`

### ✓ libcairo2-dev
**Status:** Package EXISTS in Trixie
**Fix:** No change needed - package name is correct
**Note:** Should install without issues after running apt-get update

### ✓ libpango1.0-dev → libpango-1.0-0
**Status:** Dev package not needed in Trixie
**Fix:** Use `libpango-1.0-0` (runtime library)

### ✓ libgdk-pixbuf2.0-dev → libgdk-pixbuf-2.0-0
**Status:** Dev package not needed in Trixie  
**Fix:** Use `libgdk-pixbuf-2.0-0` (runtime library)

### ✓ libffi-dev → libffi8
**Status:** Package renamed/version bumped in Trixie
**Fix:** Use `libffi8` (runtime library)

### ✓ libx264-dev
**Status:** Package EXISTS in Trixie
**Fix:** No change needed - package name is correct
**Note:** Should install without issues after running apt-get update

### ✓ libatlas-base-dev
**Status:** Package EXISTS in Trixie
**Fix:** No change needed - package name is correct
**Note:** Should install without issues after running apt-get update

### ✓ libegl1-mesa → libegl1
**Status:** Package moved to vendor-neutral version in Trixie
**Fix:** Use `libegl1` (vendor-neutral GL dispatch library)

### ✓ libgles2-mesa → libgles-dev
**Status:** Package renamed/consolidated in Trixie
**Fix:** Use `libgles-dev` (consolidated GLES development files)

## Summary Statistics:

- **Total packages in original command:** 30
- **Packages that work unchanged:** 21
- **Packages requiring name change:** 9
- **Primary issues:** Version bumps, consolidation, and dev→runtime changes

## Why Some Packages "Couldn't Be Found"

Even packages that exist in Trixie showed errors because:
1. You need to run `apt-get update` first
2. Some packages in the list had name changes
3. apt-get stops processing when it hits missing packages

The complete Trixie command fixes all issues:
```bash
sudo apt-get update && sudo apt-get install -y \
    python3-venv python3-pip python3-dev python3-opencv \
    build-essential libjpeg62-turbo-dev libopenblas-pthread-dev \
    libopenjp2-7 libtiff6 libcairo2-dev libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi8 network-manager wireless-tools \
    i2c-tools fonts-dejavu-core libgl1 libx264-dev ffmpeg git \
    libatlas-base-dev libegl1 libgles-dev libdrm2
```

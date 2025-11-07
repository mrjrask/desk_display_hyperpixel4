# Nixie clock artwork

Download the digit sprites from the MagicMirror module (https://github.com/Isaac-the-Man/MMM-nixie-clock) and copy the PNGs into this directory.

The display will look for 0-9 PNGs either directly in this folder or in a `large/` subdirectory (matching the module's default structure). An optional `colon.png` or `dot.png` can also be included if you want to override the procedural colon.

If the artwork is missing, the clock will fall back to drawing procedural digits so it still renders.

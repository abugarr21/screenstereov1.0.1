# ScreenStereo v1.0.1 Release Notes

ScreenStereo v1.0.1 is the next sterile public release following the earlier public beta.

## Principal correction

The guided first-run sequence now crosses the durable mapping boundary explicitly:

1. Discover connected displays.
2. Discover compatible audio outputs.
3. Correlate display and audio identities.
4. Require the exact user confirmation.
5. Write the confirmed durable display map.
6. Activate the selected audio mode.

Mode activation is blocked when the durable map writer fails.

## Operational behavior

ScreenStereo provides deterministic PipeWire routing for multi-display HDMI audio. It supports split left/right routing, mirrored routing, status inspection, recovery guidance, and current-only runtime state surfaces.

## Validation boundary

Static public-package validation and an isolated clean-install lifecycle passed. The isolated lifecycle covered installation, discovery, correlation, invalid-confirmation refusal, exact-confirmation acceptance, durable-map creation, default uninstall preservation, reinstall, and purge.

The controlled live mirror-audible tranche was withdrawn by the user and is not represented as passed. Controlled fault-injection and recovery validation was not run.

## Provenance

ScreenStereo was developed within Project Sentinel using evidence-first, refusal-first, authority-gated implementation practices.

## License

ScreenStereo v1.0.1 is released under GPL-3.0-or-later.

Copyright (C) 2026 Andrew Gold

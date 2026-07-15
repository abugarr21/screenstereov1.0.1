# Privacy

ScreenStereo operates locally in the current user's desktop and audio
session.

## Data it observes

The discovery and correlation components may observe:

- connected display connector information;
- display identification data such as manufacturer, model, or serial
  fields exposed by the operating system;
- local ALSA, PipeWire, and PulseAudio-compatible endpoint metadata;
- user-systemd service state;
- ScreenStereo virtual sink and module state.

This information is used to propose and resolve the relationship between
physical displays and their audio endpoints.

## Data it does not collect

The packaged runtime does not:

- record microphone audio;
- capture application audio content for storage;
- transmit telemetry;
- upload device identities;
- contact a remote service;
- maintain a cloud account;
- create an advertising or analytics identifier.

## Local storage

Durable user configuration is stored beneath:

```text
~/.config/screenstereo-pipewire/
~/.config/hbai-audio/
```

Current runtime observations and status are stored beneath:

```text
~/.local/state/screenstereo-pipewire/
~/.local/state/hbai-audio/
```

Discovery, correlation, confirmation, resolution, doctor, recovery, and
validation surfaces use fixed current-result files. A new result
overwrites the prior current result. ScreenStereo does not intentionally
create timestamped runtime-result directories.

## Mapping confirmation

A proposed mapping is not treated as durable user intent until the exact
displayed confirmation phrase is supplied. This reduces the risk that a
transient or ambiguous observation becomes a persistent hardware
association without the user's knowledge.

## Uninstallation

The default uninstaller removes managed programs, units, and icons while
preserving configuration and current state.

To remove ScreenStereo configuration and state as well, run:

```text
~/.local/bin/screenstereo-uninstall --purge
```

The purge option affects only the documented ScreenStereo-managed
configuration and state roots in the selected user home.

License: GPL-3.0-or-later.

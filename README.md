[README.md](https://github.com/user-attachments/files/30028057/README.md)
<!-- SCREENSTEREO_V1_0_1_RELEASE_IDENTITY_START -->
> **Release:** ScreenStereo v1.0.1  
> **License:** GPL-3.0-or-later  
> This sterile public package follows the earlier public beta. Its principal correction ensures that first-run writes the confirmed durable display map before activating an audio mode.

<!-- SCREENSTEREO_V1_0_1_RELEASE_IDENTITY_END -->

# ScreenStereo

ScreenStereo is a user-local Linux utility that maps two display-audio
endpoints by hardware identity and presents them as either a stereo
left/right pair or a mirrored output.

It was created as a bounded operational product of the Project Sentinel
architecture. ScreenStereo is standalone software and does not require
the wider Project Sentinel stack.

## What it does

ScreenStereo observes connected displays and available audio endpoints,
correlates their identities, presents a proposed left/right mapping, and
requires an exact typed confirmation before that mapping becomes
durable.

The confirmed mapping is then resolved at runtime so that transient
connector numbering does not become the long-term identity source.

Supported operating modes are:

- **split** — the left channel is routed to the confirmed left display
  and the right channel to the confirmed right display;
- **mirror** — the same stereo program is delivered to both confirmed
  display sinks;
- **reset** — ScreenStereo-managed virtual routing is removed;
- **apply** — the currently configured mode is reapplied;
- **status** — the current configuration and graph state are displayed.

## Reference environment

ScreenStereo was developed on Ubuntu 24.04 LTS using GNOME on X11,
PipeWire, PipeWire PulseAudio compatibility, WirePlumber, and a user
systemd session.

The packaged implementation depends on Bash, Python 3, `pactl`,
`wpctl`, `xrandr`, `aplay`, `systemctl --user`, and standard GNU command
line tools.

## Quick start

From the unpacked release directory:

```text
chmod +x install.sh first-run.sh uninstall.sh
./install.sh
~/.local/bin/screenstereo-first-run
```

The installer copies the managed programs, user-systemd units, and
status icons into the current user's home directory. Installation by
itself does not select a mapping, start the indicator, or modify the
audio graph.

Guided first-run displays the proposed mapping and asks for the exact
phrase shown by the setup program:

```text
CONFIRM LEFT=<model> RIGHT=<model>
```

Replace the model placeholders with the exact values displayed during
setup. A phrase that does not match exactly is rejected.

A noninteractive first-run may be invoked as:

```text
~/.local/bin/screenstereo-first-run \
  --confirmation 'CONFIRM LEFT=<exact-left-model> RIGHT=<exact-right-model>' \
  --mode split
```

## Operational boundaries

ScreenStereo does not silently persist an ambiguous mapping. Discovery
and runtime-resolution results are current-state files: a new result
replaces the prior result instead of creating timestamped result
directories.

The doctor is an explicit diagnostic action. It is not invoked on a
periodic timer by the indicator.

ScreenStereo does not record microphone audio, send telemetry, or upload
hardware observations.

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Operations](docs/OPERATIONS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Privacy](PRIVACY.md)
- [Security](SECURITY.md)
- [Project Sentinel reference](docs/PROJECT_SENTINEL_REFERENCE.md)

## License and provenance

Copyright (C) 2026 Andrew Gold.

ScreenStereo source code and bundled documentation are licensed under
the GNU General Public License, version 3 or, at your option, any later
version. The SPDX identifier is `GPL-3.0-or-later`.

People may use, study, modify, and redistribute ScreenStereo under those
terms. Distributed covered modifications must preserve the corresponding
freedoms and source-availability obligations of the GPL.

The dated repository history, release manifest, release checksums, and
Project Sentinel reference narrative preserve the provenance of the
original implementation.

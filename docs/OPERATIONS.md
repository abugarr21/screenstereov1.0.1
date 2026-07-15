# Operations

## Mode commands

ScreenStereo installs the mode selector at:

```text
~/.local/bin/hbai_audio_mode.sh
```

Supported commands are:

```text
~/.local/bin/hbai_audio_mode.sh split
~/.local/bin/hbai_audio_mode.sh mirror
~/.local/bin/hbai_audio_mode.sh reset
~/.local/bin/hbai_audio_mode.sh apply
~/.local/bin/hbai_audio_mode.sh status
```

`split` writes the configured mode and builds a two-channel virtual sink.
Its left channel is looped to the resolved left display sink, and its
right channel is looped to the resolved right display sink.

`mirror` writes the configured mode and builds a combine sink using both
resolved display sinks.

`reset` removes ScreenStereo-managed virtual routing and records reset as
the configured mode.

`apply` reads the saved mode and applies it. This is the action used by
the mode user service.

`status` prints the configured mode, relevant virtual sinks and sources,
and service observations.

## Services

Inspect the packaged user services:

```text
systemctl --user status hbai-audio-mode.service
systemctl --user status hbai-audio-indicator.service
```

Reapply the configured mode:

```text
systemctl --user restart hbai-audio-mode.service
```

Restart only the indicator:

```text
systemctl --user restart hbai-audio-indicator.service
```

The indicator does not run the doctor periodically.

## Doctor

Run an explicit diagnostic observation:

```text
~/.local/bin/hbai_audio_doctor.sh
```

Doctor output is written to fixed current report and status files beneath:

```text
~/.local/state/hbai-audio/
```

A new doctor result overwrites the prior current doctor result.

## Recovery

Run the recovery program only when a recovery attempt is intended:

```text
~/.local/bin/hbai_audio_recover.sh
```

Recovery reads the confirmed mapping and configured mode, observes the
current condition, and may rebuild ScreenStereo-managed virtual audio
objects.

Recovery is not a substitute for confirming an ambiguous or changed
hardware mapping.

## Mapping status

Show the current setup proposal or confirmed state:

```text
~/.local/bin/screenstereo_setup.py show
~/.local/bin/screenstereo_setup.py status
```

Reconfirmation should be performed only after reviewing the displayed
identities.

## Configuration and state

The durable display map is stored at:

```text
~/.config/screenstereo-pipewire/display-map.json
```

The selected operating mode is stored beneath:

```text
~/.config/hbai-audio/
```

Current discovery and runtime-resolution observations are stored beneath:

```text
~/.local/state/screenstereo-pipewire/
```

Current mode, doctor, recovery, indicator, split, and mirror status are
stored beneath:

```text
~/.local/state/hbai-audio/
```

These are bounded current-state surfaces rather than historical
timestamped result collections.

## Safe shutdown or removal

Remove ScreenStereo virtual routing without uninstalling:

```text
~/.local/bin/hbai_audio_mode.sh reset
```

Uninstall while preserving mapping and state:

```text
~/.local/bin/screenstereo-uninstall
```

See [Installation](INSTALLATION.md) for purge behavior.

License: GPL-3.0-or-later.

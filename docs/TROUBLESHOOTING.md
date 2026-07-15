# Troubleshooting

Begin with the explicit doctor:

```text
~/.local/bin/hbai_audio_doctor.sh
```

Then inspect mode and service state:

```text
~/.local/bin/hbai_audio_mode.sh status
systemctl --user status hbai-audio-mode.service
systemctl --user status hbai-audio-indicator.service
```

## No displays discovered

Confirm that the desktop session is X11 and that `xrandr` can see the
connected displays:

```text
xrandr --query
```

Reconnect or power-cycle the displays, then rerun:

```text
~/.local/bin/screenstereo_setup.py show
```

Do not confirm a mapping when the expected displays are absent.

## No HDMI or display-audio endpoints discovered

Confirm that the user-session audio server is reachable:

```text
pactl info
pactl list short sinks
wpctl status
```

Verify that PipeWire, PipeWire PulseAudio compatibility, and WirePlumber
are running in the user session.

## Mapping is ambiguous

ScreenStereo is designed to stop rather than guess. Review the connected
hardware and discovery output. Disconnect duplicate or unintended
displays, rerun setup, and confirm only when the displayed left/right
proposal is unambiguous.

## Confirmation phrase rejected

Copy the exact phrase shown by `screenstereo_setup.py show`. Model text,
spacing, capitalization, and left/right order must match.

The placeholder form is only an example:

```text
CONFIRM LEFT=<model> RIGHT=<model>
```

## Left and right resolve to the same sink

This is treated as a collision and is refused. Check whether both
displays expose distinct audio endpoints. Review:

```text
pactl list short sinks
wpctl status
~/.local/bin/screenstereo_setup.py show
```

Reconfirm only after distinct identities are visible.

## Display map missing or invalid

Inspect the durable map:

```text
cat ~/.config/screenstereo-pipewire/display-map.json
```

Do not hand-edit uncertain hardware identities. Rerun guided first-run
and provide the exact confirmation phrase.

## Virtual sink does not materialize

Reset the managed graph and reapply the configured mode:

```text
~/.local/bin/hbai_audio_mode.sh reset
~/.local/bin/hbai_audio_mode.sh apply
```

Then run the doctor again.

For split mode, inspect:

```text
pactl list short sinks
pactl list short sources
pactl list short sink-inputs
pactl list short modules
```

For mirror mode, inspect the combine-sink module and both resolved
physical sinks.

## Indicator reports a malfunction

The indicator reflects observed status; it does not continuously repair
the graph. Run the doctor explicitly and review its current report.

Restarting the indicator alone does not rebuild audio routing:

```text
systemctl --user restart hbai-audio-indicator.service
```

## Recovery fails

Recovery cannot authorize a new mapping. Confirm that the durable map
still matches the connected hardware and that the user-session audio
server is available.

Reset, rerun guided setup when necessary, and then select the intended
mode.

## Uninstall or purge

A normal uninstall preserves configuration and state. Use `--purge` only
when those local records should also be deleted.

```text
~/.local/bin/screenstereo-uninstall --purge
```

License: GPL-3.0-or-later.

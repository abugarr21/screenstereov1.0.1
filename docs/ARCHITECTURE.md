# Architecture

ScreenStereo is divided into observation, confirmation, resolution,
graph construction, diagnosis, and presentation layers.

## Processing flow

```text
display discovery
        |
        v
audio discovery
        |
        v
correlation
        |
        v
explicit user confirmation
        |
        v
durable display map
        |
        v
runtime resolution
        |
        v
split or mirror graph construction
        |
        v
doctor, recovery, and indicator
```

## Hardware identity

Desktop connector names and audio device numbers can change across
boots, cable changes, driver events, or enumeration order. ScreenStereo
therefore treats connector numbering as an observation, not as the
durable identity authority.

Display discovery records locally available display identity fields.
Audio discovery records the locally available audio-endpoint surface.
Correlation proposes relationships between those observations.

The setup program then displays a proposed left/right assignment and
requires an exact typed confirmation. Only confirmed identity values are
written to the durable display map.

## Components

`screenstereo_display_discover.py`
: Writes the current display-discovery result.

`screenstereo_audio_discover.py`
: Writes the current audio-discovery result.

`screenstereo_correlate.py`
: Produces the current proposed display-to-audio correlation.

`screenstereo_setup.py`
: Shows the proposal, validates the exact confirmation phrase, and
  records current confirmation evidence.

`screenstereo_write_display_map.py`
: Writes the durable user-authorized display map.

`screenstereo_resolve.py`
: Resolves confirmed identities to the current audio endpoints.

`screenstereo_runtime.py`
: Provides the shared runtime-resolution interface used by consumers.

`hbai_audio_mode.sh`
: Selects, persists, applies, resets, and reports the operating mode.

`hbai_tv_lr_split_refresh.sh`
: Builds the split virtual sink, left and right remap sources, and
  loopbacks to the resolved display sinks.

`hbai_hdmi_all_refresh.sh`
: Builds the mirror combine sink from the resolved display sinks.

`hbai_audio_doctor.sh`
: Performs an explicit diagnostic observation and writes a current
  report and status.

`hbai_audio_recover.sh`
: Performs an explicit recovery attempt using the confirmed mapping and
  configured mode.

`hbai_audio_indicator.py`
: Presents the current operational condition in the desktop session.

## Mode service model

`hbai-audio-mode.service` reapplies the configured mode in the user
session. `hbai-audio-indicator.service` runs the desktop status
indicator.

The mode selector directly executes the packaged split or mirror refresh
script. References to `hbai-hdmi-all.service` and
`hbai-tv-lr-split.service` are compatibility cleanup and diagnostic
references; those legacy units are not required for graph activation and
are not packaged.

PipeWire, PipeWire PulseAudio compatibility, and WirePlumber are
platform-owned services.

## Current-state discipline

Runtime observations are intentionally current-only. Each subsystem
maintains one current result instead of an expanding series of
timestamped directories.

This keeps the state surface bounded and prevents passive indicator
operation from generating disk churn.

## Failure behavior

ScreenStereo refuses progression when:

- a required discovery surface is unavailable;
- the mapping is ambiguous;
- left and right resolve to the same sink;
- the exact confirmation phrase does not match;
- the durable map is missing or invalid;
- the user-session audio server cannot be reached;
- a required virtual sink or route does not materialize.

Failure is reported through status files, command output, and the
indicator rather than being hidden behind an automatic guess.

License: GPL-3.0-or-later.

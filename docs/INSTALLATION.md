# Installation

## Reference platform

The reference development environment is Ubuntu 24.04 LTS with GNOME on
X11, PipeWire, PipeWire PulseAudio compatibility, WirePlumber, and a
systemd user session.

Package names vary by distribution. The required command surface
includes:

```text
bash
python3
pactl
wpctl
xrandr
aplay
systemctl
awk
grep
sed
xargs
install
mkdir
rm
cp
```

An X11 session is required by the current display-discovery path.

## Install

Unpack the release and enter its root directory:

```text
chmod +x install.sh first-run.sh uninstall.sh
./install.sh
```

The default installation copies the runtime into the current user's
home directory but does not run first-run, select a mapping, start the
status indicator, or alter the audio graph.

The principal installation destinations are:

```text
~/.local/bin/
~/.config/systemd/user/
~/.local/share/hbai-audio/icons/
~/.local/share/screenstereo-pipewire/
```

User configuration and current-state directories are also prepared
beneath `~/.config/` and `~/.local/state/`.

The installer writes an enumerated managed-file manifest at:

```text
~/.local/share/screenstereo-pipewire/installed-files.txt
```

## Guided first-run

After installation, run:

```text
~/.local/bin/screenstereo-first-run
```

First-run performs these boundaries in order:

1. show the current display/audio mapping proposal;
2. require the exact typed mapping-confirmation phrase;
3. ask for `split` or `mirror`;
4. apply that mode;
5. enable the mode and indicator user services;
6. run the doctor explicitly.

The required phrase has this form:

```text
CONFIRM LEFT=<model> RIGHT=<model>
```

Type the exact values shown by the setup program. Do not type the
placeholder text literally.

A noninteractive invocation is available when the exact observed phrase
is already known:

```text
~/.local/bin/screenstereo-first-run \
  --confirmation 'CONFIRM LEFT=<exact-left-model> RIGHT=<exact-right-model>' \
  --mode split
```

## Installer options

Show installer help:

```text
./install.sh --help
```

Install and immediately enter first-run:

```text
./install.sh --run-first-run
```

Install without first-run:

```text
./install.sh --no-first-run
```

## Test-only home override

The installer supports an alternate absolute home root for isolated
testing:

```text
SCREENSTEREO_HOME=/tmp/example-home \
SCREENSTEREO_SKIP_SYSTEMD=1 \
./install.sh --no-first-run
```

This override is intended for packaging validation, not normal desktop
operation.

## Uninstall

Remove managed programs, units, and icons while preserving configuration
and current state:

```text
~/.local/bin/screenstereo-uninstall
```

Remove the managed runtime, configuration, and current state:

```text
~/.local/bin/screenstereo-uninstall --purge
```

See [Operations](OPERATIONS.md) and
[Troubleshooting](TROUBLESHOOTING.md) before purging a mapping that may
still be useful.

License: GPL-3.0-or-later.

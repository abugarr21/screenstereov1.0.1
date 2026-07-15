# Security Policy

## Scope

ScreenStereo is a user-local display-audio routing utility. It installs
into the current user's home directory and uses user-systemd services.
Normal installation and operation do not require root privileges.

The packaged runtime does not expose a network listener, remote command
surface, telemetry channel, or automatic update service.

## Authority boundaries

ScreenStereo separates observation from durable configuration.

Display and audio discovery may observe local device metadata, but the
proposed left/right relationship is not written as a durable display map
until the user types the exact confirmation phrase presented by the
setup program.

Ambiguous, incomplete, or colliding mappings fail closed rather than
silently selecting a device.

The installer copies a fixed, enumerated set of managed files. The
uninstaller removes that same managed surface. Configuration and current
state are preserved by default and are removed only when the user invokes
the explicit `--purge` option.

## Runtime behavior

The mode service applies the configured mode in the user's PipeWire
session. The indicator reports the observed condition but does not run
the doctor periodically.

Doctor and recovery commands are explicit user actions. Recovery may
rebuild ScreenStereo-managed virtual audio objects, so it should be
invoked only when the user intends that operation.

## Release integrity

Before installing a downloaded release, compare its SHA-256 checksum
with the checksum published for that release. Review the manifest to
confirm which files are included.

A checksum proves that the downloaded bytes match the identified
release artifact. It does not replace source review or operating-system
security controls.

## Reporting a vulnerability

Use the repository's private security-advisory facility when it is
available. Otherwise, open a minimal issue stating that a security
report is available, without publishing exploit details or sensitive
device information.

Include:

- the ScreenStereo release or commit identifier;
- the operating-system and desktop-session type;
- the affected command or service;
- the observed result and expected result;
- the smallest safe reproduction description.

## Supported security boundary

ScreenStereo assumes the current user controls their own home directory
and user session. It is not designed to defend against an attacker who
already has write access to that user's executable files, configuration,
systemd user units, or PipeWire session.

License: GPL-3.0-or-later.

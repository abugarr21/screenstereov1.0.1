# Project Sentinel Reference

## Why this document exists

ScreenStereo is intentionally a simple product. Its role in Project
Sentinel is not to demonstrate scale or spectacle. It demonstrates that
the architecture can carry an ordinary operational need from observation
through governed implementation to a release that another person can
inspect, install, modify, and verify.

ScreenStereo remains a standalone utility. It does not require the wider
Project Sentinel system at runtime.

## Architectural principles demonstrated

### Evidence before action

The implementation begins by observing connected displays, audio
endpoints, and their possible relationships. Observation is not treated
as permission to persist a mapping.

### Human authority at the durable boundary

The proposed left/right relationship becomes durable only after the user
types the exact confirmation phrase presented by the setup program.

This separates machine observation from evidenced human intent.

### Hardware identity instead of fragile numbering

Connector labels and device numbers may change. ScreenStereo preserves
confirmed hardware identities and resolves them against the current
system at runtime.

### Bounded current state

Discovery, correlation, confirmation, resolution, doctor, and recovery
surfaces maintain one current result per subsystem. New observations
replace prior current observations instead of accumulating timestamped
result directories.

This policy was reinforced during implementation when evidence exposed
unwanted passive disk churn. The release carries the corrected
current-only design.

### Safe refusal

Ambiguous mappings, sink collisions, missing identities, unreachable
audio services, and failed graph creation are reported as failures rather
than being hidden behind an automatic guess.

### Observable operation

Mode status, doctor results, recovery results, service state, and the
desktop indicator provide visible evidence of the system's current
condition.

The doctor remains an explicit action rather than a periodic background
authority.

### Narrow authority

The installer copies an enumerated user-local surface. It does not select
a hardware mapping or modify the audio graph unless the user advances
into guided first-run.

The uninstaller preserves configuration by default and removes it only
after an explicit purge request.

## Work-card process

Development used structured work cards to preserve scope, authority,
progression, observed evidence, corrections, and validation boundaries.

The private implementation work cards are not required by the released
utility and are not bundled into the sterile public source tree.

Public release evidence is instead expressed through inspectable source,
documentation, repository history, a file manifest, and SHA-256
checksums.

## What this release proves

ScreenStereo provides a concrete provenance point showing that the
Project Sentinel architecture was used to produce a complete operational
system with:

- a bounded problem statement;
- identity-aware discovery;
- explicit human confirmation;
- durable configuration;
- runtime resolution;
- normal operations and recovery;
- fail-closed behavior;
- controlled state retention;
- sterile packaging;
- public documentation;
- reproducible release evidence.

Others are free to use, study, change, and redistribute the implementation
under the GPL. That freedom does not erase the dated public provenance of
the original architecture, implementation, and release.

## License

Copyright (C) 2026 Andrew Gold.

This document and the ScreenStereo implementation are licensed under
GPL-3.0-or-later.

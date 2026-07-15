#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


HOME = Path.home()

DISPLAY_MAP = (
    HOME
    / ".config/screenstereo-pipewire/display-map.json"
)

DISPLAY_DISCOVERY = (
    HOME
    / ".local/state/screenstereo-pipewire/display-discovery/latest_discovery.json"
)

AUDIO_DISCOVERY = (
    HOME
    / ".local/state/screenstereo-pipewire/audio-discovery/latest_discovery.json"
)

DISPLAY_DISCOVER_SCRIPT = (
    HOME
    / ".local/bin/screenstereo_display_discover.py"
)

AUDIO_DISCOVER_SCRIPT = (
    HOME
    / ".local/bin/screenstereo_audio_discover.py"
)

STATE_ROOT = (
    HOME
    / ".local/state/screenstereo-pipewire/runtime-resolution"
)

LATEST_JSON = STATE_ROOT / "latest_resolution.json"
LATEST_TEXT = STATE_ROOT / "latest_resolution.txt"


def now_local() -> datetime:
    return datetime.now().astimezone()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))

    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def run_script(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exit_code": None,
            "stdout": "",
            "stderr": "script missing",
        }

    result = subprocess.run(
        [str(path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    return {
        "path": str(path),
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def normalize(value: Any) -> str:
    if value is None:
        return ""

    return "".join(
        character.lower()
        for character in str(value)
        if character.isalnum()
    )


def stable_identity_matches(
    configured: dict[str, Any],
    observed: dict[str, Any],
) -> dict[str, Any]:
    score = 0
    evidence = []
    mismatches = []

    configured_edid = configured.get("edid_sha256")
    observed_edid = observed.get("edid_sha256")

    configured_model = normalize(configured.get("model_name"))
    observed_model = normalize(observed.get("model_name"))

    configured_manufacturer = normalize(
        configured.get("manufacturer")
    )
    observed_manufacturer = normalize(
        observed.get("edid_manufacturer")
    )

    if configured_edid and observed_edid:
        if configured_edid == observed_edid:
            score += 100
            evidence.append("edid_sha256_exact")
        else:
            mismatches.append("edid_sha256_mismatch")

    if configured_model and configured_model == observed_model:
        score += 40
        evidence.append("model_name_exact")
    elif configured_model:
        mismatches.append("model_name_mismatch")

    if (
        configured_manufacturer
        and configured_manufacturer == observed_manufacturer
    ):
        score += 20
        evidence.append("manufacturer_exact")
    elif configured_manufacturer:
        mismatches.append("manufacturer_mismatch")

    return {
        "score": score,
        "evidence": evidence,
        "mismatches": mismatches,
    }


def exact_pipewire_matches(
    audio_candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    matches = []

    for match in audio_candidate.get(
        "matching_pipewire_sinks",
        [],
    ):
        evidence = set(match.get("evidence", []))

        if {
            "alsa_card_index",
            "alsa_device_index",
        }.issubset(evidence):
            matches.append(match)

    return matches


def resolve_one_role(
    role: str,
    configured_entry: dict[str, Any],
    display_report: dict[str, Any],
    audio_report: dict[str, Any],
) -> dict[str, Any]:
    configured_identity = configured_entry["stable_identity"]

    display_candidates = []

    for observed in display_report.get(
        "connected_stable_identities",
        [],
    ):
        match = stable_identity_matches(
            configured_identity,
            observed,
        )

        display_candidates.append(
            {
                "observed_display": observed,
                **match,
            }
        )

    display_candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    if not display_candidates:
        return {
            "role": role,
            "status": "REFUSED",
            "classification": "display_identity_unresolved",
            "reason": "No connected display candidates were observed.",
            "display_candidates": [],
        }

    top_display = display_candidates[0]
    top_score = top_display["score"]

    tied_displays = [
        item
        for item in display_candidates
        if item["score"] == top_score
    ]

    if top_score < 100:
        return {
            "role": role,
            "status": "REFUSED",
            "classification": "display_identity_unresolved",
            "reason": (
                "No current display matched the durable identity "
                "with sufficient evidence."
            ),
            "display_candidates": display_candidates,
        }

    if len(tied_displays) != 1:
        return {
            "role": role,
            "status": "REFUSED",
            "classification": "display_identity_ambiguous",
            "reason": (
                "Multiple connected displays matched the durable "
                "identity with the same score."
            ),
            "display_candidates": display_candidates,
        }

    observed_display = top_display["observed_display"]
    observed_model = normalize(
        observed_display.get("model_name")
    )

    audio_candidates = []

    for audio in audio_report.get(
        "normalized_audio_identity_candidates",
        [],
    ):
        audio_name = normalize(
            audio.get("alsa_device_name")
        )

        score = 0
        evidence = []

        if observed_model and observed_model == audio_name:
            score += 70
            evidence.append(
                "display_model_exactly_matches_alsa_device_name"
            )

        exact_sinks = exact_pipewire_matches(audio)

        if len(exact_sinks) == 1:
            score += 30
            evidence.append(
                "unique_exact_alsa_card_device_pipewire_sink_match"
            )

        audio_candidates.append(
            {
                "audio_candidate": audio,
                "exact_sinks": exact_sinks,
                "score": score,
                "evidence": evidence,
            }
        )

    audio_candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    if not audio_candidates:
        return {
            "role": role,
            "status": "REFUSED",
            "classification": "audio_sink_unresolved",
            "reason": "No current HDMI audio candidates were observed.",
            "resolved_display": observed_display,
            "audio_candidates": [],
        }

    top_audio = audio_candidates[0]
    top_audio_score = top_audio["score"]

    tied_audio = [
        item
        for item in audio_candidates
        if item["score"] == top_audio_score
    ]

    if top_audio_score < 100:
        return {
            "role": role,
            "status": "REFUSED",
            "classification": "audio_sink_unresolved",
            "reason": (
                "No HDMI audio candidate matched the resolved display "
                "with sufficient evidence."
            ),
            "resolved_display": observed_display,
            "audio_candidates": audio_candidates,
        }

    if len(tied_audio) != 1:
        return {
            "role": role,
            "status": "REFUSED",
            "classification": "display_audio_correlation_ambiguous",
            "reason": (
                "Multiple HDMI audio candidates matched the display "
                "with the same score."
            ),
            "resolved_display": observed_display,
            "audio_candidates": audio_candidates,
        }

    exact_sinks = top_audio["exact_sinks"]

    if len(exact_sinks) != 1:
        return {
            "role": role,
            "status": "REFUSED",
            "classification": "audio_sink_unresolved",
            "reason": (
                "The selected ALSA HDMI device did not resolve to one "
                "unique current PipeWire sink."
            ),
            "resolved_display": observed_display,
            "audio_candidates": audio_candidates,
        }

    audio = top_audio["audio_candidate"]
    sink = exact_sinks[0]

    return {
        "role": role,
        "status": "RESOLVED",
        "classification": "stable_identity_resolved",
        "reason": (
            "The durable stable display identity resolved to one "
            "current ALSA device and one current PipeWire sink."
        ),
        "configured_stable_identity": configured_identity,
        "resolved_display": observed_display,
        "display_resolution_score": top_score,
        "display_resolution_evidence": top_display["evidence"],
        "resolved_audio": {
            "alsa_card_index": audio.get("alsa_card_index"),
            "alsa_card_name": audio.get("alsa_card_name"),
            "alsa_device_index": audio.get("alsa_device_index"),
            "alsa_device_name": audio.get("alsa_device_name"),
            "alsa_device_id": audio.get("alsa_device_id"),
        },
        "resolved_pipewire_sink": {
            "name": sink.get("sink_name"),
            "state": sink.get("sink_state"),
            "description": sink.get("sink_description"),
            "alsa_card": sink.get("alsa_card"),
            "alsa_device": sink.get("alsa_device"),
            "device_profile_name": sink.get(
                "device_profile_name"
            ),
        },
        "audio_resolution_score": top_audio_score,
        "audio_resolution_evidence": top_audio["evidence"],
        "runtime_sink_name_authoritative": False,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = []

    lines.append("=== SCREENSTEREO RUNTIME RESOLUTION ===")
    lines.append(f"ts={report['observed_local']}")
    lines.append(f"run_id={report['run_id']}")
    lines.append(
        "audio_graph_mutation_performed="
        + str(report["audio_graph_mutation_performed"])
    )
    lines.append(
        "profile_change_performed="
        + str(report["profile_change_performed"])
    )
    lines.append(
        "default_sink_change_performed="
        + str(report["default_sink_change_performed"])
    )
    lines.append("")

    for role in ["left", "right"]:
        result = report["role_resolutions"][role]

        lines.append(role.upper())
        lines.append(
            "  status="
            + str(result.get("status"))
        )
        lines.append(
            "  classification="
            + str(result.get("classification"))
        )
        lines.append(
            "  reason="
            + str(result.get("reason"))
        )

        if result.get("status") == "RESOLVED":
            display = result["resolved_display"]
            audio = result["resolved_audio"]
            sink = result["resolved_pipewire_sink"]

            lines.append(
                "  display="
                + str(display.get("edid_manufacturer"))
                + "/"
                + str(display.get("model_name"))
            )
            lines.append(
                "  connector="
                + str(display.get("connector_name"))
            )
            lines.append(
                "  alsa_card="
                + str(audio.get("alsa_card_index"))
            )
            lines.append(
                "  alsa_device="
                + str(audio.get("alsa_device_index"))
            )
            lines.append(
                "  pipewire_sink="
                + str(sink.get("name"))
            )
            lines.append(
                "  display_score="
                + str(result.get("display_resolution_score"))
            )
            lines.append(
                "  audio_score="
                + str(result.get("audio_resolution_score"))
            )
            lines.append(
                "  runtime_sink_name_authoritative="
                + str(
                    result.get(
                        "runtime_sink_name_authoritative"
                    )
                )
            )

        lines.append("")

    lines.append("=== Resolution result ===")
    lines.append(f"status={report['status']}")
    lines.append(
        f"classification={report['classification']}"
    )
    lines.append(f"reason={report['reason']}")
    lines.append(
        "left_sink="
        + str(report.get("resolved_runtime", {}).get("left_sink"))
    )
    lines.append(
        "right_sink="
        + str(report.get("resolved_runtime", {}).get("right_sink"))
    )
    lines.append(
        "distinct_sinks="
        + str(report.get("resolved_runtime", {}).get("distinct_sinks"))
    )
    lines.append("")
    lines.append(
        f"json_report={report['paths']['json_report']}"
    )
    lines.append(
        f"text_report={report['paths']['text_report']}"
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    observed = now_local()
    run_id = "current"

    run_dir = STATE_ROOT
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    json_report = LATEST_JSON
    text_report = LATEST_TEXT

    try:
        display_map = load_json(DISPLAY_MAP)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(
            f"RUNTIME_RESOLUTION_REFUSED: {exc}",
            file=sys.stderr,
        )
        return 2

    display_discovery_result = run_script(
        DISPLAY_DISCOVER_SCRIPT
    )
    audio_discovery_result = run_script(
        AUDIO_DISCOVER_SCRIPT
    )

    if display_discovery_result["exit_code"] not in {0}:
        print(
            "RUNTIME_RESOLUTION_REFUSED: display discovery failed",
            file=sys.stderr,
        )
        return 2

    if audio_discovery_result["exit_code"] not in {0}:
        print(
            "RUNTIME_RESOLUTION_REFUSED: audio discovery failed",
            file=sys.stderr,
        )
        return 2

    try:
        display_report = load_json(DISPLAY_DISCOVERY)
        audio_report = load_json(AUDIO_DISCOVERY)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(
            f"RUNTIME_RESOLUTION_REFUSED: {exc}",
            file=sys.stderr,
        )
        return 2

    left_result = resolve_one_role(
        "left",
        display_map["left_display"],
        display_report,
        audio_report,
    )

    right_result = resolve_one_role(
        "right",
        display_map["right_display"],
        display_report,
        audio_report,
    )

    both_resolved = (
        left_result.get("status") == "RESOLVED"
        and right_result.get("status") == "RESOLVED"
    )

    left_sink = (
        left_result.get("resolved_pipewire_sink", {}).get("name")
        if both_resolved
        else None
    )

    right_sink = (
        right_result.get("resolved_pipewire_sink", {}).get("name")
        if both_resolved
        else None
    )

    distinct_sinks = bool(
        both_resolved
        and left_sink
        and right_sink
        and left_sink != right_sink
    )

    if both_resolved and distinct_sinks:
        status = "PASS"
        classification = "runtime_identity_resolution_complete"
        reason = (
            "Both durable display identities resolved uniquely to "
            "distinct current PipeWire sinks."
        )
    elif both_resolved:
        status = "REFUSED"
        classification = "resolved_sink_collision"
        reason = (
            "Both durable display identities resolved, but they did "
            "not resolve to distinct current PipeWire sinks."
        )
    else:
        status = "REFUSED"
        classification = "runtime_identity_resolution_incomplete"
        reason = (
            "One or more durable display identities could not be "
            "resolved without ambiguity."
        )

    report = {
        "schema_version": 0,
        "report_type": "screenstereo_runtime_resolution",
        "observed_local": observed.isoformat(
            timespec="milliseconds"
        ),
        "run_id": run_id,
        "display_map_path": str(DISPLAY_MAP),
        "display_map_sha256": file_sha256(DISPLAY_MAP),
        "source_discovery": {
            "display_discovery_path": str(DISPLAY_DISCOVERY),
            "display_discovery_run_id": display_report.get("run_id"),
            "audio_discovery_path": str(AUDIO_DISCOVERY),
            "audio_discovery_run_id": audio_report.get("run_id"),
        },
        "discovery_execution": {
            "display_discovery": display_discovery_result,
            "audio_discovery": audio_discovery_result,
        },
        "role_resolutions": {
            "left": left_result,
            "right": right_result,
        },
        "resolved_runtime": {
            "left_sink": left_sink,
            "right_sink": right_sink,
            "distinct_sinks": distinct_sinks,
            "runtime_sink_names_authoritative": False,
        },
        "status": status,
        "classification": classification,
        "reason": reason,
        "audio_graph_mutation_performed": False,
        "profile_change_performed": False,
        "default_sink_change_performed": False,
        "durable_configuration_changed": False,
        "paths": {
            "run_dir": str(run_dir),
            "json_report": str(json_report),
            "text_report": str(text_report),
            "latest_json": str(LATEST_JSON),
            "latest_text": str(LATEST_TEXT),
        },
    }

    json_report.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    text = render_text(report)
    text_report.write_text(text, encoding="utf-8")

    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    print(text, end="")

    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())

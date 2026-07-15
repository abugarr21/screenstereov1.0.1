#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


STATE_ROOT = Path.home() / ".local/state/screenstereo-pipewire/correlation"
DISPLAY_JSON = (
    Path.home()
    / ".local/state/screenstereo-pipewire/display-discovery/latest_discovery.json"
)
AUDIO_JSON = (
    Path.home()
    / ".local/state/screenstereo-pipewire/audio-discovery/latest_discovery.json"
)

LATEST_JSON = STATE_ROOT / "latest_correlation.json"
LATEST_TEXT = STATE_ROOT / "latest_correlation.txt"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))

    return json.loads(path.read_text(encoding="utf-8"))


def normalize_identity_text(value: Any) -> str:
    if value is None:
        return ""

    return "".join(
        character.lower()
        for character in str(value).strip()
        if character.isalnum()
    )


def geometry_role(identity: dict[str, Any]) -> str | None:
    geometry = identity.get("desktop_geometry") or {}
    x_value = geometry.get("x")

    if x_value is None:
        return None

    return "left" if int(x_value) == 0 else "right"


def exact_sink_matches(
    audio_candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    exact_matches = []

    for match in audio_candidate.get("matching_pipewire_sinks", []):
        evidence = set(match.get("evidence", []))

        if {
            "alsa_card_index",
            "alsa_device_index",
        }.issubset(evidence):
            exact_matches.append(match)

    return exact_matches


def score_candidate(
    display: dict[str, Any],
    audio: dict[str, Any],
) -> dict[str, Any]:
    display_model = normalize_identity_text(display.get("model_name"))
    audio_name = normalize_identity_text(audio.get("alsa_device_name"))

    score = 0
    evidence = []
    cautions = []

    model_exact = bool(display_model and display_model == audio_name)

    if model_exact:
        score += 70
        evidence.append("display_model_exactly_matches_alsa_device_name")
    else:
        cautions.append("display_model_does_not_match_alsa_device_name")

    exact_sinks = exact_sink_matches(audio)

    if len(exact_sinks) == 1:
        score += 25
        evidence.append("unique_exact_alsa_card_device_pipewire_sink_match")
    elif len(exact_sinks) == 0:
        cautions.append("no_exact_alsa_card_device_pipewire_sink_match")
    else:
        cautions.append("multiple_exact_pipewire_sink_matches")

    role = geometry_role(display)

    if role is not None:
        score += 5
        evidence.append("desktop_geometry_role_available")
    else:
        cautions.append("desktop_geometry_role_unavailable")

    if model_exact and len(exact_sinks) == 1:
        confidence = "high"
        automatic_mapping_allowed = True
        sink = exact_sinks[0]
    elif score >= 50:
        confidence = "medium"
        automatic_mapping_allowed = False
        sink = exact_sinks[0] if len(exact_sinks) == 1 else None
    else:
        confidence = "low"
        automatic_mapping_allowed = False
        sink = exact_sinks[0] if len(exact_sinks) == 1 else None

    return {
        "score": score,
        "confidence": confidence,
        "automatic_mapping_allowed": automatic_mapping_allowed,
        "evidence": evidence,
        "cautions": cautions,
        "role_candidate": role,
        "display": {
            "connector_name": display.get("connector_name"),
            "manufacturer": display.get("edid_manufacturer"),
            "model_name": display.get("model_name"),
            "numeric_serial": display.get("edid_numeric_serial"),
            "descriptor_serial": display.get("edid_descriptor_serial"),
            "edid_sha256": display.get("edid_sha256"),
            "desktop_geometry": display.get("desktop_geometry"),
        },
        "audio": {
            "alsa_card_index": audio.get("alsa_card_index"),
            "alsa_card_name": audio.get("alsa_card_name"),
            "alsa_device_index": audio.get("alsa_device_index"),
            "alsa_device_name": audio.get("alsa_device_name"),
            "alsa_device_id": audio.get("alsa_device_id"),
        },
        "resolved_sink": {
            "name": sink.get("sink_name") if sink else None,
            "state": sink.get("sink_state") if sink else None,
            "description": sink.get("sink_description") if sink else None,
            "alsa_card": sink.get("alsa_card") if sink else None,
            "alsa_device": sink.get("alsa_device") if sink else None,
            "device_profile_name": (
                sink.get("device_profile_name") if sink else None
            ),
        },
    }


def build_ranked_candidates(
    display_report: dict[str, Any],
    audio_report: dict[str, Any],
) -> list[dict[str, Any]]:
    ranked = []

    displays = display_report.get("connected_stable_identities", [])
    audio_candidates = audio_report.get(
        "normalized_audio_identity_candidates",
        [],
    )

    for display_index, display in enumerate(displays, start=1):
        candidates = []

        for audio_index, audio in enumerate(audio_candidates, start=1):
            scored = score_candidate(display, audio)
            scored["audio_candidate_index"] = audio_index
            candidates.append(scored)

        candidates.sort(
            key=lambda candidate: (
                candidate["score"],
                candidate["confidence"] == "high",
            ),
            reverse=True,
        )

        ranked.append(
            {
                "display_index": display_index,
                "display_identity": display,
                "role_candidate": geometry_role(display),
                "ranked_audio_candidates": candidates,
            }
        )

    return ranked


def choose_recommended_mapping(
    ranked: list[dict[str, Any]],
) -> dict[str, Any]:
    selected = []
    refused_reasons = []
    used_sink_names = set()

    for display_entry in ranked:
        candidates = display_entry["ranked_audio_candidates"]

        if not candidates:
            refused_reasons.append(
                f"display_{display_entry['display_index']}_has_no_audio_candidates"
            )
            continue

        top = candidates[0]

        if top["confidence"] != "high":
            refused_reasons.append(
                f"display_{display_entry['display_index']}_top_candidate_not_high_confidence"
            )
            continue

        if not top["automatic_mapping_allowed"]:
            refused_reasons.append(
                f"display_{display_entry['display_index']}_automatic_mapping_not_allowed"
            )
            continue

        sink_name = top["resolved_sink"]["name"]

        if not sink_name:
            refused_reasons.append(
                f"display_{display_entry['display_index']}_sink_unresolved"
            )
            continue

        if sink_name in used_sink_names:
            refused_reasons.append(
                f"display_{display_entry['display_index']}_sink_reused"
            )
            continue

        top_score = top["score"]
        tied = [
            candidate
            for candidate in candidates
            if candidate["score"] == top_score
        ]

        if len(tied) != 1:
            refused_reasons.append(
                f"display_{display_entry['display_index']}_top_score_ambiguous"
            )
            continue

        used_sink_names.add(sink_name)

        selected.append(
            {
                "display_index": display_entry["display_index"],
                "role": display_entry["role_candidate"],
                "manufacturer": top["display"]["manufacturer"],
                "model_name": top["display"]["model_name"],
                "connector_name": top["display"]["connector_name"],
                "edid_sha256": top["display"]["edid_sha256"],
                "alsa_card_index": top["audio"]["alsa_card_index"],
                "alsa_device_index": top["audio"]["alsa_device_index"],
                "alsa_device_name": top["audio"]["alsa_device_name"],
                "pipewire_sink": sink_name,
                "pipewire_sink_state": top["resolved_sink"]["state"],
                "confidence": top["confidence"],
                "score": top["score"],
                "evidence": top["evidence"],
            }
        )

    role_values = {entry.get("role") for entry in selected}

    if len(selected) == len(ranked) and role_values == {"left", "right"}:
        mapping_status = "PROPOSED"
        user_confirmation_required = True
    else:
        mapping_status = "REFUSED"
        user_confirmation_required = True

        if len(selected) != len(ranked):
            refused_reasons.append(
                "not_every_display_has_one_unique_high_confidence_mapping"
            )

        if role_values != {"left", "right"}:
            refused_reasons.append(
                "left_and_right_geometry_roles_not_uniquely_resolved"
            )

    return {
        "mapping_status": mapping_status,
        "user_confirmation_required": user_confirmation_required,
        "silent_application_allowed": False,
        "selected": selected,
        "refused_reasons": sorted(set(refused_reasons)),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = []

    lines.append("=== SCREENSTEREO DISPLAY-AUDIO CORRELATION ===")
    lines.append(f"ts={report['observed_local']}")
    lines.append(f"run_id={report['run_id']}")
    lines.append(f"observation_only={report['observation_only']}")
    lines.append(
        "audio_graph_mutation_performed="
        + str(report["audio_graph_mutation_performed"])
    )
    lines.append("")

    for display_entry in report["ranked_display_audio_candidates"]:
        identity = display_entry["display_identity"]
        lines.append(
            "display_"
            + str(display_entry["display_index"])
            + ":"
        )
        lines.append(
            "  manufacturer="
            + str(identity.get("edid_manufacturer"))
        )
        lines.append(
            "  model_name="
            + str(identity.get("model_name"))
        )
        lines.append(
            "  connector="
            + str(identity.get("connector_name"))
        )
        lines.append(
            "  role_candidate="
            + str(display_entry.get("role_candidate"))
        )

        for rank, candidate in enumerate(
            display_entry["ranked_audio_candidates"][:3],
            start=1,
        ):
            lines.append(
                f"  rank_{rank}_alsa_device="
                + str(candidate["audio"]["alsa_device_index"])
            )
            lines.append(
                f"  rank_{rank}_alsa_name="
                + str(candidate["audio"]["alsa_device_name"])
            )
            lines.append(
                f"  rank_{rank}_sink="
                + str(candidate["resolved_sink"]["name"])
            )
            lines.append(
                f"  rank_{rank}_score="
                + str(candidate["score"])
            )
            lines.append(
                f"  rank_{rank}_confidence="
                + str(candidate["confidence"])
            )
            lines.append(
                f"  rank_{rank}_automatic_mapping_allowed="
                + str(candidate["automatic_mapping_allowed"])
            )
        lines.append("")

    recommendation = report["recommended_mapping"]

    lines.append("=== Recommended mapping ===")
    lines.append(
        "mapping_status="
        + recommendation["mapping_status"]
    )
    lines.append(
        "user_confirmation_required="
        + str(recommendation["user_confirmation_required"])
    )
    lines.append(
        "silent_application_allowed="
        + str(recommendation["silent_application_allowed"])
    )

    for selected in recommendation["selected"]:
        lines.append(
            selected["role"]
            + "_display="
            + str(selected["manufacturer"])
            + "/"
            + str(selected["model_name"])
        )
        lines.append(
            selected["role"]
            + "_alsa_device="
            + str(selected["alsa_device_index"])
        )
        lines.append(
            selected["role"]
            + "_pipewire_sink="
            + str(selected["pipewire_sink"])
        )
        lines.append(
            selected["role"]
            + "_confidence="
            + str(selected["confidence"])
        )
        lines.append(
            selected["role"]
            + "_score="
            + str(selected["score"])
        )

    if recommendation["refused_reasons"]:
        lines.append(
            "refused_reasons="
            + ",".join(recommendation["refused_reasons"])
        )

    lines.append("")
    lines.append("=== Correlation result ===")
    lines.append(f"status={report['status']}")
    lines.append(f"classification={report['classification']}")
    lines.append(f"reason={report['reason']}")
    lines.append("")
    lines.append(f"json_report={report['paths']['json_report']}")
    lines.append(f"text_report={report['paths']['text_report']}")

    return "\n".join(lines) + "\n"


def main() -> int:
    observed = datetime.now().astimezone()
    run_id = "current"
    run_dir = STATE_ROOT
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    json_report = LATEST_JSON
    text_report = LATEST_TEXT

    try:
        display_report = load_json(DISPLAY_JSON)
        audio_report = load_json(AUDIO_JSON)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"CORRELATION_INPUT_FAILURE: {exc}", file=sys.stderr)
        return 1

    ranked = build_ranked_candidates(
        display_report,
        audio_report,
    )

    recommendation = choose_recommended_mapping(ranked)

    if recommendation["mapping_status"] == "PROPOSED":
        status = "PASS"
        classification = "high_confidence_mapping_proposed"
        reason = (
            "Each connected display has one unique high-confidence "
            "ALSA and PipeWire mapping. User confirmation is still required."
        )
    else:
        status = "REFUSED"
        classification = "display_audio_correlation_ambiguous"
        reason = (
            "A unique high-confidence display-to-audio mapping could not "
            "be proposed without guessing."
        )

    report = {
        "schema_version": 0,
        "report_type": "screenstereo_display_audio_correlation",
        "observed_local": observed.isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "observation_only": True,
        "audio_graph_mutation_performed": False,
        "durable_configuration_written": False,
        "user_confirmation_recorded": False,
        "source_reports": {
            "display_discovery": str(DISPLAY_JSON),
            "display_discovery_run_id": display_report.get("run_id"),
            "audio_discovery": str(AUDIO_JSON),
            "audio_discovery_run_id": audio_report.get("run_id"),
        },
        "confidence_policy": {
            "display_model_exact_alsa_name_points": 70,
            "unique_exact_alsa_card_device_sink_points": 25,
            "desktop_geometry_role_points": 5,
            "card_only_match_automatic_mapping_allowed": False,
            "high_confidence_requires": [
                "exact normalized display model and ALSA device-name match",
                "one unique exact ALSA card/device PipeWire sink match",
            ],
            "silent_application_allowed": False,
        },
        "ranked_display_audio_candidates": ranked,
        "recommended_mapping": recommendation,
        "status": status,
        "classification": classification,
        "reason": reason,
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

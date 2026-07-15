#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


CORRELATION_JSON = (
    Path.home()
    / ".local/state/screenstereo-pipewire/correlation/latest_correlation.json"
)

STATE_ROOT = Path.home() / ".local/state/screenstereo-pipewire/setup"
LATEST_STATUS_JSON = STATE_ROOT / "latest_setup_status.json"
LATEST_STATUS_TEXT = STATE_ROOT / "latest_setup_status.txt"
LATEST_CONFIRMATION_JSON = STATE_ROOT / "latest_confirmation.json"


def now_local() -> datetime:
    return datetime.now().astimezone()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))

    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def selected_by_role(
    correlation: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    selected = correlation.get(
        "recommended_mapping",
        {},
    ).get("selected", [])

    roles: dict[str, dict[str, Any]] = {}

    for item in selected:
        role = item.get("role")
        if role in {"left", "right"}:
            roles[role] = item

    return roles


def required_confirmation_phrase(
    roles: dict[str, dict[str, Any]],
) -> str:
    left = roles["left"]
    right = roles["right"]

    return (
        "CONFIRM "
        f"LEFT={left['model_name']} "
        f"RIGHT={right['model_name']}"
    )


def render_proposal(
    correlation: dict[str, Any],
) -> str:
    mapping = correlation.get("recommended_mapping", {})
    roles = selected_by_role(correlation)

    lines: list[str] = []

    lines.append("=== SCREENSTEREO GUIDED SETUP ===")
    lines.append(
        "mapping_status="
        + str(mapping.get("mapping_status"))
    )
    lines.append(
        "user_confirmation_required="
        + str(mapping.get("user_confirmation_required"))
    )
    lines.append(
        "silent_application_allowed="
        + str(mapping.get("silent_application_allowed"))
    )
    lines.append("")

    if set(roles) != {"left", "right"}:
        lines.append("status=REFUSED")
        lines.append(
            "reason=unique left and right proposed mappings are unavailable"
        )
        return "\n".join(lines) + "\n"

    for role in ["left", "right"]:
        item = roles[role]

        lines.append(role.upper())
        lines.append(
            "  display="
            + str(item.get("manufacturer"))
            + "/"
            + str(item.get("model_name"))
        )
        lines.append(
            "  connector="
            + str(item.get("connector_name"))
        )
        lines.append(
            "  alsa_card="
            + str(item.get("alsa_card_index"))
        )
        lines.append(
            "  alsa_device="
            + str(item.get("alsa_device_index"))
        )
        lines.append(
            "  pipewire_sink="
            + str(item.get("pipewire_sink"))
        )
        lines.append(
            "  confidence="
            + str(item.get("confidence"))
        )
        lines.append(
            "  score="
            + str(item.get("score"))
        )
        lines.append("")

    lines.append("Required confirmation phrase:")
    lines.append(required_confirmation_phrase(roles))
    lines.append("")
    lines.append(
        "No durable configuration or audio graph change will occur "
        "during this confirmation step."
    )

    return "\n".join(lines) + "\n"


def write_status(
    *,
    status: str,
    classification: str,
    reason: str,
    command: str,
    correlation: dict[str, Any] | None,
    confirmation_recorded: bool,
    confirmation_path: Path | None,
) -> None:
    observed = now_local()

    payload = {
        "schema_version": 0,
        "report_type": "screenstereo_setup_status",
        "observed_local": observed.isoformat(timespec="milliseconds"),
        "status": status,
        "classification": classification,
        "reason": reason,
        "command": command,
        "observation_only": True,
        "audio_graph_mutation_performed": False,
        "durable_configuration_written": False,
        "user_confirmation_recorded": confirmation_recorded,
        "source_correlation_run_id": (
            correlation.get("run_id")
            if correlation
            else None
        ),
        "confirmation_path": (
            str(confirmation_path)
            if confirmation_path
            else None
        ),
    }

    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    LATEST_STATUS_JSON.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        f"ts={payload['observed_local']}",
        f"status={payload['status']}",
        f"classification={payload['classification']}",
        f"reason={payload['reason']}",
        f"command={payload['command']}",
        f"observation_only={payload['observation_only']}",
        (
            "audio_graph_mutation_performed="
            + str(payload["audio_graph_mutation_performed"])
        ),
        (
            "durable_configuration_written="
            + str(payload["durable_configuration_written"])
        ),
        (
            "user_confirmation_recorded="
            + str(payload["user_confirmation_recorded"])
        ),
        (
            "source_correlation_run_id="
            + str(payload["source_correlation_run_id"])
        ),
        (
            "confirmation_path="
            + str(payload["confirmation_path"])
        ),
    ]

    LATEST_STATUS_TEXT.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def command_show() -> int:
    try:
        correlation = load_json(CORRELATION_JSON)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        write_status(
            status="REFUSED",
            classification="correlation_input_unavailable",
            reason=str(exc),
            command="show",
            correlation=None,
            confirmation_recorded=False,
            confirmation_path=None,
        )
        print(f"SETUP_REFUSED: {exc}", file=sys.stderr)
        return 2

    mapping = correlation.get("recommended_mapping", {})
    roles = selected_by_role(correlation)

    if (
        correlation.get("status") != "PASS"
        or mapping.get("mapping_status") != "PROPOSED"
        or set(roles) != {"left", "right"}
    ):
        write_status(
            status="REFUSED",
            classification="mapping_not_confirmable",
            reason=(
                "Correlation does not contain one unique proposed "
                "left and right mapping."
            ),
            command="show",
            correlation=correlation,
            confirmation_recorded=False,
            confirmation_path=None,
        )
        print(render_proposal(correlation), end="")
        return 2

    write_status(
        status="AWAITING_CONFIRMATION",
        classification="high_confidence_mapping_awaiting_user_confirmation",
        reason=(
            "One unique high-confidence left/right mapping is available "
            "and requires explicit user confirmation."
        ),
        command="show",
        correlation=correlation,
        confirmation_recorded=False,
        confirmation_path=None,
    )

    print(render_proposal(correlation), end="")
    return 0


def command_confirm(provided_phrase: str) -> int:
    try:
        correlation = load_json(CORRELATION_JSON)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        write_status(
            status="REFUSED",
            classification="correlation_input_unavailable",
            reason=str(exc),
            command="confirm",
            correlation=None,
            confirmation_recorded=False,
            confirmation_path=None,
        )
        print(f"CONFIRMATION_REFUSED: {exc}", file=sys.stderr)
        return 2

    mapping = correlation.get("recommended_mapping", {})
    roles = selected_by_role(correlation)

    if (
        correlation.get("status") != "PASS"
        or mapping.get("mapping_status") != "PROPOSED"
        or set(roles) != {"left", "right"}
    ):
        write_status(
            status="REFUSED",
            classification="mapping_not_confirmable",
            reason=(
                "Correlation does not contain one unique proposed "
                "left and right mapping."
            ),
            command="confirm",
            correlation=correlation,
            confirmation_recorded=False,
            confirmation_path=None,
        )
        print("CONFIRMATION_REFUSED: mapping not confirmable")
        return 2

    required_phrase = required_confirmation_phrase(roles)

    if provided_phrase != required_phrase:
        write_status(
            status="REFUSED",
            classification="confirmation_phrase_mismatch",
            reason=(
                "Provided confirmation phrase did not exactly match "
                "the required mapping phrase."
            ),
            command="confirm",
            correlation=correlation,
            confirmation_recorded=False,
            confirmation_path=None,
        )

        print("CONFIRMATION_REFUSED")
        print("required_phrase=" + required_phrase)
        print("provided_phrase=" + provided_phrase)
        return 2

    observed = now_local()
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    confirmation_path = LATEST_CONFIRMATION_JSON

    confirmed_mapping = {
        "left": roles["left"],
        "right": roles["right"],
    }

    confirmation = {
        "schema_version": 0,
        "record_type": "screenstereo_mapping_confirmation",
        "confirmed_local": observed.isoformat(timespec="milliseconds"),
        "confirmation_method": "exact_typed_mapping_phrase",
        "confirmation_phrase": provided_phrase,
        "user_confirmed": True,
        "source_correlation_path": str(CORRELATION_JSON),
        "source_correlation_run_id": correlation.get("run_id"),
        "source_correlation_sha256": canonical_sha256(correlation),
        "confirmed_mapping": confirmed_mapping,
        "confirmed_mapping_sha256": canonical_sha256(
            confirmed_mapping
        ),
        "audio_graph_mutation_performed": False,
        "durable_configuration_written": False,
        "next_boundary": (
            "Step 05 may write a durable versioned display map "
            "from this confirmation evidence."
        ),
    }

    confirmation_path.write_text(
        json.dumps(confirmation, indent=2) + "\n",
        encoding="utf-8",
    )

    write_status(
        status="CONFIRMED",
        classification="high_confidence_mapping_user_confirmed",
        reason=(
            "The user explicitly confirmed the proposed left and right "
            "display-to-audio mapping."
        ),
        command="confirm",
        correlation=correlation,
        confirmation_recorded=True,
        confirmation_path=confirmation_path,
    )

    print("CONFIRMATION_STATUS=CONFIRMED")
    print(
        "left_display="
        + str(roles["left"].get("manufacturer"))
        + "/"
        + str(roles["left"].get("model_name"))
    )
    print(
        "left_pipewire_sink="
        + str(roles["left"].get("pipewire_sink"))
    )
    print(
        "right_display="
        + str(roles["right"].get("manufacturer"))
        + "/"
        + str(roles["right"].get("model_name"))
    )
    print(
        "right_pipewire_sink="
        + str(roles["right"].get("pipewire_sink"))
    )
    print("confirmation_record=" + str(confirmation_path))
    print("durable_configuration_written=False")
    print("audio_graph_mutation_performed=False")

    return 0


def command_status() -> int:
    if not LATEST_STATUS_TEXT.exists():
        print("status=NOT_RUN")
        return 1

    print(
        LATEST_STATUS_TEXT.read_text(
            encoding="utf-8"
        ),
        end="",
    )

    return 0


def usage() -> None:
    print(
        "Usage:\n"
        "  screenstereo_setup.py show\n"
        "  screenstereo_setup.py confirm "
        "'CONFIRM LEFT=<model> RIGHT=<model>'\n"
        "  screenstereo_setup.py status"
    )


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "show"

    if command == "show":
        return command_show()

    if command == "confirm":
        if len(sys.argv) != 3:
            usage()
            return 64

        return command_confirm(sys.argv[2])

    if command == "status":
        return command_status()

    usage()
    return 64


if __name__ == "__main__":
    sys.exit(main())

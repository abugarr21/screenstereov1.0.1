#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


CONFIRMATION_PATH = (
    Path.home()
    / ".local/state/screenstereo-pipewire/setup/latest_confirmation.json"
)

CONFIG_DIR = Path.home() / ".config/screenstereo-pipewire"
DISPLAY_MAP_PATH = CONFIG_DIR / "display-map.json"
DISPLAY_MAP_SHA256_PATH = CONFIG_DIR / "display-map.json.sha256"

STATE_DIR = Path.home() / ".local/state/screenstereo-pipewire/display-map"
LATEST_STATUS_JSON = STATE_DIR / "latest_write_status.json"
LATEST_STATUS_TEXT = STATE_DIR / "latest_write_status.txt"


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )

    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        temp_path.chmod(0o600)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def stable_identity_from_confirmed(
    role: str,
    confirmed: dict[str, Any],
) -> dict[str, Any]:
    geometry = confirmed.get("desktop_geometry") or {}

    return {
        "role": role,
        "channel_role": "front-left" if role == "left" else "front-right",
        "stable_identity": {
            "manufacturer": confirmed.get("manufacturer"),
            "model_name": confirmed.get("model_name"),
            "edid_sha256": confirmed.get("edid_sha256"),
            "numeric_serial": confirmed.get("numeric_serial"),
            "descriptor_serial": confirmed.get("descriptor_serial"),
        },
        "connector_observation_at_confirmation": {
            "connector_name": confirmed.get("connector_name"),
            "desktop_connector_name": geometry.get("connector_name"),
            "geometry": {
                "x": geometry.get("x"),
                "y": geometry.get("y"),
                "width": geometry.get("width"),
                "height": geometry.get("height"),
                "primary": geometry.get("primary"),
            },
            "authoritative_identity": False,
        },
        "audio_observation_at_confirmation": {
            "alsa_card_index": confirmed.get("alsa_card_index"),
            "alsa_device_index": confirmed.get("alsa_device_index"),
            "alsa_device_name": confirmed.get("alsa_device_name"),
            "pipewire_sink": confirmed.get("pipewire_sink"),
            "pipewire_sink_state": confirmed.get("pipewire_sink_state"),
            "authoritative_identity": False,
            "rediscover_at_runtime": True,
        },
        "confirmation_evidence": {
            "confidence": confirmed.get("confidence"),
            "score": confirmed.get("score"),
            "evidence": confirmed.get("evidence", []),
        },
    }


def write_status(
    *,
    status: str,
    classification: str,
    reason: str,
    backup_path: str | None,
    config_sha256: str | None,
) -> None:
    observed = now_local()

    payload = {
        "schema_version": 0,
        "report_type": "screenstereo_display_map_write_status",
        "observed_local": observed.isoformat(timespec="milliseconds"),
        "status": status,
        "classification": classification,
        "reason": reason,
        "confirmation_path": str(CONFIRMATION_PATH),
        "display_map_path": str(DISPLAY_MAP_PATH),
        "display_map_sha256_path": str(DISPLAY_MAP_SHA256_PATH),
        "backup_path": backup_path,
        "config_sha256": config_sha256,
        "durable_configuration_written": status == "WRITTEN",
        "audio_graph_mutation_performed": False,
        "profile_change_performed": False,
        "default_sink_change_performed": False,
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    LATEST_STATUS_JSON.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        f"ts={payload['observed_local']}",
        f"status={payload['status']}",
        f"classification={payload['classification']}",
        f"reason={payload['reason']}",
        f"confirmation_path={payload['confirmation_path']}",
        f"display_map_path={payload['display_map_path']}",
        f"display_map_sha256_path={payload['display_map_sha256_path']}",
        f"backup_path={payload['backup_path']}",
        f"config_sha256={payload['config_sha256']}",
        (
            "durable_configuration_written="
            + str(payload["durable_configuration_written"])
        ),
        (
            "audio_graph_mutation_performed="
            + str(payload["audio_graph_mutation_performed"])
        ),
        (
            "profile_change_performed="
            + str(payload["profile_change_performed"])
        ),
        (
            "default_sink_change_performed="
            + str(payload["default_sink_change_performed"])
        ),
    ]

    LATEST_STATUS_TEXT.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    try:
        confirmation = load_json(CONFIRMATION_PATH)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        write_status(
            status="REFUSED",
            classification="confirmation_evidence_unavailable",
            reason=str(exc),
            backup_path=None,
            config_sha256=None,
        )
        print(f"DISPLAY_MAP_WRITE_REFUSED: {exc}", file=sys.stderr)
        return 2

    if confirmation.get("record_type") != "screenstereo_mapping_confirmation":
        reason = "Confirmation record type is not recognized."
        write_status(
            status="REFUSED",
            classification="invalid_confirmation_record_type",
            reason=reason,
            backup_path=None,
            config_sha256=None,
        )
        print("DISPLAY_MAP_WRITE_REFUSED: " + reason, file=sys.stderr)
        return 2

    if confirmation.get("user_confirmed") is not True:
        reason = "Confirmation evidence does not contain explicit user confirmation."
        write_status(
            status="REFUSED",
            classification="user_confirmation_missing",
            reason=reason,
            backup_path=None,
            config_sha256=None,
        )
        print("DISPLAY_MAP_WRITE_REFUSED: " + reason, file=sys.stderr)
        return 2

    confirmed_mapping = confirmation.get("confirmed_mapping", {})

    if set(confirmed_mapping) != {"left", "right"}:
        reason = "Confirmation does not contain exactly one left and one right mapping."
        write_status(
            status="REFUSED",
            classification="confirmed_mapping_incomplete",
            reason=reason,
            backup_path=None,
            config_sha256=None,
        )
        print("DISPLAY_MAP_WRITE_REFUSED: " + reason, file=sys.stderr)
        return 2

    left = confirmed_mapping["left"]
    right = confirmed_mapping["right"]

    left_edid = left.get("edid_sha256")
    right_edid = right.get("edid_sha256")

    if not left.get("model_name") or not right.get("model_name"):
        reason = "Both confirmed displays must contain model identity."
        write_status(
            status="REFUSED",
            classification="stable_identity_incomplete",
            reason=reason,
            backup_path=None,
            config_sha256=None,
        )
        print("DISPLAY_MAP_WRITE_REFUSED: " + reason, file=sys.stderr)
        return 2

    if left.get("pipewire_sink") == right.get("pipewire_sink"):
        reason = "Left and right confirmation records resolve to the same sink."
        write_status(
            status="REFUSED",
            classification="confirmed_sink_collision",
            reason=reason,
            backup_path=None,
            config_sha256=None,
        )
        print("DISPLAY_MAP_WRITE_REFUSED: " + reason, file=sys.stderr)
        return 2

    observed = now_local()

    display_map = {
        "schema_version": 1,
        "config_type": "screenstereo_stable_display_map",
        "configured_local": observed.isoformat(timespec="milliseconds"),
        "configuration_authority": {
            "source": "explicit_user_confirmation",
            "confirmation_method": confirmation.get("confirmation_method"),
            "confirmation_phrase": confirmation.get("confirmation_phrase"),
            "source_confirmation_path": str(CONFIRMATION_PATH),
            "source_confirmation_record_sha256": canonical_sha256(
                confirmation
            ),
            "confirmed_mapping_sha256": confirmation.get(
                "confirmed_mapping_sha256"
            ),
            "user_confirmed": True,
        },
        "identity_policy": {
            "stable_hardware_identity_is_configuration_truth": True,
            "pipewire_sink_name_is_configuration_truth": False,
            "alsa_card_index_is_configuration_truth": False,
            "alsa_device_index_is_configuration_truth": False,
            "connector_name_is_globally_stable": False,
            "runtime_sink_rediscovery_required": True,
            "silent_identity_replacement_allowed": False,
            "silent_role_reassignment_allowed": False,
            "confirmation_required_on_ambiguity": True,
            "confirmation_required_on_hardware_replacement": True,
        },
        "left_display": stable_identity_from_confirmed("left", left),
        "right_display": stable_identity_from_confirmed("right", right),
        "validation_constraints": {
            "left_and_right_must_resolve_uniquely": True,
            "left_and_right_must_resolve_to_distinct_sinks": True,
            "missing_identity_must_fail_first": True,
            "ambiguous_identity_must_fail_first": True,
            "runtime_resolution_must_record_evidence": True,
        },
        "runtime_policy": {
            "preferred_mode": "split",
            "resolve_before_graph_build": True,
            "allow_cached_sink_only_when_current_observation_matches": True,
            "allow_static_sink_fallback_without_identity_match": False,
        },
        "baseline_observation": {
            "left_edid_sha256": left_edid,
            "right_edid_sha256": right_edid,
            "left_pipewire_sink_observed": left.get("pipewire_sink"),
            "right_pipewire_sink_observed": right.get("pipewire_sink"),
            "non_authoritative": True,
        },
    }

    backup_path = None

    if DISPLAY_MAP_PATH.exists():
        backup_path_obj = CONFIG_DIR / (
            "display-map.json.pre_step05_"
            + observed.strftime("%Y%m%d_%H%M%S")
            + ".bak"
        )
        shutil.copy2(DISPLAY_MAP_PATH, backup_path_obj)
        backup_path = str(backup_path_obj)

    atomic_write_json(DISPLAY_MAP_PATH, display_map)

    config_sha256 = file_sha256(DISPLAY_MAP_PATH)

    DISPLAY_MAP_SHA256_PATH.write_text(
        f"{config_sha256}  {DISPLAY_MAP_PATH}\n",
        encoding="utf-8",
    )
    DISPLAY_MAP_SHA256_PATH.chmod(0o600)

    verification = load_json(DISPLAY_MAP_PATH)

    if verification.get("config_type") != "screenstereo_stable_display_map":
        reason = "Written configuration failed read-back validation."
        write_status(
            status="FAILED",
            classification="display_map_readback_failed",
            reason=reason,
            backup_path=backup_path,
            config_sha256=config_sha256,
        )
        print("DISPLAY_MAP_WRITE_FAILED: " + reason, file=sys.stderr)
        return 1

    write_status(
        status="WRITTEN",
        classification="durable_stable_identity_map_written",
        reason=(
            "Explicit user confirmation was converted into a versioned "
            "durable stable-identity display map."
        ),
        backup_path=backup_path,
        config_sha256=config_sha256,
    )

    print("DISPLAY_MAP_WRITE_STATUS=WRITTEN")
    print("classification=durable_stable_identity_map_written")
    print("display_map_path=" + str(DISPLAY_MAP_PATH))
    print("display_map_sha256=" + config_sha256)
    print("backup_path=" + str(backup_path))
    print("left_identity=" + str(left.get("manufacturer")) + "/" + str(left.get("model_name")))
    print("right_identity=" + str(right.get("manufacturer")) + "/" + str(right.get("model_name")))
    print("runtime_sink_rediscovery_required=True")
    print("audio_graph_mutation_performed=False")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


STATE_ROOT = Path.home() / ".local/state/screenstereo-pipewire/audio-discovery"
LATEST_JSON = STATE_ROOT / "latest_discovery.json"
LATEST_TEXT = STATE_ROOT / "latest_discovery.txt"


def now_local() -> datetime:
    return datetime.now().astimezone()


def run_command(command: list[str], timeout: int = 20) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return {
            "command": command,
            "available": True,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except FileNotFoundError:
        return {
            "command": command,
            "available": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "command not found",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "available": True,
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": "command timed out",
        }


def parse_aplay_devices(text: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []

    pattern = re.compile(
        r"^card\s+(?P<card>\d+):\s+(?P<card_id>[^\[]+)\[(?P<card_name>[^\]]+)\],\s+"
        r"device\s+(?P<device>\d+):\s+(?P<device_id>[^\[]+)\[(?P<device_name>[^\]]+)\]"
    )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = pattern.match(line)
        if not match:
            continue

        values = match.groupdict()
        card_name = values["card_name"].strip()
        device_name = values["device_name"].strip()
        device_id = values["device_id"].strip()

        is_hdmi = any(
            token in value.upper()
            for value in [card_name, device_name, device_id]
            for token in ["HDMI", "DISPLAYPORT", "DP "]
        )

        devices.append(
            {
                "card_index": int(values["card"]),
                "card_id": values["card_id"].strip(),
                "card_name": card_name,
                "device_index": int(values["device"]),
                "device_id": device_id,
                "device_name": device_name,
                "is_hdmi_candidate": is_hdmi,
                "raw_line": line,
            }
        )

    return devices


def parse_pactl_short_sinks(text: str) -> list[dict[str, Any]]:
    sinks: list[dict[str, Any]] = []

    for raw_line in text.splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 5:
            continue

        index, name, driver, sample_spec, state = parts[:5]

        sinks.append(
            {
                "index": int(index) if index.isdigit() else index,
                "name": name,
                "driver": driver,
                "sample_spec": sample_spec,
                "state": state,
                "is_virtual": not name.startswith("alsa_output."),
                "is_hdmi_candidate": (
                    name.startswith("alsa_output.")
                    and (
                        ".hdmi-" in name
                        or ".pro-output-" in name
                        or "hdmi" in name.lower()
                    )
                ),
            }
        )

    return sinks


def parse_key_value_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if re.match(r"^(Card|Sink) #\d+$", line):
            if current is not None:
                blocks.append(current)

            kind, number = line.split(" #", 1)
            current = {
                "kind": kind.lower(),
                "index": int(number),
                "properties": {},
                "ports": [],
                "profiles": [],
            }
            section = None
            continue

        if current is None:
            continue

        stripped = line.strip()

        if stripped.startswith("Name:"):
            current["name"] = stripped.split(":", 1)[1].strip()
            continue

        if stripped.startswith("Description:"):
            current["description"] = stripped.split(":", 1)[1].strip()
            continue

        if stripped.startswith("Driver:"):
            current["driver"] = stripped.split(":", 1)[1].strip()
            continue

        if stripped.startswith("State:"):
            current["state"] = stripped.split(":", 1)[1].strip()
            continue

        if stripped.startswith("Active Profile:"):
            current["active_profile"] = stripped.split(":", 1)[1].strip()
            continue

        if stripped.startswith("Active Port:"):
            current["active_port"] = stripped.split(":", 1)[1].strip()
            continue

        if stripped == "Properties:":
            section = "properties"
            continue

        if stripped == "Ports:":
            section = "ports"
            continue

        if stripped == "Profiles:":
            section = "profiles"
            continue

        if section == "properties":
            property_match = re.match(r'^\s*([^=]+?)\s*=\s*"(.*)"\s*$', line)
            if property_match:
                key = property_match.group(1).strip()
                value = property_match.group(2)
                current["properties"][key] = value
            continue

        if section == "ports":
            port_match = re.match(
                r"^\s*([^\s:]+):\s+(.*?)\s+\(type:\s+([^,]+),.*availability group:\s*([^,]+),\s+available\)"
                r"|^\s*([^\s:]+):\s+(.*)$",
                line,
            )
            if port_match:
                if port_match.group(1):
                    current["ports"].append(
                        {
                            "name": port_match.group(1),
                            "description": port_match.group(2),
                            "type": port_match.group(3),
                            "availability_group": port_match.group(4),
                        }
                    )
                else:
                    current["ports"].append(
                        {
                            "name": port_match.group(5),
                            "description": port_match.group(6),
                        }
                    )
            continue

        if section == "profiles":
            profile_match = re.match(r"^\s*([^\s:]+):\s+(.*)$", line)
            if profile_match:
                current["profiles"].append(
                    {
                        "name": profile_match.group(1),
                        "description": profile_match.group(2),
                    }
                )

    if current is not None:
        blocks.append(current)

    return blocks


def normalize_pactl_cards(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for card in blocks:
        props = card.get("properties", {})
        name = card.get("name")
        description = card.get("description")

        normalized.append(
            {
                "index": card.get("index"),
                "name": name,
                "description": description,
                "driver": card.get("driver"),
                "active_profile": card.get("active_profile"),
                "device_bus_path": props.get("device.bus_path"),
                "device_path": props.get("device.path"),
                "alsa_card": props.get("alsa.card"),
                "alsa_card_name": props.get("alsa.card_name"),
                "alsa_long_card_name": props.get("alsa.long_card_name"),
                "api_alsa_card_name": props.get("api.alsa.card.name"),
                "profiles": card.get("profiles", []),
                "ports": card.get("ports", []),
                "properties": props,
            }
        )

    return normalized


def normalize_pactl_sinks(
    blocks: list[dict[str, Any]],
    short_sinks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    short_by_name = {sink["name"]: sink for sink in short_sinks}
    normalized: list[dict[str, Any]] = []

    for sink in blocks:
        props = sink.get("properties", {})
        name = sink.get("name")
        short = short_by_name.get(name, {})

        normalized.append(
            {
                "index": sink.get("index"),
                "name": name,
                "description": sink.get("description"),
                "driver": sink.get("driver"),
                "state": sink.get("state") or short.get("state"),
                "active_port": sink.get("active_port"),
                "alsa_card": props.get("alsa.card"),
                "alsa_card_name": props.get("alsa.card_name"),
                "alsa_device": props.get("alsa.device"),
                "alsa_pcm_card": props.get("api.alsa.pcm.card"),
                "alsa_pcm_device": props.get("api.alsa.pcm.device"),
                "device_bus_path": props.get("device.bus_path"),
                "device_path": props.get("device.path"),
                "device_profile_name": props.get("device.profile.name"),
                "device_profile_description": props.get(
                    "device.profile.description"
                ),
                "device_product_name": props.get("device.product.name"),
                "node_name": props.get("node.name"),
                "media_class": props.get("media.class"),
                "is_virtual": not str(name).startswith("alsa_output."),
                "is_hdmi_candidate": (
                    str(name).startswith("alsa_output.")
                    and (
                        ".hdmi-" in str(name)
                        or ".pro-output-" in str(name)
                        or "hdmi" in str(name).lower()
                    )
                ),
                "ports": sink.get("ports", []),
                "properties": props,
            }
        )

    known_names = {sink.get("name") for sink in normalized}

    for short in short_sinks:
        if short["name"] in known_names:
            continue
        normalized.append(short)

    return normalized


def build_audio_identity_candidates(
    alsa_devices: list[dict[str, Any]],
    sinks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for device in alsa_devices:
        if not device["is_hdmi_candidate"]:
            continue

        matching_sinks = []

        for sink in sinks:
            if not sink.get("is_hdmi_candidate"):
                continue

            sink_card = sink.get("alsa_card") or sink.get("alsa_pcm_card")
            sink_device = sink.get("alsa_device") or sink.get("alsa_pcm_device")

            card_match = (
                sink_card is not None
                and str(sink_card) == str(device["card_index"])
            )
            device_match = (
                sink_device is not None
                and str(sink_device) == str(device["device_index"])
            )

            evidence = []

            if card_match:
                evidence.append("alsa_card_index")
            if device_match:
                evidence.append("alsa_device_index")

            if card_match and device_match:
                confidence = "high"
            elif card_match:
                confidence = "medium"
            else:
                continue

            matching_sinks.append(
                {
                    "sink_name": sink.get("name"),
                    "sink_state": sink.get("state"),
                    "sink_description": sink.get("description"),
                    "confidence": confidence,
                    "evidence": evidence,
                    "alsa_card": sink_card,
                    "alsa_device": sink_device,
                    "device_profile_name": sink.get("device_profile_name"),
                    "device_profile_description": sink.get(
                        "device_profile_description"
                    ),
                    "active_port": sink.get("active_port"),
                }
            )

        candidates.append(
            {
                "alsa_card_index": device["card_index"],
                "alsa_card_name": device["card_name"],
                "alsa_device_index": device["device_index"],
                "alsa_device_name": device["device_name"],
                "alsa_device_id": device["device_id"],
                "matching_pipewire_sinks": matching_sinks,
            }
        )

    return candidates


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("=== SCREENSTEREO HDMI AUDIO DISCOVERY ===")
    lines.append(f"ts={report['observed_local']}")
    lines.append(f"run_id={report['run_id']}")
    lines.append(f"observation_only={report['observation_only']}")
    lines.append(
        f"audio_graph_mutation_performed={report['audio_graph_mutation_performed']}"
    )
    lines.append(f"default_sink={report['pulse']['default_sink']}")
    lines.append("")

    lines.append("=== ALSA HDMI devices ===")

    if not report["alsa"]["hdmi_devices"]:
        lines.append("NONE")
    else:
        for index, device in enumerate(
            report["alsa"]["hdmi_devices"],
            start=1,
        ):
            lines.append(f"alsa_hdmi_{index}:")
            lines.append(f"  card_index={device['card_index']}")
            lines.append(f"  card_name={device['card_name']}")
            lines.append(f"  device_index={device['device_index']}")
            lines.append(f"  device_name={device['device_name']}")
            lines.append(f"  device_id={device['device_id']}")

    lines.append("")
    lines.append("=== PipeWire HDMI candidate sinks ===")

    if not report["pipewire"]["hdmi_candidate_sinks"]:
        lines.append("NONE")
    else:
        for index, sink in enumerate(
            report["pipewire"]["hdmi_candidate_sinks"],
            start=1,
        ):
            lines.append(f"pipewire_sink_{index}:")
            lines.append(f"  name={sink.get('name')}")
            lines.append(f"  description={sink.get('description')}")
            lines.append(f"  state={sink.get('state')}")
            lines.append(f"  alsa_card={sink.get('alsa_card') or sink.get('alsa_pcm_card')}")
            lines.append(f"  alsa_device={sink.get('alsa_device') or sink.get('alsa_pcm_device')}")
            lines.append(f"  profile={sink.get('device_profile_name')}")
            lines.append(f"  active_port={sink.get('active_port')}")

    lines.append("")
    lines.append("=== Normalized audio identity candidates ===")

    if not report["normalized_audio_identity_candidates"]:
        lines.append("NONE")
    else:
        for index, candidate in enumerate(
            report["normalized_audio_identity_candidates"],
            start=1,
        ):
            lines.append(f"candidate_{index}:")
            lines.append(
                f"  alsa_card_index={candidate['alsa_card_index']}"
            )
            lines.append(
                f"  alsa_device_index={candidate['alsa_device_index']}"
            )
            lines.append(
                f"  alsa_device_name={candidate['alsa_device_name']}"
            )

            matches = candidate["matching_pipewire_sinks"]
            lines.append(f"  pipewire_match_count={len(matches)}")

            for match_index, match in enumerate(matches, start=1):
                lines.append(
                    f"  match_{match_index}_sink={match['sink_name']}"
                )
                lines.append(
                    f"  match_{match_index}_confidence={match['confidence']}"
                )
                lines.append(
                    f"  match_{match_index}_evidence={','.join(match['evidence'])}"
                )

    lines.append("")
    lines.append("=== Discovery result ===")
    lines.append(
        f"alsa_playback_device_count={report['counts']['alsa_playback_device_count']}"
    )
    lines.append(
        f"alsa_hdmi_device_count={report['counts']['alsa_hdmi_device_count']}"
    )
    lines.append(
        f"pipewire_sink_count={report['counts']['pipewire_sink_count']}"
    )
    lines.append(
        f"pipewire_hdmi_candidate_count={report['counts']['pipewire_hdmi_candidate_count']}"
    )
    lines.append(
        f"virtual_sink_count={report['counts']['virtual_sink_count']}"
    )
    lines.append(
        f"normalized_candidate_count={report['counts']['normalized_candidate_count']}"
    )
    lines.append(f"status={report['status']}")
    lines.append(f"classification={report['classification']}")
    lines.append(f"reason={report['reason']}")
    lines.append("")
    lines.append(f"json_report={report['paths']['json_report']}")
    lines.append(f"text_report={report['paths']['text_report']}")

    return "\n".join(lines) + "\n"


def main() -> int:
    observed = now_local()
    run_id = "current"
    run_dir = STATE_ROOT
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    json_report = LATEST_JSON
    text_report = LATEST_TEXT

    aplay_result = run_command(["aplay", "-l"])
    pactl_info_result = run_command(["pactl", "info"])
    pactl_short_sinks_result = run_command(["pactl", "list", "short", "sinks"])
    pactl_cards_result = run_command(["pactl", "list", "cards"])
    pactl_sinks_result = run_command(["pactl", "list", "sinks"])
    wpctl_result = run_command(["wpctl", "status"])

    alsa_devices = parse_aplay_devices(aplay_result["stdout"])
    hdmi_devices = [
        device for device in alsa_devices if device["is_hdmi_candidate"]
    ]

    short_sinks = parse_pactl_short_sinks(
        pactl_short_sinks_result["stdout"]
    )

    card_blocks = parse_key_value_blocks(pactl_cards_result["stdout"])
    sink_blocks = parse_key_value_blocks(pactl_sinks_result["stdout"])

    cards = normalize_pactl_cards(card_blocks)
    sinks = normalize_pactl_sinks(sink_blocks, short_sinks)

    hdmi_sinks = [
        sink for sink in sinks if sink.get("is_hdmi_candidate")
    ]
    virtual_sinks = [
        sink for sink in sinks if sink.get("is_virtual")
    ]

    candidates = build_audio_identity_candidates(hdmi_devices, sinks)

    default_sink = None
    server_name = None

    for line in pactl_info_result["stdout"].splitlines():
        if line.startswith("Default Sink:"):
            default_sink = line.split(":", 1)[1].strip()
        elif line.startswith("Server Name:"):
            server_name = line.split(":", 1)[1].strip()

    command_failures = [
        name
        for name, result in [
            ("aplay -l", aplay_result),
            ("pactl info", pactl_info_result),
            ("pactl list short sinks", pactl_short_sinks_result),
            ("pactl list cards", pactl_cards_result),
            ("pactl list sinks", pactl_sinks_result),
        ]
        if result["exit_code"] != 0
    ]

    matched_candidates = sum(
        1
        for candidate in candidates
        if candidate["matching_pipewire_sinks"]
    )

    if command_failures:
        status = "FAILED"
        classification = "audio_discovery_command_failure"
        reason = (
            "Required audio discovery commands failed: "
            + ", ".join(command_failures)
        )
    elif not hdmi_devices:
        status = "FAILED"
        classification = "no_alsa_hdmi_playback_devices"
        reason = "No ALSA HDMI playback devices were observed."
    elif not hdmi_sinks:
        status = "PARTIAL"
        classification = "alsa_hdmi_present_pipewire_hdmi_unresolved"
        reason = (
            "ALSA HDMI playback devices were observed, but no current "
            "PipeWire HDMI candidate sinks were normalized."
        )
    elif matched_candidates == 0:
        status = "PARTIAL"
        classification = "hdmi_audio_surfaces_present_correlation_incomplete"
        reason = (
            "ALSA and PipeWire HDMI surfaces were observed, but no "
            "ALSA-device-to-PipeWire-sink correlation was resolved."
        )
    else:
        status = "PASS"
        classification = "hdmi_audio_surfaces_observed"
        reason = (
            "ALSA HDMI playback devices and current PipeWire HDMI sink "
            "surfaces were observed and normalized."
        )

    report: dict[str, Any] = {
        "schema_version": 0,
        "report_type": "screenstereo_audio_discovery",
        "observed_local": observed.isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "observation_only": True,
        "audio_graph_mutation_performed": False,
        "profile_change_performed": False,
        "default_sink_change_performed": False,
        "environment": {
            "xdg_session_type": os.environ.get("XDG_SESSION_TYPE"),
            "xdg_current_desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
            "display": os.environ.get("DISPLAY"),
        },
        "counts": {
            "alsa_playback_device_count": len(alsa_devices),
            "alsa_hdmi_device_count": len(hdmi_devices),
            "pipewire_card_count": len(cards),
            "pipewire_sink_count": len(sinks),
            "pipewire_hdmi_candidate_count": len(hdmi_sinks),
            "virtual_sink_count": len(virtual_sinks),
            "normalized_candidate_count": len(candidates),
            "normalized_candidates_with_pipewire_match": matched_candidates,
        },
        "alsa": {
            "command_result": aplay_result,
            "playback_devices": alsa_devices,
            "hdmi_devices": hdmi_devices,
        },
        "pulse": {
            "server_name": server_name,
            "default_sink": default_sink,
            "info_command_result": pactl_info_result,
        },
        "pipewire": {
            "cards": cards,
            "sinks": sinks,
            "hdmi_candidate_sinks": hdmi_sinks,
            "virtual_sinks": virtual_sinks,
            "pactl_short_sinks_command_result": pactl_short_sinks_result,
            "pactl_cards_command_result": pactl_cards_result,
            "pactl_sinks_command_result": pactl_sinks_result,
            "wpctl_status_command_result": wpctl_result,
        },
        "normalized_audio_identity_candidates": candidates,
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

    return 0 if status in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    sys.exit(main())

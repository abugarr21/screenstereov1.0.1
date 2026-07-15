#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


STATE_ROOT = Path.home() / ".local/state/screenstereo-pipewire/display-discovery"
LATEST_JSON = STATE_ROOT / "latest_discovery.json"
LATEST_TEXT = STATE_ROOT / "latest_discovery.txt"


def now_local() -> datetime:
    return datetime.now().astimezone()


def run_command(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
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


def decode_manufacturer(raw: bytes) -> str | None:
    if len(raw) < 10:
        return None

    value = int.from_bytes(raw[8:10], byteorder="big")
    letters = [
        chr(((value >> 10) & 0x1F) + 64),
        chr(((value >> 5) & 0x1F) + 64),
        chr((value & 0x1F) + 64),
    ]

    manufacturer = "".join(letters)
    if not manufacturer.isalpha():
        return None

    return manufacturer


def decode_descriptor_text(block: bytes) -> str:
    text = block[5:18]
    text = text.split(b"\n", 1)[0]
    text = text.split(b"\x00", 1)[0]
    return text.decode("ascii", errors="replace").strip()


def parse_edid(raw: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {
        "present": bool(raw),
        "byte_length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest() if raw else None,
        "header_valid": False,
        "manufacturer": None,
        "product_code_decimal": None,
        "product_code_hex": None,
        "numeric_serial": None,
        "model_name": None,
        "descriptor_serial": None,
        "manufacture_week": None,
        "manufacture_year": None,
        "width_cm": None,
        "height_cm": None,
        "extension_count": None,
    }

    if len(raw) < 128:
        return result

    result["header_valid"] = raw[:8] == b"\x00\xff\xff\xff\xff\xff\xff\x00"
    result["manufacturer"] = decode_manufacturer(raw)

    product_code = struct.unpack_from("<H", raw, 10)[0]
    numeric_serial = struct.unpack_from("<I", raw, 12)[0]

    result["product_code_decimal"] = product_code
    result["product_code_hex"] = f"0x{product_code:04x}"
    result["numeric_serial"] = numeric_serial if numeric_serial != 0 else None
    result["manufacture_week"] = raw[16] if raw[16] != 0 else None
    result["manufacture_year"] = 1990 + raw[17]
    result["width_cm"] = raw[21] if raw[21] != 0 else None
    result["height_cm"] = raw[22] if raw[22] != 0 else None
    result["extension_count"] = raw[126]

    for offset in range(54, 126, 18):
        block = raw[offset : offset + 18]
        if len(block) != 18:
            continue

        if block[0:3] != b"\x00\x00\x00":
            continue

        descriptor_type = block[3]

        if descriptor_type == 0xFC:
            result["model_name"] = decode_descriptor_text(block)
        elif descriptor_type == 0xFF:
            result["descriptor_serial"] = decode_descriptor_text(block)

    return result


def normalize_drm_connector(sysfs_name: str) -> str:
    match = re.match(r"card\d+-(.+)", sysfs_name)
    if match:
        return match.group(1)
    return sysfs_name


def collect_drm_connectors() -> list[dict[str, Any]]:
    connectors: list[dict[str, Any]] = []

    for connector_path in sorted(Path("/sys/class/drm").glob("card*-*")):
        status_path = connector_path / "status"
        if not status_path.exists():
            continue

        status = status_path.read_text(encoding="utf-8", errors="replace").strip()
        enabled_path = connector_path / "enabled"
        modes_path = connector_path / "modes"
        edid_path = connector_path / "edid"

        enabled = (
            enabled_path.read_text(encoding="utf-8", errors="replace").strip()
            if enabled_path.exists()
            else None
        )

        modes = (
            [
                line.strip()
                for line in modes_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if line.strip()
            ]
            if modes_path.exists()
            else []
        )

        edid_raw = edid_path.read_bytes() if edid_path.exists() else b""

        connectors.append(
            {
                "sysfs_name": connector_path.name,
                "connector_name": normalize_drm_connector(connector_path.name),
                "sysfs_path": str(connector_path),
                "status": status,
                "enabled": enabled,
                "modes": modes,
                "edid": parse_edid(edid_raw),
            }
        )

    return connectors


def collect_xrandr() -> dict[str, Any]:
    command_result = run_command(["xrandr", "--query"])
    displays: list[dict[str, Any]] = []

    if command_result["exit_code"] == 0:
        pattern = re.compile(
            r"^(?P<connector>\S+)\s+connected"
            r"(?P<primary>\s+primary)?"
            r"(?:\s+(?P<width>\d+)x(?P<height>\d+)"
            r"\+(?P<x>-?\d+)\+(?P<y>-?\d+))?"
        )

        for line in command_result["stdout"].splitlines():
            match = pattern.match(line)
            if not match:
                continue

            groups = match.groupdict()

            displays.append(
                {
                    "connector_name": groups["connector"],
                    "primary": bool(groups["primary"]),
                    "width": int(groups["width"]) if groups["width"] else None,
                    "height": int(groups["height"]) if groups["height"] else None,
                    "x": int(groups["x"]) if groups["x"] else None,
                    "y": int(groups["y"]) if groups["y"] else None,
                    "raw_line": line,
                }
            )

    return {
        "command_result": command_result,
        "connected_displays": displays,
    }


def connector_family_and_index(name: str) -> tuple[str, int] | None:
    match = re.match(r"^(.*?)(\d+)$", name)
    if not match:
        return None

    return match.group(1), int(match.group(2))


def correlate_geometry(
    connectors: list[dict[str, Any]],
    xrandr_displays: list[dict[str, Any]],
) -> None:
    for connector in connectors:
        connector["desktop_geometry"] = None
        connector["desktop_geometry_match"] = None

    connected_drm = [
        connector
        for connector in connectors
        if connector.get("status") == "connected"
    ]

    drm_groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    xrandr_groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}

    for connector in connected_drm:
        parsed = connector_family_and_index(connector["connector_name"])
        if parsed is None:
            continue

        family, index = parsed
        drm_groups.setdefault(family, []).append((index, connector))

    for display in xrandr_displays:
        parsed = connector_family_and_index(display["connector_name"])
        if parsed is None:
            continue

        family, index = parsed
        xrandr_groups.setdefault(family, []).append((index, display))

    matched_drm_ids: set[int] = set()
    matched_xrandr_names: set[str] = set()

    for family, drm_items in drm_groups.items():
        xr_items = xrandr_groups.get(family, [])

        if not xr_items or len(drm_items) != len(xr_items):
            continue

        drm_items = sorted(drm_items, key=lambda item: item[0])
        xr_items = sorted(xr_items, key=lambda item: item[0])

        offsets = {
            xr_index - drm_index
            for (drm_index, _connector), (xr_index, _display)
            in zip(drm_items, xr_items)
        }

        if len(offsets) != 1:
            continue

        offset = next(iter(offsets))

        for (drm_index, connector), (xr_index, display) in zip(
            drm_items,
            xr_items,
        ):
            connector["desktop_geometry"] = display
            connector["desktop_geometry_match"] = {
                "method": "connector_family_constant_numeric_offset",
                "connector_family": family,
                "drm_index": drm_index,
                "desktop_index": xr_index,
                "numeric_offset": offset,
            }
            matched_drm_ids.add(id(connector))
            matched_xrandr_names.add(display["connector_name"])

    xrandr_by_name = {
        display["connector_name"]: display
        for display in xrandr_displays
        if display["connector_name"] not in matched_xrandr_names
    }

    for connector in connected_drm:
        if id(connector) in matched_drm_ids:
            continue

        display = xrandr_by_name.get(connector["connector_name"])
        if display is None:
            continue

        connector["desktop_geometry"] = display
        connector["desktop_geometry_match"] = {
            "method": "exact_connector_name",
            "drm_connector": connector["connector_name"],
            "desktop_connector": display["connector_name"],
        }


def stable_identity_summary(connector: dict[str, Any]) -> dict[str, Any]:
    edid = connector["edid"]

    return {
        "connector_name": connector["connector_name"],
        "status": connector["status"],
        "enabled": connector["enabled"],
        "edid_manufacturer": edid["manufacturer"],
        "edid_product_code_decimal": edid["product_code_decimal"],
        "edid_product_code_hex": edid["product_code_hex"],
        "edid_numeric_serial": edid["numeric_serial"],
        "edid_descriptor_serial": edid["descriptor_serial"],
        "model_name": edid["model_name"],
        "edid_sha256": edid["sha256"],
        "desktop_geometry": connector.get("desktop_geometry"),
    }


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("=== SCREENSTEREO DISPLAY DISCOVERY ===")
    lines.append(f"ts={report['observed_local']}")
    lines.append(f"run_id={report['run_id']}")
    lines.append(f"session_type={report['session']['xdg_session_type']}")
    lines.append(f"desktop={report['session']['xdg_current_desktop']}")
    lines.append(f"display={report['session']['display']}")
    lines.append("")

    lines.append("=== Connected DRM displays ===")

    connected = report["connected_stable_identities"]

    if not connected:
        lines.append("NONE")
    else:
        for index, identity in enumerate(connected, start=1):
            geometry = identity.get("desktop_geometry") or {}

            lines.append(f"display_{index}:")
            lines.append(f"  connector={identity['connector_name']}")
            lines.append(f"  status={identity['status']}")
            lines.append(f"  enabled={identity['enabled']}")
            lines.append(
                f"  manufacturer={identity['edid_manufacturer'] or 'unavailable'}"
            )
            lines.append(
                "  product_code_decimal="
                + str(identity["edid_product_code_decimal"])
            )
            lines.append(
                f"  product_code_hex={identity['edid_product_code_hex'] or 'unavailable'}"
            )
            lines.append(
                "  numeric_serial="
                + str(identity["edid_numeric_serial"])
            )
            lines.append(
                "  descriptor_serial="
                + str(identity["edid_descriptor_serial"])
            )
            lines.append(
                f"  model_name={identity['model_name'] or 'unavailable'}"
            )
            lines.append(
                f"  edid_sha256={identity['edid_sha256'] or 'unavailable'}"
            )
            lines.append(
                "  geometry="
                + (
                    f"{geometry.get('width')}x{geometry.get('height')}"
                    f"+{geometry.get('x')}+{geometry.get('y')}"
                    if geometry
                    else "unavailable"
                )
            )
            lines.append(
                f"  primary={geometry.get('primary') if geometry else 'unavailable'}"
            )

    lines.append("")
    lines.append("=== Discovery result ===")
    lines.append(
        f"drm_connector_count={report['counts']['drm_connector_count']}"
    )
    lines.append(
        f"drm_connected_count={report['counts']['drm_connected_count']}"
    )
    lines.append(
        f"xrandr_connected_count={report['counts']['xrandr_connected_count']}"
    )
    lines.append(
        f"connected_with_edid_count={report['counts']['connected_with_edid_count']}"
    )
    lines.append(
        f"connected_with_geometry_count={report['counts']['connected_with_geometry_count']}"
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

    connectors = collect_drm_connectors()
    xrandr = collect_xrandr()

    correlate_geometry(connectors, xrandr["connected_displays"])

    connected_connectors = [
        connector for connector in connectors if connector["status"] == "connected"
    ]

    connected_identities = [
        stable_identity_summary(connector)
        for connector in connected_connectors
    ]

    connected_with_edid = sum(
        1 for connector in connected_connectors if connector["edid"]["present"]
    )

    connected_with_geometry = sum(
        1
        for connector in connected_connectors
        if connector.get("desktop_geometry") is not None
    )

    if not connected_connectors:
        status = "FAILED"
        classification = "no_connected_display_identity"
        reason = "No connected DRM display connector was observed."
    elif connected_with_edid == 0:
        status = "FAILED"
        classification = "connected_displays_without_edid"
        reason = (
            "Connected DRM displays were observed, but no EDID identity data "
            "was available."
        )
    elif connected_with_geometry < len(connected_connectors):
        status = "PARTIAL"
        classification = "display_identity_present_geometry_incomplete"
        reason = (
            "Stable display identity was observed, but desktop geometry "
            "could not be correlated for every connected display."
        )
    else:
        status = "PASS"
        classification = "display_identity_observed"
        reason = (
            "Connected DRM displays were observed with EDID identity and "
            "desktop geometry evidence."
        )

    report: dict[str, Any] = {
        "schema_version": 0,
        "report_type": "screenstereo_display_discovery",
        "observed_local": observed.isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "observation_only": True,
        "audio_graph_mutation_performed": False,
        "session": {
            "xdg_session_type": os.environ.get("XDG_SESSION_TYPE"),
            "xdg_current_desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
            "display": os.environ.get("DISPLAY"),
            "wayland_display": os.environ.get("WAYLAND_DISPLAY"),
        },
        "counts": {
            "drm_connector_count": len(connectors),
            "drm_connected_count": len(connected_connectors),
            "xrandr_connected_count": len(xrandr["connected_displays"]),
            "connected_with_edid_count": connected_with_edid,
            "connected_with_geometry_count": connected_with_geometry,
        },
        "drm_connectors": connectors,
        "xrandr": xrandr,
        "connected_stable_identities": connected_identities,
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

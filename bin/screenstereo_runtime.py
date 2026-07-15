#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


HOME = Path.home()

RESOLVER_SCRIPT = HOME / ".local/bin/screenstereo_resolve.py"
RESOLUTION_JSON = (
    HOME
    / ".local/state/screenstereo-pipewire/runtime-resolution/latest_resolution.json"
)

STATE_DIR = (
    HOME
    / ".local/state/screenstereo-pipewire/runtime-resolution"
)

CONSUMER_ENV = STATE_DIR / "consumer.env"
CONSUMER_JSON = STATE_DIR / "consumer.json"
CONSUMER_STATUS = STATE_DIR / "consumer_status.txt"


def now_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))

    return json.loads(path.read_text(encoding="utf-8"))


def run_resolver() -> tuple[int, str, str]:
    if not RESOLVER_SCRIPT.exists():
        return 2, "", f"resolver missing: {RESOLVER_SCRIPT}"

    result = subprocess.run(
        [str(RESOLVER_SCRIPT)],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    return result.returncode, result.stdout, result.stderr


def display_label(role_result: dict[str, Any]) -> str:
    display = role_result.get("resolved_display", {})
    manufacturer = display.get("edid_manufacturer") or "unknown"
    model = display.get("model_name") or "unknown"

    return f"{manufacturer}/{model}"


def validate_resolution(report: dict[str, Any]) -> dict[str, str]:
    errors: list[str] = []

    if report.get("status") != "PASS":
        errors.append("resolution_status_not_pass")

    if report.get("classification") != "runtime_identity_resolution_complete":
        errors.append("resolution_classification_invalid")

    roles = report.get("role_resolutions", {})
    left = roles.get("left", {})
    right = roles.get("right", {})

    if left.get("status") != "RESOLVED":
        errors.append("left_role_not_resolved")

    if right.get("status") != "RESOLVED":
        errors.append("right_role_not_resolved")

    runtime = report.get("resolved_runtime", {})
    left_sink = runtime.get("left_sink")
    right_sink = runtime.get("right_sink")
    distinct = runtime.get("distinct_sinks")

    if not left_sink:
        errors.append("left_sink_missing")

    if not right_sink:
        errors.append("right_sink_missing")

    if distinct is not True:
        errors.append("distinct_sinks_not_true")

    if left_sink and right_sink and left_sink == right_sink:
        errors.append("left_right_sink_collision")

    if errors:
        raise ValueError(",".join(errors))

    return {
        "STATUS": "PASS",
        "CLASSIFICATION": "runtime_identity_resolution_complete",
        "LEFT_SINK": str(left_sink),
        "RIGHT_SINK": str(right_sink),
        "LEFT_DISPLAY": display_label(left),
        "RIGHT_DISPLAY": display_label(right),
        "DISTINCT_SINKS": "True",
        "RESOLUTION_RUN_ID": str(report.get("run_id") or ""),
        "RESOLUTION_JSON": str(RESOLUTION_JSON),
    }


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )

    temp_path = Path(temp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        temp_path.chmod(mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_consumer_surfaces(values: dict[str, str]) -> None:
    env_lines = [
        key + "=" + shlex.quote(value)
        for key, value in values.items()
    ]

    atomic_write(
        CONSUMER_ENV,
        "\n".join(env_lines) + "\n",
    )

    atomic_write(
        CONSUMER_JSON,
        json.dumps(
            {
                "schema_version": 0,
                "report_type": "screenstereo_runtime_consumer",
                "generated_local": now_local(),
                **values,
                "audio_graph_mutation_performed": False,
            },
            indent=2,
        ) + "\n",
    )

    status_lines = [
        "ts=" + now_local(),
        "status=PASS",
        "classification=runtime_consumer_ready",
        "left_sink=" + values["LEFT_SINK"],
        "right_sink=" + values["RIGHT_SINK"],
        "left_display=" + values["LEFT_DISPLAY"],
        "right_display=" + values["RIGHT_DISPLAY"],
        "distinct_sinks=" + values["DISTINCT_SINKS"],
        "consumer_env=" + str(CONSUMER_ENV),
        "consumer_json=" + str(CONSUMER_JSON),
        "audio_graph_mutation_performed=False",
    ]

    atomic_write(
        CONSUMER_STATUS,
        "\n".join(status_lines) + "\n",
    )


def resolve() -> int:
    resolver_rc, resolver_stdout, resolver_stderr = run_resolver()

    if resolver_rc != 0:
        print("STATUS=REFUSED")
        print("CLASSIFICATION=runtime_resolver_failed")
        print("RESOLVER_EXIT_CODE=" + str(resolver_rc))
        print("REASON=" + shlex.quote(
            resolver_stderr.strip()
            or resolver_stdout.strip()
            or "runtime resolver failed"
        ))
        return 2

    try:
        report = load_json(RESOLUTION_JSON)
        values = validate_resolution(report)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print("STATUS=REFUSED")
        print("CLASSIFICATION=runtime_resolution_invalid")
        print("REASON=" + shlex.quote(str(exc)))
        return 2

    write_consumer_surfaces(values)

    for key in [
        "STATUS",
        "CLASSIFICATION",
        "LEFT_SINK",
        "RIGHT_SINK",
        "LEFT_DISPLAY",
        "RIGHT_DISPLAY",
        "DISTINCT_SINKS",
        "RESOLUTION_RUN_ID",
        "RESOLUTION_JSON",
    ]:
        print(key + "=" + values[key])

    print("CONSUMER_ENV=" + str(CONSUMER_ENV))
    print("CONSUMER_JSON=" + str(CONSUMER_JSON))
    print("AUDIO_GRAPH_MUTATION_PERFORMED=False")

    return 0


def status() -> int:
    if not CONSUMER_STATUS.exists():
        print("status=NOT_READY")
        print("classification=runtime_consumer_not_generated")
        return 1

    print(
        CONSUMER_STATUS.read_text(encoding="utf-8"),
        end="",
    )

    return 0


def shell() -> int:
    if not CONSUMER_ENV.exists():
        resolve_rc = resolve()
        if resolve_rc != 0:
            return resolve_rc

    print(
        CONSUMER_ENV.read_text(encoding="utf-8"),
        end="",
    )

    return 0


def usage() -> None:
    print(
        "Usage:\n"
        "  screenstereo_runtime.py resolve\n"
        "  screenstereo_runtime.py status\n"
        "  screenstereo_runtime.py shell"
    )


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"

    if command == "resolve":
        return resolve()

    if command == "status":
        return status()

    if command == "shell":
        return shell()

    usage()
    return 64


if __name__ == "__main__":
    sys.exit(main())

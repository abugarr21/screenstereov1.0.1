#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import AyatanaAppIndicator3, GLib, Gtk


HOME = Path.home()

STATE_DIR = HOME / ".local/state/hbai-audio"
MODE_STATUS = STATE_DIR / "hbai_audio_mode_status.txt"
DOCTOR_STATUS = STATE_DIR / "hbai_audio_doctor_status.txt"
RECOVERY_STATUS = STATE_DIR / "hbai_audio_recovery_status.txt"
INDICATOR_STATUS = STATE_DIR / "hbai_audio_indicator_status.txt"

RUNTIME_STATUS = (
    HOME
    / ".local/state/screenstereo-pipewire/runtime-resolution/consumer_status.txt"
)

MODE_SCRIPT = HOME / ".local/bin/hbai_audio_mode.sh"
DOCTOR_SCRIPT = HOME / ".local/bin/hbai_audio_doctor.sh"
RECOVER_SCRIPT = HOME / ".local/bin/hbai_audio_recover.sh"

ICON_DIR = HOME / ".local/share/hbai-audio/icons"
GREEN_ICON = ICON_DIR / "hbai-audio-running.svg"
RED_ICON = ICON_DIR / "hbai-audio-malfunction.svg"

POLL_INTERVAL_SECONDS = 2


def now_local() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_kv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return values
    except OSError:
        return values

    for line in text.splitlines():
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key] = value

    return values


def mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def write_status(values: dict[str, str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    ordered_keys = [
        "ts",
        "status",
        "mode",
        "classification",
        "indicator_state",
        "icon_state",
        "message",
        "doctor_status",
        "doctor_classification",
        "resolution_status",
        "resolution_classification",
        "left_display",
        "right_display",
        "resolver_backed",
    ]

    lines = []

    for key in ordered_keys:
        lines.append(f"{key}={values.get(key, 'unknown')}")

    temp_path = INDICATOR_STATUS.with_suffix(".txt.tmp")
    temp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temp_path, INDICATOR_STATUS)


class ScreenStereoIndicator:
    def __init__(self) -> None:
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "screenstereo-audio",
            str(RED_ICON),
            AyatanaAppIndicator3.IndicatorCategory.HARDWARE,
        )

        self.indicator.set_status(
            AyatanaAppIndicator3.IndicatorStatus.ACTIVE
        )

        self.menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label="ScreenStereo: starting")
        self.status_item.set_sensitive(False)
        self.menu.append(self.status_item)

        self.mode_item = Gtk.MenuItem(label="Mode: unknown")
        self.mode_item.set_sensitive(False)
        self.menu.append(self.mode_item)

        self.left_item = Gtk.MenuItem(label="Left: unknown")
        self.left_item.set_sensitive(False)
        self.menu.append(self.left_item)

        self.right_item = Gtk.MenuItem(label="Right: unknown")
        self.right_item.set_sensitive(False)
        self.menu.append(self.right_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        split_item = Gtk.MenuItem(label="Use split mode")
        split_item.connect("activate", self.on_mode, "split")
        self.menu.append(split_item)

        mirror_item = Gtk.MenuItem(label="Use mirror mode")
        mirror_item.connect("activate", self.on_mode, "mirror")
        self.menu.append(mirror_item)

        reset_item = Gtk.MenuItem(label="Reset virtual graph")
        reset_item.connect("activate", self.on_mode, "reset")
        self.menu.append(reset_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        doctor_item = Gtk.MenuItem(label="Run doctor")
        doctor_item.connect("activate", self.on_doctor)
        self.menu.append(doctor_item)

        recover_item = Gtk.MenuItem(label="Run bounded recovery")
        recover_item.connect("activate", self.on_recover)
        self.menu.append(recover_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit indicator")
        quit_item.connect("activate", self.on_quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        self.last_mode_mtime = 0.0
        self.last_doctor_request_mode_mtime = -1.0
        pass
        self.doctor_running = False
        self.action_running = False

        self.refresh_display(force_doctor=False)

        GLib.timeout_add_seconds(
            POLL_INTERVAL_SECONDS,
            self.poll,
        )

    def set_icon(self, green: bool) -> None:
        icon = GREEN_ICON if green else RED_ICON
        description = (
            "ScreenStereo healthy"
            if green
            else "ScreenStereo attention required"
        )

        self.indicator.set_icon_full(str(icon), description)

    def run_background(
        self,
        command: list[str],
        after_doctor: bool = True,
    ) -> None:
        if self.action_running:
            return

        self.action_running = True
        self.show_resolving("Applying requested action")

        def worker() -> None:
            try:
                subprocess.run(
                    command,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=120,
                )

                if after_doctor and DOCTOR_SCRIPT.exists():
                    subprocess.run(
                        [str(DOCTOR_SCRIPT)],
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=120,
                    )
            finally:
                GLib.idle_add(self.finish_action)

        threading.Thread(target=worker, daemon=True).start()

    def finish_action(self) -> bool:
        self.action_running = False
        self.refresh_display(force_doctor=False)
        return False

    def request_doctor(self) -> None:
        if self.doctor_running or self.action_running:
            return

        if not DOCTOR_SCRIPT.exists():
            self.refresh_display(force_doctor=False)
            return

        self.doctor_running = True
        self.show_resolving("Refreshing diagnosis")

        def worker() -> None:
            try:
                subprocess.run(
                    [str(DOCTOR_SCRIPT)],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=120,
                )
            finally:
                GLib.idle_add(self.finish_doctor)

        threading.Thread(target=worker, daemon=True).start()

    def finish_doctor(self) -> bool:
        self.doctor_running = False
        pass
        self.refresh_display(force_doctor=False)
        return False

    def show_resolving(self, message: str) -> None:
        mode_data = read_kv(MODE_STATUS)
        doctor_data = read_kv(DOCTOR_STATUS)

        mode = mode_data.get("mode", doctor_data.get("mode", "unknown"))
        left = (
            mode_data.get("left_display")
            or doctor_data.get("left_display")
            or "unknown"
        )
        right = (
            mode_data.get("right_display")
            or doctor_data.get("right_display")
            or "unknown"
        )

        self.set_icon(False)
        self.status_item.set_label("ScreenStereo: resolving")
        self.mode_item.set_label(f"Mode: {mode}")
        self.left_item.set_label(f"Left: {left}")
        self.right_item.set_label(f"Right: {right}")

        write_status(
            {
                "ts": now_local(),
                "status": "RESOLVING",
                "mode": mode,
                "classification": "runtime_resolution_refresh_in_progress",
                "indicator_state": "resolving",
                "icon_state": "red",
                "message": message,
                "doctor_status": doctor_data.get("status", "unknown"),
                "doctor_classification": doctor_data.get(
                    "classification",
                    "unknown",
                ),
                "resolution_status": doctor_data.get(
                    "resolution_status",
                    "unknown",
                ),
                "resolution_classification": doctor_data.get(
                    "resolution_classification",
                    "unknown",
                ),
                "left_display": left,
                "right_display": right,
                "resolver_backed": doctor_data.get(
                    "resolver_backed",
                    "unknown",
                ),
            }
        )

    def classify(
        self,
        doctor: dict[str, str],
        mode: dict[str, str],
    ) -> dict[str, str]:
        doctor_status = doctor.get("status", "MISSING")
        classification = doctor.get(
            "classification",
            "doctor_status_unavailable",
        )
        active_mode = doctor.get("mode") or mode.get("mode") or "unknown"

        left = (
            doctor.get("left_display")
            or mode.get("left_display")
            or "unknown"
        )
        right = (
            doctor.get("right_display")
            or mode.get("right_display")
            or "unknown"
        )

        if doctor_status == "RUNNING" and classification == "healthy":
            if active_mode == "split":
                state = "healthy_split"
                label = "healthy split"
            elif active_mode == "mirror":
                state = "healthy_mirror"
                label = "healthy mirror"
            else:
                state = "malfunction"
                label = "unsupported healthy mode"

            green = state in {"healthy_split", "healthy_mirror"}
            status = "RUNNING" if green else "MALFUNCTION"

        elif (
            doctor_status == "RESET"
            or classification == "hbai_audio_virtual_graph_inactive"
        ):
            state = "reset"
            label = "virtual graph reset"
            green = False
            status = "RESET"

        elif classification == "setup_required":
            state = "setup_required"
            label = "setup required"
            green = False
            status = "REFUSED"

        elif classification in {
            "display_identity_ambiguous",
            "display_audio_correlation_ambiguous",
        }:
            state = "identity_ambiguous"
            label = "identity ambiguous"
            green = False
            status = "REFUSED"

        elif classification in {
            "display_identity_unresolved",
            "audio_sink_unresolved",
            "configured_hardware_changed",
            "runtime_resolution_failed",
            "runtime_resolution_stale",
        }:
            state = "identity_unresolved"
            label = "identity unresolved"
            green = False
            status = "REFUSED"

        elif classification in {
            "split_graph_mismatch",
            "mirror_graph_mismatch",
        }:
            state = "graph_mismatch"
            label = "audio graph mismatch"
            green = False
            status = "MALFUNCTION"

        else:
            state = "malfunction"
            label = classification.replace("_", " ")
            green = False
            status = "MALFUNCTION"

        message = doctor.get("reason") or mode.get("message") or label

        return {
            "status": status,
            "mode": active_mode,
            "classification": classification,
            "indicator_state": state,
            "icon_state": "green" if green else "red",
            "label": label,
            "message": message,
            "doctor_status": doctor_status,
            "doctor_classification": classification,
            "resolution_status": doctor.get(
                "resolution_status",
                "unknown",
            ),
            "resolution_classification": doctor.get(
                "resolution_classification",
                "unknown",
            ),
            "left_display": left,
            "right_display": right,
            "resolver_backed": doctor.get(
                "resolver_backed",
                mode.get("resolver_backed", "unknown"),
            ),
        }

    def refresh_display(self, force_doctor: bool) -> None:
        mode_data = read_kv(MODE_STATUS)
        doctor_data = read_kv(DOCTOR_STATUS)

        mode_time = mtime(MODE_STATUS)
        doctor_time = mtime(DOCTOR_STATUS)

        doctor_is_older = (
            mode_time > 0
            and doctor_time < mode_time
        )

        if force_doctor or doctor_is_older or not doctor_data:
            if (
                not self.doctor_running
                and self.last_doctor_request_mode_mtime != mode_time
            ):
                self.last_doctor_request_mode_mtime = mode_time
                self.request_doctor()
                return

        state = self.classify(doctor_data, mode_data)

        self.set_icon(state["icon_state"] == "green")

        self.status_item.set_label(
            "ScreenStereo: " + state["label"]
        )
        self.mode_item.set_label("Mode: " + state["mode"])
        self.left_item.set_label(
            "Left: " + state["left_display"]
        )
        self.right_item.set_label(
            "Right: " + state["right_display"]
        )

        write_status(
            {
                "ts": now_local(),
                "status": state["status"],
                "mode": state["mode"],
                "classification": state["classification"],
                "indicator_state": state["indicator_state"],
                "icon_state": state["icon_state"],
                "message": state["message"],
                "doctor_status": state["doctor_status"],
                "doctor_classification": state[
                    "doctor_classification"
                ],
                "resolution_status": state["resolution_status"],
                "resolution_classification": state[
                    "resolution_classification"
                ],
                "left_display": state["left_display"],
                "right_display": state["right_display"],
                "resolver_backed": state["resolver_backed"],
            }
        )

    def poll(self) -> bool:
        mode_time = mtime(MODE_STATUS)
        current_time = datetime.now().timestamp()

        if mode_time != self.last_mode_mtime:
            self.last_mode_mtime = mode_time

            if mode_time > 0:
                self.last_doctor_request_mode_mtime = mode_time
                self.request_doctor()
                return True

        pass

        if not self.doctor_running and not self.action_running:
            self.refresh_display(force_doctor=False)

        return True

    def on_mode(
        self,
        _item: Gtk.MenuItem,
        mode: str,
    ) -> None:
        self.run_background([str(MODE_SCRIPT), mode])

    def on_doctor(self, _item: Gtk.MenuItem) -> None:
        self.request_doctor()

    def on_recover(self, _item: Gtk.MenuItem) -> None:
        self.run_background(
            [str(RECOVER_SCRIPT), "auto"],
            after_doctor=True,
        )

    def on_quit(self, _item: Gtk.MenuItem) -> None:
        Gtk.main_quit()


def main() -> int:
    ScreenStereoIndicator()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

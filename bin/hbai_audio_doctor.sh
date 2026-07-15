#!/usr/bin/env bash
set -u

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

STATE_DIR="$HOME/.local/state/hbai-audio"
STATUS_FILE="$STATE_DIR/hbai_audio_doctor_status.txt"
REPORT_FILE="$STATE_DIR/hbai_audio_doctor_report.txt"

MODE_STATUS_FILE="$STATE_DIR/hbai_audio_mode_status.txt"
SPLIT_STATUS_FILE="$STATE_DIR/hbai_tv_lr_split_status.txt"
INDICATOR_STATUS_FILE="$STATE_DIR/hbai_audio_indicator_status.txt"

MODE_CONFIG="$HOME/.config/hbai-audio/mode.conf"
MODE_SCRIPT="$HOME/.local/bin/hbai_audio_mode.sh"

DISPLAY_MAP="$HOME/.config/screenstereo-pipewire/display-map.json"
RUNTIME_HELPER="$HOME/.local/bin/screenstereo_runtime.py"
RUNTIME_ENV="$HOME/.local/state/screenstereo-pipewire/runtime-resolution/consumer.env"
RUNTIME_JSON="$HOME/.local/state/screenstereo-pipewire/runtime-resolution/latest_resolution.json"

MIRROR_SINK="hbai_hdmi_all"
SPLIT_SINK="hbai_tv_lr_split"
LEFT_SOURCE="hbai_tv_lr_left_source"
RIGHT_SOURCE="hbai_tv_lr_right_source"

mkdir -p "$STATE_DIR"

tmp_report="$(mktemp)"
runtime_output="$(mktemp)"
trap 'rm -f "$tmp_report" "$runtime_output"' EXIT

kv_get() {
  local file="$1"
  local key="$2"

  if [ -f "$file" ]; then
    awk -F= -v k="$key" '$1==k {print substr($0, length(k)+2); exit}' "$file"
  fi
}

line() {
  echo "$*" | tee -a "$tmp_report"
}

write_doctor_status() {
  local doctor_status="$1"
  local mode="$2"
  local classification="$3"
  local reason="$4"
  local action="$5"

  {
    echo "ts=$(/bin/date --iso-8601=seconds)"
    echo "status=$doctor_status"
    echo "mode=$mode"
    echo "classification=$classification"
    echo "reason=$reason"
    echo "recommended_action=$action"
    echo "resolver_backed=${RESOLVER_BACKED:-False}"
    echo "resolution_status=${STATUS:-unknown}"
    echo "resolution_classification=${CLASSIFICATION:-unknown}"
    echo "resolution_run_id=${RESOLUTION_RUN_ID:-unknown}"
    echo "left_display=${LEFT_DISPLAY:-unknown}"
    echo "right_display=${RIGHT_DISPLAY:-unknown}"
    echo "left_sink=${LEFT_SINK:-unknown}"
    echo "right_sink=${RIGHT_SINK:-unknown}"
    echo "distinct_sinks=${DISTINCT_SINKS:-unknown}"
    echo "display_map=$DISPLAY_MAP"
    echo "runtime_resolution_json=$RUNTIME_JSON"
  } > "$STATUS_FILE"

  cp "$tmp_report" "$REPORT_FILE"
}

finish() {
  local exit_code="$1"
  local doctor_status="$2"
  local mode="$3"
  local classification="$4"
  local reason="$5"
  local action="$6"

  line ""
  line "=== Diagnosis ==="
  line "status=$doctor_status"
  line "classification=$classification"
  line "reason=$reason"
  line "recommended_action=$action"

  write_doctor_status \
    "$doctor_status" \
    "$mode" \
    "$classification" \
    "$reason" \
    "$action"

  exit "$exit_code"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

sink_exists() {
  pactl list short sinks 2>/dev/null \
    | awk '{print $2}' \
    | grep -Fxq "$1"
}

source_exists() {
  pactl list short sources 2>/dev/null \
    | awk '{print $2}' \
    | grep -Fxq "$1"
}

default_sink() {
  pactl info 2>/dev/null \
    | awk -F': ' '/Default Sink/ {print $2; exit}'
}

service_active() {
  systemctl --user is-active "$1" 2>/dev/null || true
}

service_enabled() {
  systemctl --user is-enabled "$1" 2>/dev/null || true
}

count_drm_connected() {
  local count=0
  local status_path

  for status_path in \
    /sys/class/drm/card*-HDMI-A-*/status \
    /sys/class/drm/card*-DP-*/status
  do
    [ -e "$status_path" ] || continue

    if [ "$(cat "$status_path" 2>/dev/null || true)" = "connected" ]; then
      count=$((count + 1))
    fi
  done

  echo "$count"
}

print_drm_connected() {
  local status_path

  for status_path in \
    /sys/class/drm/card*-HDMI-A-*/status \
    /sys/class/drm/card*-DP-*/status
  do
    [ -e "$status_path" ] || continue

    if [ "$(cat "$status_path" 2>/dev/null || true)" = "connected" ]; then
      echo "$(basename "$(dirname "$status_path")")=connected"
    fi
  done
}

count_alsa_hdmi() {
  if ! command_exists aplay; then
    echo "0"
    return
  fi

  aplay -l 2>/dev/null \
    | grep -Ei 'HDMI|DisplayPort' \
    | wc -l \
    | awk '{print $1}'
}

classify_runtime_failure() {
  local helper_text="$1"

  if printf '%s\n' "$helper_text" | grep -q 'display_identity_ambiguous'; then
    echo "display_identity_ambiguous"
  elif printf '%s\n' "$helper_text" | grep -q 'display_identity_unresolved'; then
    echo "display_identity_unresolved"
  elif printf '%s\n' "$helper_text" | grep -q 'audio_sink_unresolved'; then
    echo "audio_sink_unresolved"
  elif printf '%s\n' "$helper_text" | grep -q 'display_audio_correlation_ambiguous'; then
    echo "display_audio_correlation_ambiguous"
  elif printf '%s\n' "$helper_text" | grep -q 'configured_hardware_changed'; then
    echo "configured_hardware_changed"
  else
    echo "runtime_resolution_failed"
  fi
}

mode_config="$(kv_get "$MODE_CONFIG" mode)"
mode_status="$(kv_get "$MODE_STATUS_FILE" status)"
mode_name="$(kv_get "$MODE_STATUS_FILE" mode)"
mode_message="$(kv_get "$MODE_STATUS_FILE" message)"

split_status="$(kv_get "$SPLIT_STATUS_FILE" status)"
split_message="$(kv_get "$SPLIT_STATUS_FILE" message)"

indicator_status="$(kv_get "$INDICATOR_STATUS_FILE" status)"
indicator_mode="$(kv_get "$INDICATOR_STATUS_FILE" mode)"
indicator_icon="$(kv_get "$INDICATOR_STATUS_FILE" icon_state)"
indicator_message="$(kv_get "$INDICATOR_STATUS_FILE" message)"

mode_config="${mode_config:-missing}"
mode_status="${mode_status:-MISSING}"
mode_name="${mode_name:-unknown}"
mode_message="${mode_message:-mode status missing}"
split_status="${split_status:-MISSING}"
split_message="${split_message:-split status missing}"
indicator_status="${indicator_status:-MISSING}"
indicator_mode="${indicator_mode:-unknown}"
indicator_icon="${indicator_icon:-unknown}"
indicator_message="${indicator_message:-indicator status missing}"

RESOLVER_BACKED=False
STATUS="unknown"
CLASSIFICATION="unknown"
RESOLUTION_RUN_ID="unknown"
LEFT_DISPLAY="unknown"
RIGHT_DISPLAY="unknown"
LEFT_SINK=""
RIGHT_SINK=""
DISTINCT_SINKS="unknown"

line "=== HBAI AUDIO DOCTOR ==="
line "ts=$(/bin/date --iso-8601=seconds)"
line "node=$(/bin/hostname)"
line ""

line "=== Layer 0: command availability ==="

missing_commands=""

for cmd in pactl systemctl awk grep sed xargs python3; do
  if command_exists "$cmd"; then
    line "PASS command=$cmd"
  else
    line "FAIL command=$cmd missing"
    missing_commands="$missing_commands $cmd"
  fi
done

if command_exists aplay; then
  line "PASS command=aplay"
else
  line "WARN command=aplay missing"
fi

if [ -n "$missing_commands" ]; then
  finish \
    1 \
    "FAILED" \
    "$mode_name" \
    "missing_required_command" \
    "required command missing:$missing_commands" \
    "install the missing command package or repair PATH"
fi

line ""

drm_count="$(count_drm_connected)"
alsa_count="$(count_alsa_hdmi)"

line "=== Layer 1: physical display connectors ==="

if [ "$drm_count" -gt 0 ]; then
  line "PASS drm_connected_count=$drm_count"
  print_drm_connected | sed 's/^/DRM /' | tee -a "$tmp_report"
else
  line "FAIL drm_connected_count=0"
fi

line ""
line "=== Layer 2: ALSA HDMI playback devices ==="

if command_exists aplay; then
  if [ "$alsa_count" -gt 0 ]; then
    line "PASS alsa_hdmi_line_count=$alsa_count"
    aplay -l 2>/dev/null \
      | grep -Ei 'HDMI|DisplayPort' \
      | sed 's/^/ALSA /' \
      | tee -a "$tmp_report"
  else
    line "FAIL alsa_hdmi_line_count=0"
  fi
else
  line "WARN aplay unavailable; ALSA layer could not be fully inspected"
fi

line ""
line "=== Layer 3: user-session PipeWire/Pulse control ==="

if ! pactl info >/dev/null 2>&1; then
  line "FAIL pactl_user_session=unreachable"

  finish \
    1 \
    "FAILED" \
    "$mode_name" \
    "user_session_audio_route_unavailable" \
    "physical display or ALSA surfaces may exist, but pactl cannot reach the user-session audio server" \
    "restart PipeWire, PipeWire Pulse, and WirePlumber user services"
fi

line "PASS pactl_user_session=reachable"
line "default_sink=$(default_sink)"

line ""
line "=== Layer 4: durable stable-identity configuration ==="

if [ ! -f "$DISPLAY_MAP" ]; then
  line "FAIL display_map_missing=$DISPLAY_MAP"

  finish \
    2 \
    "REFUSED" \
    "$mode_name" \
    "setup_required" \
    "durable ScreenStereo display-map configuration is missing" \
    "$HOME/.local/bin/screenstereo_setup.py show"
fi

if ! python3 -m json.tool "$DISPLAY_MAP" >/dev/null 2>&1; then
  line "FAIL display_map_json_invalid=$DISPLAY_MAP"

  finish \
    2 \
    "REFUSED" \
    "$mode_name" \
    "setup_required" \
    "durable ScreenStereo display-map configuration is invalid" \
    "rerun guided setup and explicitly confirm the display mapping"
fi

line "PASS display_map_present=$DISPLAY_MAP"
line "PASS display_map_json_valid=True"

line ""
line "=== Layer 5: stable-identity runtime resolution ==="

if [ ! -x "$RUNTIME_HELPER" ]; then
  line "FAIL runtime_helper_missing=$RUNTIME_HELPER"

  finish \
    1 \
    "FAILED" \
    "$mode_name" \
    "runtime_resolution_failed" \
    "runtime-resolution consumer helper is missing or not executable" \
    "restore or reinstall screenstereo_runtime.py"
fi

"$RUNTIME_HELPER" resolve >"$runtime_output" 2>&1
runtime_rc=$?

cat "$runtime_output" | sed 's/^/RUNTIME /' | tee -a "$tmp_report"

if [ "$runtime_rc" -ne 0 ]; then
  runtime_text="$(cat "$runtime_output")"
  runtime_classification="$(classify_runtime_failure "$runtime_text")"

  finish \
    2 \
    "REFUSED" \
    "$mode_name" \
    "$runtime_classification" \
    "stable display identity could not be resolved uniquely to current audio sinks" \
    "$HOME/.local/bin/screenstereo_setup.py show"
fi

if [ ! -f "$RUNTIME_ENV" ]; then
  finish \
    1 \
    "FAILED" \
    "$mode_name" \
    "runtime_resolution_failed" \
    "runtime helper succeeded but did not create the consumer environment" \
    "$RUNTIME_HELPER resolve"
fi

set -a
. "$RUNTIME_ENV"
set +a

if [ "${STATUS:-}" != "PASS" ] \
  || [ "${CLASSIFICATION:-}" != "runtime_identity_resolution_complete" ] \
  || [ "${DISTINCT_SINKS:-}" != "True" ] \
  || [ -z "${LEFT_SINK:-}" ] \
  || [ -z "${RIGHT_SINK:-}" ] \
  || [ "$LEFT_SINK" = "$RIGHT_SINK" ]
then
  finish \
    2 \
    "REFUSED" \
    "$mode_name" \
    "runtime_resolution_failed" \
    "runtime consumer surface did not satisfy the required distinct left/right resolution contract" \
    "$RUNTIME_HELPER resolve"
fi

RESOLVER_BACKED=True

line "PASS resolution_status=$STATUS"
line "PASS resolution_classification=$CLASSIFICATION"
line "PASS resolution_run_id=$RESOLUTION_RUN_ID"
line "PASS left_display=$LEFT_DISPLAY"
line "PASS right_display=$RIGHT_DISPLAY"
line "PASS left_sink=$LEFT_SINK"
line "PASS right_sink=$RIGHT_SINK"
line "PASS distinct_sinks=$DISTINCT_SINKS"

if ! sink_exists "$LEFT_SINK"; then
  finish \
    2 \
    "REFUSED" \
    "$mode_name" \
    "audio_sink_unresolved" \
    "resolved left sink is not present in the current PipeWire graph: $LEFT_SINK" \
    "$RUNTIME_HELPER resolve"
fi

if ! sink_exists "$RIGHT_SINK"; then
  finish \
    2 \
    "REFUSED" \
    "$mode_name" \
    "audio_sink_unresolved" \
    "resolved right sink is not present in the current PipeWire graph: $RIGHT_SINK" \
    "$RUNTIME_HELPER resolve"
fi

line ""
line "=== Layer 6: mode and status surfaces ==="
line "mode_config=$mode_config"
line "mode_status=$mode_status"
line "mode_name=$mode_name"
line "mode_message=$mode_message"
line "split_status=$split_status"
line "split_message=$split_message"
line "indicator_status=$indicator_status"
line "indicator_mode=$indicator_mode"
line "indicator_icon_state=$indicator_icon"
line "indicator_message=$indicator_message"

line ""
line "=== Layer 7: user services ==="

for service in \
  hbai-audio-mode.service \
  hbai-audio-indicator.service \
  hbai-hdmi-all.service \
  hbai-tv-lr-split.service
do
  line "$service active=$(service_active "$service") enabled=$(service_enabled "$service")"
done

line ""
line "=== Layer 8: resolver-backed PipeWire graph ==="
line "relevant_sinks:"

pactl list short sinks \
  | awk -v left="$LEFT_SINK" -v right="$RIGHT_SINK" '
      $2==left || $2==right || $2=="hbai_hdmi_all" || $2=="hbai_tv_lr_split"
    ' \
  | sed 's/^/SINK /' \
  | tee -a "$tmp_report" \
  || true

line "relevant_sources:"

pactl list short sources \
  | grep -E 'hbai_tv_lr_left|hbai_tv_lr_right|hbai_tv_lr_split' \
  | sed 's/^/SOURCE /' \
  | tee -a "$tmp_report" \
  || true

if [ "$mode_status" = "RESET" ] || [ "$mode_name" = "reset" ]; then
  fallback="$(default_sink)"

  if [ "$fallback" != "$LEFT_SINK" ] && [ "$fallback" != "$RIGHT_SINK" ]; then
    finish \
      1 \
      "FAILED" \
      "reset" \
      "hbai_audio_virtual_graph_inactive" \
      "virtual graph is inactive and the default sink is not one of the current resolved physical sinks" \
      "$MODE_SCRIPT split"
  fi

  finish \
    3 \
    "RESET" \
    "reset" \
    "hbai_audio_virtual_graph_inactive" \
    "ScreenStereo virtual graph is intentionally unloaded; resolved physical fallback is active: $fallback" \
    "$MODE_SCRIPT split OR $MODE_SCRIPT mirror"
fi

if [ "$mode_status" != "RUNNING" ]; then
  finish \
    1 \
    "FAILED" \
    "$mode_name" \
    "hbai_audio_mode_status_not_running" \
    "mode status is not RUNNING: $mode_status" \
    "$MODE_SCRIPT apply"
fi

current_default="$(default_sink)"

case "$mode_name" in
  split)
    missing=""

    for sink in "$LEFT_SINK" "$RIGHT_SINK" "$SPLIT_SINK"; do
      if ! sink_exists "$sink"; then
        missing="$missing $sink"
      fi
    done

    for source in "$SPLIT_SINK.monitor" "$LEFT_SOURCE" "$RIGHT_SOURCE"; do
      if ! source_exists "$source"; then
        missing="$missing $source"
      fi
    done

    if [ "$current_default" != "$SPLIT_SINK" ]; then
      missing="$missing default_sink_expected_${SPLIT_SINK}_got_${current_default}"
    fi

    if [ -n "$missing" ]; then
      finish \
        1 \
        "FAILED" \
        "split" \
        "split_graph_mismatch" \
        "missing_or_wrong:$missing" \
        "$MODE_SCRIPT split"
    fi
    ;;

  mirror)
    missing=""

    for sink in "$LEFT_SINK" "$RIGHT_SINK" "$MIRROR_SINK"; do
      if ! sink_exists "$sink"; then
        missing="$missing $sink"
      fi
    done

    if [ "$current_default" != "$MIRROR_SINK" ]; then
      missing="$missing default_sink_expected_${MIRROR_SINK}_got_${current_default}"
    fi

    if ! pactl list short modules \
      | grep -F 'module-combine-sink' \
      | grep -F "sink_name=$MIRROR_SINK" \
      | grep -F "slaves=$LEFT_SINK,$RIGHT_SINK" \
      >/dev/null
    then
      missing="$missing resolver_backed_combine_module"
    fi

    if [ -n "$missing" ]; then
      finish \
        1 \
        "FAILED" \
        "mirror" \
        "mirror_graph_mismatch" \
        "missing_or_wrong:$missing" \
        "$MODE_SCRIPT mirror"
    fi
    ;;

  *)
    finish \
      1 \
      "FAILED" \
      "$mode_name" \
      "unsupported_running_mode" \
      "mode status reports unsupported running mode: $mode_name" \
      "$MODE_SCRIPT split OR $MODE_SCRIPT mirror"
    ;;
esac

finish \
  0 \
  "RUNNING" \
  "$mode_name" \
  "healthy" \
  "stable identity, runtime resolution, and selected audio graph all passed" \
  "none"

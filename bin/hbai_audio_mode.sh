#!/usr/bin/env bash
set -u

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

CONFIG_DIR="$HOME/.config/hbai-audio"
STATE_DIR="$HOME/.local/state/hbai-audio"

MODE_CONFIG="$CONFIG_DIR/mode.conf"
STATUS_FILE="$STATE_DIR/hbai_audio_mode_status.txt"
SPLIT_STATUS_FILE="$STATE_DIR/hbai_tv_lr_split_status.txt"

MIRROR_SCRIPT="$HOME/.local/bin/hbai_hdmi_all_refresh.sh"
SPLIT_SCRIPT="$HOME/.local/bin/hbai_tv_lr_split_refresh.sh"

RUNTIME_HELPER="$HOME/.local/bin/screenstereo_runtime.py"
RUNTIME_ENV="$HOME/.local/state/screenstereo-pipewire/runtime-resolution/consumer.env"

MIRROR_SERVICE="hbai-hdmi-all.service"
SPLIT_SERVICE="hbai-tv-lr-split.service"

MIRROR_SINK="hbai_hdmi_all"
SPLIT_SINK="hbai_tv_lr_split"

mkdir -p "$CONFIG_DIR" "$STATE_DIR"

write_status() {
  local status="$1"
  local mode="$2"
  local message="$3"

  {
    echo "ts=$(/bin/date --iso-8601=seconds)"
    echo "status=$status"
    echo "mode=$mode"
    echo "message=$message"
    echo "resolver_backed=${RESOLVER_BACKED:-False}"
    echo "resolution_status=${STATUS:-unknown}"
    echo "resolution_classification=${CLASSIFICATION:-unknown}"
    echo "resolution_run_id=${RESOLUTION_RUN_ID:-unknown}"
    echo "left_display=${LEFT_DISPLAY:-unknown}"
    echo "right_display=${RIGHT_DISPLAY:-unknown}"
    echo "left_sink=${LEFT_SINK:-unknown}"
    echo "right_sink=${RIGHT_SINK:-unknown}"
    echo "distinct_sinks=${DISTINCT_SINKS:-unknown}"
  } > "$STATUS_FILE"

  echo "$status: mode=$mode message=$message"
}

write_split_inactive_status() {
  local reason="$1"

  {
    echo "ts=$(/bin/date --iso-8601=seconds)"
    echo "status=INACTIVE"
    echo "mode=hbai_tv_lr_split"
    echo "message=HBAI_TV_LR_SPLIT_INACTIVE reason=$reason"
  } > "$SPLIT_STATUS_FILE"
}

fail() {
  write_status "FAILED" "${2:-unknown}" "$1"
  exit 1
}

refuse() {
  write_status "REFUSED" "${2:-unknown}" "$1"
  exit 2
}

need_pactl() {
  local mode="${1:-unknown}"

  command -v pactl >/dev/null 2>&1 \
    || fail "pactl not found; PipeWire/Pulse control unavailable." "$mode"

  pactl info >/dev/null 2>&1 \
    || fail "pactl cannot reach the user-session PipeWire/Pulse server." "$mode"
}

sink_exists() {
  pactl list short sinks \
    | awk '{print $2}' \
    | grep -Fxq "$1"
}

source_exists() {
  pactl list short sources \
    | awk '{print $2}' \
    | grep -Fxq "$1"
}

read_config_mode() {
  if [ -f "$MODE_CONFIG" ]; then
    awk -F= '$1=="mode" {print $2; exit}' "$MODE_CONFIG"
  else
    echo "split"
  fi
}

write_config_mode() {
  local mode="$1"
  echo "mode=$mode" > "$MODE_CONFIG"
}

stop_mode_services() {
  systemctl --user stop "$MIRROR_SERVICE" >/dev/null 2>&1 || true
  systemctl --user stop "$SPLIT_SERVICE" >/dev/null 2>&1 || true
}

unload_hbai_modules() {
  pactl list short modules \
    | awk '$2=="module-loopback" && $0 ~ /hbai_tv_lr_/ {print $1}' \
    | xargs -r -n1 pactl unload-module

  pactl list short modules \
    | awk '$2=="module-remap-source" && $0 ~ /hbai_tv_lr_/ {print $1}' \
    | xargs -r -n1 pactl unload-module

  pactl list short modules \
    | awk '$2=="module-null-sink" && $0 ~ /sink_name=hbai_tv_lr_split/ {print $1}' \
    | xargs -r -n1 pactl unload-module

  pactl list short modules \
    | awk '$2=="module-combine-sink" && $0 ~ /sink_name=hbai_hdmi_all/ {print $1}' \
    | xargs -r -n1 pactl unload-module
}

load_runtime_resolution() {
  local mode="${1:-unknown}"

  RESOLVER_BACKED=False

  [ -x "$RUNTIME_HELPER" ] \
    || refuse "runtime consumer helper missing or not executable: $RUNTIME_HELPER" "$mode"

  "$RUNTIME_HELPER" resolve >/dev/null
  local runtime_rc=$?

  if [ "$runtime_rc" -ne 0 ]; then
    refuse "runtime identity resolution failed with exit code $runtime_rc" "$mode"
  fi

  [ -f "$RUNTIME_ENV" ] \
    || refuse "runtime consumer environment missing after resolution: $RUNTIME_ENV" "$mode"

  set -a
  . "$RUNTIME_ENV"
  set +a

  [ "${STATUS:-}" = "PASS" ] \
    || refuse "runtime resolution status is not PASS: ${STATUS:-missing}" "$mode"

  [ "${CLASSIFICATION:-}" = "runtime_identity_resolution_complete" ] \
    || refuse "runtime resolution classification is invalid: ${CLASSIFICATION:-missing}" "$mode"

  [ "${DISTINCT_SINKS:-}" = "True" ] \
    || refuse "runtime resolution did not prove distinct sinks" "$mode"

  [ -n "${LEFT_SINK:-}" ] \
    || refuse "runtime resolution did not provide LEFT_SINK" "$mode"

  [ -n "${RIGHT_SINK:-}" ] \
    || refuse "runtime resolution did not provide RIGHT_SINK" "$mode"

  [ "$LEFT_SINK" != "$RIGHT_SINK" ] \
    || refuse "runtime resolution produced a left/right sink collision" "$mode"

  sink_exists "$LEFT_SINK" \
    || refuse "resolved left display sink is not currently visible: $LEFT_SINK" "$mode"

  sink_exists "$RIGHT_SINK" \
    || refuse "resolved right display sink is not currently visible: $RIGHT_SINK" "$mode"

  RESOLVER_BACKED=True
}

load_existing_runtime_surface() {
  RESOLVER_BACKED=False

  if [ -f "$RUNTIME_ENV" ]; then
    set -a
    . "$RUNTIME_ENV"
    set +a

    if [ "${STATUS:-}" = "PASS" ] \
      && [ "${CLASSIFICATION:-}" = "runtime_identity_resolution_complete" ] \
      && [ "${DISTINCT_SINKS:-}" = "True" ]
    then
      RESOLVER_BACKED=True
    fi
  fi
}

apply_mirror() {
  need_pactl "mirror"
  load_runtime_resolution "mirror"

  [ -x "$MIRROR_SCRIPT" ] \
    || fail "mirror refresh script missing or not executable: $MIRROR_SCRIPT" "mirror"

  stop_mode_services
  unload_hbai_modules
  write_split_inactive_status "mode_switch_to_mirror"

  "$MIRROR_SCRIPT"
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    fail "mirror mode failed: $MIRROR_SCRIPT exited with status $rc" "mirror"
  fi

  sleep 1

  sink_exists "$MIRROR_SINK" \
    || fail "mirror mode failed: expected sink missing after refresh: $MIRROR_SINK" "mirror"

  pactl set-default-sink "$MIRROR_SINK" \
    || fail "mirror mode failed: could not set default sink to $MIRROR_SINK" "mirror"

  write_status \
    "RUNNING" \
    "mirror" \
    "HBAI_AUDIO_MODE_READY resolver_backed=True sink=$MIRROR_SINK left_display=$LEFT_DISPLAY left=$LEFT_SINK right_display=$RIGHT_DISPLAY right=$RIGHT_SINK"
}

apply_split() {
  need_pactl "split"
  load_runtime_resolution "split"

  [ -x "$SPLIT_SCRIPT" ] \
    || fail "split refresh script missing or not executable: $SPLIT_SCRIPT" "split"

  stop_mode_services
  unload_hbai_modules

  "$SPLIT_SCRIPT"
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    fail "split mode failed: $SPLIT_SCRIPT exited with status $rc" "split"
  fi

  sleep 1

  sink_exists "$SPLIT_SINK" \
    || fail "split mode failed: expected sink missing after refresh: $SPLIT_SINK" "split"

  source_exists "hbai_tv_lr_left_source" \
    || fail "split mode failed: left source missing after refresh: hbai_tv_lr_left_source" "split"

  source_exists "hbai_tv_lr_right_source" \
    || fail "split mode failed: right source missing after refresh: hbai_tv_lr_right_source" "split"

  pactl set-default-sink "$SPLIT_SINK" \
    || fail "split mode failed: could not set default sink to $SPLIT_SINK" "split"

  write_status \
    "RUNNING" \
    "split" \
    "HBAI_AUDIO_MODE_READY resolver_backed=True sink=$SPLIT_SINK left_display=$LEFT_DISPLAY left=$LEFT_SINK right_display=$RIGHT_DISPLAY right=$RIGHT_SINK"
}

apply_reset() {
  need_pactl "reset"
  load_runtime_resolution "reset"

  stop_mode_services
  unload_hbai_modules
  write_split_inactive_status "reset_unloaded_virtual_graph"

  local fallback=""

  if sink_exists "$RIGHT_SINK"; then
    fallback="$RIGHT_SINK"
  elif sink_exists "$LEFT_SINK"; then
    fallback="$LEFT_SINK"
  else
    refuse "reset refused: neither resolved physical sink remains visible" "reset"
  fi

  pactl set-default-sink "$fallback" \
    || fail "reset failed: could not set resolved fallback sink to $fallback" "reset"

  write_status \
    "RESET" \
    "reset" \
    "HBAI audio virtual graph unloaded; resolver_backed=True default sink set to resolved fallback=$fallback"
}

show_status() {
  load_existing_runtime_surface

  echo "=== HBAI audio mode status ==="

  echo ""
  echo "mode_config=$MODE_CONFIG"
  if [ -f "$MODE_CONFIG" ]; then
    cat "$MODE_CONFIG"
  else
    echo "mode=split"
  fi

  echo ""
  echo "mode_status_file=$STATUS_FILE"
  if [ -f "$STATUS_FILE" ]; then
    cat "$STATUS_FILE"
  else
    echo "status_file_missing=true"
  fi

  echo ""
  echo "runtime_consumer_env=$RUNTIME_ENV"
  if [ -f "$RUNTIME_ENV" ]; then
    cat "$RUNTIME_ENV"
  else
    echo "runtime_consumer_missing=true"
  fi

  echo ""
  echo "split_status_file=$SPLIT_STATUS_FILE"
  if [ -f "$SPLIT_STATUS_FILE" ]; then
    cat "$SPLIT_STATUS_FILE"
  else
    echo "split_status_file_missing=true"
  fi

  echo ""
  echo "default_sink:"
  pactl info 2>/dev/null \
    | awk -F': ' '/Default Sink/ {print $2}' \
    || true

  echo ""
  echo "resolved_physical_sinks:"
  if [ -n "${LEFT_SINK:-}" ]; then
    pactl list short sinks 2>/dev/null \
      | awk '{print $2}' \
      | grep -Fx "$LEFT_SINK" \
      || true
  fi

  if [ -n "${RIGHT_SINK:-}" ]; then
    pactl list short sinks 2>/dev/null \
      | awk '{print $2}' \
      | grep -Fx "$RIGHT_SINK" \
      || true
  fi

  echo ""
  echo "virtual_sinks:"
  pactl list short sinks 2>/dev/null \
    | grep -E 'hbai_hdmi_all|hbai_tv_lr_split' \
    || true

  echo ""
  echo "relevant_sources:"
  pactl list short sources 2>/dev/null \
    | grep -E 'hbai_tv_lr_left|hbai_tv_lr_right|hbai_tv_lr_split' \
    || true

  echo ""
  echo "mode_services:"
  systemctl --user --no-pager --plain is-enabled hbai-audio-mode.service 2>/dev/null \
    | sed 's/^/hbai-audio-mode.enabled=/' \
    || true

  systemctl --user --no-pager --plain is-active hbai-audio-mode.service 2>/dev/null \
    | sed 's/^/hbai-audio-mode.active=/' \
    || true

  systemctl --user --no-pager --plain is-enabled "$MIRROR_SERVICE" 2>/dev/null \
    | sed 's/^/hbai-hdmi-all.enabled=/' \
    || true

  systemctl --user --no-pager --plain is-enabled "$SPLIT_SERVICE" 2>/dev/null \
    | sed 's/^/hbai-tv-lr-split.enabled=/' \
    || true
}

usage() {
  cat <<USAGE
Usage:
  hbai_audio_mode.sh mirror
  hbai_audio_mode.sh split
  hbai_audio_mode.sh reset
  hbai_audio_mode.sh apply
  hbai_audio_mode.sh status
USAGE
}

cmd="${1:-status}"

case "$cmd" in
  mirror)
    write_config_mode "mirror"
    apply_mirror
    ;;

  split)
    write_config_mode "split"
    apply_split
    ;;

  reset)
    write_config_mode "reset"
    apply_reset
    ;;

  apply)
    configured_mode="$(read_config_mode)"

    case "$configured_mode" in
      mirror)
        apply_mirror
        ;;
      split)
        apply_split
        ;;
      reset)
        apply_reset
        ;;
      *)
        refuse "configured mode is unsupported: $configured_mode" "apply"
        ;;
    esac
    ;;

  status)
    show_status
    ;;

  *)
    usage
    exit 64
    ;;
esac

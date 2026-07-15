#!/usr/bin/env bash
set -u

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUNTIME_HELPER="$HOME/.local/bin/screenstereo_runtime.py"
RUNTIME_ENV="$HOME/.local/state/screenstereo-pipewire/runtime-resolution/consumer.env"

SPLIT_SINK="hbai_tv_lr_split"
LEFT_SOURCE="hbai_tv_lr_left_source"
RIGHT_SOURCE="hbai_tv_lr_right_source"

STATE_DIR="$HOME/.local/state/hbai-audio"
STATUS_FILE="$STATE_DIR/hbai_tv_lr_split_status.txt"

mkdir -p "$STATE_DIR"

write_status() {
  local status="$1"
  local message="$2"

  {
    echo "ts=$(/bin/date --iso-8601=seconds)"
    echo "status=$status"
    echo "mode=hbai_tv_lr_split"
    echo "message=$message"
    echo "resolution_status=${STATUS:-unknown}"
    echo "resolution_classification=${CLASSIFICATION:-unknown}"
    echo "resolution_run_id=${RESOLUTION_RUN_ID:-unknown}"
    echo "left_display=${LEFT_DISPLAY:-unknown}"
    echo "right_display=${RIGHT_DISPLAY:-unknown}"
    echo "left_sink=${LEFT_SINK:-unknown}"
    echo "right_sink=${RIGHT_SINK:-unknown}"
    echo "distinct_sinks=${DISTINCT_SINKS:-unknown}"
  } > "$STATUS_FILE"

  echo "$status: $message"
}

fail() {
  write_status "FAILED" "$1"
  exit 1
}

refuse() {
  write_status "REFUSED" "$1"
  exit 2
}

need_command() {
  command -v "$1" >/dev/null 2>&1 \
    || fail "$1 not found; PipeWire/Pulse control unavailable."
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

unload_matching_modules() {
  pactl list short modules \
    | awk '$2=="module-loopback" && $0 ~ /hbai_tv_lr_/ {print $1}' \
    | xargs -r -n1 pactl unload-module

  pactl list short modules \
    | awk '$2=="module-remap-source" && $0 ~ /hbai_tv_lr_/ {print $1}' \
    | xargs -r -n1 pactl unload-module

  pactl list short modules \
    | awk '$2=="module-null-sink" && $0 ~ /sink_name=hbai_tv_lr_split/ {print $1}' \
    | xargs -r -n1 pactl unload-module
}

derive_pro_audio_card() {
  local sink="$1"
  local base=""

  case "$sink" in
    alsa_output.*.pro-output-*)
      base="${sink%.pro-output-*}"
      echo "${base/alsa_output./alsa_card.}"
      ;;
    *)
      echo ""
      ;;
  esac
}

load_runtime_resolution() {
  [ -x "$RUNTIME_HELPER" ] \
    || refuse "runtime consumer helper missing or not executable: $RUNTIME_HELPER"

  "$RUNTIME_HELPER" resolve >/dev/null
  local runtime_rc=$?

  if [ "$runtime_rc" -ne 0 ]; then
    refuse "runtime identity resolution failed with exit code $runtime_rc"
  fi

  [ -f "$RUNTIME_ENV" ] \
    || refuse "runtime consumer environment missing after resolution: $RUNTIME_ENV"

  set -a
  . "$RUNTIME_ENV"
  set +a

  [ "${STATUS:-}" = "PASS" ] \
    || refuse "runtime resolution status is not PASS: ${STATUS:-missing}"

  [ "${CLASSIFICATION:-}" = "runtime_identity_resolution_complete" ] \
    || refuse "runtime resolution classification is invalid: ${CLASSIFICATION:-missing}"

  [ "${DISTINCT_SINKS:-}" = "True" ] \
    || refuse "runtime resolution did not prove distinct sinks"

  [ -n "${LEFT_SINK:-}" ] \
    || refuse "runtime resolution did not provide LEFT_SINK"

  [ -n "${RIGHT_SINK:-}" ] \
    || refuse "runtime resolution did not provide RIGHT_SINK"

  [ "$LEFT_SINK" != "$RIGHT_SINK" ] \
    || refuse "runtime resolution produced a left/right sink collision"
}

need_command pactl
need_command awk
need_command grep
need_command xargs

pactl info >/dev/null 2>&1 \
  || fail "pactl cannot reach the user-session PipeWire/Pulse server."

load_runtime_resolution

if ! sink_exists "$LEFT_SINK"; then
  refuse "resolved left display sink is not currently visible: $LEFT_SINK"
fi

if ! sink_exists "$RIGHT_SINK"; then
  refuse "resolved right display sink is not currently visible: $RIGHT_SINK"
fi

LEFT_CARD="$(derive_pro_audio_card "$LEFT_SINK")"
RIGHT_CARD="$(derive_pro_audio_card "$RIGHT_SINK")"

if [ -n "$LEFT_CARD" ]; then
  pactl set-card-profile "$LEFT_CARD" pro-audio >/dev/null 2>&1 \
    || fail "could not retain pro-audio profile for resolved left card: $LEFT_CARD"
fi

if [ -n "$RIGHT_CARD" ] && [ "$RIGHT_CARD" != "$LEFT_CARD" ]; then
  pactl set-card-profile "$RIGHT_CARD" pro-audio >/dev/null 2>&1 \
    || fail "could not retain pro-audio profile for resolved right card: $RIGHT_CARD"
fi

sleep 2

if ! sink_exists "$LEFT_SINK"; then
  refuse "resolved left sink disappeared after profile verification: $LEFT_SINK"
fi

if ! sink_exists "$RIGHT_SINK"; then
  refuse "resolved right sink disappeared after profile verification: $RIGHT_SINK"
fi

unload_matching_modules

pactl load-module module-null-sink \
  sink_name="$SPLIT_SINK" \
  channels=2 \
  channel_map=front-left,front-right \
  sink_properties=device.description="HBAI TV LR Split" >/dev/null \
  || fail "could not create split sink: $SPLIT_SINK"

sleep 1

pactl load-module module-remap-source \
  source_name="$LEFT_SOURCE" \
  master="$SPLIT_SINK.monitor" \
  channels=1 \
  master_channel_map=front-left \
  channel_map=mono \
  remix=no \
  source_properties=device.description="HBAI TV LR Left Source" >/dev/null \
  || fail "could not create left remap source: $LEFT_SOURCE"

pactl load-module module-remap-source \
  source_name="$RIGHT_SOURCE" \
  master="$SPLIT_SINK.monitor" \
  channels=1 \
  master_channel_map=front-right \
  channel_map=mono \
  remix=no \
  source_properties=device.description="HBAI TV LR Right Source" >/dev/null \
  || fail "could not create right remap source: $RIGHT_SOURCE"

sleep 1

source_exists "$LEFT_SOURCE" \
  || fail "left remap source did not materialize: $LEFT_SOURCE"

source_exists "$RIGHT_SOURCE" \
  || fail "right remap source did not materialize: $RIGHT_SOURCE"

pactl load-module module-loopback \
  source="$LEFT_SOURCE" \
  sink="$LEFT_SINK" \
  latency_msec=25 \
  source_output_properties=media.name=hbai_tv_lr_left_channel \
  sink_input_properties=media.name=hbai_tv_lr_left_channel >/dev/null \
  || fail "could not route left channel to resolved left display sink: $LEFT_SINK"

pactl load-module module-loopback \
  source="$RIGHT_SOURCE" \
  sink="$RIGHT_SINK" \
  latency_msec=25 \
  source_output_properties=media.name=hbai_tv_lr_right_channel \
  sink_input_properties=media.name=hbai_tv_lr_right_channel >/dev/null \
  || fail "could not route right channel to resolved right display sink: $RIGHT_SINK"

sleep 1

sink_exists "$SPLIT_SINK" \
  || fail "split sink did not materialize: $SPLIT_SINK"

pactl set-default-sink "$SPLIT_SINK" \
  || fail "could not set default sink to $SPLIT_SINK"

pactl set-sink-mute "$SPLIT_SINK" 0 \
  || fail "could not unmute $SPLIT_SINK"

pactl set-sink-volume "$SPLIT_SINK" 80% \
  || fail "could not set volume for $SPLIT_SINK"

write_status \
  "RUNNING" \
  "HBAI_TV_LR_SPLIT_READY resolver_backed=True left_display=$LEFT_DISPLAY left=$LEFT_SINK right_display=$RIGHT_DISPLAY right=$RIGHT_SINK"

echo ""
echo "=== Runtime resolution used ==="
echo "resolution_status=$STATUS"
echo "resolution_classification=$CLASSIFICATION"
echo "resolution_run_id=$RESOLUTION_RUN_ID"
echo "left_display=$LEFT_DISPLAY"
echo "left_sink=$LEFT_SINK"
echo "right_display=$RIGHT_DISPLAY"
echo "right_sink=$RIGHT_SINK"
echo "distinct_sinks=$DISTINCT_SINKS"

echo ""
echo "=== Sinks ==="
pactl list short sinks \
  | grep -F -e "$SPLIT_SINK" -e "$LEFT_SINK" -e "$RIGHT_SINK" \
  || true

echo ""
echo "=== Sources ==="
pactl list short sources \
  | grep -E 'hbai_tv_lr_left|hbai_tv_lr_right|hbai_tv_lr_split' \
  || true

echo ""
echo "=== Sink inputs ==="
pactl list short sink-inputs \
  | grep -E 'hbai_tv_lr_left|hbai_tv_lr_right' \
  || true

echo ""
echo "=== Status file ==="
cat "$STATUS_FILE"

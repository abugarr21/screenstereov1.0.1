#!/usr/bin/env bash
set -u

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUNTIME_HELPER="$HOME/.local/bin/screenstereo_runtime.py"
RUNTIME_ENV="$HOME/.local/state/screenstereo-pipewire/runtime-resolution/consumer.env"

MIRROR_SINK="hbai_hdmi_all"

STATE_DIR="$HOME/.local/state/hbai-audio"
STATUS_FILE="$STATE_DIR/hbai_hdmi_all_status.txt"

mkdir -p "$STATE_DIR"

write_status() {
  local status="$1"
  local message="$2"

  {
    echo "ts=$(/bin/date --iso-8601=seconds)"
    echo "status=$status"
    echo "mode=hbai_hdmi_all"
    echo "message=$message"
    echo "resolution_status=${STATUS:-unknown}"
    echo "resolution_classification=${CLASSIFICATION:-unknown}"
    echo "resolution_run_id=${RESOLUTION_RUN_ID:-unknown}"
    echo "left_display=${LEFT_DISPLAY:-unknown}"
    echo "right_display=${RIGHT_DISPLAY:-unknown}"
    echo "left_sink=${LEFT_SINK:-unknown}"
    echo "right_sink=${RIGHT_SINK:-unknown}"
    echo "distinct_sinks=${DISTINCT_SINKS:-unknown}"
    echo "mirror_slaves=${LEFT_SINK:-unknown},${RIGHT_SINK:-unknown}"
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

unload_existing_mirror() {
  pactl list short modules \
    | awk '$2=="module-combine-sink" && $0 ~ /sink_name=hbai_hdmi_all/ {print $1}' \
    | xargs -r -n1 pactl unload-module

  pactl list short modules \
    | awk '$2=="module-null-sink" && $0 ~ /sink_name=hbai_hdmi_all/ {print $1}' \
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

sink_exists "$LEFT_SINK" \
  || refuse "resolved left display sink is not currently visible: $LEFT_SINK"

sink_exists "$RIGHT_SINK" \
  || refuse "resolved right display sink is not currently visible: $RIGHT_SINK"

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

sink_exists "$LEFT_SINK" \
  || refuse "resolved left sink disappeared after profile verification: $LEFT_SINK"

sink_exists "$RIGHT_SINK" \
  || refuse "resolved right sink disappeared after profile verification: $RIGHT_SINK"

unload_existing_mirror

pactl load-module module-combine-sink \
  sink_name="$MIRROR_SINK" \
  slaves="$LEFT_SINK,$RIGHT_SINK" \
  channels=2 \
  channel_map=front-left,front-right \
  sink_properties=device.description="HBAI HDMI All Displays" >/dev/null \
  || fail "could not create mirror sink from the resolved display sinks"

sleep 2

sink_exists "$MIRROR_SINK" \
  || fail "mirror sink did not materialize: $MIRROR_SINK"

pactl set-default-sink "$MIRROR_SINK" \
  || fail "could not set default sink to $MIRROR_SINK"

pactl set-sink-mute "$LEFT_SINK" 0 \
  || fail "could not unmute resolved left sink: $LEFT_SINK"

pactl set-sink-mute "$RIGHT_SINK" 0 \
  || fail "could not unmute resolved right sink: $RIGHT_SINK"

pactl set-sink-mute "$MIRROR_SINK" 0 \
  || fail "could not unmute mirror sink: $MIRROR_SINK"

pactl set-sink-volume "$LEFT_SINK" 80% \
  || fail "could not set volume for resolved left sink"

pactl set-sink-volume "$RIGHT_SINK" 80% \
  || fail "could not set volume for resolved right sink"

pactl set-sink-volume "$MIRROR_SINK" 80% \
  || fail "could not set volume for mirror sink"

write_status \
  "RUNNING" \
  "HBAI_HDMI_ALL_READY resolver_backed=True left_display=$LEFT_DISPLAY left=$LEFT_SINK right_display=$RIGHT_DISPLAY right=$RIGHT_SINK"

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
echo "=== Mirror sink ==="
pactl list short sinks \
  | grep -F -e "$MIRROR_SINK" -e "$LEFT_SINK" -e "$RIGHT_SINK" \
  || true

echo ""
echo "=== Combine module ==="
pactl list short modules \
  | grep -F "sink_name=$MIRROR_SINK" \
  || true

echo ""
echo "=== Status file ==="
cat "$STATUS_FILE"

#!/usr/bin/env bash
set -u

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

STATE_DIR="$HOME/.local/state/hbai-audio"

STATUS_FILE="$STATE_DIR/hbai_audio_recovery_status.txt"
REPORT_FILE="$STATE_DIR/hbai_audio_recovery_report.txt"

DOCTOR_SCRIPT="$HOME/.local/bin/hbai_audio_doctor.sh"
DOCTOR_STATUS="$STATE_DIR/hbai_audio_doctor_status.txt"

MODE_SCRIPT="$HOME/.local/bin/hbai_audio_mode.sh"
MODE_CONFIG="$HOME/.config/hbai-audio/mode.conf"

RUNTIME_HELPER="$HOME/.local/bin/screenstereo_runtime.py"
RUNTIME_ENV="$HOME/.local/state/screenstereo-pipewire/runtime-resolution/consumer.env"

mkdir -p "$STATE_DIR"

tmp_report="$(mktemp)"
runtime_output="$(mktemp)"
trap 'rm -f "$tmp_report" "$runtime_output"' EXIT

line() {
  echo "$*" | tee -a "$tmp_report"
}

kv_get() {
  local file="$1"
  local key="$2"

  if [ -f "$file" ]; then
    awk -F= -v k="$key" '
      $1 == k {
        print substr($0, length(k) + 2)
        exit
      }
    ' "$file"
  fi
}

configured_mode() {
  local mode=""

  mode="$(kv_get "$MODE_CONFIG" mode)"

  case "$mode" in
    split|mirror)
      echo "$mode"
      ;;
    *)
      echo "split"
      ;;
  esac
}

write_status() {
  local status="$1"
  local classification="$2"
  local decision="$3"
  local action="$4"
  local before_status="$5"
  local before_classification="$6"
  local after_status="$7"
  local after_classification="$8"
  local message="$9"

  {
    echo "ts=$(/bin/date --iso-8601=seconds)"
    echo "status=$status"
    echo "classification=$classification"
    echo "decision=$decision"
    echo "action=$action"
    echo "before_status=$before_status"
    echo "before_classification=$before_classification"
    echo "after_status=$after_status"
    echo "after_classification=$after_classification"
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

  cp "$tmp_report" "$REPORT_FILE"
}

finish() {
  local exit_code="$1"
  local status="$2"
  local classification="$3"
  local decision="$4"
  local action="$5"
  local before_status="$6"
  local before_classification="$7"
  local after_status="$8"
  local after_classification="$9"
  local message="${10}"

  line ""
  line "=== Recovery result ==="
  line "status=$status"
  line "classification=$classification"
  line "decision=$decision"
  line "action=$action"
  line "before_status=$before_status"
  line "before_classification=$before_classification"
  line "after_status=$after_status"
  line "after_classification=$after_classification"
  line "message=$message"

  write_status \
    "$status" \
    "$classification" \
    "$decision" \
    "$action" \
    "$before_status" \
    "$before_classification" \
    "$after_status" \
    "$after_classification" \
    "$message"

  exit "$exit_code"
}

run_doctor() {
  [ -x "$DOCTOR_SCRIPT" ] || return 127

  "$DOCTOR_SCRIPT"
}

load_fresh_runtime_resolution() {
  RESOLVER_BACKED=False

  [ -x "$RUNTIME_HELPER" ] || return 20

  "$RUNTIME_HELPER" resolve >"$runtime_output" 2>&1
  local rc=$?

  cat "$runtime_output" | sed 's/^/RUNTIME /' | tee -a "$tmp_report"

  [ "$rc" -eq 0 ] || return 21
  [ -f "$RUNTIME_ENV" ] || return 22

  set -a
  . "$RUNTIME_ENV"
  set +a

  [ "${STATUS:-}" = "PASS" ] || return 23
  [ "${CLASSIFICATION:-}" = "runtime_identity_resolution_complete" ] || return 24
  [ "${DISTINCT_SINKS:-}" = "True" ] || return 25
  [ -n "${LEFT_SINK:-}" ] || return 26
  [ -n "${RIGHT_SINK:-}" ] || return 27
  [ "$LEFT_SINK" != "$RIGHT_SINK" ] || return 28

  RESOLVER_BACKED=True
  return 0
}

refused_classification() {
  case "$1" in
    setup_required|display_identity_unresolved|display_identity_ambiguous|configured_hardware_changed|audio_sink_unresolved|display_audio_correlation_ambiguous|runtime_resolution_failed|user_session_audio_route_unavailable|missing_required_command)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

show_status() {
  if [ -f "$STATUS_FILE" ]; then
    cat "$STATUS_FILE"
  else
    echo "status=NOT_RUN"
    echo "classification=recovery_status_unavailable"
  fi
}

command="${1:-auto}"

if [ "$command" = "status" ]; then
  show_status
  exit 0
fi

line "=== SCREENSTEREO BOUNDED RECOVERY ==="
line "ts=$(/bin/date --iso-8601=seconds)"
line "command=$command"
line ""

if [ "$command" = "test-refusal" ]; then
  line "=== Safe refusal-boundary test ==="
  line "simulated_classification=display_identity_ambiguous"
  line "audio_graph_mutation_performed=False"

  finish \
    2 \
    "REFUSED" \
    "display_identity_ambiguous" \
    "refuse_automatic_repair" \
    "none" \
    "REFUSED" \
    "display_identity_ambiguous" \
    "NOT_RUN" \
    "not_repaired" \
    "automatic recovery correctly refused an ambiguous identity state"
fi

case "$command" in
  auto|split|mirror)
    ;;
  *)
    echo "Usage:"
    echo "  hbai_audio_recover.sh auto"
    echo "  hbai_audio_recover.sh split"
    echo "  hbai_audio_recover.sh mirror"
    echo "  hbai_audio_recover.sh status"
    echo "  hbai_audio_recover.sh test-refusal"
    exit 64
    ;;
esac

[ -x "$DOCTOR_SCRIPT" ] || {
  finish \
    1 \
    "FAILED" \
    "doctor_missing" \
    "refuse_automatic_repair" \
    "none" \
    "UNKNOWN" \
    "doctor_missing" \
    "NOT_RUN" \
    "not_repaired" \
    "doctor script is missing or not executable"
}

[ -x "$MODE_SCRIPT" ] || {
  finish \
    1 \
    "FAILED" \
    "mode_script_missing" \
    "refuse_automatic_repair" \
    "none" \
    "UNKNOWN" \
    "mode_script_missing" \
    "NOT_RUN" \
    "not_repaired" \
    "mode script is missing or not executable"
}

line "=== Doctor before recovery ==="

run_doctor || true

before_status="$(kv_get "$DOCTOR_STATUS" status)"
before_classification="$(kv_get "$DOCTOR_STATUS" classification)"
before_reason="$(kv_get "$DOCTOR_STATUS" reason)"

before_status="${before_status:-UNKNOWN}"
before_classification="${before_classification:-unknown}"
before_reason="${before_reason:-doctor status unavailable}"

line "before_status=$before_status"
line "before_classification=$before_classification"
line "before_reason=$before_reason"
line ""

if [ "$before_status" = "RUNNING" ] \
  && [ "$before_classification" = "healthy" ]
then
  finish \
    0 \
    "RUNNING" \
    "healthy" \
    "no_action_needed" \
    "none" \
    "$before_status" \
    "$before_classification" \
    "$before_status" \
    "$before_classification" \
    "audio graph already healthy"
fi

if refused_classification "$before_classification"; then
  finish \
    2 \
    "REFUSED" \
    "$before_classification" \
    "refuse_automatic_repair" \
    "none" \
    "$before_status" \
    "$before_classification" \
    "NOT_RUN" \
    "not_repaired" \
    "doctor classification does not authorize automatic graph repair"
fi

case "$before_classification" in
  hbai_audio_virtual_graph_inactive|split_graph_mismatch|mirror_graph_mismatch|hbai_audio_mode_status_not_running|unsupported_running_mode|runtime_resolution_stale)
    ;;
  *)
    finish \
      2 \
      "REFUSED" \
      "$before_classification" \
      "refuse_unknown_repair" \
      "none" \
      "$before_status" \
      "$before_classification" \
      "NOT_RUN" \
      "not_repaired" \
      "classification is outside the bounded recovery policy"
    ;;
esac

line "=== Fresh runtime resolution before repair ==="

load_fresh_runtime_resolution
runtime_rc=$?

if [ "$runtime_rc" -ne 0 ]; then
  finish \
    2 \
    "REFUSED" \
    "runtime_resolution_failed" \
    "refuse_automatic_repair" \
    "none" \
    "$before_status" \
    "$before_classification" \
    "NOT_RUN" \
    "not_repaired" \
    "fresh stable-identity runtime resolution failed with code $runtime_rc"
fi

line "resolution_status=$STATUS"
line "resolution_classification=$CLASSIFICATION"
line "resolution_run_id=$RESOLUTION_RUN_ID"
line "left_display=$LEFT_DISPLAY"
line "right_display=$RIGHT_DISPLAY"
line "left_sink=$LEFT_SINK"
line "right_sink=$RIGHT_SINK"
line "distinct_sinks=$DISTINCT_SINKS"
line ""

target_mode="$command"

if [ "$command" = "auto" ]; then
  case "$before_classification" in
    split_graph_mismatch)
      target_mode="split"
      ;;
    mirror_graph_mismatch)
      target_mode="mirror"
      ;;
    *)
      target_mode="$(configured_mode)"
      ;;
  esac
fi

case "$target_mode" in
  split|mirror)
    ;;
  *)
    finish \
      2 \
      "REFUSED" \
      "unsupported_recovery_target" \
      "refuse_automatic_repair" \
      "none" \
      "$before_status" \
      "$before_classification" \
      "NOT_RUN" \
      "not_repaired" \
      "recovery target is not split or mirror"
    ;;
esac

action="$MODE_SCRIPT $target_mode"

line "=== Bounded repair action ==="
line "target_mode=$target_mode"
line "action=$action"
line ""

"$MODE_SCRIPT" "$target_mode"
mode_rc=$?

if [ "$mode_rc" -ne 0 ]; then
  finish \
    1 \
    "FAILED" \
    "bounded_repair_action_failed" \
    "repair_attempted" \
    "$action" \
    "$before_status" \
    "$before_classification" \
    "FAILED" \
    "mode_application_failed" \
    "mode script exited with status $mode_rc"
fi

line ""
line "=== Fresh runtime resolution after repair ==="

load_fresh_runtime_resolution
after_resolution_rc=$?

if [ "$after_resolution_rc" -ne 0 ]; then
  finish \
    1 \
    "FAILED" \
    "post_repair_runtime_resolution_failed" \
    "repair_attempted" \
    "$action" \
    "$before_status" \
    "$before_classification" \
    "FAILED" \
    "runtime_resolution_failed" \
    "repair ran, but post-repair identity resolution failed"
fi

line ""
line "=== Doctor after recovery ==="

run_doctor || true

after_status="$(kv_get "$DOCTOR_STATUS" status)"
after_classification="$(kv_get "$DOCTOR_STATUS" classification)"
after_reason="$(kv_get "$DOCTOR_STATUS" reason)"

after_status="${after_status:-UNKNOWN}"
after_classification="${after_classification:-unknown}"
after_reason="${after_reason:-doctor status unavailable}"

line "after_status=$after_status"
line "after_classification=$after_classification"
line "after_reason=$after_reason"

if [ "$after_status" = "RUNNING" ] \
  && [ "$after_classification" = "healthy" ]
then
  finish \
    0 \
    "RECOVERED" \
    "bounded_recovery_succeeded" \
    "repair_completed" \
    "$action" \
    "$before_status" \
    "$before_classification" \
    "$after_status" \
    "$after_classification" \
    "bounded recovery succeeded using fresh stable-identity runtime resolution"
fi

finish \
  1 \
  "FAILED" \
  "post_repair_validation_failed" \
  "repair_attempted" \
  "$action" \
  "$before_status" \
  "$before_classification" \
  "$after_status" \
  "$after_classification" \
  "repair action completed, but the final doctor state is not healthy"

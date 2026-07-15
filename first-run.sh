#!/usr/bin/env bash
set -u
set -o pipefail

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

usage() {
  cat <<'EOF'
Usage:
  screenstereo-first-run
  screenstereo-first-run --confirmation 'CONFIRM LEFT=<model> RIGHT=<model>' --mode split
  screenstereo-first-run --confirmation 'CONFIRM LEFT=<model> RIGHT=<model>' --mode mirror

Options:
  --confirmation <exact phrase>
  --mode split|mirror
  --help
EOF
}

main() {
  local target_home="${SCREENSTEREO_HOME:-$HOME}"
  local skip_systemd="${SCREENSTEREO_SKIP_SYSTEMD:-0}"
  local confirmation=""
  local selected_mode=""
  local argument

  case "$target_home" in
    /*)
      ;;
    *)
      echo "SCREENSTEREO_HOME must be an absolute path." >&2
      return 64
      ;;
  esac

  if [ "$target_home" = "/" ]; then
    echo "Refusing to use / as SCREENSTEREO_HOME." >&2
    return 64
  fi

  while [ "$#" -gt 0 ]
  do
    argument="$1"

    case "$argument" in
      --confirmation)
        if [ "$#" -lt 2 ]; then
          echo "--confirmation requires a value." >&2
          return 64
        fi

        confirmation="$2"
        shift 2
        ;;
      --mode)
        if [ "$#" -lt 2 ]; then
          echo "--mode requires split or mirror." >&2
          return 64
        fi

        selected_mode="$2"
        shift 2
        ;;
      --help|-h)
        usage
        return 0
        ;;
      *)
        echo "Unknown argument: $argument" >&2
        usage
        return 64
        ;;
    esac
  done

  export HOME="$target_home"

  local setup_script="$HOME/.local/bin/screenstereo_setup.py"
  local map_writer_script="$HOME/.local/bin/screenstereo_write_display_map.py"
  local mode_script="$HOME/.local/bin/hbai_audio_mode.sh"
  local doctor_script="$HOME/.local/bin/hbai_audio_doctor.sh"

  if [ ! -x "$map_writer_script" ]; then
    echo "Required program is missing or not executable: $map_writer_script" >&2
    return 69
  fi

  for required_file in \
    "$setup_script" \
    "$mode_script" \
    "$doctor_script"
  do
    if [ ! -x "$required_file" ]; then
      echo "Required installed program is missing: $required_file" >&2
      return 66
    fi
  done

  echo "=== ScreenStereo hardware mapping ==="

  "$setup_script" show
  local show_status="$?"

  if [ "$show_status" -ne 0 ]; then
    echo "Hardware mapping is not ready for confirmation." >&2
    return "$show_status"
  fi

  if [ -z "$confirmation" ]; then
    if [ ! -t 0 ]; then
      echo "Interactive confirmation requires a terminal." >&2
      return 64
    fi

    echo ""
    read -r -p "Type the exact confirmation phrase shown above: " confirmation
  fi

  "$setup_script" confirm "$confirmation"
  local confirm_status="$?"

  if [ "$confirm_status" -ne 0 ]; then
    echo "Mapping confirmation failed." >&2
    return "$confirm_status"
  fi

  "$map_writer_script"
  local map_write_status="$?"

  if [ "$map_write_status" -ne 0 ]; then
    echo "Durable display-map write failed." >&2
    return "$map_write_status"
  fi

  if [ -z "$selected_mode" ]; then
    if [ ! -t 0 ]; then
      echo "A noninteractive run requires --mode split or --mode mirror." >&2
      return 64
    fi

    echo ""
    read -r -p "Initial mode [split/mirror] (default split): " selected_mode

    if [ -z "$selected_mode" ]; then
      selected_mode="split"
    fi
  fi

  case "$selected_mode" in
    split|mirror)
      ;;
    *)
      echo "Mode must be split or mirror." >&2
      return 64
      ;;
  esac

  "$mode_script" "$selected_mode"
  local mode_status="$?"

  if [ "$mode_status" -ne 0 ]; then
    echo "Initial audio mode selection failed." >&2
    return "$mode_status"
  fi

  if [ "$skip_systemd" != "1" ]; then
    systemctl --user daemon-reload
    local reload_status="$?"

    if [ "$reload_status" -ne 0 ]; then
      echo "systemctl --user daemon-reload failed." >&2
      return "$reload_status"
    fi

    systemctl --user enable --now hbai-audio-mode.service
    local mode_service_status="$?"

    if [ "$mode_service_status" -ne 0 ]; then
      echo "Unable to enable the ScreenStereo mode service." >&2
      return "$mode_service_status"
    fi

    systemctl --user enable --now hbai-audio-indicator.service
    local indicator_service_status="$?"

    if [ "$indicator_service_status" -ne 0 ]; then
      echo "Unable to enable the ScreenStereo indicator service." >&2
      return "$indicator_service_status"
    fi
  fi

  "$doctor_script"
  local doctor_status="$?"

  if [ "$doctor_status" -ne 0 ]; then
    echo "Setup completed, but the explicit doctor check reported a problem." >&2
    return "$doctor_status"
  fi

  echo ""
  echo "SCREENSTEREO_FIRST_RUN=PASS"
  echo "mapping_confirmed=True"
  echo "durable_mapping_written=True"
  echo "selected_mode=$selected_mode"
  echo "doctor_validation=PASS"

  return 0
}

main "$@"
exit $?

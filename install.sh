#!/usr/bin/env bash
set -u
set -o pipefail

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

main() {
  local script_dir
  local target_home
  local skip_systemd
  local run_first_run=0
  local argument
  local missing=()
  local command_name

  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  target_home="${SCREENSTEREO_HOME:-$HOME}"
  skip_systemd="${SCREENSTEREO_SKIP_SYSTEMD:-0}"

  for argument in "$@"
  do
    case "$argument" in
      --no-first-run)
        run_first_run=0
        ;;
      --run-first-run)
        run_first_run=1
        ;;
      --help|-h)
        cat <<'EOF'
Usage:
  ./install.sh [--no-first-run]
  ./install.sh --run-first-run

Environment:
  SCREENSTEREO_HOME=<absolute path>
  SCREENSTEREO_SKIP_SYSTEMD=1
EOF
        return 0
        ;;
      *)
        echo "Unknown argument: $argument" >&2
        return 64
        ;;
    esac
  done

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

  for command_name in \
    bash python3 pactl wpctl xrandr systemctl \
    awk grep sed xargs install mkdir rm cp aplay
  do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      missing+=("$command_name")
    fi
  done

  if [ "${#missing[@]}" -ne 0 ]; then
    echo "Missing required commands: ${missing[*]}" >&2
    return 69
  fi

  local bin_dir="$target_home/.local/bin"
  local unit_dir="$target_home/.config/systemd/user"
  local icon_dir="$target_home/.local/share/hbai-audio/icons"
  local product_dir="$target_home/.local/share/screenstereo-pipewire"
  local manifest="$product_dir/installed-files.txt"

  install -d -m 0755 \
    "$bin_dir" \
    "$unit_dir" \
    "$icon_dir" \
    "$product_dir" \
    "$target_home/.config/hbai-audio" \
    "$target_home/.config/screenstereo-pipewire" \
    "$target_home/.local/state/hbai-audio" \
    "$target_home/.local/state/screenstereo-pipewire"

  local executable

  for executable in \
    screenstereo_display_discover.py \
    screenstereo_audio_discover.py \
    screenstereo_correlate.py \
    screenstereo_setup.py \
    screenstereo_write_display_map.py \
    screenstereo_resolve.py \
    screenstereo_runtime.py \
    hbai_tv_lr_split_refresh.sh \
    hbai_hdmi_all_refresh.sh \
    hbai_audio_mode.sh \
    hbai_audio_doctor.sh \
    hbai_audio_recover.sh \
    hbai_audio_indicator.py
  do
    install -m 0755 \
      "$script_dir/bin/$executable" \
      "$bin_dir/$executable"
  done

  install -m 0755 \
    "$script_dir/install.sh" \
    "$bin_dir/screenstereo-install"

  install -m 0755 \
    "$script_dir/uninstall.sh" \
    "$bin_dir/screenstereo-uninstall"

  install -m 0755 \
    "$script_dir/first-run.sh" \
    "$bin_dir/screenstereo-first-run"

  install -m 0644 \
    "$script_dir/systemd/user/hbai-audio-mode.service" \
    "$unit_dir/hbai-audio-mode.service"

  install -m 0644 \
    "$script_dir/systemd/user/hbai-audio-indicator.service" \
    "$unit_dir/hbai-audio-indicator.service"

  install -m 0644 \
    "$script_dir/share/icons/hbai-audio-running.svg" \
    "$icon_dir/hbai-audio-running.svg"

  install -m 0644 \
    "$script_dir/share/icons/hbai-audio-malfunction.svg" \
    "$icon_dir/hbai-audio-malfunction.svg"

  cat > "$manifest" <<EOF
$bin_dir/screenstereo_display_discover.py
$bin_dir/screenstereo_audio_discover.py
$bin_dir/screenstereo_correlate.py
$bin_dir/screenstereo_setup.py
$bin_dir/screenstereo_write_display_map.py
$bin_dir/screenstereo_resolve.py
$bin_dir/screenstereo_runtime.py
$bin_dir/hbai_tv_lr_split_refresh.sh
$bin_dir/hbai_hdmi_all_refresh.sh
$bin_dir/hbai_audio_mode.sh
$bin_dir/hbai_audio_doctor.sh
$bin_dir/hbai_audio_recover.sh
$bin_dir/hbai_audio_indicator.py
$bin_dir/screenstereo-install
$bin_dir/screenstereo-uninstall
$bin_dir/screenstereo-first-run
$unit_dir/hbai-audio-mode.service
$unit_dir/hbai-audio-indicator.service
$icon_dir/hbai-audio-running.svg
$icon_dir/hbai-audio-malfunction.svg
EOF

  chmod 0644 "$manifest"

  if [ "$skip_systemd" != "1" ]; then
    systemctl --user daemon-reload

    if [ "$?" -ne 0 ]; then
      echo "systemctl --user daemon-reload failed." >&2
      return 70
    fi
  fi

  echo "SCREENSTEREO_INSTALL=PASS"
  echo "target_home=$target_home"
  echo "services_started=False"
  echo "audio_graph_modified=False"
  echo "next_command=$bin_dir/screenstereo-first-run"

  if [ "$run_first_run" -eq 1 ]; then
    "$bin_dir/screenstereo-first-run"
    return "$?"
  fi

  return 0
}

main "$@"
exit $?

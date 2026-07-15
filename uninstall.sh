#!/usr/bin/env bash
set -u
set -o pipefail

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

usage() {
  cat <<'EOF'
Usage:
  screenstereo-uninstall
  screenstereo-uninstall --purge

By default, user mapping, mode configuration, and current state are preserved.
Use --purge to remove ScreenStereo configuration and state.
EOF
}

main() {
  local target_home="${SCREENSTEREO_HOME:-$HOME}"
  local skip_systemd="${SCREENSTEREO_SKIP_SYSTEMD:-0}"
  local purge=0
  local argument

  for argument in "$@"
  do
    case "$argument" in
      --purge)
        purge=1
        ;;
      --help|-h)
        usage
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

  export HOME="$target_home"

  local bin_dir="$HOME/.local/bin"
  local unit_dir="$HOME/.config/systemd/user"
  local icon_dir="$HOME/.local/share/hbai-audio/icons"
  local product_dir="$HOME/.local/share/screenstereo-pipewire"

  if [ "$skip_systemd" != "1" ]; then
    systemctl --user disable --now hbai-audio-indicator.service >/dev/null 2>&1 || true
    systemctl --user disable --now hbai-audio-mode.service >/dev/null 2>&1 || true
    systemctl --user disable --now hbai-hdmi-all.service >/dev/null 2>&1 || true
    systemctl --user disable --now hbai-tv-lr-split.service >/dev/null 2>&1 || true
  fi

  local managed_file

  for managed_file in \
    "$bin_dir/screenstereo_display_discover.py" \
    "$bin_dir/screenstereo_audio_discover.py" \
    "$bin_dir/screenstereo_correlate.py" \
    "$bin_dir/screenstereo_setup.py" \
    "$bin_dir/screenstereo_write_display_map.py" \
    "$bin_dir/screenstereo_resolve.py" \
    "$bin_dir/screenstereo_runtime.py" \
    "$bin_dir/hbai_tv_lr_split_refresh.sh" \
    "$bin_dir/hbai_hdmi_all_refresh.sh" \
    "$bin_dir/hbai_audio_mode.sh" \
    "$bin_dir/hbai_audio_doctor.sh" \
    "$bin_dir/hbai_audio_recover.sh" \
    "$bin_dir/hbai_audio_indicator.py" \
    "$bin_dir/screenstereo-install" \
    "$bin_dir/screenstereo-uninstall" \
    "$bin_dir/screenstereo-first-run" \
    "$unit_dir/hbai-audio-mode.service" \
    "$unit_dir/hbai-audio-indicator.service" \
    "$unit_dir/hbai-hdmi-all.service" \
    "$unit_dir/hbai-tv-lr-split.service" \
    "$icon_dir/hbai-audio-running.svg" \
    "$icon_dir/hbai-audio-malfunction.svg"
  do
    rm -f -- "$managed_file"
  done

  rm -f -- "$product_dir/installed-files.txt"
  rmdir "$product_dir" 2>/dev/null || true
  rmdir "$icon_dir" 2>/dev/null || true

  if [ "$purge" -eq 1 ]; then
    rm -rf -- \
      "$HOME/.config/hbai-audio" \
      "$HOME/.config/screenstereo-pipewire" \
      "$HOME/.local/state/hbai-audio" \
      "$HOME/.local/state/screenstereo-pipewire"
  fi

  if [ "$skip_systemd" != "1" ]; then
    systemctl --user daemon-reload
    local reload_status="$?"

    if [ "$reload_status" -ne 0 ]; then
      echo "Uninstall completed, but systemd daemon-reload failed." >&2
      return "$reload_status"
    fi
  fi

  echo "SCREENSTEREO_UNINSTALL=PASS"
  echo "target_home=$target_home"
  echo "configuration_purged=$([ "$purge" -eq 1 ] && echo True || echo False)"

  return 0
}

main "$@"
exit $?

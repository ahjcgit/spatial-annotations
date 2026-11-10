#!/usr/bin/env bash
# Source this file. Honor explicit toolchain paths; also find this workspace's existing install.
_spatial_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for _spatial_tools in "$_spatial_root/../.toolchain" "$_spatial_root/../../.toolchain"; do
  if [[ -z "${ANDROID_HOME:-}" && -d "$_spatial_tools/android-sdk" ]]; then export ANDROID_HOME="$_spatial_tools/android-sdk"; fi
  if [[ -z "${JAVA_HOME:-}" ]]; then
    for _spatial_jdk in "$_spatial_tools"/zulu17*; do
      if [[ -x "$_spatial_jdk/bin/java" ]]; then export JAVA_HOME="$_spatial_jdk"; break; fi
    done
  fi
done
export PATH="${JAVA_HOME:+$JAVA_HOME/bin:}${ANDROID_HOME:+$ANDROID_HOME/platform-tools:}$PATH"
unset _spatial_root _spatial_tools _spatial_jdk

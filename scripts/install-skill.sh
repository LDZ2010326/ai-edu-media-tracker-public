#!/bin/sh

set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: sh scripts/install-skill.sh <install|uninstall> <claude|codex>" >&2
  exit 2
fi

mode=$1
host=$2
case "$host" in
  claude) skill_parent="${HOME:?HOME is required}/.claude/skills" ;;
  codex) skill_parent="${HOME:?HOME is required}/.codex/skills" ;;
  *) echo "unsupported host: $host" >&2; exit 2 ;;
esac

target="$skill_parent/ai-edu-media-tracker"
marker="$target/.ai-edu-media-tracker-install"
marker_value="ai-edu-media-tracker:v1"

case "$mode" in
  install)
    if [ -e "$target" ] || [ -L "$target" ]; then
      echo "refusing to overwrite existing path: $target" >&2
      exit 1
    fi
    script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    source_dir="$script_dir/../skills/$host"
    if [ ! -f "$source_dir/SKILL.md" ]; then
      echo "skill source is missing: $source_dir/SKILL.md" >&2
      exit 1
    fi
    mkdir -p "$skill_parent"
    cp -R "$source_dir" "$target"
    printf '%s\n' "$marker_value" >"$marker"
    ;;
  uninstall)
    if [ ! -f "$marker" ] || [ "$(sed -n '1p' "$marker")" != "$marker_value" ]; then
      echo "refusing to remove a directory not owned by this installer: $target" >&2
      exit 1
    fi
    if [ ! -f "$target/SKILL.md" ] || ! grep -q '^name: ai-edu-media-tracker$' "$target/SKILL.md"; then
      echo "refusing to remove a directory with an unexpected Skill identity: $target" >&2
      exit 1
    fi
    rm -rf -- "$target"
    ;;
  *) echo "unsupported mode: $mode" >&2; exit 2 ;;
esac

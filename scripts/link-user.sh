#!/bin/sh
# Link tamsu/user/* into ~/.claude, one file at a time.
#   scripts/link-user.sh          link; shows a diff and asks before replacing a real file
#   scripts/link-user.sh --check  report links that are missing or were replaced by a plain file
set -eu

src="$(cd "$(dirname "$0")/../user" && pwd)"
dest="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
mode="${1:-link}"
status=0

for file in $(cd "$src" && find . -type f ! -name '.DS_Store' | sed 's|^\./||'); do
  target="$dest/$file"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$src/$file" ]; then
    [ "$mode" = "--check" ] && echo "ok       $file"
    continue
  fi
  if [ "$mode" = "--check" ]; then
    if [ -e "$target" ]; then echo "NOT LINKED (plain file) $file"; else echo "MISSING  $file"; fi
    status=1
    continue
  fi
  mkdir -p "$(dirname "$target")"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    if cmp -s "$target" "$src/$file"; then
      :
    else
      echo "--- $target will be replaced by a link to $src/$file:"
      diff -u "$target" "$src/$file" || true
      printf "Replace? [y/N] "
      read -r answer || answer=""
      [ "$answer" = "y" ] || { echo "skipped  $file"; continue; }
    fi
  fi
  ln -sfn "$src/$file" "$target"
  echo "linked   $file"
done
exit $status

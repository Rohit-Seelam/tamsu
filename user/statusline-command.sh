#!/bin/sh
input=$(cat)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Format token count: 523  →  "523", 39500 → "39.5K", 1000000 → "1M"
fmt_tokens() {
  awk -v n="$1" 'BEGIN {
    if (n >= 1000000) {
      v = n / 1000000
      if (v == int(v)) printf "%dM", v; else printf "%.1fM", v
    } else if (n >= 1000) {
      v = n / 1000
      if (v == int(v)) printf "%dK", v; else printf "%.1fK", v
    } else {
      printf "%d", n
    }
  }'
}

# Format a unix epoch as "Fri Apr 25 05:50" (macOS -r, Linux -d fallback)
fmt_reset() {
  date -r "$1" "+%a %b %d %H:%M" 2>/dev/null \
    || date -d "@$1" "+%a %b %d %H:%M" 2>/dev/null \
    || echo ""
}

# Append a non-empty segment to $parts, pipe-separated
append() {
  [ -n "$1" ] || return
  if [ -z "$parts" ]; then
    parts="$1"
  else
    parts="$parts | $1"
  fi
}

# ---------------------------------------------------------------------------
# Extract fields
# ---------------------------------------------------------------------------

model=$(echo "$input" | jq -r '.model.display_name // "unknown"')

ctx_size=$(echo "$input" | jq -r '.context_window.context_window_size // empty')
ctx_used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')

# Exact context tokens = sum of current_usage input/cache fields (most accurate)
used_tokens=$(echo "$input" | jq -r '
  (.context_window.current_usage // {}) as $u
  | ( ($u.input_tokens // 0)
    + ($u.cache_read_input_tokens // 0)
    + ($u.cache_creation_input_tokens // 0)
    ) as $total
  | if $total > 0 then $total else empty end
')

# Session cumulative totals (all turns combined)
sess_in=$(echo "$input"  | jq -r '.context_window.total_input_tokens  // empty')
sess_out=$(echo "$input" | jq -r '.context_window.total_output_tokens // empty')

# Rate limits
five_pct=$(echo "$input"   | jq -r '.rate_limits.five_hour.used_percentage // empty')
five_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at      // empty')
week_pct=$(echo "$input"   | jq -r '.rate_limits.seven_day.used_percentage // empty')
week_reset=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at      // empty')

# Session metadata
effort=$(echo "$input"       | jq -r '.effort.level      // empty')
thinking=$(echo "$input"     | jq -r '.thinking.enabled  // empty')
output_style=$(echo "$input" | jq -r '.output_style.name // empty')
vim_mode=$(echo "$input"     | jq -r '.vim.mode          // empty')
sess_name=$(echo "$input"    | jq -r '.session_name      // empty')
wt_name=$(echo "$input"      | jq -r '.worktree.name     // empty')
wt_branch=$(echo "$input"    | jq -r '.worktree.branch   // empty')
orig_branch=$(echo "$input"  | jq -r '.worktree.original_branch // empty')

# ---------------------------------------------------------------------------
# Build output — ordered most-relevant-to-current-work first
# ---------------------------------------------------------------------------

parts=""

# 1. Model
append "$model"

# 2. Context window: used/total (pct%)
if [ -n "$ctx_size" ]; then
  # Fall back to percentage-derived count only if current_usage not yet populated
  if [ -z "$used_tokens" ] && [ -n "$ctx_used_pct" ]; then
    used_tokens=$(awk -v p="$ctx_used_pct" -v s="$ctx_size" \
      'BEGIN { printf "%d", (p/100)*s + 0.5 }')
  fi

  if [ -n "$used_tokens" ]; then
    used_fmt=$(fmt_tokens "$used_tokens")
    size_fmt=$(fmt_tokens "$ctx_size")
    pct_fmt=$(awk -v u="$used_tokens" -v s="$ctx_size" \
      'BEGIN { printf "%.0f", (u/s)*100 }')
    append "${used_fmt}/${size_fmt} (${pct_fmt}%)"
  fi
fi

# 3. 5-hour rolling rate limit
if [ -n "$five_pct" ]; then
  five_fmt=$(printf "%.0f" "$five_pct")
  seg="5h: ${five_fmt}%"
  if [ -n "$five_reset" ]; then
    r=$(fmt_reset "$five_reset")
    [ -n "$r" ] && seg="${seg} (resets $r)"
  fi
  append "$seg"
fi

# 4. 7-day all-models weekly rate limit
if [ -n "$week_pct" ]; then
  week_fmt=$(printf "%.0f" "$week_pct")
  seg="7d: ${week_fmt}%"
  if [ -n "$week_reset" ]; then
    r=$(fmt_reset "$week_reset")
    [ -n "$r" ] && seg="${seg} (resets $r)"
  fi
  append "$seg"
fi

# 5. Session cumulative token totals (in + out)
if [ -n "$sess_in" ] && [ -n "$sess_out" ]; then
  si=$(fmt_tokens "$sess_in")
  so=$(fmt_tokens "$sess_out")
  append "session: ${si} in / ${so} out"
elif [ -n "$sess_in" ]; then
  append "session: $(fmt_tokens "$sess_in") in"
fi

# 6. Effort level (only show when present — it's optional/model-dependent)
if [ -n "$effort" ]; then
  append "effort: $effort"
fi

# 7. Extended thinking (only flag when enabled)
if [ "$thinking" = "true" ]; then
  append "thinking"
fi

# 8. Output style (only when non-default)
if [ -n "$output_style" ] && [ "$output_style" != "default" ]; then
  append "style: $output_style"
fi

# 9. Vim mode (only when vim is active)
if [ -n "$vim_mode" ]; then
  append "vim: $vim_mode"
fi

# 10. Worktree info (only when in a linked worktree session)
if [ -n "$wt_name" ]; then
  if [ -n "$wt_branch" ] && [ -n "$orig_branch" ]; then
    append "worktree: $wt_name (${orig_branch}→${wt_branch})"
  elif [ -n "$wt_branch" ]; then
    append "worktree: $wt_name ($wt_branch)"
  else
    append "worktree: $wt_name"
  fi
fi

# 11. Session name (only when explicitly set via /rename)
if [ -n "$sess_name" ]; then
  append "[$sess_name]"
fi

printf "%s" "$parts"

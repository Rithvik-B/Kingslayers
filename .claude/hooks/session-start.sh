#!/usr/bin/env bash
# SessionStart hook: prints team sync state, decisions and ideas into Claude's context.
# Must never block or fail a session, so every step is best-effort and the script always exits 0.

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" 2>/dev/null || exit 0

echo "## Team sync (from .claude/hooks/session-start.sh)"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Fetch with a time limit where `timeout` exists (not on stock macOS); never prompt for credentials.
  if command -v timeout >/dev/null 2>&1; then
    GIT_TERMINAL_PROMPT=0 timeout 10 git fetch --quiet origin >/dev/null 2>&1
  else
    GIT_TERMINAL_PROMPT=0 git fetch --quiet origin >/dev/null 2>&1
  fi

  branch=$(git branch --show-current 2>/dev/null)
  upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)
  dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')

  if [ -n "$upstream" ]; then
    counts=$(git rev-list --left-right --count "$upstream...HEAD" 2>/dev/null)
    behind=${counts%%[[:space:]]*}
    ahead=${counts##*[[:space:]]}
    echo "- Branch \`$branch\` vs \`$upstream\`: ${behind:-?} behind, ${ahead:-?} ahead, $dirty uncommitted file(s)."
    if [ "${behind:-0}" -gt 0 ] 2>/dev/null; then
      echo "- BEHIND ORIGIN. Tell the user and offer /sync before doing any work. Teammates pushed:"
      git log --format='  - %h %an (%ar): %s' "HEAD..$upstream" 2>/dev/null | head -15
    fi
  else
    echo "- Branch \`$branch\` has no upstream; $dirty uncommitted file(s)."
  fi
fi

echo
echo "## Decisions (docs/decisions/, newest last)"
found=0
for f in docs/decisions/2*.md; do
  [ -f "$f" ] || continue
  found=1
  title=$(sed -n 's/^title:[[:space:]]*//p' "$f" | head -1)
  status=$(sed -n 's/^status:[[:space:]]*//p' "$f" | head -1)
  echo "- [${status:-?}] ${title:-$(basename "$f")} ($f)"
done
[ "$found" -eq 1 ] || echo "- none yet"

echo
echo "## Ideas (docs/ideas/)"
found=0
for f in docs/ideas/*.md; do
  [ -f "$f" ] || continue
  [ "$(basename "$f")" = "README.md" ] && continue
  found=1
  title=$(sed -n 's/^title:[[:space:]]*//p' "$f" | head -1)
  status=$(sed -n 's/^status:[[:space:]]*//p' "$f" | head -1)
  author=$(sed -n 's/^author:[[:space:]]*//p' "$f" | head -1)
  echo "- [${status:-?}] ${title:-$(basename "$f")} by ${author:-?} ($f)"
done
[ "$found" -eq 1 ] || echo "- none yet"

exit 0

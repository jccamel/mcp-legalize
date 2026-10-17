#!/usr/bin/env bash
# Hook UserPromptSubmit: si el repositorio está marcado como "local-only" en
# .ai-policy, bloquea el prompt antes de que llegue a Claude.
#
# Es una segunda barrera. La primera es la función de shell de
# scripts/claude-guard.zsh, que impide incluso arrancar Claude Code en ese repo.

set -uo pipefail

dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Buscar .ai-policy en el proyecto y en sus carpetas superiores.
policy=""
while [[ "$dir" != "/" && -n "$dir" ]]; do
  if [[ -f "$dir/.ai-policy" ]]; then
    policy="$dir/.ai-policy"
    break
  fi
  dir="$(dirname "$dir")"
done

[[ -z "$policy" ]] && exit 0

if grep -Eiq '^[[:space:]]*mode[[:space:]]*:[[:space:]]*local-only[[:space:]]*$' "$policy"; then
  echo "Bloqueado: este repositorio está marcado como 'local-only' en $policy. Usa OpenCode con el modelo local para trabajar en él." >&2
  exit 2
fi

exit 0

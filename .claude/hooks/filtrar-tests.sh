#!/usr/bin/env bash
# Hook PreToolUse (Bash): envuelve los comandos de test y build para que Claude
# reciba solo los fallos y un resumen, en lugar de miles de líneas de salida.
# El log completo se guarda en .claude/logs/ por si hace falta consultarlo.
#
# Solo actúa sobre comandos SIMPLES (sin ; & | ` $( < > ni saltos de línea),
# para no aprobar nunca una cadena de comandos que empiece por un test.

set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

passthrough() { echo '{}'; exit 0; }

[[ -z "$cmd" ]] && passthrough

# Comandos compuestos, redirecciones o sustituciones: no tocar.
case "$cmd" in
  *';'*|*'&'*|*'|'*|*'`'*|*'$('*|*'<'*|*'>'*|*$'\n'*) passthrough ;;
esac

# Comandos de test/build reconocidos (ajústalos a tu stack).
pattern='^(npm (run )?test|npm run (build|lint)|pnpm (run )?test|pnpm (run )?build|yarn (run )?test|yarn (run )?build|pytest|(\.venv/bin/)?python3? -m pytest|(\.venv/bin/)?python3? scripts/update_index\.py --self-test|uv run pytest|go (test|build|vet)|cargo (test|build|clippy)|mvn (test|verify|package)|gradle(w)? (test|build)|\./gradlew (test|build)|make (test|check|build))( |$)'

if [[ ! "$cmd" =~ $pattern ]]; then
  passthrough
fi

runner="${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/ejecutar-filtrado.sh"
new_cmd="$(printf '%q %q' "$runner" "$cmd")"

jq -n --arg c "$new_cmd" --argjson orig "$(printf '%s' "$input" | jq '.tool_input')" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "allow",
    permissionDecisionReason: "Comando de test/build envuelto para filtrar la salida",
    updatedInput: ($orig + {command: $c})
  }
}'

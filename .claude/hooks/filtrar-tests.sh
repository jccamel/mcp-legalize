#!/usr/bin/env bash
# Hook PreToolUse (Bash): envuelve los comandos de test y build para que Claude
# reciba solo los fallos y un resumen, en lugar de miles de líneas de salida.
# El log completo se guarda en .claude/logs/ por si hace falta consultarlo.
#
# Solo aprueba las ejecuciones de tests de ESTE proyecto, con argumentos de una
# lista blanca (ver comando_de_test.py). Cualquier otra orden sigue el flujo
# normal de permisos: no se deniega, pero tampoco se aprueba en nombre del
# usuario.

set -euo pipefail

input="$(cat)"
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"

passthrough() { echo '{}'; exit 0; }

[[ -z "$cmd" ]] && passthrough

# Comandos compuestos, redirecciones, sustituciones o expansiones: no tocar.
# El validador ya los rechazaría; esto es una segunda barrera barata.
case "$cmd" in
  *';'*|*'&'*|*'|'*|*'`'*|*'$'*|*'<'*|*'>'*|*$'\n'*|*$'\r'*) passthrough ;;
esac

hooks="${CLAUDE_PROJECT_DIR:-.}/.claude/hooks"
# -I: el validador no importa nada del directorio de trabajo.
args_json="$(python3 -I "$hooks/comando_de_test.py" "$cmd")" || passthrough

# El ejecutor recibe los argumentos ya separados y los ejecuta tal cual, sin
# volver a pasar por un shell que pudiera expandirlos de otra forma.
new_cmd="$(printf '%q' "$hooks/ejecutar-filtrado.sh")"
while IFS= read -r arg; do
  new_cmd+=" $(printf '%q' "$arg")"
done < <(printf '%s' "$args_json" | jq -r '.[]')

jq -n --arg c "$new_cmd" --argjson orig "$(printf '%s' "$input" | jq '.tool_input')" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "allow",
    permissionDecisionReason: "Comando de test/build envuelto para filtrar la salida",
    updatedInput: ($orig + {command: $c})
  }
}'

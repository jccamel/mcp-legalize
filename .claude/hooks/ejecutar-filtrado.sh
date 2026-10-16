#!/usr/bin/env bash
# Ejecuta un comando de test/build, guarda la salida completa en .claude/logs/
# y muestra solo lo útil: líneas de error con algo de contexto y el resumen final.
# Conserva el código de salida del comando original.

set -uo pipefail

cmd="$1"
log_dir="${CLAUDE_PROJECT_DIR:-.}/.claude/logs"
mkdir -p "$log_dir"
log_file="$log_dir/$(date +%Y%m%d-%H%M%S)-$(printf '%s' "$cmd" | tr -c 'A-Za-z0-9' '_' | cut -c1-40).log"

bash -c "$cmd" >"$log_file" 2>&1
rc=$?

total_lines=$(wc -l <"$log_file" | tr -d ' ')

echo "\$ $cmd"
echo "Código de salida: $rc · Salida completa: $total_lines líneas en ${log_file#"${CLAUDE_PROJECT_DIR:-.}"/}"

if [[ $rc -ne 0 ]]; then
  echo "--- Fallos (máx. 120 líneas) ---"
  grep -n -E -i -B2 -A5 '(^|[^a-z])(fail(ed|ure)?|error|exception|traceback|panic|assert(ion)?error|✗|✘)' "$log_file" \
    | head -n 120
fi

echo "--- Final de la salida ---"
tail -n 8 "$log_file"

# Mantener solo los 30 logs más recientes.
ls -1t "$log_dir"/*.log 2>/dev/null | tail -n +31 | while IFS= read -r old; do rm -f "$old"; done

exit $rc

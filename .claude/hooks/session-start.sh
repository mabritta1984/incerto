#!/bin/bash
# copiado de mabritta1984/Lastro@1676115 .claude/hooks/session-start.sh
# SessionStart do Incerto: na sessão do Claude Code na web, instala as dependências pinadas
# e roda o verificador frio, para que desenvolver aqui já comece verificado.
# Idempotente; não bloqueia a sessão quando uma prova reprova (a tabela fica no contexto).
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ"
export PYTHONDONTWRITEBYTECODE=1

# Imagem Debian: pacote do sistema (ex.: pyparsing) não desinstala por pip — sobrepõe com --ignore-installed.
PIP="python3 -m pip install --quiet --disable-pip-version-check -r build/requisitos.txt"
$PIP 2>/dev/null || $PIP --break-system-packages --ignore-installed

python3 -B build/verificar_incerto.py \
  || echo "verificar_incerto.py reprovou (tabela acima) — a sessão segue; corrija antes de commitar."

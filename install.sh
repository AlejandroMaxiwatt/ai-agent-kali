#!/usr/bin/env bash
# ============================================================
#   MAXIWATT AGENT · One-line Installer
#   Agente de IA local para pentesting ofensivo en Kali Linux
# ============================================================
#
#   Instalación (usuario final):
#       curl -fsSL https://raw.githubusercontent.com/AlejandroMaxiwatt/ai-agent-kali/main/install.sh | bash
#
#   o con wget:
#       wget -qO- https://raw.githubusercontent.com/AlejandroMaxiwatt/ai-agent-kali/main/install.sh | bash
#
#   El script:
#     1. Comprueba dependencias del sistema (Python 3.11+, venv, pip, git/curl).
#     2. Lanza un asistente de configuración interactivo (LM Studio, modelo, API keys, ...).
#     3. Descarga el proyecto desde GitHub al directorio elegido.
#     4. Crea las carpetas de trabajo (reports/, scans/, evidence/, ...) limpias.
#     5. Crea el venv, instala dependencias Python.
#     6. Parchea agent.py con las preferencias del usuario.
#     7. Genera .env con las API keys.
#     8. Instala el launcher `maxiwatt` en ~/.local/bin.
#
# ============================================================
#   CONFIG DEL MANTENEDOR · edita estas dos líneas antes de publicar.
# ============================================================
REPO="${MAXIWATT_REPO:-AlejandroMaxiwatt/ai-agent-kali}"
BRANCH="${MAXIWATT_BRANCH:-main}"
# Para test local SIN descarga remota:
#   INSTALL_FROM_LOCAL=/ruta/al/proyecto bash install.sh
LOCAL_SRC="${INSTALL_FROM_LOCAL:-}"
# ============================================================

set -euo pipefail

# Si nos están invocando vía `curl ... | bash`, stdin es el pipe del curl
# (no es tty) y el wizard no podría leer respuestas del usuario. Reabrimos
# stdin desde /dev/tty para que `read` funcione siempre. Si /dev/tty no es
# accesible (e.g. test con heredoc, contenedor sin tty), confiamos en el
# stdin existente. Probamos primero en subshell para no abortar si falla.
if [[ ! -t 0 ]]; then
    if (exec 0</dev/tty) 2>/dev/null; then
        exec </dev/tty
    fi
fi

# ────────────────────────────────────────────────────────────
# Colores y helpers
# ────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'; C_MAGENTA=$'\033[35m'; C_CYAN=$'\033[36m'
    C_ORANGE=$'\033[38;5;208m'
else
    C_RESET=""; C_BOLD=""; C_DIM=""; C_RED=""; C_GREEN=""
    C_YELLOW=""; C_BLUE=""; C_MAGENTA=""; C_CYAN=""; C_ORANGE=""
fi

log()    { printf '%s[*]%s %s\n' "$C_CYAN"   "$C_RESET" "$*"; }
ok()     { printf '%s[+]%s %s\n' "$C_GREEN"  "$C_RESET" "$*"; }
warn()   { printf '%s[!]%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
err()    { printf '%s[x]%s %s\n' "$C_RED"    "$C_RESET" "$*" >&2; }
ask()    { printf '%s[?]%s %s' "$C_MAGENTA" "$C_RESET" "$*"; }
section(){ printf '\n%s%s═══ %s ═══%s\n' "$C_BOLD" "$C_ORANGE" "$*" "$C_RESET"; }
die()    { err "$*"; exit 1; }

ask_default() {
    local prompt="$1" def="$2" var="$3" answer
    ask "${prompt} ${C_DIM}[${def}]${C_RESET}: "
    IFS= read -r answer || answer=""
    [[ -z "$answer" ]] && answer="$def"
    printf -v "$var" '%s' "$answer"
}

ask_yesno() {
    local prompt="$1" def="$2" var="$3" answer hint
    if [[ "$def" == "y" ]]; then hint="Y/n"; else hint="y/N"; fi
    while true; do
        ask "${prompt} ${C_DIM}[${hint}]${C_RESET}: "
        IFS= read -r answer || answer=""
        answer="${answer:-$def}"
        case "${answer,,}" in
            y|yes|s|si|sí) printf -v "$var" 'y'; return 0 ;;
            n|no)          printf -v "$var" 'n'; return 0 ;;
            *) warn "Responde y/n." ;;
        esac
    done
}

ask_choice() {
    local prompt="$1" opts="$2" def="$3" var="$4" answer
    while true; do
        ask "${prompt} ${C_DIM}(${opts// /|}) [${def}]${C_RESET}: "
        IFS= read -r answer || answer=""
        answer="${answer:-$def}"
        for o in $opts; do
            if [[ "$answer" == "$o" ]]; then
                printf -v "$var" '%s' "$answer"; return 0
            fi
        done
        warn "Opción no válida. Elige una de: $opts"
    done
}

# ────────────────────────────────────────────────────────────
# Banner
# ────────────────────────────────────────────────────────────
banner() {
    cat <<EOF

${C_ORANGE}${C_BOLD}
  ███╗   ███╗ █████╗ ██╗  ██╗██╗██╗    ██╗ █████╗ ████████╗████████╗
  ████╗ ████║██╔══██╗╚██╗██╔╝██║██║    ██║██╔══██╗╚══██╔══╝╚══██╔══╝
  ██╔████╔██║███████║ ╚███╔╝ ██║██║ █╗ ██║███████║   ██║      ██║
  ██║╚██╔╝██║██╔══██║ ██╔██╗ ██║██║███╗██║██╔══██║   ██║      ██║
  ██║ ╚═╝ ██║██║  ██║██╔╝ ██╗██║╚███╔███╔╝██║  ██║   ██║      ██║
  ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝      ╚═╝
${C_RESET}${C_CYAN}                A G E N T   ·   I N S T A L L E R${C_RESET}
${C_DIM}        Offensive Security Assistant · Local LLM · Kali Linux${C_RESET}

EOF
}

# ────────────────────────────────────────────────────────────
# Pre-flight
# ────────────────────────────────────────────────────────────
preflight() {
    section "Comprobando sistema"

    [[ "$(uname -s)" == "Linux" ]] || die "Solo soportado en Linux."
    ok "Sistema operativo: Linux"

    if command -v apt-get >/dev/null 2>&1; then
        PKG_MGR="apt"; ok "Gestor de paquetes: apt (Debian/Kali/Ubuntu)"
    elif command -v pacman >/dev/null 2>&1; then
        PKG_MGR="pacman"; warn "Detectado pacman. El auto-install de herramientas del agente asume apt; instala las herramientas a mano."
    else
        PKG_MGR="none"; warn "No detecto apt ni pacman. Instala las herramientas (nmap, ffuf, etc.) a mano."
    fi

    command -v python3 >/dev/null 2>&1 \
        || die "No se encuentra python3. En Kali: sudo apt install python3 python3-venv python3-pip"
    local py_ver py_major py_minor
    py_ver="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    py_major="${py_ver%.*}"; py_minor="${py_ver#*.}"
    if (( py_major < 3 )) || { (( py_major == 3 )) && (( py_minor < 11 )); }; then
        die "Python 3.11+ requerido. Detectado: $py_ver"
    fi
    ok "Python: $py_ver"

    python3 -c 'import venv' >/dev/null 2>&1 \
        || die "Falta python3-venv. En Kali: sudo apt install python3-venv"
    ok "python3-venv: disponible"

    python3 -m pip --version >/dev/null 2>&1 \
        || die "Falta pip. En Kali: sudo apt install python3-pip"
    ok "pip: disponible"

    # Necesitamos git o curl/wget para descargar el proyecto.
    if [[ -n "$LOCAL_SRC" ]]; then
        [[ -d "$LOCAL_SRC" ]] || die "INSTALL_FROM_LOCAL apunta a una ruta que no existe: $LOCAL_SRC"
        ok "Modo local: usando $LOCAL_SRC (no se descarga nada)"
        DOWNLOADER="local"
    elif command -v git >/dev/null 2>&1; then
        DOWNLOADER="git"; ok "Descargador: git (clone --depth 1)"
    elif command -v curl >/dev/null 2>&1 && command -v tar >/dev/null 2>&1; then
        DOWNLOADER="curl"; ok "Descargador: curl + tar (tarball)"
    elif command -v wget >/dev/null 2>&1 && command -v tar >/dev/null 2>&1; then
        DOWNLOADER="wget"; ok "Descargador: wget + tar (tarball)"
    else
        die "Necesito git, curl o wget para descargar el proyecto."
    fi

    command -v rsync >/dev/null 2>&1 && HAS_RSYNC=1 || HAS_RSYNC=0
}

# ────────────────────────────────────────────────────────────
# Wizard de configuración
# ────────────────────────────────────────────────────────────
wizard() {
    section "Configuración"
    printf "${C_DIM}Pulsa ENTER para aceptar el valor por defecto entre corchetes.${C_RESET}\n\n"

    ask_default "Directorio de instalación" "$HOME/ai-agent-kali" INSTALL_DIR
    INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

    echo
    log "Backend del LLM (LM Studio expone una API compatible OpenAI):"
    ask_default "  URL base de LM Studio" "http://127.0.0.1:1234/v1" CFG_LMSTUDIO_URL
    ask_default "  Modelo por defecto (fallback si LM Studio no expone ninguno)" "qwen/qwen3.6-27b" CFG_MODEL

    echo
    log "Comportamiento del agente:"
    ask_yesno  "  ¿Auto-ejecutar comandos clasificados como SAFE sin confirmación?" "y" CFG_AUTOEXEC_YN
    if [[ "$CFG_AUTOEXEC_YN" == "y" ]]; then CFG_AUTOEXEC="True"; else CFG_AUTOEXEC="False"; fi
    ask_choice "  Modo proxy para herramientas de red" "proxychains torify off" "proxychains" CFG_PROXY

    echo
    log "Herramientas opcionales del sistema (mejoran el render del splash):"
    if [[ "$PKG_MGR" == "apt" ]]; then
        ask_yesno "  ¿Instalar chafa + kitty con apt? (necesita sudo)" "n" CFG_INSTALL_EXTRAS
    else
        CFG_INSTALL_EXTRAS="n"
        warn "  Sin apt; salta la instalación de chafa/kitty."
    fi

    echo
    log "API keys (opcional · pulsa ENTER para omitir cualquiera):"
    ask_default "  SHODAN_API_KEY"          "" CFG_SHODAN
    ask_default "  CENSYS_API_ID"           "" CFG_CENSYS_ID
    ask_default "  CENSYS_API_SECRET"       "" CFG_CENSYS_SECRET
    ask_default "  CENSYS_API_TOKEN"        "" CFG_CENSYS_TOKEN
    ask_default "  VIRUSTOTAL_API_KEY"      "" CFG_VT
    ask_default "  SECURITYTRAILS_API_KEY"  "" CFG_ST
    ask_default "  CHAOS_API_KEY"           "" CFG_CHAOS
    ask_default "  GITHUB_TOKEN"            "" CFG_GH
    ask_default "  HUNTERIO_API_KEY"        "" CFG_HUNTER
    ask_default "  WPSCAN_API_TOKEN"        "" CFG_WPSCAN
    ask_default "  HIBP_API_KEY"            "" CFG_HIBP

    echo
    section "Resumen"
    cat <<EOF
  ${C_BOLD}Origen${C_RESET}         : $( [[ -n "$LOCAL_SRC" ]] && echo "local ($LOCAL_SRC)" || echo "github.com/${REPO}@${BRANCH}" )
  ${C_BOLD}Directorio${C_RESET}     : $INSTALL_DIR
  ${C_BOLD}LM Studio URL${C_RESET}  : $CFG_LMSTUDIO_URL
  ${C_BOLD}Modelo fallback${C_RESET}: $CFG_MODEL
  ${C_BOLD}AUTO_EXECUTE${C_RESET}   : $CFG_AUTOEXEC
  ${C_BOLD}PROXY_MODE${C_RESET}     : $CFG_PROXY
  ${C_BOLD}Instalar extras${C_RESET}: $([[ "$CFG_INSTALL_EXTRAS" == "y" ]] && echo "sí (chafa, kitty)" || echo "no")
  ${C_BOLD}API keys${C_RESET}       : $(_count_apikeys) configuradas

EOF
    ask_yesno "¿Proceder con la instalación?" "y" CONFIRM
    [[ "$CONFIRM" == "y" ]] || die "Instalación cancelada por el usuario."
}

_count_apikeys() {
    local n=0 v
    for v in "$CFG_SHODAN" "$CFG_CENSYS_ID" "$CFG_CENSYS_SECRET" "$CFG_CENSYS_TOKEN" \
             "$CFG_VT" "$CFG_ST" "$CFG_CHAOS" "$CFG_GH" "$CFG_HUNTER" \
             "$CFG_WPSCAN" "$CFG_HIBP"; do
        [[ -n "$v" ]] && ((n++)) || true
    done
    echo "$n"
}

# ────────────────────────────────────────────────────────────
# Descarga del proyecto
# ────────────────────────────────────────────────────────────
download_project() {
    section "Descargando proyecto"

    if [[ -d "$INSTALL_DIR" ]] && [[ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]]; then
        warn "El directorio $INSTALL_DIR ya existe y no está vacío."
        ask_yesno "  ¿Continuar y sobreescribir? (tus datos en reports/scans/evidence/logs/memory/targets/ se respetarán)" "n" OVR
        [[ "$OVR" == "y" ]] || die "Instalación cancelada."
    fi
    mkdir -p "$INSTALL_DIR"

    local tmpdir
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' RETURN

    case "$DOWNLOADER" in
        local)
            log "Copiando desde $LOCAL_SRC..."
            cp -a "$LOCAL_SRC/." "$tmpdir/"
            ;;
        git)
            log "Clonando github.com/${REPO} (rama ${BRANCH})..."
            git clone --quiet --depth 1 --branch "$BRANCH" \
                "https://github.com/${REPO}.git" "$tmpdir/repo" \
                || die "git clone falló. Revisa REPO/BRANCH o tu conexión."
            cp -a "$tmpdir/repo/." "$tmpdir/"
            rm -rf "$tmpdir/repo" "$tmpdir/.git"
            ;;
        curl|wget)
            local url="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"
            log "Descargando tarball de ${url}..."
            if [[ "$DOWNLOADER" == "curl" ]]; then
                curl -fsSL "$url" | tar -xz -C "$tmpdir" --strip-components=1 \
                    || die "Descarga/extracción falló."
            else
                wget -qO- "$url" | tar -xz -C "$tmpdir" --strip-components=1 \
                    || die "Descarga/extracción falló."
            fi
            ;;
    esac
    ok "Proyecto descargado"

    # Copia a INSTALL_DIR excluyendo datos sensibles / runtime.
    log "Instalando archivos en $INSTALL_DIR..."
    local excludes=(
        --exclude='venv/'           --exclude='.venv/'
        --exclude='__pycache__/'    --exclude='*.pyc'
        --exclude='.env'            --exclude='.env.local' --exclude='.env.*.local'
        --exclude='privkey.pem'     --exclude='*.pem'
        --exclude='agent_old.py'    --exclude='theharvester_*'
        --exclude='reports/'        --exclude='scans/'
        --exclude='evidence/'       --exclude='logs/'
        --exclude='memory/sessions/' --exclude='memory/subagents/' --exclude='memory/lessons/'
        --exclude='targets/*/'
        --exclude='.git/'           --exclude='.vscode/' --exclude='.idea/'
        --exclude='install.sh'
    )
    if (( HAS_RSYNC )); then
        rsync -a "${excludes[@]}" "$tmpdir/" "$INSTALL_DIR/"
    else
        # Fallback: cp + limpieza manual.
        cp -a "$tmpdir/." "$INSTALL_DIR/"
        rm -rf \
            "$INSTALL_DIR/venv" "$INSTALL_DIR/.venv" \
            "$INSTALL_DIR/reports" "$INSTALL_DIR/scans" \
            "$INSTALL_DIR/evidence" "$INSTALL_DIR/logs" \
            "$INSTALL_DIR/memory/sessions" "$INSTALL_DIR/memory/subagents" \
            "$INSTALL_DIR/memory/lessons" \
            "$INSTALL_DIR/.git" "$INSTALL_DIR/.vscode" "$INSTALL_DIR/.idea"
        find "$INSTALL_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +
        find "$INSTALL_DIR" -type f -name '*.pyc' -delete
        rm -f "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.local" \
              "$INSTALL_DIR/privkey.pem" "$INSTALL_DIR/agent_old.py" \
              "$INSTALL_DIR/install.sh"
        find "$INSTALL_DIR" -maxdepth 1 -name 'theharvester_*' -delete
        if [[ -d "$INSTALL_DIR/targets" ]]; then
            find "$INSTALL_DIR/targets" -mindepth 1 -maxdepth 1 \
                ! -name 'README.md' -exec rm -rf {} +
        fi
    fi
    ok "Archivos instalados (skills, hooks, plugins, tools_master, assets incluidos)"

    # Carpetas de trabajo VACÍAS
    mkdir -p \
        "$INSTALL_DIR/reports" "$INSTALL_DIR/scans" \
        "$INSTALL_DIR/evidence" "$INSTALL_DIR/logs" \
        "$INSTALL_DIR/memory/sessions" "$INSTALL_DIR/memory/subagents" \
        "$INSTALL_DIR/memory/lessons" "$INSTALL_DIR/targets"
    ok "Carpetas de trabajo creadas vacías (reports, scans, evidence, logs, memory/, targets)"
}

# ────────────────────────────────────────────────────────────
# Patch de constantes en agent.py
# ────────────────────────────────────────────────────────────
patch_agent_py() {
    section "Aplicando configuración a agent.py"

    local agent="$INSTALL_DIR/agent.py"
    [[ -f "$agent" ]] || die "No encuentro $agent (¿la descarga falló?)."

    python3 - "$agent" \
        "$CFG_LMSTUDIO_URL" "$CFG_MODEL" "$INSTALL_DIR" \
        "$CFG_AUTOEXEC" "$CFG_PROXY" <<'PYEOF'
import re, sys, pathlib
path, url, model, workspace, autoexec, proxy = sys.argv[1:7]
src = pathlib.Path(path).read_text(encoding="utf-8")

def replace_assign(text, var, new_value_literal):
    pattern = re.compile(rf"^(\s*){re.escape(var)}\s*=\s*.*$", re.MULTILINE)
    return pattern.sub(lambda m: f"{m.group(1)}{var} = {new_value_literal}", text, count=1)

src = replace_assign(src, "LMSTUDIO_BASE_URL",   repr(url))
src = replace_assign(src, "MODEL_NAME_FALLBACK", repr(model))
src = replace_assign(src, "AUTO_EXECUTE",        autoexec)
src = replace_assign(src, "PROXY_MODE",          repr(proxy))

default_ws = pathlib.Path("~/ai-agent-kali").expanduser().as_posix()
if pathlib.Path(workspace).as_posix() != default_ws:
    src = replace_assign(src, "WORKSPACE",
                         f'os.path.expanduser({repr(workspace)})')

pathlib.Path(path).write_text(src, encoding="utf-8")
PYEOF
    ok "agent.py parcheado (LM Studio URL, modelo, AUTO_EXECUTE, PROXY_MODE)"
}

# ────────────────────────────────────────────────────────────
# .env
# ────────────────────────────────────────────────────────────
write_env() {
    section "Generando .env"
    local env_file="$INSTALL_DIR/.env"
    cat > "$env_file" <<EOF
# Generado por install.sh el $(date -Iseconds)
# Edita libremente. Las claves vacías se ignoran.

# ── Shodan ───────────────────────────────────────────────────
SHODAN_API_KEY=${CFG_SHODAN}

# ── Censys ───────────────────────────────────────────────────
CENSYS_API_ID=${CFG_CENSYS_ID}
CENSYS_API_SECRET=${CFG_CENSYS_SECRET}
CENSYS_API_TOKEN=${CFG_CENSYS_TOKEN}

# ── Otras APIs de recon ──────────────────────────────────────
VIRUSTOTAL_API_KEY=${CFG_VT}
SECURITYTRAILS_API_KEY=${CFG_ST}
CHAOS_API_KEY=${CFG_CHAOS}
GITHUB_TOKEN=${CFG_GH}
HUNTERIO_API_KEY=${CFG_HUNTER}

# ── WPScan ───────────────────────────────────────────────────
WPSCAN_API_TOKEN=${CFG_WPSCAN}

# ── Have I Been Pwned ────────────────────────────────────────
HIBP_API_KEY=${CFG_HIBP}
EOF
    chmod 600 "$env_file"
    ok ".env creado (chmod 600)"
}

# ────────────────────────────────────────────────────────────
# venv + dependencias Python
# ────────────────────────────────────────────────────────────
setup_venv() {
    section "Creando entorno virtual e instalando dependencias"
    local venv="$INSTALL_DIR/venv"
    if [[ -d "$venv" ]]; then
        warn "venv ya existe en $venv, lo reutilizo."
    else
        python3 -m venv "$venv"
        ok "venv creado en $venv"
    fi

    local req="$INSTALL_DIR/requirements.txt"
    if [[ ! -f "$req" ]]; then
        cat > "$req" <<'EOF'
openai>=2.36.0
rich>=15.0.0
pyfiglet>=1.0.4
requests>=2.33.0
python-dotenv>=1.2.0
EOF
        log "requirements.txt no estaba, lo he generado."
    fi

    log "Instalando paquetes Python..."
    "$venv/bin/pip" install --quiet --upgrade pip
    "$venv/bin/pip" install --quiet -r "$req"
    ok "Dependencias instaladas: $(awk '{print $1}' "$req" | tr '\n' ' ')"
}

# ────────────────────────────────────────────────────────────
# Extras del sistema
# ────────────────────────────────────────────────────────────
install_system_extras() {
    [[ "$CFG_INSTALL_EXTRAS" == "y" ]] || return 0
    section "Instalando extras del sistema (chafa, kitty)"
    log "Vas a necesitar sudo..."
    sudo apt-get update -qq
    sudo apt-get install -y chafa kitty || warn "Algún paquete falló; continúo."
    ok "Extras instalados (los que se hayan podido)"
}

# ────────────────────────────────────────────────────────────
# Launcher
# ────────────────────────────────────────────────────────────
install_launcher() {
    section "Instalando launcher 'maxiwatt'"
    local bindir="$HOME/.local/bin"
    local launcher="$bindir/maxiwatt"
    mkdir -p "$bindir"

    cat > "$launcher" <<EOF
#!/usr/bin/env bash
# MAXIWATT AGENT launcher (generado por install.sh)
WORKSPACE="$INSTALL_DIR"
cd "\$WORKSPACE" || { echo "No puedo cd a \$WORKSPACE"; exit 1; }
exec "\$WORKSPACE/venv/bin/python" "\$WORKSPACE/agent.py" "\$@"
EOF
    chmod +x "$launcher"
    ok "Launcher creado: $launcher"

    case ":$PATH:" in
        *":$bindir:"*) ok "$bindir ya está en tu PATH" ;;
        *)
            warn "$bindir NO está en tu PATH."
            local shellrc=""
            case "${SHELL##*/}" in
                zsh)  shellrc="$HOME/.zshrc" ;;
                bash) shellrc="$HOME/.bashrc" ;;
                fish) shellrc="$HOME/.config/fish/config.fish" ;;
            esac
            if [[ -n "$shellrc" ]]; then
                ask_yesno "  ¿Añadir 'export PATH=\"\$HOME/.local/bin:\$PATH\"' a $shellrc?" "y" ADDPATH
                if [[ "$ADDPATH" == "y" ]]; then
                    if [[ "$shellrc" == *fish* ]]; then
                        mkdir -p "$(dirname "$shellrc")"
                        echo 'set -gx PATH $HOME/.local/bin $PATH' >> "$shellrc"
                    else
                        printf '\n# Añadido por MAXIWATT AGENT installer\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$shellrc"
                    fi
                    ok "PATH añadido a $shellrc (abre una shell nueva o ejecuta: source $shellrc)"
                fi
            fi
            ;;
    esac
}

# ────────────────────────────────────────────────────────────
# Mensaje final
# ────────────────────────────────────────────────────────────
final_message() {
    section "Instalación completada"
    cat <<EOF

  ${C_GREEN}${C_BOLD}MAXIWATT AGENT instalado correctamente${C_RESET}

  ${C_BOLD}Para arrancar:${C_RESET}
      ${C_CYAN}maxiwatt${C_RESET}                  ${C_DIM}# si .local/bin está en tu PATH${C_RESET}
      ${C_CYAN}$INSTALL_DIR/venv/bin/python $INSTALL_DIR/agent.py${C_RESET}

  ${C_BOLD}Antes del primer arranque:${C_RESET}
    • Asegúrate de que LM Studio está corriendo y exponiendo la API en:
      ${C_CYAN}$CFG_LMSTUDIO_URL${C_RESET}
    • Carga un modelo (recomendado: context window ≥ 32k tokens).
    • Tor (si PROXY_MODE=proxychains): ${C_CYAN}sudo systemctl start tor${C_RESET}

  ${C_BOLD}Estructura instalada:${C_RESET}
      $INSTALL_DIR/
      ├── agent.py            ${C_DIM}(parcheado con tu config)${C_RESET}
      ├── skills/             ${C_DIM}(intactas)${C_RESET}
      ├── hooks/  plugins/  tools_master/  assets/   ${C_DIM}(intactos)${C_RESET}
      ├── memory/             ${C_DIM}(vacía: sessions, subagents, lessons)${C_RESET}
      ├── targets/            ${C_DIM}(vacía, solo README)${C_RESET}
      ├── reports/  scans/  evidence/  logs/   ${C_DIM}(vacías)${C_RESET}
      ├── .env                ${C_DIM}(tus API keys, chmod 600)${C_RESET}
      └── venv/               ${C_DIM}(deps Python)${C_RESET}

  ${C_BOLD}Reconfigurar más tarde:${C_RESET}
    • URL/modelo: edita las primeras líneas de ${C_CYAN}agent.py${C_RESET}.
    • API keys:   edita ${C_CYAN}$INSTALL_DIR/.env${C_RESET}.

  ${C_DIM}Happy hacking — y solo dentro del alcance autorizado.${C_RESET}

EOF
}

# ────────────────────────────────────────────────────────────
# main
# ────────────────────────────────────────────────────────────
banner
preflight
wizard
download_project
patch_agent_py
write_env
setup_venv
install_system_extras
install_launcher
final_message

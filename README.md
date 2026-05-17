# MAXIWATT AGENT

Agente de IA local para pentesting ofensivo en Kali Linux. Conecta con un LLM expuesto por **LM Studio**, ejecuta comandos en la máquina anfitriona, mantiene contexto entre sesiones y puede orquestar **mini-agentes autónomos** que trabajan en paralelo contra un mismo objetivo.

```
                MAXIWATT  ·  AGENT
       Offensive Security Assistant  •  Local LLM  •  Kali Linux
```

---

## Índice

- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Cómo arrancar](#cómo-arrancar)
- [Flujo típico de uso](#flujo-típico-de-uso)
- [Comandos del agente](#comandos-del-agente)
  - [Barra de contexto](#barra-de-contexto)
  - [Generales](#generales)
  - [Skills](#skills)
  - [Targets](#targets-contexto-del-objetivo)
  - [Subagentes autónomos](#subagentes-autónomos)
  - [Goal-driven orchestration](#goal-driven-orchestration)
  - [Sesiones](#sesiones)
  - [Lecciones (memoria persistente)](#lecciones-memoria-persistente)
  - [Sudo, timeout, proxy](#sudo-timeout-proxy)
- [Clasificación de comandos y AUTO_EXECUTE](#clasificación-de-comandos-y-auto_execute)
- [Salvaguardas del agente](#salvaguardas-del-agente)
- [Skills disponibles](#skills-disponibles)
- [Herramientas conocidas](#herramientas-conocidas)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Solución de problemas](#solución-de-problemas)

---

## Requisitos

- **Kali Linux** (o cualquier distro Linux moderna con Python 3.11+).
- **Python 3.11+** con venv.
- **LM Studio** corriendo en local o LAN con un modelo cargado y la API expuesta (por defecto `http://127.0.0.1:1234/v1`). Modelo recomendado: cualquiera con context window ≥ 32k tokens (Qwen 2.5/3.x 14B-32B, Llama 3.1/3.3 70B, etc.).
- **chafa** (render del emblema): `sudo apt install chafa`
- **kitty terminal** (recomendado, render pixel-perfect del emblema): `sudo apt install kitty`
- **Mullvad CLI** (opcional, estado VPN en el splash): `sudo apt install mullvad-vpn`
- Herramientas ofensivas (`nmap`, `gobuster`, `ffuf`, `nuclei`, `sqlmap`, `hydra`, etc.). El comando `tools` muestra el inventario completo.

## Instalación

```bash
git clone <tu-repo> ~/ai-agent-kali
cd ~/ai-agent-kali

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
# o si no hay requirements.txt:
pip install requests openai rich pyfiglet
```

## Configuración

Edita las constantes al principio de `agent.py`:

| Variable | Default | Descripción |
|---|---|---|
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` | Endpoint de LM Studio |
| `MODEL_NAME_FALLBACK` | `qwen/qwen3.6-27b` | Modelo a usar si LM Studio no expone ninguno |
| `WORKSPACE` | `~/ai-agent-kali` | Ruta del proyecto |
| `AUTO_EXECUTE` | `True` | Auto-ejecuta comandos `safe` sin confirmación |
| `MAX_CONTEXT_TOKENS` | `65536` | Context window del modelo |
| `COMMAND_TIMEOUT_S` | `300` | Timeout base por comando shell (s) |
| `COMMAND_TIMEOUT_S_LARGE` | `1800` | Timeout extendido para wordlists ≥ 5000 líneas |
| `WORDLIST_MEDIUM_THRESHOLD_LINES` | `5000` | Líneas a partir de las que un wordlist se considera medio/grande |
| `MAX_CONCURRENT_SUBAGENTS` | `3` | Subagentes simultáneos máximo |
| `SUBAGENT_DEFAULT_MAX_TURNS` | `12` | Turnos LLM por subagente antes de "exhausted" |
| `GOAL_MAX_PHASES` | `5` | Fases máximas del orquestador |
| `GOAL_PHASE_TIMEOUT_S` | `1800` | Timeout por fase del orquestador (s) |
| `PROXY_MODE` | `"proxychains"` | Routing: `"proxychains"`, `"torify"`, `"off"` |
| `STREAM_COMMAND_OUTPUT` | `False` | Stream línea a línea de stdout/stderr (vs panel al final) |

## Cómo arrancar

```bash
python agent.py
# o desde fuera del venv:
~/ai-agent-kali/venv/bin/python ~/ai-agent-kali/agent.py
```

> Arranca dentro de **kitty** para el emblema en pixel-perfect:
> ```bash
> kitty -e ~/ai-agent-kali/venv/bin/python ~/ai-agent-kali/agent.py
> ```

Para salir: `salir`, `exit`, `quit`, o `Ctrl+C`. La sesión se auto-guarda.

## Flujo típico de uso

```
$ python agent.py

# 1. Cargar password sudo (opcional pero recomendado — permite a
#    subagentes/autopilot usar sudo sin pedirla cada vez)
Tú > sudo set
    Password sudo (no se guarda a disco, solo en memoria): ******
    ✓ Password validada y almacenada en memoria.

# 2. Cargar un target (alcance, hosts, notas previas)
Tú > target empresa1

# 3. Activar la skill que necesites
Tú > use recon

# 4. Modo A: pedir tareas manualmente
Tú > Haz recon pasivo del dominio.

# 5. Modo B: lanzar UN subagente autónomo concreto
Tú > subagent new osint1 recon "OSINT pasivo de gc-heat.de:
     theHarvester todas las fuentes, crosslinked patrón
     {first}.{last}@gc-heat.de, holehe por email. Volcar a
     identities.md."
    (mientras corre puedes seguir trabajando)

# 6. Modo C: lanzar un GOAL orquestado (el agente planifica
#    fases, lanza varios subagentes por fase, itera hasta cumplir)
Tú > goal Identificar el vector de intrusión más probable

# 7. Cuando termine, panel verde + bell + path al informe
#    automático generado en reports/

# 8. Salir — sesión guardada
Tú > salir
```

---

## Comandos del agente

> Todos los comandos aceptan **prefijo opcional `/`** estilo slash-command. `comandos` y `/comandos` son equivalentes. Hay alias bilingüe (inglés/español) para los principales.

### Barra de contexto

Antes de cada prompt `Tú >`:

```
│ ████░░░░░░░░░░░░░░░░ 18.4%  12,043 / 65,536 tokens  ·  7 turnos  ·  1 skill  ·  target: empresa1  ·  🔒 sudo
```

- **Verde** (<50%) — espacio holgado.
- **Ámbar** (50–80%) — empieza a llenarse.
- **Rojo** (80–95%) — `⚠ alto`.
- **Rojo brillante** (95–100%) — `⚠ CRÍTICO` (aviso una vez).
- **Magenta** (≥100%) — `⚠ OVERFLOW` + panel grande explicando qué se compacta automáticamente y cuándo iniciar nueva sesión.

Indicadores extra:
- `🔒 sudo` — password sudo almacenada (subagentes pueden usar sudo sin prompt).
- `target: <nombre>` — target activo.

### Generales

| Comando | Acción |
|---|---|
| `help` / `ayuda` | Ayuda extendida |
| `comandos` / `commands` | Tabla compacta con todos los comandos |
| `refresh` / `clear` | Redibuja el splash |
| `models` / `modelos` | Modelos expuestos por LM Studio |
| `tools` / `herramientas` | Tabla categorizada de las **137 herramientas** que el agente reconoce (17 categorías) con instaladas/faltantes |
| `compact` / `compactar` | Compacta history (acelera prefill del modelo en sesiones largas) |
| `salir` / `exit` / `quit` | Cierra el agente |

### Skills

| Comando | Acción |
|---|---|
| `skills` / `habilidades` | Lista skills · ●=activa ○=disponible ✗=falta skill.md |
| `tools_master` / `master` | Lista las listas exhaustivas de herramientas por skill |
| `use <skill>` / `usar <skill>` | Activa skill + carga `tools_master/<skill>.md` si existe |
| `unuse <skill>` / `quitar <skill>` | Desactiva una skill |

Puedes tener varias skills activas. Al activar una skill con su `tools_master/<skill>.md`, el modelo recibe la lista exhaustiva de herramientas a recorrer para esa fase y debe justificar cada omisión en `notes.md`.

### Targets (contexto del objetivo)

Estructura:

```
targets/
└── empresa1/
    ├── scope.md             # alcance autorizado (PROTEGIDO — sólo el operador)
    ├── attack-surface.md    # hosts/puertos/endpoints/tecnologías
    ├── infrastructure.md    # DNS/ASN/hosting/certs
    ├── identities.md        # emails/usuarios/repos/leaks
    ├── credentials.md       # creds obtenidas
    ├── wifi.md              # SSIDs/BSSIDs
    ├── notes.md             # decisiones, TODOs, hilos sueltos
    ├── _timeline.md         # bitácora cronológica (auto-gestionada)
    └── _runs.md             # checklist de scans ejecutados (auto-gestionada)
```

| Comando | Acción |
|---|---|
| `target` / `objetivo` | Lista los targets disponibles · ●=activo |
| `target <nombre>` | Carga `targets/<nombre>/` en el contexto |
| `target reload` | Recarga el target activo |
| `target unload` | Quita el target del contexto |
| `report` / `informe [extras]` | Genera informe técnico → `reports/informe-<target>-<ts>.md` |

#### Auto-actualización por el modelo (TARGET_UPDATE)

El modelo escribe a los archivos del target emitiendo bloques:

```
[[TARGET_UPDATE: attack-surface.md]]
## [2026-05-15 18:30] Hallazgos nmap a 203.0.113.11
- 443/tcp open https nginx 1.24.0
[[/TARGET_UPDATE]]
```

El agente:
- Hace **append** al archivo (nunca sobrescribe).
- Acepta cierres tolerantes: `[[/TARGET_UPDATE]]`, próximo `[[TARGET_UPDATE:`, o EOF.
- Avisa si encuentra bloques sin cierre explícito (se recuperan igual).
- Rechaza `scope.md` (lo decide el operador) y `_timeline.md` (auto-gestionado).
- Recarga el target tras aplicar updates → el modelo ve la nueva info en el siguiente turno.

#### Auto-tracking de comandos

Tras cada `COMANDO:` ejecutado:
- **`_timeline.md`** — bitácora cronológica con comando + output truncado.
- **`_runs.md`** — checklist estructurada con UNA línea por scan, agrupada por herramienta. Anti-duplicación: si propones el mismo scan, el agente avisa.

### Subagentes autónomos

Mini-agentes LLM independientes con su propia history pero compartiendo el target con el agente principal. Cada uno:
- Recibe SYSTEM_PROMPT + skill + `tools_master/<skill>.md` + archivos del target.
- Auto-ejecuta sus COMANDOs (sin pedir confirmación).
- Aplica TARGET_UPDATEs sobre los archivos compartidos del target.
- Loguea en `memory/subagents/<nombre>.log`.
- Termina al emitir `TAREA COMPLETA`, al agotar 12 turnos LLM, al fallar, o al recibir kill.
- **Silenciado**: durante su ejecución NO ensucia tu terminal — sólo verás el panel-resumen al terminar.

| Comando | Acción |
|---|---|
| `subagent new <nombre> <skill> <descripción>` | Lanza un subagente autónomo |
| `subagent list` | Tabla con todos los subagentes (activos + terminados) |
| `subagent show <nombre>` | Panel-resumen de un subagente |
| `subagent kill <nombre>` | Detiene un subagente en ejecución |

**Cuándo usar un subagente**:
- Paralelismo manual (delegar enum SMB de un host mientras tú trabajas el web).
- Escaneos largos predecibles (gobuster sobre wordlist grande).
- Tarea derivada directamente de una skill concreta (auditoría WP completa).
- Procesamiento batch sobre lista de hosts.
- Investigación OSINT paralela.

Cuando NO usar subagente: si el objetivo es abstracto ("encuentra el vector de entrada"), usa `goal` que orquesta varios subagentes en fases.

Máximo `MAX_CONCURRENT_SUBAGENTS = 3` activos a la vez.

### Goal-driven orchestration

Orquestador que recibe un objetivo en lenguaje natural y lo ejecuta en fases iterativas. El LLM-orquestador decide:
- Cuántos subagentes lanzar por fase (1-3).
- Qué skill y qué misión para cada uno.
- Cuándo el objetivo está cumplido (`GOAL_DONE`), bloqueado (`GOAL_BLOCKED`) o necesita otra fase (`PLAN`).

| Comando | Acción |
|---|---|
| `goal <descripción>` | Lanza el orquestador en background |
| `goal status` | Estado actual (fase, subagentes lanzados, motivo) |
| `goal show` | Panel-resumen completo |
| `goal kill` | Detiene goal y subagentes de la fase actual |

**Flujo del orquestador**:

```
goal Identificar vector de intrusión más probable
   │
   ▼  start_goal() crea GoalRun en thread daemon
┌──┴────────────────────────────────────────────┐
│  FASE k (max GOAL_MAX_PHASES = 5):            │
│    1. LLM-orquestador recibe goal + estado    │
│       del target (archivos truncados) +       │
│       historial de fases anteriores           │
│    2. Decide: PLAN / GOAL_DONE / GOAL_BLOCKED │
│    3. Si PLAN → spawn_subagent() de cada uno  │
│    4. _goal_wait_phase() poll cada 2s hasta   │
│       todos done/failed/killed (timeout       │
│       GOAL_PHASE_TIMEOUT_S = 30 min)          │
│    5. Recolecta summaries → next phase prompt │
└──┬────────────────────────────────────────────┘
   │ loop con retry escalonado (3 intentos:
   │ full → reinforced → minimal prompt)
   ▼
Evaluación FINAL tras última fase (última
oportunidad de GOAL_DONE basado en TARGET_UPDATEs
de la última fase).
   │
   ▼
INFORME AUTOMÁTICO (LLM genera markdown completo
en reports/informe-goal-<id>-<target>-<ts>.md).
   │
   ▼
Terminal bell + panel grande con:
  · Estado final con emoji (✅⚠️⏱️✋❌)
  · Resumen del orquestador
  · Subagentes lanzados por fase + sus summaries
  · Path al informe automático
```

**Salvaguardas del orquestador**:
- Solo **UN GoalRun activo** a la vez.
- Retry escalonado si el modelo no responde: full prompt → reinforced → minimal (solo attack-surface + notes + identities, head corto).
- Detecta respuesta vacía y reporta causa específica (prompt grande / modelo sobrecargado).
- Excluye `_timeline.md` del prompt del orquestador (160 kB típicos, no aporta a planificar).
- El informe automático se genera incluso si el goal terminó EXHAUSTED — y se le pide al LLM que **rebata la decisión del orquestador** si hay un vector en `notes.md`.

### Sesiones

Auto-guardadas en `memory/sessions/<SESSION_ID>.json` tras cada turno.

| Comando | Acción |
|---|---|
| `sessions` / `sesiones` | Últimas 20 sesiones guardadas |
| `resume` / `retomar` | Retoma la última sesión |
| `resume <id>` / `retomar <id>` | Retoma una sesión concreta |
| `new` / `nueva` | Cierra contexto actual y empieza sesión limpia |

> **Cuándo usar `new`**: si la barra muestra ≥95%. Los archivos del target (evidencia) persisten en disco — la nueva sesión sólo descarta la conversación literal.

### Lecciones (memoria persistente)

Reglas globales del operador que se inyectan en el SYSTEM_PROMPT en **todas las sesiones futuras**.

| Comando | Acción |
|---|---|
| `aprende <regla>` / `learn <regla>` / `recuerda <regla>` | Guarda en `memory/lessons/` |
| `lecciones` / `lessons` | Lista lecciones guardadas |
| `olvida <fragmento>` / `forget <fragmento>` | Borra la lección cuyo nombre contiene el fragmento |

El modelo también puede guardar lecciones por su cuenta vía `agent:learn <texto>` cuando le corriges o le das una convención de tu entorno.

### Sudo, timeout, proxy

#### `sudo` — gestión de password

| Comando | Acción |
|---|---|
| `sudo` / `sudo status` | Muestra estado del caché + si hay password almacenada |
| `sudo refresh` | Ejecuta `sudo -v` interactivo (refresca caché ~15 min) |
| `sudo set` | Pide password con getpass y la **almacena en memoria** del proceso |
| `sudo clear` | Borra la password de memoria + invalida caché |

Con `sudo set`:
- Password **solo en memoria del proceso Python**. NO se persiste a disco, NO se loggea, NO entra en `session_*.json`.
- Subagentes y autopilot usan `sudo -S` con la password automáticamente — sin interrumpirte.
- Indicador `🔒 sudo` en la barra de contexto.
- Se pierde al salir del agente.

#### `timeout` — timeout dinámico

Por defecto cada `COMANDO:` tiene timeout de **300s**. Si usa un wordlist con ≥5000 líneas (gobuster, ffuf, hydra), sube **automáticamente a 1800s (30 min)**.

| Comando | Acción |
|---|---|
| `timeout` / `timeout status` | Muestra valores actuales |
| `timeout <N>` | Cambia el base (10–7200 s) |
| `timeout large <N>` | Cambia el extendido (60–14400 s) |
| `timeout threshold <N>` | Cambia el umbral de líneas (≥100) |
| `timeout default` | Restaura 300/1800/5000 |

Cuando un comando supera su timeout, el output capturado hasta ese momento **se preserva** (no se descarta como antes).

#### `proxy` — routing por Tor/proxychains

| Comando | Acción |
|---|---|
| `proxy` / `proxy status` | Estado actual + Tor en puerto 9050 |
| `proxy on` | `proxychains4` (default) |
| `proxy torify` | torify (sólo TCP, más simple) |
| `proxy off` | Conexión directa (recomendado para fuzzing web) |

El modelo puede emitir `agent:noproxy <comando>` para un bypass single-shot sin cambiar el modo global. Útil para herramientas de fuzzing por Tor que son inviables (gobuster con 200k wordlist por Tor = horas + bloqueos por exit nodes).

---

## Clasificación de comandos y AUTO_EXECUTE

Cada `COMANDO:` se clasifica:

| Categoría | Color | Comportamiento con `AUTO_EXECUTE = True` |
|---|---|---|
| **safe** (`ls`, `cat`, `grep`, `whoami`, `searchsploit`, `curl GET`, etc.) | verde | **Auto-ejecuta** sin confirmación |
| **intrusive** (`nmap`, `gobuster`, `nikto`, `nuclei`, `wpscan`, `curl POST`, `sudo <safe>`) | ámbar | Pide confirmación `[s/N]` |
| **destructive** (`rm`, `sqlmap`, `hydra`, `apt install`, redirects a `/etc/`) | rojo | Pide confirmación con **⚠ DESTRUCTIVO** |

**Degradación de auto-execute** (incluso si el comando es `safe`):
- **Duplicate detection**: si el mismo tool+target+flags clave ya está en `_runs.md` → panel "⚠ ESCANEO YA REALIZADO" + prompt manual.
- **Tool saturation**: si una herramienta ya tiene ≥3 runs en `_runs.md` → panel "⚠ HERRAMIENTA SATURADA" + prompt manual. El modelo es empujado hacia otra categoría del tools_master.

### Auto-install de herramientas faltantes

Si un comando falla por `command not found`:
1. Detecta el binario en `stderr`.
2. Ejecuta `sudo apt-get install -y <tool>` (usa la password almacenada con `sudo set` si la hay).
3. Reintenta el comando original.

Desactivable con `AUTO_INSTALL_MISSING_TOOLS = False`.

---

## Salvaguardas del agente

Reglas duras en el SYSTEM_PROMPT y enforcement en código contra los patrones de fallo más comunes del LLM:

### Anti-fabricación de output del sistema

El modelo a veces fabricaba bloques que SÓLO produce el agente: `[DIAGNÓSTICO …]`, `Comando propuesto`, `instaladas: …`, paneles falsos.

- Regla dura prohibiendo emitir esos formatos.
- Detector `_detect_system_output_hallucination` con 14 patrones — panel rojo en pantalla cuando dispara.
- Tu turno termina en `COMANDO:`. El análisis va en el **siguiente** turno cuando recibes `Resultado del comando:`.

### Anti-regurgitación del contexto system

El modelo a veces copiaba literalmente `[Scans en disco …]`, `[Target activo: …]`, `=== _runs.md ===` en su respuesta.

- Regla dura prohibiendo regurgitar bloques system.
- Strip agresivo `_strip_context_regurgitation`: si detecta cualquiera de 7 markers, trunca desde la primera aparición hasta el final del answer ANTES de meterlo en history. Si lo que queda es <40 chars, sustituye por nota explicativa.
- Aviso al operador: `› N bloque(s) de contexto system regurgitado(s)`.

### Anti-loop / anti-repetición

- **`_build_tool_runs_summary`**: ephemeral system message cada turno con uso acumulado por herramienta y marcador `⛔ SATURADA (≥3 runs)`.
- **Regla "anti-loop por herramienta"**: ≥3 runs del mismo tool → siguiente COMANDO debe ser de OTRA categoría del tools_master.
- **Regla "anti-repetición de análisis"**: si el análisis sería casi idéntico al turno anterior, decir "Sin novedades respecto al turno anterior" en lugar de regenerar.

### Probe-list vs finding

NSE scripts como `http-enum` listan paths *probados*, no *encontrados*. Antes el modelo confundía `/wp-login.php` (probado) con "WordPress instalado".

- Regla dura: una ruta es "encontrada" sólo si lleva status code (200, 301, 302, 401, 403) o marcador (`+`, `[+]`, `FOUND`, `VULNERABLE`).
- Sin marcador → es un CANDIDATO PROBADO, no un hallazgo. No se incluye en `attack-surface.md`.

### Revisión de creencias

Cuando el operador corrige un hecho del target ("este sitio es TYPO3, no WordPress"), esa afirmación es ground truth para el resto de la sesión. El modelo:
1. Deja de mencionar la hipótesis contradicha.
2. Emite `TARGET_UPDATE: notes.md` con la corrección.
3. NO la reintroduce porque una herramienta saque un keyword relacionado.

### Cancelación de comando (rc=-1)

Cuando cancelas un comando con `N`, el agente NO dispara el `analysis_prompt` automático — antes el modelo asumía que "el comando seguía ejecutándose" y entraba en bucle proponiendo variantes.

### `./scans/` enforcement

Cada turno con target activo, ephemeral system message `[Scans en disco — relevantes a 'X']` con la lista de archivos en `./scans/` filtrada por tokens del target (IP, hostname, root domain), con preview de 2 líneas por archivo. Regla: si la info que buscas está en uno de esos archivos, propón `cat`/`head`/`grep` en lugar de un nuevo escaneo.

### Fidelidad al guardar datos del operador

Cuando el operador pega datos estructurados (Censys, Shodan, una tabla) y dice "guarda", el modelo debe reproducir TODOS los campos verbatim en el `TARGET_UPDATE` — sin resumir, sin descartar campos, sin inventar fuente.

---

## Skills disponibles

Cada skill es un directorio en `skills/` con un archivo `skill.md` cuyo contenido se inyecta como mensaje `system` cuando se activa con `use`.

| Skill | Foco |
|---|---|
| `recon` | Reconocimiento pasivo / semi-pasivo. OSINT, DNS, subdominios, fingerprinting. Sin port-scans completos ni fuzzing |
| `recon_activo` | Reconocimiento activo: port scanning, enum SMB/LDAP/SNMP, fuzzing web, NSE vuln scripts |
| `web_pentest` | OWASP Top 10. Fuzzing, SQLi, XSS, SSRF, IDOR, SSTI |
| `wordpress_audit` | WPScan, plugins/temas vulnerables, XML-RPC, REST API, backups expuestos |
| `internal_network_audit` | AD/SMB/Kerberos. Kerberoasting, AS-REP, BloodHound, ADCS, password spraying |
| `reporting` | Genera informe final estructurado |

### `tools_master/<skill>.md` — listas exhaustivas

Cada skill puede llevar asociada una `tools_master/<skill>.md` que se carga automáticamente al hacer `use <skill>`. Formato `| Herramienta | Instalación | Comando de ejemplo |`. Listas actuales:

- `tools_master/recon.md` — ~83 herramientas en 19 categorías (OSINT, DNS, certs, histórico web, etc. — exclusivamente pasivo/semi-pasivo).
- `tools_master/recon_activo.md` — ~130 herramientas en 27 categorías (port scanning, fingerprinting activo, fuzzing, enum AD, etc.).

El modelo recibe instrucción de recorrer la lista exhaustivamente y justificar cada omisión en `notes.md` vía `TARGET_UPDATE`.

---

## Herramientas conocidas

El comando `tools` muestra una tabla categorizada con **137 herramientas** en **17 categorías**:

1. Port scan & host discovery
2. Service fingerprinting
3. DNS recon
4. Web fuzzing & crawling
5. Web vuln scan & CMS
6. SSL/TLS
7. SMB / NetBIOS / AD
8. LDAP & Kerberos (Impacket incluido)
9. SNMP / SMTP / FTP / SSH
10. Databases
11. RDP / VNC
12. VoIP / Wireless / Bluetooth
13. Brute force / Passwords
14. Exploitation
15. OSINT / APIs
16. Sniffing & Network
17. Utilidades

Las faltantes se pueden auto-instalar cuando el modelo intente usarlas (auto-install vía `_try_install_tool` → `_sudo_run` con tu password almacenada).

---

## Estructura del proyecto

```
~/ai-agent-kali/
├── agent.py                         # Script principal
├── README.md                        # Este archivo
├── venv/                            # Entorno virtual Python
├── assets/                          # Imágenes para splash
│
├── skills/                          # Skills cargables (use <nombre>)
│   ├── recon/skill.md
│   ├── recon_activo/skill.md
│   ├── web_pentest/skill.md
│   ├── wordpress_audit/skill.md
│   ├── internal_network_audit/skill.md
│   └── reporting/skill.md
│
├── tools_master/                    # Listas exhaustivas por fase
│   ├── recon.md
│   ├── recon_activo.md
│   └── README.md
│
├── memory/
│   ├── sessions/                    # Sesiones auto-guardadas
│   │   └── 20260516-152027.json
│   ├── lessons/                     # Lecciones globales
│   │   └── INDEX.md
│   └── subagents/                   # Logs de subagentes + goals
│       ├── <subagente>.log
│       └── _goal-<id>.log
│
├── targets/                         # Contexto del objetivo
│   └── empresa1/
│       ├── scope.md                 # PROTEGIDO (sólo operador)
│       ├── attack-surface.md
│       ├── infrastructure.md
│       ├── identities.md
│       ├── credentials.md
│       ├── wifi.md
│       ├── notes.md
│       ├── _timeline.md             # auto-gestionado
│       └── _runs.md                 # auto-gestionado
│
├── plugins/                         # (placeholder)
├── hooks/                           # Hooks before_command/after_command/on_error/on_report
├── logs/                            # (sin uso activo)
├── reports/                         # Informes (incluye los auto-generados al cerrar goal)
├── scans/                           # Outputs de nmap, gobuster, nuclei…
└── evidence/                        # Capturas, requests, hashes, ficheros extraídos
```

---

## Solución de problemas

**El splash sale con caracteres raros / cuadritos vacíos**
> La fuente del terminal no soporta los símbolos Unicode que chafa usa. Solución: instala una Nerd Font (FiraCode, JetBrains Mono Nerd Font) o usa kitty.

**El agente no se conecta al modelo**
> ```bash
> curl http://127.0.0.1:1234/v1/models
> ```
> Si LM Studio está en otra máquina, edita `LMSTUDIO_BASE_URL` en `agent.py`.

**El goal falla con "Modelo devolvió respuesta VACÍA"**
> El prompt del orquestador supera el context window real del modelo. El agente reintenta automáticamente con prompt MINIMAL (sólo attack-surface + notes + identities, head corto). Si aun así falla, revisa el log en `memory/subagents/_goal-<id>.log`, baja `MAX_CONTEXT_TOKENS` para coincidir con el modelo real, o usa un modelo con context window más grande.

**Un subagente bloquea pidiendo password sudo**
> Tu password no está almacenada o se cargó incorrectamente. Sal del prompt sudo con Ctrl+C, ejecuta `sudo set` desde el REPL principal, verifica el mensaje verde `✓ Password validada y almacenada en memoria`. La barra mostrará `🔒 sudo`. Subagentes futuros la usarán automáticamente.

**El modelo regurgita su propio contexto / se inventa output del sistema**
> El agente lo detecta (panel rojo "⚠ Alucinación de output del sistema detectada") y trunca la regurgitación antes de meterla en history. Si pasa repetidamente, ejecuta `compact` o inicia `new` — el modelo está saturado.

**Gobuster/ffuf no encuentra nada por Tor**
> Fuzzing por Tor es inviable (10 hilos × 1-3s/req × 200k entries = horas). Ejecuta `proxy off` para esa fase, o que el modelo use `agent:noproxy gobuster …` para un bypass single-shot.

**Una sesión guardada está corrupta y `resume` falla**
> ```bash
> rm memory/sessions/<id>.json
> ```

**`tools` muestra herramientas instaladas como faltantes**
> El agente usa `shutil.which()` que respeta `$PATH`. Asegúrate de que `/usr/sbin`, `/snap/bin` etc. están en tu PATH.

**El contexto llegó al 100% y el modelo se está perdiendo**
> Ejecuta `compact` para forzar compactación adicional, o `new` para empezar sesión limpia. La evidencia en `targets/<nombre>/` está a salvo — el nuevo agente la carga al hacer `target <nombre>`.

---

## Reglas de uso responsable

El agente está diseñado para auditorías de seguridad **autorizadas**. Antes de cualquier acción ofensiva real:

1. Confirma alcance con autorización por escrito.
2. Define ventana de pruebas y nivel de agresividad permitido.
3. No toques sistemas fuera del alcance.
4. No realices acciones destructivas sin doble confirmación.
5. Documenta toda la actividad para el informe.

El system prompt del agente incluye estas reglas y las refuerza en cada interacción, pero la **responsabilidad final es del operador humano**.

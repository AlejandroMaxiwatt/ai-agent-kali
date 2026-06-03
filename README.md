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
  - [Edición de código por el modelo (FILE_*)](#edición-de-código-por-el-modelo-file_)
  - [Subagentes autónomos](#subagentes-autónomos)
  - [Goal-driven orchestration](#goal-driven-orchestration)
  - [VSCode/Cursor bridge](#vscodecursor-bridge)
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
| `TROUBLESHOOT_AUTOPILOT` | `True` | Auto-fix de comandos fallidos vía LLM (ver [auto-troubleshooting](#auto-troubleshooting-autopilot)) |

#### Perfiles de inferencia (`_LLM_PROFILES`)

Las cuatro vías que llaman al LLM (`main` / `subagent` / `orchestrator` / `report`) usan una **tabla única** de `temperature`, `max_tokens`, `frequency_penalty`, `presence_penalty`. Antes cada bucle pasaba sus propios kwargs hardcodeados — eso generaba drift entre llamadas con cada refactor. Si quieres tunear cómo responde cada bucle, edita `_LLM_PROFILES` (cerca del top de `agent.py`):

| Perfil | temp | max_tokens | penalties |
|---|---|---|---|
| `main` | 0.1 | 4096 | freq=0.4, pres=0.2 |
| `subagent` | 0.1 | 2048 | freq=0.4, pres=0.2 |
| `orchestrator` | 0.2 | 2048 | sin penalties |
| `report` | 0.3 | 6000 | sin penalties |

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
| `copy [n]` / `c [n]` / `copiar [n]` | Copia el último comando propuesto (o el n-ésimo desde el final) al portapapeles vía OSC 52 + fallbacks nativos (xclip, wl-copy, pbcopy) |
| `salir` / `exit` / `quit` | Cierra el agente |

#### Edición de archivos desde el REPL (operador)

Las mismas operaciones que el modelo puede hacer vía bloques `FILE_*` están disponibles para ti directamente. Útil para preparar contenido cuando el modelo se queda atascado o cuando quieres tocar tú mismo.

| Comando | Acción |
|---|---|
| `view <ruta>` / `ver <ruta>` / `cat <ruta>` | Lee el archivo con líneas numeradas + syntax highlight |
| `edit <ruta>` / `editar <ruta>` | Prompt interactivo: pegas el bloque OLD, `EOF`, el bloque NEW, `EOF` |
| `diff <ruta1> <ruta2>` | Diff coloreado entre dos archivos del workspace |
| `write <ruta>` / `escribir <ruta>` | Prompt interactivo: pegas contenido, `EOF`. Crea o sobreescribe |

Las rutas pueden ser relativas (resueltas contra `WORKSPACE`) o absolutas. Los archivos protegidos (`.env`, `privkey.pem`, ssh keys, etc.) se bloquean en la validación.

#### Menciones `@archivo` (inyección de contexto)

Si escribes `@<ruta>` en tu prompt, el agente busca el archivo en el workspace y, si hay varias coincidencias, te pregunta cuál usar. El contenido se inyecta como bloque de contexto delante de tu petición, sin que tengas que copiar/pegar.

```
Tú > revisa @agent.py:L6321-L6500 y dime si la rama de stuck funciona
```

Acepta rango opcional `:L<inicio>-L<fin>` para inyectar sólo un fragmento. Si está activo el [bridge VSCode/Cursor](#vscodecursor-bridge), la selección actual del editor se auto-attachea sin tener que escribir `@…`.

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

### Edición de código por el modelo (`FILE_*`)

Aparte de `TARGET_UPDATE`, el modelo puede leer/editar/crear cualquier archivo del sistema usando tres tipos de bloque. Útil para que el agente arregle bugs en tus propios scripts, ajuste configs, o construya artefactos para el engagement.

```
[[FILE_READ: ruta/al/archivo.py]]               ← sin cuerpo (inyecta el contenido)
[[FILE_READ: ruta/al/archivo.py L10-L40]]       ← rango opcional

[[FILE_EDIT: ruta/al/archivo.py]]
[[OLD]]
texto exacto que existe en el archivo (debe ser único)
[[/OLD]]
[[NEW]]
texto que lo sustituye
[[/NEW]]
[[/FILE_EDIT]]

[[FILE_WRITE: ruta/al/archivo.py]]
contenido entero (crea o sobreescribe)
[[/FILE_WRITE]]
```

Detalles del wire:
- Las rutas pueden ser **relativas** (resueltas contra `WORKSPACE`) o **absolutas en cualquier parte del sistema**. El acceso lo decide el SO según los permisos UNIX del usuario que corre el agente — no hay confinamiento al workspace.
- **Archivos protegidos** (`.env`, `privkey.pem`, ssh keys, etc.) se bloquean a nivel de validación.
- **FILE_EDIT** exige que el bloque OLD sea ÚNICO en el archivo (anti-ambigüedad). Para varios cambios en un archivo, varios bloques consecutivos.
- Antes de aplicar EDIT/WRITE el agente muestra un **panel diff coloreado**. Si `AUTO_EXECUTE=True` se aplica directo; si no, pide `y/N`.
- **FILE_READ inyecta** el contenido al history con líneas numeradas → el modelo lo "ve" en el siguiente turno.

Sólo se soporta el formato V2 (`[[OLD]]/[[/OLD]]`). El antiguo `<<<OLD/OLD>>>` fue retirado (era propenso a errores en modelos locales).

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
| `goal list` | Lista todos los goals persistidos en disco (incluyendo terminados) |
| `goal resume [id]` | Reanuda un goal interrumpido desde la última fase completa. Sin `id` toma el huérfano más reciente |
| `goal discard <id>` | Borra el estado persistido de un goal (el log de ejecución sigue en disco) |

**Persistencia / resume**: el orquestador guarda un snapshot del estado (`memory/subagents/_goal-<id>.state.json`) tras cada fase completada. Si el agente se cierra a media fase, al arrancar avisa de "goals huérfanos" y puedes reanudar con `goal resume`. Las fases ya completadas no se repiten — la evidencia ya está en los archivos del target.

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

### VSCode/Cursor bridge

Extensión opcional (`vscode-extension/`) que conecta el agente con tu editor para que **vea en directo qué archivo tienes abierto y qué selección tienes activa** — equivalente a escribir `@<archivo>:L<a>-L<b>` a mano pero sin tener que hacerlo.

**Auto-instalación silenciosa**: al arrancar el agente desde el terminal integrado de VSCode/Cursor, intenta instalar la extensión (`maxiwatt-agent`) de forma idempotente. Si no estás en un terminal de editor, es un no-op silencioso. Compatible con **Remote SSH** (la extensión se fuerza a `extensionKind: workspace`).

Lo que añade el bridge una vez instalado:
- **Auto-attach**: si tienes una selección activa <120s antes de enviar tu prompt, el contenido del archivo+rango se inyecta automáticamente. Verás `› auto-attached: @archivo:L43-L45` confirmando.
- **Badge en vivo** en la bottom toolbar de `prompt_toolkit`: `📋 N líneas seleccionadas en archivo.py` con refresh cada 1s mientras escribes.
- **TTY interactivo** vía `script(1)` wrap (commit `4937c6d`) para que herramientas con TTY (vim, less, msfconsole) funcionen aunque el agente corra dentro de un side-panel.
- **Splash modo lite** automático cuando el terminal mide < 130 columnas (paneles SSH/IDE estrechos).

Si la extensión no carga, el agente funciona igual — solo pierdes auto-attach y el badge en vivo. Puedes seguir escribiendo `@archivo` a mano.

Para desactivar la auto-instalación, edita `agent.py` y comenta la llamada a `maybe_install_vscode_extension()` en `main()`.

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

### Anti-loop en edición de archivos

Detector `_detect_file_block_stuck_pattern` que clasifica tres atascos típicos del modelo cuando edita código y aplica un nudge específico en el siguiente turno:

- **`reread_loop`**: el modelo ha emitido `[[FILE_READ: X]]` en ≥2 turnos consecutivos sin un solo `[[FILE_EDIT: X]]` → el contenido ya está en el history, releer no aporta. El agente filtra el history (drop assistant vacíos, colapsa lecturas duplicadas a placeholder), sube temperature a 0.7 y desactiva las penalties para romper el atractor.
- **`malformed_edit`**: el modelo escribió `[[FILE_EDIT:` literal pero la sintaxis está rota (delimitadores inline, falta `[[/FILE_EDIT]]`, etc.) → el archivo NO se modificó. Panel rojo al operador + nudge correctivo.
- **`no_block`**: el modelo habló de `FILE_READ`/`FILE_EDIT` en prosa pero NO emitió ningún bloque → typical "voy a editar el archivo" sin hacerlo. Nudge obligando al bloque ya.

### Anti-promesa de edición sin cumplir

Tras cada respuesta, si el modelo dijo en prosa "modifico/cambio/actualizo X" pero NO emitió un bloque `FILE_EDIT`/`FILE_WRITE` → panel rojo "⚠ Promesa de edición sin cumplir" con el snippet detectado. Si el bloque sí existe pero está malformado, se prioriza ese aviso (no se duplica).

### Comandos quemados (autopilot burn list)

Cuando el [troubleshoot autopilot](#auto-troubleshooting-autopilot) agota intentos contra un mismo comando, ese comando se añade a `_AUTOPILOT_BURNED_COMMANDS` y se inyecta como ephemeral system message: "NO VOLVER A PROPONER". Evita que el modelo proponga el mismo comando fallido turno tras turno (con cambios cosméticos en comillas o espacios).

### Auto-troubleshooting (autopilot)

Activable con `TROUBLESHOOT_AUTOPILOT = True` (default). Cuando un comando falla con rc≠0 (y NO es un rc benigno tipo `grep -q` sin matches), el agente entra en un bucle de auto-fix:

1. Le pide al modelo un comando de diagnóstico (`--help`, `which`, `dpkg -l`, `ls /usr/share/…`, instalación de paquete, etc.).
2. Lo ejecuta sin pedir confirmación.
3. Hasta `TROUBLESHOOT_MAX_ATTEMPTS` intentos. Si en algún momento el modelo propone `noop` o se agota, se rinde y pasa al análisis con el output original.
4. Soporta **meta-acciones del modelo**: `agent:proxy off`, `agent:proxy on`, `agent:tor restart` para resolver problemas de routing sin tocar shell.

Los subagentes tienen su **propio recovery más simple** (sin LLM): `_subagent_try_recover` clasifica el fallo (`proxy` / `rate_limit` / `complexity` / `other`) y aplica heurísticas (`proxy off`, `_simplify_command`). Funciona en silencio dentro del thread del subagente sin contaminar la console del operador.

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

**El badge de selección de VSCode no aparece**
> 1) Confirma que estás en un terminal *integrado* de VSCode/Cursor (no en uno externo). 2) Confirma que la extensión `maxiwatt-agent` está instalada y activa (`code --list-extensions | grep maxiwatt`). 3) Si vas por Remote SSH, la extensión debe estar instalada en el host **remoto** (la auto-install la fuerza). El bridge solo funciona si el editor y el agente comparten el mismo host. Sin él, sigues pudiendo usar `@archivo:L<a>-L<b>` a mano.

**El modelo re-lee el mismo archivo turno tras turno sin editar**
> Es el `reread_loop`. El agente lo detecta automáticamente, filtra el history y sube `temperature` para romper el atractor. Si aun así no edita, pídeselo más concreto (`@archivo:L43-L45 cambia X por Y`) — el bloque `[[FILE_EDIT:]]` necesita un `OLD` único en el archivo.

**El comando `edit <ruta>` se queda esperando**
> Espera la marca `EOF` en una línea sola tras pegar el bloque OLD, luego pegas NEW, luego `EOF` otra vez. Si cancelas con Ctrl+C en mitad, no se aplica nada al archivo.

---

## Reglas de uso responsable

El agente está diseñado para auditorías de seguridad **autorizadas**. Antes de cualquier acción ofensiva real:

1. Confirma alcance con autorización por escrito.
2. Define ventana de pruebas y nivel de agresividad permitido.
3. No toques sistemas fuera del alcance.
4. No realices acciones destructivas sin doble confirmación.
5. Documenta toda la actividad para el informe.

El system prompt del agente incluye estas reglas y las refuerza en cada interacción, pero la **responsabilidad final es del operador humano**.

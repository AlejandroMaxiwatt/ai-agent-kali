# Arquitectura del agente (post P0/P1/P2)

## Uso rápido

```bash
# REPL con auto-continuación (por defecto ON)
python agent.py

# Desactivar la auto-continuación o cambiar el límite
auto off
auto steps 50

# Goal con criterios verificables
goal Comprometer TYPO3 || criteria: file_exists:evidence/x.txt; cmd_rc:test -s evidence/x.txt || budget: 4h, 300 comandos

# Goal headless (CI/cron)
python agent.py --goal "Comprometer TYPO3 || criteria: file_exists:evidence/x.txt" --target acme

# Enjambre permanente (Recon + Guardian)
swarm start --target acme --scope targets/acme/scope.md
# versión distribuida opcional
swarm start --target acme --store postgres --dsn postgresql://user:pass@host/agent --redis redis://127.0.0.1:6379/0

# Tests
./scripts/run_tests.sh
```

## Mapa de módulos

```
agent.py                     # harness + REPL + ejecución + UI (monolito)
prompts/system.md            # contrato del modelo (system prompt versionado)
agent_core/
├── results.py               # CommandResult
└── goalspec.py              # GoalSpec + verificador objetivo de criterios
agent_swarm/                 # 1 principal + 2 subagentes permanentes
├── orchestrator.py          # orquestador determinista
├── policy.py                # alcance, niveles, duplicados, rate limits
├── store.py                 # memoria compartida SQLite
├── postgres_store.py        # adaptador PostgreSQL opcional
├── event_bus.py             # eventos en proceso / Redis Streams
├── workers.py               # ReconWorker + GuardianWorker
└── models.py                # Task/Finding/Evidence/Decision
skills/validation/skill.md   # validación independiente del Guardian
tests/
├── test_core.py             # núcleo puro (sin LLM ni Rich)
├── test_agent_integration.py# P0/P1: ejecución, proxy aislado, goal loop
├── test_swarm_*.py          # enjambre, políticas, validación
└── test_swarm_distributed.py# PostgreSQL + Redis (servidores temporales)
```

`agent_core` no importa Rich, OpenAI ni el estado global del REPL. Se puede
testear de forma aislada.

## Ciclo del agente principal

```
prompt operador
   │
   ▼
ask_model() ──► LLM ──► answer (COMANDO + TARGET_UPDATE + FILE_*)
   │
   ▼
extract_command()
   │
   ▼
run_command() ──► CommandResult {rc, output, stdout, stderr,
   │                             duration, artifacts, error_class,
   │                             proxy_mode, meta}
   ▼
timeline / _runs.md
   │
   ├─ rc != 0 ──► troubleshoot_loop() (auto-fix)
   │
   ▼
_build_analysis_prompt() ──► ask_model() ──► ¿nuevo COMANDO?
   │                                              │
   │◄────────── AUTO_CONTINUE (máx. N pasos) ◄────┘
   ▼
sin COMANDO / cancelado / límite → vuelve al prompt
```

Punto clave P0: **cada ejecución devuelve su propio `CommandResult`**. Ya no
se lee `LAST_COMMAND_RC` (alias legacy sin lectores internos), así que dos
subagentes concurrentes no pueden pisarse el rc.

## Aislamiento por agente

- `run_command(command, auto, target, proxy_mode)` recibe el target y el modo
  de proxy explícitos.
- Un `Subagent` guarda su propio `target` y `proxy_mode`. Las meta-acciones
  `agent:proxy …` de un subagente solo cambian su estado, no el global.
- Los subagentes procesan `FILE_READ/EDIT/WRITE` con
  `process_file_blocks_headless()` (sin UI ni prompts).

## Goal controller (P1)

```
GoalSpec (goal + criteria + budget + constraints)
   │
   ▼
verify_goal_criteria() ──► ¿ya cumplido? ── sí ──► done
   │ no
   ▼
┌─ bucle por fases (máx. GOAL_MAX_PHASES) ──────────────────────┐
│  ¿presupuesto agotado? ── sí ──► budget_exhausted             │
│  _goal_request_plan() ──► PLAN / GOAL_DONE / GOAL_BLOCKED     │
│     · GOAL_DONE → verificar criterios; si fallan, RECHAZAR   │
│     · GOAL_BLOCKED → forzar replanificación (máx. N)         │
│     · PLAN → _goal_execute_phase() con DAG `depends_on`       │
│  ejecutar olas de subagentes (máx. N concurrentes)            │
│  verificar criterios → si OK, done                            │
│  blackboard: attempts / dead_ends / verifications             │
└────────────────────────────────────────────────────────────────┘
   │
   ▼
informe automático + estado persistido (reanudable)
```

### Criterios soportados

`file_exists`, `file_missing`, `dir_exists`, `file_contains`,
`file_not_contains`, `cmd_rc`, `cmd_output`, `port_open`.

Sintaxis en el REPL:

```
goal Comprometer el panel TYPO3 || criteria: file_exists:evidence/typo3.txt; file_contains:notes.md:FLAG\{ || budget: 4h, 300 comandos || constraints: no_destructive
```

O desde archivo (multilínea): `goal spec ./goals/acme-typo3.txt`.

El archivo también admite formato por líneas:

```
goal: Comprometer el panel TYPO3
criteria:
  - file_exists:evidence/typo3.txt
  - file_contains:notes.md:FLAG\{
budget: 4h, 300 comandos
constraints: no_destructive
target: acme
```

### Regla de parada

Un goal solo termina por:

1. criterios objetivos verificados (`done`),
2. presupuesto agotado (`budget_exhausted`),
3. bloqueo persistente tras N replanificaciones (`blocked`),
4. fases agotadas (`exhausted`),
5. kill del operador (`killed`).

## Ventana de contexto dinámica

La ventana efectiva ya no es un número fijo. `get_max_context_tokens()` la
resuelve por modelo y la cachea por `(backend, modelo)`:

- **LM Studio** → `/api/v0/models` (`loaded_context_length` o
  `max_context_length`).
- **Ollama Cloud** → `POST /api/show` → `model_info.<arquitectura>.context_length`.
- **Fallback** → `MAX_CONTEXT_TOKENS` si el backend no expone el dato.

Se usa en la barra de contexto y en el umbral de compactación
(`COMPACT_TRIGGER_PCT`). Al cambiar de modelo (`models N`) o de backend
(`backend ollama`) se invalida la caché y se vuelve a resolver.

## Modo headless

```bash
python agent.py --goal "..." --target acme --max-phases 12
```

Devuelve código 0 si `status == "done"` y 1 en cualquier otro caso. Al final
imprime un JSON con estado, criterios y ruta del informe.

## Despacho del REPL

`main()` ya no contiene la cadena de ~1.400 líneas de `if/elif`. Cada
comando interno vive en `_repl_<nombre>()` y se registra en `_REPL_TABLE`:

- `exact`: coincide con el input completo (`help`, `salir`, `compact`, …).
- `first`: coincide con la primera palabra (`goal …`, `target …`, `auto …`).

`_dispatch_repl()` devuelve `_REPL_HANDLED`, `_REPL_EXIT`,
`_REPL_FALLTHROUGH` o `(_REPL_FALLTHROUGH, nuevo_input)` para el caso
`use <skill> <texto>`.

## Deuda técnica pendiente (P2+)

- Los dos motores de auto-fix (`troubleshoot_loop` LLM-driven y
  `_subagent_try_recover` heurístico) comparten clasificación y
  `CommandResult.error_class`, pero siguen siendo dos implementaciones.
- Los destructivos (`sqlmap`, `hydra`, `metasploit`, `netexec`, …) siguen
  bloqueados en subagentes por defecto. Un goal puede autorizarlos
  explícitamente con `constraints: allow_destructive`; el subagente lo
  registra en su log y el operador asume la responsabilidad.

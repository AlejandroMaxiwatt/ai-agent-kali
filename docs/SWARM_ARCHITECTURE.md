# Arquitectura del enjambre (1 principal + 2 permanentes)

Implementación de la arquitectura propuesta en la conversación
**“Subagentes para Red Team”**: un agente principal que ejecuta, un worker
permanente de **Recon & Attack Intelligence** y un worker permanente de
**Validation & Guardian**, coordinados por un **orquestador determinista**
externo a los modelos.

## Diagrama

```mermaid
flowchart TD
    U["Operador Red Team"] --> P["Agente principal<br/>Red Team Operator"]
    P --> G{"PolicyEngine<br/>determinista"}
    G -->|nivel 1-2| T["run_command<br/>herramientas"]
    G -->|nivel 3| H["Aprobación humana"]
    G -->|nivel 4| X["Bloqueo"]
    P <--> S[("SQLite<br/>memoria compartida")]
    R["ReconWorker<br/>permanente"] <--> S
    V["GuardianWorker<br/>permanente"] <--> S
    R --> T
    V --> D["Decisiones<br/>confirmed / rejected /<br/>needs_more_evidence"]
    D --> S
    S --> P
```

## Componentes

| Componente | Implementación | Responsabilidad |
|---|---|---|
| Agente principal | `agent.py` (`run_command`, `ask_model`) | Planifica y ejecuta. Sus comandos pasan por el motor de políticas. |
| ReconWorker | `agent_swarm/workers.py` | Procesa la cola de recon, extrae activos/hallazgos, encola seguimientos. |
| GuardianWorker | `agent_swarm/workers.py` | Valida hallazgos con evidencia y alcance; confirma, rechaza o pide más evidencia. |
| PolicyEngine | `agent_swarm/policy.py` | Alcance, riesgo, autonomía, duplicados y rate limits. No es un modelo. |
| Store | `agent_swarm/store.py` | SQLite: tareas, activos, hallazgos, evidencias, decisiones, eventos, bloqueos. |
| Orquestador | `agent_swarm/orchestrator.py` | Ciclo de vida, colas, workers, API del enjambre. No es un tercer modelo. |

## Modelo de datos (SQLite)

- `tasks`: cola (`role`, `kind`, `target`, `command`, `finding_id`,
  `priority`, `status`, `fingerprint`, `result`, `rc`).
- `assets`: hosts/puertos/servicios/versiones descubiertos.
- `findings`: hallazgos con `status` (`pending_validation`, `confirmed`,
  `rejected`, `needs_more_evidence`) y `severity`.
- `evidence`: rutas, SHA-256 y extracto de la prueba.
- `decisions`: decisión del Guardian/Policy con motivo y contexto.
- `events`: trazabilidad de todo lo que ocurre.
- `blocks`: targets bloqueados por el operador o el Guardian.
- `agents`: workers registrados.

## Niveles de autonomía

| Nivel | Significado | Comportamiento |
|---|---|---|
| 1 | Auto | Lectura/pasivo (`ls`, `dig`, `grep`, …). |
| 2 | Preaprobado | Recon activo controlado (`nmap`, `subfinder`, `ffuf`, …). |
| 3 | Aprobación humana | Explotación/credenciales (`sqlmap`, `hydra`, `metasploit`, …). Siempre pide confirmación al operador; los workers de fondo no pueden ejecutarlo. |
| 4 | Bloqueo | Destructivo, fuera de alcance o patrón peligroso. |

`swarm start --level N` solo permite `N=1` o `2`; el nivel 3 no se puede
autoaprobar por diseño.

## Flujo de un comando del agente principal

1. `run_command` construye `CommandResult`.
2. Antes de ejecutar, si el enjambre está activo:
   - `_SWARM.authorize_command(command, role, target)`.
3. El motor comprueba, en orden:
   - bloqueo activo del target,
   - hosts fuera de alcance,
   - riesgo por herramienta/patrón,
   - rol (recon/validation nunca ejecutan nivel 3),
   - rate limit por target/tool,
   - duplicado por fingerprint,
   - nivel vs autonomía.
4. Resultado:
   - `allowed`: ejecuta.
   - `requires_approval`: en modo interactivo pide confirmación; en
     autopilot/subagente se rechaza con un mensaje claro.
   - `blocked`: no se ejecuta; se registra el motivo.
5. Tras ejecutar, `record_command` guarda comando, rc y tamaño de salida
   para trazabilidad y rate limits.

## Flujo de un hallazgo

1. El agente principal crea un `finding` (estado `pending_validation`)
   emitiendo una línea con formato:

   ```text
   FINDING: <info|low|medium|high|critical> | <título> | <afirmación + evidencia>
   ```

   El orquestador la parsea en `ask_model` y la registra. Recon también
   crea findings automáticamente a partir de salidas tipo nuclei/CVE.
2. Se encola una tarea `validation`.
3. El Guardian:
   - comprueba alcance,
   - verifica que la evidencia existe y su hash coincide,
   - busca marcadores de prueba real (`CVE-...`, `exploit`, `uid=0`,
     `shell`, `FLAG{...}`, …),
   - si solo hay versión/banner → `needs_more_evidence`,
   - opcionalmente pide una segunda opinión a un LLM validador
     (`--llm`).
4. Actualiza el estado y registra una `decision`.
5. El agente principal recibe en su prompt un bloque
   `[ENJAMBRE · contexto validado]` con hallazgos confirmados, pendientes y
   rechazados. **No debe presentar como confirmado lo que no lo está.**

## Comandos REPL

```text
swarm start [--target X] [--scope ruta] [--level 1-2] [--llm] [--poll seg]
swarm stop
swarm status
swarm plan [--enqueue]
swarm task <comando>
swarm finding add <título>
swarm evidence <id> <ruta>
swarm validate <id>
swarm findings [estado]
swarm queue [rol]
swarm events [N]
swarm block <target> <motivo>
swarm unblock <target>
swarm help
```

## Propiedades de seguridad

- El motor de políticas es **determinista y externo** a los modelos; ningún
  modelo puede modificar sus límites.
- Sin scope configurado, los comandos con host se bloquean.
- Los workers de fondo nunca piden aprobación humana: si un comando supera
  su nivel, se bloquea.
- El Guardian puede rechazar hallazgos, pero el bloqueo real de operaciones
  lo aplica el `PolicyEngine`/`Store`, no el modelo.
- Todo queda en `memory/swarm/swarm.db` (ignorado por git).

## Backends y operación

- **Store:** `sqlite` (default) o `postgres`:
  ```
  swarm start --store postgres --dsn postgresql://user:pass@host:5432/agent
  ```
  `PostgresStore` reutiliza la API de `Store` y usa `FOR UPDATE SKIP LOCKED`
  para reclamar tareas entre varios procesos.
- **Eventos:** `InProcessEventBus` (default) o Redis Streams:
  ```
  swarm start --redis redis://127.0.0.1:6379/0
  ```
  Redis se usa para notificar/observar; la cola autoritativa sigue en el
  Store.
- **Preempción real:** `swarm cancel <id>` mata el subproceso en ejecución
  (`cancel_event` → watcher → `proc.kill()`), no solo lo marca.
- **Panel en vivo:** el REPL muestra una línea `swarm recon=… · cola … ·
  hallazgos …` antes de cada prompt.

## Limitaciones actuales / siguientes pasos

- NATS no implementado; Redis Streams cubre la comunicación distribuida.
- El store PostgreSQL requiere `psycopg2-binary`; el bus Redis requiere
  `redis`. Ambos son opcionales y están en `requirements.txt`.
- Los workers usan reglas deterministas para activos/seguimientos; el
  planner LLM es opcional (`--llm`) y está acotado a 3 comandos.
- El Guardian valida con reglas + LLM opcional; no ejecuta explotación.
- La preempción mata el proceso, pero no garantiza limpieza de ficheros
  temporales que la herramienta hubiera creado a medias.

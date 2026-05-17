# MAXIWATT Agent — VSCode/Cursor bridge

Esta extensión hace que el agente [MAXIWATT](https://github.com/AlejandroMaxiwatt/ai-agent-kali) "vea" qué archivo tienes abierto en VSCode/Cursor y qué tienes seleccionado, igual que Claude Code muestra `📎 In file.py` o `📋 N lines selected` en su prompt.

## Cómo funciona

La extensión escribe el estado del editor (archivo activo + rango de selección) en `<workspace>/.maxiwatt/state.json` cada vez que cambia (con throttle de 200 ms). El agente MAXIWATT lee ese archivo antes de cada prompt:

- Muestra un badge encima de `Tú >`: `📋 3 líneas seleccionadas en payload.c:L43-L45` o `📎 In payload.c`.
- Si hay selección activa, la auto-adjunta al contexto cuando envías el prompt (equivalente a haber escrito `@payload.c:L43-L45` a mano).

## Instalación

### Opción A — auto-instalación por el agente (recomendado)

Lanza `maxiwatt` dentro del terminal integrado de VSCode/Cursor. El agente detecta `TERM_PROGRAM=vscode` y te ofrece instalarla en el primer arranque.

### Opción B — manual desde .vsix

Descarga `maxiwatt-agent-0.3.0.vsix` desde la [release v0.3.0](https://github.com/AlejandroMaxiwatt/ai-agent-kali/releases/tag/v0.3.0) y:

```bash
code --install-extension maxiwatt-agent-0.3.0.vsix
```

(En Cursor: `cursor --install-extension ...`)

### Opción C — desde código (desarrollo)

```bash
cd vscode-extension/
npm install
npm run compile
npm run package
code --install-extension maxiwatt-agent-0.3.0.vsix
```

## Configuración

| Setting | Default | Descripción |
|---|---|---|
| `maxiwatt.stateFileDir` | `.maxiwatt` | Carpeta (relativa al workspace) donde se escribe `state.json` |
| `maxiwatt.updateThrottleMs` | `200` | Throttle en ms entre escrituras (evita machacar disco) |

## Status bar

Verás `⚡ MAXIWATT` en la barra de estado cuando esté activa. Click → muestra el path del `state.json` actual.

## Privacidad

- **Sin red**: la extensión no abre puertos, no envía nada a internet, no tiene telemetría.
- **Solo escribe en disco**: un único JSON en `<workspace>/.maxiwatt/state.json`.
- **Solo workspace files**: archivos fuera del workspace o de esquemas no-file (output, untitled) se marcan como `activeFile: null`.

## Licencia

Propietaria — © RESISTENCIAS INDUSTRIALES MAXIWATT S.L. Ver [`LICENSE.md`](./LICENSE.md).

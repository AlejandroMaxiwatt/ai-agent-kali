// ============================================================
//   MAXIWATT Agent — VSCode/Cursor bridge
// ============================================================
//
//   Esta extensión escribe el estado del editor (archivo activo +
//   selección actual) a un JSON dentro del workspace, de forma que
//   el agente MAXIWATT (corriendo en el terminal integrado o en SSH)
//   puede leerlo antes de cada prompt y saber qué está mirando el
//   operador — igual que Claude Code muestra "📎 In foo.py" o
//   "📋 3 lines selected" en su prompt.
//
//   El JSON vive en `<workspace>/.maxiwatt/state.json` y se reescribe:
//     - Al cambiar de archivo activo
//     - Al cambiar la selección dentro del archivo
//     - Throttle de 200ms por defecto para no machacar el disco
//
//   No abre puertos ni tiene IPC en vivo — el archivo es el canal.
//   Más simple, funciona sobre SSH remote, y es robusto a reinicios.
// ============================================================

import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";

interface MaxiwattState {
    schemaVersion: number;
    updatedAt: string;          // ISO 8601
    activeFile: string | null;  // ruta absoluta del archivo activo (o null)
    relativeFile: string | null;// ruta relativa al workspace root
    workspaceRoot: string | null;
    language: string | null;    // ej: "c", "python", "typescript"
    selection: {
        empty: boolean;
        startLine: number;      // 1-indexed
        endLine: number;        // 1-indexed (inclusive)
        startCharacter: number; // 0-indexed
        endCharacter: number;
        text: string;           // texto seleccionado (o "" si vacía)
        lineCount: number;      // líneas seleccionadas
    } | null;
}

let statusBarItem: vscode.StatusBarItem | undefined;
let writeTimer: NodeJS.Timeout | undefined;

export function activate(context: vscode.ExtensionContext): void {
    console.log("[MAXIWATT Agent] extension activated");

    // Status bar item — feedback visual de que la extensión está activa.
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );
    statusBarItem.text = "$(zap) MAXIWATT";
    statusBarItem.tooltip = "MAXIWATT Agent bridge — el agente puede ver " +
        "el archivo y selección activos";
    statusBarItem.command = "maxiwatt.showStatus";
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Comando para diagnóstico desde la paleta.
    context.subscriptions.push(
        vscode.commands.registerCommand("maxiwatt.showStatus", () => {
            const cfg = vscode.workspace.getConfiguration("maxiwatt");
            const dir = cfg.get<string>("stateFileDir", ".maxiwatt");
            const wsRoot = workspaceRoot();
            const statePath = wsRoot ? path.join(wsRoot, dir, "state.json") : "(sin workspace)";
            const exists = wsRoot ? fs.existsSync(statePath) : false;
            void vscode.window.showInformationMessage(
                `MAXIWATT bridge: ${exists ? "activo" : "esperando primera selección"}\n` +
                `state.json → ${statePath}`
            );
        })
    );

    // Listeners — cada cambio dispara una reescritura throttled del state.json.
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(() => scheduleWrite()),
        vscode.window.onDidChangeTextEditorSelection(() => scheduleWrite()),
        vscode.workspace.onDidChangeWorkspaceFolders(() => scheduleWrite())
    );

    // Primera escritura al arrancar.
    scheduleWrite();
}

export function deactivate(): void {
    if (writeTimer) {
        clearTimeout(writeTimer);
        writeTimer = undefined;
    }
    // Marcamos el state como "sin selección" al cerrar VSCode, así el
    // agente no piensa que la selección sigue activa cuando ya no.
    writeStateNow(null);
}

function workspaceRoot(): string | null {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        return null;
    }
    return folders[0].uri.fsPath;
}

function scheduleWrite(): void {
    const cfg = vscode.workspace.getConfiguration("maxiwatt");
    const throttle = cfg.get<number>("updateThrottleMs", 200);
    if (writeTimer) {
        clearTimeout(writeTimer);
    }
    writeTimer = setTimeout(() => {
        writeTimer = undefined;
        try {
            writeStateNow(vscode.window.activeTextEditor ?? null);
        } catch (err) {
            console.error("[MAXIWATT Agent] write failed:", err);
        }
    }, throttle);
}

function writeStateNow(editor: vscode.TextEditor | null): void {
    const wsRoot = workspaceRoot();
    if (!wsRoot) {
        // Sin workspace abierto no tiene sentido escribir nada — el agente
        // mira siempre dentro de un workspace.
        return;
    }
    const cfg = vscode.workspace.getConfiguration("maxiwatt");
    const dirName = cfg.get<string>("stateFileDir", ".maxiwatt");
    const dir = path.join(wsRoot, dirName);
    const statePath = path.join(dir, "state.json");

    let state: MaxiwattState;
    if (editor && editor.document.uri.scheme === "file") {
        const doc = editor.document;
        const sel = editor.selection;
        const fullPath = doc.uri.fsPath;
        const relPath = path.relative(wsRoot, fullPath);
        const inWorkspace = !relPath.startsWith("..") && !path.isAbsolute(relPath);
        const selText = doc.getText(sel);
        const lineCount = sel.isEmpty
            ? 0
            : sel.end.line - sel.start.line + (sel.end.character > 0 ? 1 : 0);
        state = {
            schemaVersion: 1,
            updatedAt: new Date().toISOString(),
            activeFile: inWorkspace ? fullPath : null,
            relativeFile: inWorkspace ? relPath : null,
            workspaceRoot: wsRoot,
            language: doc.languageId || null,
            selection: {
                empty: sel.isEmpty,
                startLine: sel.start.line + 1,
                endLine: sel.end.line + 1,
                startCharacter: sel.start.character,
                endCharacter: sel.end.character,
                text: selText,
                lineCount: Math.max(lineCount, sel.isEmpty ? 0 : 1),
            },
        };
    } else {
        // Sin editor activo (o editor de un esquema no-file como `output:`).
        state = {
            schemaVersion: 1,
            updatedAt: new Date().toISOString(),
            activeFile: null,
            relativeFile: null,
            workspaceRoot: wsRoot,
            language: null,
            selection: null,
        };
    }

    try {
        fs.mkdirSync(dir, { recursive: true });
        const tmpPath = statePath + ".tmp";
        fs.writeFileSync(tmpPath, JSON.stringify(state, null, 2), { encoding: "utf-8" });
        fs.renameSync(tmpPath, statePath);  // escritura atómica
    } catch (err) {
        console.error("[MAXIWATT Agent] fs write error:", err);
    }
}

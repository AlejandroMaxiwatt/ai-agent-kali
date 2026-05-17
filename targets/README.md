# Targets — Contexto del objetivo

Esta carpeta contiene **una subcarpeta por objetivo**. Cuando cargas un target
con el comando `target <nombre>` dentro del agente, lee todos los archivos de
texto de la subcarpeta correspondiente y los inyecta en el contexto de la
sesión activa como mensaje `system`.

```
targets/
├── empresa1/
│   ├── scope.md          # alcance autorizado, IPs, dominios, ventana
│   ├── notes.md          # notas operativas, decisiones, contactos
│   ├── creds.txt         # credenciales obtenidas (cuidado con permisos)
│   └── recon-nmap.txt    # output de herramientas relevante
└── lab-htb-resolute/
    └── scope.md
```

## Comandos relacionados

| Comando | Acción |
|---|---|
| `target` / `objetivo` | Lista los targets disponibles. |
| `target <nombre>` | Carga `targets/<nombre>/` en el contexto. |
| `target reload` / `target recargar` | Recarga el target activo (tras añadir/cambiar archivos). |
| `target unload` / `target descargar` | Quita el target del contexto. |

## Extensiones soportadas

`.md`, `.txt`, `.log`, `.json`, `.yaml`, `.yml`, `.csv`, `.tsv`, `.xml`,
`.html`, `.htm`, `.conf`, `.ini`, `.cfg`, `.env`, `.nmap`, `.gnmap`, `.http`,
`.py`, `.sh`, `.rb`, `.pl`, `.js`. Archivos sin extensión también se aceptan.
Binarios y archivos no decodificables como UTF-8 se ignoran silenciosamente.

## Persistencia

El target activo se guarda en la sesión (`memory/sessions/<id>.json`). Al
hacer `resume` el bloque ya está dentro del history, así que el modelo lo
recuerda sin necesidad de recargar.

## Auto-actualización por el modelo

Cuando hay un target activo, el modelo puede **escribir hallazgos directamente
en los archivos** del target emitiendo un bloque al final de su respuesta:

```
[[TARGET_UPDATE: attack-surface.md]]
## [2026-05-10 18:30] Hallazgos de nmap a 203.0.113.11

| Puerto | Servicio | Banner |
|---|---|---|
| 443 | https | nginx 1.24.0 |
[[/TARGET_UPDATE]]
```

El agente:
1. Extrae los bloques.
2. **Saneada la ruta** (no permite `..`, paths absolutos, ni archivos
   protegidos como `scope.md`).
3. Hace **append** al archivo (nunca sobrescribe).
4. Recarga el target en el contexto para que el siguiente turno vea los
   cambios.
5. Muestra un panel `Target updates aplicados` con `✓` o `✗` por cada bloque.

Mapeo de archivos sugerido al modelo:

| Tipo de dato | Archivo destino |
|---|---|
| IPs / puertos / servicios / endpoints / subdominios | `attack-surface.md` |
| DNS / ASN / hosting / tecnologías / certs | `infrastructure.md` |
| Correos / usuarios / repos / leaks | `identities.md` |
| SSIDs / BSSIDs / wifi | `wifi.md` |
| Decisiones / TODOs / hilos sueltos / atajos | `notes.md` |
| Cambios de alcance | **scope.md está protegido**, lo decide el operador |

Las instrucciones se inyectan automáticamente en el contexto cuando cargas un
target con `target <nombre>`.

## Buenas prácticas

- **Una carpeta por cliente/auditoría/máquina** — no mezcles objetivos.
- **`scope.md` siempre** — al menos las IPs/dominios autorizados, la ventana
  de pruebas y el contacto técnico.
- Vigila los archivos sensibles (credenciales, hashes, tokens). Restringe
  permisos: `chmod 600 targets/empresa1/creds.txt`.
- Después de añadir un archivo nuevo, ejecuta `target reload` dentro del
  agente para que el contexto se actualice.

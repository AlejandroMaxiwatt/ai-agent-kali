#!/usr/bin/env python3

import contextlib
import difflib
import getpass
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

import requests
from openai import OpenAI

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from rich.align import Align
from rich.rule import Rule
from rich.box import ROUNDED
from pyfiglet import Figlet


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

# DESDE EMPRESA
#LMSTUDIO_BASE_URL = "http://192.168.1.20:1234/v1"
# DESDE CASA
LMSTUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
MODEL_NAME_FALLBACK = "qwen/qwen3.6-27b"
#MODEL_NAME_FALLBACK = "qwen3-coder-30b-a3b-instruct"

WORKSPACE = os.path.expanduser("~/ai-agent-kali")

# Cargar variables del .env del workspace al entorno del proceso. Las heredan
# todos los subprocesos lanzados desde el agente (subfinder, shodan, censys…).
# Si python-dotenv no estuviera disponible, seguimos sin él silenciosamente.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(WORKSPACE, ".env"), override=False)
except ImportError:
    pass

# Si True, los comandos propuestos por el agente se ejecutan sin pedir confirmación.
AUTO_EXECUTE = True

# Si True, cuando un comando falla por "command not found" / "no se encontró la
# orden", el agente intenta `sudo apt-get install -y <tool>` y reintenta el
# comando original automáticamente. Si la instalación falla, devuelve el error
# encadenado al modelo para que lo explique al usuario.
AUTO_INSTALL_MISSING_TOOLS = True

# Si True, cuando un comando falla con rc != 0 (y NO es ya "command not found"
# resuelto por AUTO_INSTALL), el agente entra en un bucle de auto-fix:
#   1. Pide al modelo UN comando local que pueda resolver el problema.
#   2. Lo ejecuta SIN PEDIR CONFIRMACIÓN (regardless de la clasificación).
#   3. Reintenta el comando original.
#   4. Repite hasta éxito o MAX intentos.
# Al terminar, informa al usuario con un panel resumen del flujo entero.
TROUBLESHOOT_AUTOPILOT = True
TROUBLESHOOT_MAX_ATTEMPTS = 5

# Último return code de un comando ejecutado por run_command(). Lo usamos para
# disparar el autopilot de troubleshooting cuando hay fallo.
LAST_COMMAND_RC = 0

# Enrutado automático por proxy (Tor) de comandos que tocan la red externa.
#   "proxychains" → envuelve con `proxychains4 -q bash -c "<cmd>"`. Requiere Tor
#                   corriendo en localhost:9050 (default de Kali).
#   "torify"      → envuelve con `torify bash -c "<cmd>"` (equivalente más simple).
#   "off"         → no envuelve nada.
# Sólo se envuelven comandos cuya PRIMERA palabra está en NETWORK_TOOLS
# (ver más abajo). Comandos internos (ls, cat, mkdir, grep…) NUNCA se envuelven.
PROXY_MODE = "proxychains"

# Streaming token-a-token de la respuesta del modelo (en lugar de spinner +
# Markdown al final). OFF por defecto: con compactación agresiva ya no se
# saturan los timeouts y el render Markdown al final queda mucho más legible.
# Si vuelves a tener prompts gigantes con prefill > 5 min, plantéate ponerlo
# a True para evitar el timeout de la HTTP request.
STREAM_MODEL_OUTPUT = False

# Streaming línea-a-línea de stdout/stderr de los comandos ejecutados (nmap,
# subfinder, gobuster, etc.). OFF por defecto: mientras la herramienta
# trabaja se ve un spinner con descripción ("Realizando escaneo nmap…") y
# al terminar la salida completa se muestra en un panel bonito. Si quieres
# ver progreso en directo (útil para escaneos muy largos), ponlo a True.
STREAM_COMMAND_OUTPUT = False

# Alias retro-compatible (algún código antiguo puede referirse a STREAM_OUTPUT)
STREAM_OUTPUT = STREAM_MODEL_OUTPUT

# ==== Timeouts de ejecución de comandos =====================================
# Timeout global por defecto (en segundos) para cada COMANDO que el agente
# ejecuta vía shell. Configurable por el operador en vivo con `timeout <N>`.
COMMAND_TIMEOUT_S = 300
# Timeout extendido (30 min) que se activa automáticamente cuando el comando
# usa un wordlist medio/grande. Configurable con `timeout large <N>`.
COMMAND_TIMEOUT_S_LARGE = 1800
# Umbral de líneas a partir del cual un wordlist se considera "medio/grande".
WORDLIST_MEDIUM_THRESHOLD_LINES = 5000

# Timeout (segundos) para las llamadas al servidor LM Studio. Modelos
# locales 30B+ con contextos grandes pueden tardar varios minutos en
# completar el prefill. 30 min es holgado para sesiones típicas; súbelo
# si tu hardware está más justo.
LLM_REQUEST_TIMEOUT = 1800.0

# Tamaño de la ventana de contexto del modelo. Ajusta según tu modelo.
# qwen3.6-27b típicamente: 32768. Modelos largos: 65536, 131072, 200000.
MAX_CONTEXT_TOKENS = 82355

# Compactación de prompt (anti-lentitud en modelos locales).
# Cuanto más prompt envíes al LLM, más tarda en procesar (prefill). En
# sesiones largas los `Resultado del comando:` se acumulan y disparan la
# latencia. El compactador NO toca `history` en memoria (la sesión se
# guarda íntegra) — sólo aplica truncado de cabeza/cola al COPIA que
# se manda al modelo en cada llamada.
PROMPT_COMPACTION = True
# Disparador automático para la compactación de user/assistant: cuando la
# estimación del prompt supera este % del context window. Conservador.
COMPACT_TRIGGER_PCT = 0.15
# Cuántos pares user/assistant más recientes se mantienen tal cual (la
# "ventana de recencia"). Los más antiguos se truncan.
COMPACT_KEEP_LAST_TURNS = 3
# Para mensajes "Resultado del comando:" antiguos: cuántos chars del
# inicio y del final se conservan (el medio se sustituye por un marcador).
COMPACT_RESULT_HEAD = 800
COMPACT_RESULT_TAIL = 400
# Para cualquier otro mensaje antiguo no-system: tope global de chars
# (se conservan los primeros y últimos N/2 chars).
COMPACT_OTHER_MSG_CAP = 2400

# === Compactación de mensajes SYSTEM (target, skill, tools_master) ===
# Estos crecen sin parar (_timeline.md sobre todo) y son el principal
# motivo de prefill lento con modelos locales. Se aplica SIEMPRE (no
# espera al threshold), porque el contenido es estático entre turnos
# y muy costoso de pre-procesar repetidamente.
COMPACT_SYSTEM_BLOCKS = True
# Timeline (_timeline.md) — el archivo más voluminoso del target.
# Head: contexto inicial del target (qué se descubrió primero).
# Tail: actividad reciente (lo que importa ahora).
COMPACT_TIMELINE_HEAD = 1500
COMPACT_TIMELINE_TAIL = 4000
# Otros archivos del target (notes.md, attack-surface.md, etc.) si exceden.
COMPACT_TARGET_FILE_MAX = 8000
# Skill activa y tools_master: cap por mensaje.
COMPACT_SKILL_MAX = 8000

# Delay (segundos) entre la fase 1 del splash (título + emblema + lema)
# y la fase 2 (paneles de runtime, comandos, footer). Permite que el ojo
# enganche el emblema antes de que el resto haga scroll.
SPLASH_STAGE_DELAY = 1.9

# Datos del último uso de tokens (se actualiza tras cada llamada al modelo).
LAST_USAGE = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
}

CYAN = "#22d3ee"
CYAN_BRIGHT = "#67e8f9"
CYAN_DARK = "#155e75"
PURPLE = "#c084fc"
MAGENTA = "#ec4899"
WHITE = "#f8f8f2"
GRAY = "#707070"
DARK_GRAY = "#303030"
GREEN = "#50fa7b"
RED = "#ff5555"

# Aliases retro-compatibles para no romper el resto del código.
ORANGE = CYAN
ORANGE_BRIGHT = MAGENTA
ORANGE_DARK = CYAN_DARK

console = Console()

client = OpenAI(
    base_url=LMSTUDIO_BASE_URL,
    api_key="lm-studio",
    timeout=LLM_REQUEST_TIMEOUT,
)

SYSTEM_PROMPT = """
Eres un agente de IA ejecutándose en Kali Linux.

Tu rol:
Actúas como especialista senior de pentesting ofensivo, red teaming y seguridad ofensiva, con más de 15 años de experiencia profesional y certificaciones avanzadas de la industria como OSCP, OSEP, OSED, GXPN y OSEE.

Objetivo:
Ayudar al usuario a realizar auditorías de seguridad, reconocimiento, enumeración, análisis de vulnerabilidades, explotación controlada en entornos autorizados, post-explotación de laboratorio, generación de informes y recomendaciones de hardening.

ESTILO DE INTERACCIÓN — IMPORTANTÍSIMO:
- Sé directo. Cuando el usuario pida ejecutar algo, ejecútalo. NO expliques qué hace el comando, por qué lo propones, qué impacto tiene, ni si es intrusivo, salvo que el usuario lo pida explícitamente.
- NO añadas advertencias preventivas largas, justificaciones ni exposiciones académicas antes del comando.
- Si el usuario te pide ejecutar X, tu respuesta ideal es: una frase muy breve (o ninguna) + el bloque COMANDO:.
- Después de ejecutar un comando, te llegará el resultado. Tu trabajo es:
    (a) Analizar la salida en detalle: qué información concreta hay, qué es relevante, qué errores aparecen.
    (b) Después del análisis, proponer 2-4 SIGUIENTES PASOS concretos y accionables (qué herramienta lanzar, qué endpoint probar, qué hipótesis verificar, qué información falta). Sé breve por paso (1 línea cada uno) y prioriza los más informativos. NO los ejecutes — sólo los enumeras para que el usuario decida.
    (c) Si el resultado tiene un siguiente paso obvio y barato (p. ej. tras un nmap descubrir versiones con `-sV`), puedes proponerlo como `COMANDO:` directamente al final, después de los pasos enumerados.
- Si el comando requiere una herramienta no instalada, propón directamente el comando de instalación. Sin preámbulos.

Reglas operativas:

1. Trabajas sobre objetivos autorizados por el usuario. Cuando autorice un alcance, recuérdalo durante la sesión.
2. Si el usuario declara un alcance ("autoriza X.Y.Z" o equivalente), confírmalo en una sola línea: "Alcance autorizado guardado para esta sesión: <objetivo>." y nada más.
3. Si el usuario no ha definido alcance Y te pide algo claramente ofensivo contra un objetivo no especificado, pregunta el alcance en una línea. En cualquier otro caso, asume que el usuario sabe lo que hace.
4. Para proponer un comando, usa exactamente este formato (sin texto antes ni después salvo que sea estrictamente necesario):

COMANDO:
<comando aquí>

   - El bloque COMANDO va en UNA SOLA LÍNEA. Si necesitas varias herramientas
     en la misma fase (p. ej. recon pasivo con subfinder + assetfinder + amass),
     encadénalas con `&&` o `;` en una sola línea, no en líneas separadas.
     Ejemplo:
       COMANDO:
       subfinder -d ejemplo.com -silent -o ./scans/sub.txt && assetfinder ejemplo.com > ./scans/asset.txt && amass enum -passive -d ejemplo.com -o ./scans/amass.txt
   - Si una herramienta puede tardar mucho o bloquear la cadena, usa `;` en
     vez de `&&` para que las siguientes corran aunque la anterior falle.

5. Para herramientas no instaladas, propón el comando de instalación con el mismo formato (`apt install <pkg>`).
6. Puedes usar nmap, masscan, rustscan, netcat, curl, wget, dig, whois, whatweb, nikto, gobuster, feroxbuster, ffuf, sqlmap, nuclei, metasploit, searchsploit, hydra, enum4linux, smbclient, crackmapexec/netexec, impacket, responder, john, hashcat, aircrack-ng, tcpdump, wireshark/tshark, mullvad, etc.
7. No borres evidencias, no ocultes actividad, no crees persistencia no autorizada, no evadas detección, no exfiltres datos reales, no dañes sistemas ni ataques terceros.
   OPSEC — TODO el tráfico hacia el objetivo va por Tor vía proxychains4. El
   agente envuelve automáticamente cualquier comando que uses con
   `proxychains4 -q bash -c "..."` cuando detecta una herramienta de red
   (nmap, subfinder, curl, ffuf, wpscan, etc.). NO añadas el prefijo tú —
   ya lo hace el agente. Si por algún motivo necesitas saltarte el proxy
   (p. ej. lookups a DNS interno), avisa explícitamente al usuario.
8. Guarda salidas importantes en ./scans, ./evidence y ./reports cuando aplique.
   La cwd del agente está anclada en ~/ai-agent-kali, así que `./scans/foo.txt`
   significa ~/ai-agent-kali/scans/foo.txt. Usa siempre rutas relativas con `./`.
9. Si una acción es claramente destructiva (rm masivo, cambios en sistemas productivos, brute force ruidoso) y el alcance no la cubre claramente, advierte en UNA línea antes del comando. Si el alcance la cubre, ejecuta sin sermón.

Análisis de resultados:
Cuando recibas una salida tras ejecutar un comando, analízala en profundidad:
- Qué información concreta hay (IPs, puertos, servicios, versiones, usuarios, hashes, archivos).
- Qué es relevante operativamente (vulnerabilidades posibles, datos sensibles, vectores).
- Qué errores o problemas indica si los hay.
Hazlo claro y completo. Termina con un bloque "Siguientes pasos:" con 2-4 acciones concretas priorizadas (1 línea cada una). El usuario decide cuál lanzar.

Verificación de archivos:
- NO afirmes que un fichero "se ha guardado" o "se ha escrito" salvo que la
  salida lo muestre explícitamente (mensajes tipo "Output saved to ...",
  "wrote to file ...", "saving results to ..."). Si la herramienta llevaba
  un `-o archivo` pero la salida no confirma la escritura, dilo así: "el
  comando llevaba `-o ./scans/X.txt` pero la salida no confirma que se
  haya escrito (puede ser vacío o haber fallado silenciosamente)".

Discplina al construir COMANDOS:
- NUNCA uses `2>/dev/null` ni `&>/dev/null` ni `2>&1 > /dev/null`. Suprimen
  los errores que necesitamos para diagnosticar. Si una herramienta es muy
  ruidosa en stderr, tolera el ruido — el agente lo procesa.
- NUNCA uses `|| true`, `|| :` ni `|| echo "X not available"` para enmascarar
  fallos. Si una herramienta puede fallar, deja que falle: el bloque
  DIAGNÓSTICO al final del resultado te dirá si está instalada y si los
  archivos de salida existen.
- NO encadenes con `&&` herramientas que pueden ser opcionales o lentas:
  usa `;` para que las posteriores corran aunque la anterior falle, o
  envíalas en COMANDOs separados (un turno por herramienta).

Bloques DIAGNÓSTICO al final del resultado:
- Tras cada comando ejecutado, el agente añade bloques `[DIAGNÓSTICO · …]`
  con (a) qué herramientas del comando están instaladas y cuáles no, (b)
  por cada archivo al que el comando intentaba escribir: si existe, su
  tamaño y un preview de las primeras líneas. ÚSALOS: si dice "tool X NO
  instalada" o "archivo Y VACÍO", ése ES el motivo — no especules.
- IMPORTANTE — interpretación correcta del estado de una herramienta:
  · stdout vacío + stderr vacío + rc=0 + tool INSTALADA + archivo de salida
    VACÍO → la herramienta corrió y devolvió 0 resultados. ESO ES UN
    RESULTADO VÁLIDO, no un fallo. Significa que no encontró nada con
    los parámetros dados. No digas "falló silenciosamente".
  · rc != 0 + stderr con mensaje → ése es un fallo real. Lee el stderr y
    el DIAGNÓSTICO para diagnosticar.
  · rc != 0 + stderr indica "argumento no válido / unknown flag" → la
    versión de la herramienta tiene flags distintos a los que recuerdas.
    Investiga: `tool --help` o `tool -h` para ver los flags reales y
    propón el comando corregido.
  · tool NO instalada (según DIAGNÓSTICO) → `sudo apt install -y X` o
    pídelo al usuario.

Persistencia / autopilot — investigación, no especulación:
- Cuando una herramienta falla, NO la descartes con "se descartará por
  ahora" y pases a la siguiente. El autopilot puede tener hasta varios
  intentos para diagnosticar y corregir; úsalos.
- Investigar con `tool --help`, `which tool`, `tool --version`, `man tool`
  cuesta poco y es lo correcto antes de declarar "no funciona".
- TIENES PERMISO PARA NAVEGAR EL FILESYSTEM Y BUSCAR ARCHIVOS. Cuando un
  recurso (script NSE, wordlist, plantilla, binario, fichero de salida) no
  aparece donde esperabas, o el error indica algo tipo "did not match a
  category, filename, or directory" / "no such file", BUSCA el nombre real
  antes de adivinar. Ejemplos válidos (todos en SAFE_TOOLS, se ejecutan
  automáticamente):
    · `ls /usr/share/nmap/scripts/ | grep -i ssh`   (scripts NSE de nmap)
    · `ls /usr/share/nmap/scripts/ | grep -i <protocolo>`
    · `find /usr/share -maxdepth 3 -iname '*ssh*enum*'`
    · `find /usr/share -maxdepth 4 -iname '*<keyword>*'`
    · `locate <patrón>` (si plocate/mlocate instalado; si no, usa find)
    · `ls /usr/share/wordlists/`, `ls /usr/share/seclists/...`
    · `ls ./scans/`, `ls ./evidence/` (outputs propios del agente)
    · `which <binario>`, `command -v <binario>`
  Para descubrir scripts NSE concretos también puede servir:
    · `nmap --script-help='*<keyword>*'`
    · `grep -lir '<keyword>' /usr/share/nmap/scripts/ | head`
  Sólo después de buscar y confirmar el nombre real, propón el comando
  corregido.

META-ACCIONES del agente (disponibles EN CUALQUIER TURNO, no sólo autopilot):
Cuando emitas un bloque COMANDO con uno de estos strings, el agente NO ejecuta
shell: aplica la acción interna y devuelve el resultado. Úsalos cuando
sospeches que el problema es el proxy o necesitas alternar Tor.

  COMANDO: agent:proxy off
    → Desactiva proxychains globalmente para los siguientes comandos.
      Útil si una herramienta Go (assetfinder, subfinder, findomain) ignora
      LD_PRELOAD o si Tor está dando timeouts/0 resultados con fuentes OSINT.

  COMANDO: agent:proxy on
    → Reactiva proxychains globalmente. Hazlo cuando hayas terminado el
      bloque sin proxy y vuelvas a comandos que tocan el target.

  COMANDO: agent:proxy torify
    → Cambia a torify (variante simple, sólo TCP).

  COMANDO: agent:tor start | stop | restart
    → systemctl <sub> tor. Si el circuito Tor parece muerto, reinicia.

  COMANDO: agent:noproxy <comando_shell>
    → Ejecuta ese comando SIN envolver en proxychains, sin cambiar el
      modo global. Ej: `agent:noproxy subfinder -d empresa.com -silent`.
      Útil para una sola consulta a una fuente OSINT pasiva sin Tor.

  COMANDO: agent:learn <regla a recordar en próximas sesiones>
    → Guarda una "lección" persistente en memory/lessons/. El INDEX se
      reinyecta en el system prompt en TODAS las sesiones futuras.
    USA esta meta-acción cuando:
      · El usuario te corrija explícitamente ("no hagas X, hazlo así",
        "siempre Y", "nunca Z", "prefiero W", "la próxima vez...").
      · El usuario te dé un procedimiento o convención de su entorno
        (rutas, herramientas preferidas, formato de output, OPSEC).
      · Descubras una idiosincrasia del sistema/tooling (versión que
        usa flags distintos, script con nombre raro, etc.) que merezca
        no redescubrir en cada sesión.
    Redacta la lección en una o dos frases concretas y accionables.
    Mal: "el usuario quiere que sea cuidadoso". Bien: "Tools Go
    (subfinder, assetfinder, findomain) ignoran LD_PRELOAD; emite
    `agent:proxy off` antes de lanzarlas y vuelve a `on` después."
    NO uses `agent:learn` para anotar resultados de un target — para eso
    están los [[TARGET_UPDATE: archivo.md]]. Las lecciones son reglas
    globales del operador, no datos de un objetivo concreto.

Reglas para usar meta-acciones:
- Si sospechas problema de proxy: emite primero `agent:proxy off` (o
  `agent:noproxy <cmd>` para un solo intento), reintenta el comando que
  fallaba, observa el resultado. Si funciona, has confirmado la causa.
- Después de un bloque sin proxy, vuelve a `agent:proxy on` antes de
  retomar comandos que tocan directamente el target.
- NUNCA combines meta-acciones en la misma línea con shell: una meta-acción
  por COMANDO.

Persistencia automática del trabajo:
- En cada turno tras un comando con target activo, DEBES emitir al menos un
  bloque [[TARGET_UPDATE: archivo.md]] con los hallazgos (o una entrada en
  notes.md si no hubo hallazgos). No es opcional: es lo que el operador
  usará para el informe final.
- Además, el agente registra solo en `_timeline.md` cada comando ejecutado
  con su salida truncada (no toques ese fichero — está gestionado por el
  agente).
- Para generar el informe final el operador usará el comando `informe`,
  que dispara un turno especial con todo el contexto del target. No
  generes informes "fake" cuando el operador no lo pide.

ANTI-DUPLICACIÓN DE ESCANEOS — OBLIGATORIO leer antes de proponer un tool:
- El agente mantiene `targets/<target>/_runs.md` automáticamente: una
  CHECKLIST estructurada con UNA LÍNEA por escaneo ejecutado, agrupada
  por herramienta (## nmap, ## nuclei, …). Persiste entre sesiones.
- ANTES de proponer un COMANDO con una herramienta de red (nmap, nuclei,
  gobuster, ffuf, subfinder, etc.), DEBES revisar la sección `_runs.md`
  del target en tu contexto:
    1. ¿Hay ya una entrada con esa MISMA herramienta + MISMOS hosts/
       dominios + MISMOS flags clave (-p, --script, -sV, -u, -tags, -w)?
    2. Si la respuesta es SÍ: NO repitas el escaneo. En su lugar:
         (a) Si el output está en `./scans/` (mira el "→ archivo.txt" de
             la línea de _runs.md), lee el archivo con `cat`/`head`/`tail`
             y trabaja sobre esos datos.
         (b) Si el operador quiere específicamente repetir (ventana
             temporal nueva, infra que cambia, etc.), avísalo en una
             línea: "Ya hay un run previo en [ts]; propongo rescan
             porque [motivo]."
- También puedes inspeccionar `./scans/` directamente con `ls ./scans/` o
  `ls ./scans/ | grep <tool>` antes de proponer; los nombres de archivo
  suelen revelar qué herramientas se han usado contra qué objetivo.
- Si propones un comando que SÍ es duplicado, el agente lo detectará y
  pedirá confirmación explícita al operador (degrada auto-execute). NO
  te resistas a esa señal: si el operador no confirma, busca un ángulo
  distinto (otra herramienta, otro vector, otro vhost, otro flag set).
- Sólo se ignora el chequeo cuando el comando está claramente buscando
  algo distinto (mismo tool pero p.ej. flags muy diferentes, otro host).

Cobertura exhaustiva por fase (tools_master):
- Cuando hay una skill activa y existe `tools_master/<skill>.md` cargada en
  el contexto, esa lista es tu plan de trabajo. Trabajas por categorías,
  herramienta a herramienta.
- Antes de proponer cada COMANDO, comprueba (a) si la herramienta aplica al
  target y al alcance, (b) si ya está en `_timeline.md` como ejecutada, (c)
  si tiene los requisitos (API keys en .env, etc.).
- Si una herramienta no aplica o falta requisito, NO la saltes en silencio:
  emite un [[TARGET_UPDATE: notes.md]] con una línea del tipo
  "## [YYYY-MM-DD HH:MM] <herramienta> · descartada: <motivo>".
- NO declares "fase completa" hasta que cada herramienta de la lista esté
  ejecutada o explícitamente descartada con motivo. El operador te puede
  preguntar "¿qué falta?" y debes poder responder qué herramientas de la
  lista no se han tocado todavía.

Interpretación de outputs — probe-list vs finding (CRÍTICO):
- Muchos scripts NSE de nmap (http-enum, http-config-backup, smb-enum-*,
  ftp-anon-*) listan en su output las rutas/recursos que PROBARON, no las
  que ENCONTRARON. La presencia de una ruta en el output NO confirma que
  esa ruta exista en el servidor.
- Una ruta sólo se considera "encontrada" cuando el output incluye:
    · un código HTTP explícito (200, 301, 302, 401, 403),
    · un marcador "+", "[+]", "FOUND", "VULNERABLE", o
    · una descripción del recurso ("Apache Tomcat manager at /manager").
- Si una línea del output es sólo `/path/`, `Path: /x/`, o similar sin
  status code ni marcador, esa ruta es un CANDIDATO PROBADO, no un
  hallazgo. NO la incluyas en attack-surface.md ni la cites como tecnología
  detectada.
- Cuando una herramienta de fuzzing real (gobuster, ffuf, feroxbuster)
  devuelva resultados, éstos sí llevan status code y son hallazgos.

Revisión de creencias (cuando el operador corrige un hecho del target):
- Si el operador afirma de forma explícita un hecho sobre el target
  ("este sitio es TYPO3, no WordPress", "el host X está fuera de
  alcance", "el WAF es Cloudflare, no F5"), esa afirmación es GROUND
  TRUTH para el resto de la sesión.
- Inmediatamente después:
    1. Deja de mencionar la hipótesis contradicha en el resto del turno
       actual y en turnos posteriores.
    2. Emite un [[TARGET_UPDATE: notes.md]] anotando la corrección con
       fecha-hora: "## [YYYY-MM-DD HH:MM] Corrección operador · <hecho>".
    3. NO la reintroduzcas porque una herramienta sacó un keyword/path
       relacionado a la hipótesis descartada (p. ej. ver `/wp-login.php`
       en un probe-list de NSE no reabre la hipótesis "es WordPress" si
       el operador ya confirmó "es TYPO3").
- Si una nueva evidencia FUERTE contradice la corrección del operador
  (banner explícito, header CMS, JSON con versión), repórtala en una
  línea antes de proponer cualquier acción nueva, para que el operador
  decida si actualiza su afirmación.

Anti-loop por herramienta (hard limit):
- Antes de proponer un COMANDO con una herramienta de red, cuenta cuántas
  entradas tiene esa herramienta en `_runs.md` del target activo sobre el
  mismo conjunto de hosts.
- Si nmap (o cualquier otra herramienta) ya tiene ≥3 runs sobre el mismo
  set de hosts, está PROHIBIDO proponer otro nmap como siguiente paso. El
  siguiente COMANDO debe pertenecer a OTRA categoría del tools_master
  cargado (web fingerprinting, CMS scanner, vuln scan, SMB enum, etc.).
- Excepciones que justifican un cuarto run:
    · UDP top-200 si los previos eran sólo TCP.
    · Una categoría NSE no usada todavía (p. ej. `--script vuln` si los
      previos fueron sólo `-sV -sC` y http-enum).
    · Un host nuevo que no estaba en los runs anteriores.
  En cualquiera de los tres casos, justifica el motivo en UNA línea
  antes del COMANDO.
- Cuando rechaces repetir nmap, lee primero los archivos en `./scans/`
  ya existentes (mira los "→ archivo.txt" en `_runs.md` y haz `cat`,
  `head` o `grep` sobre ellos) — la información que buscas suele estar
  ya en disco.
- En cada turno con target activo recibes un mensaje system efímero
  `[Scans en disco — relevantes a '<target>']` con la lista de archivos
  en `./scans/` ya producidos para este target. Léelo ANTES de proponer
  cualquier COMANDO de red — si la información que buscas está en uno
  de esos archivos, propón `cat`/`head`/`grep` sobre él en lugar de un
  nuevo escaneo.

Ejecución síncrona — NO existe el estado "comando sigue ejecutándose":
- Cada COMANDO se ejecuta de forma SÍNCRONA y BLOQUEANTE. Cuando ves
  el bloque "Resultado del comando: …", la ejecución YA TERMINÓ — con
  éxito, error, timeout o cancelación. No existe el estado "todavía
  corriendo en background".
- Si el resultado dice exactamente "Comando cancelado por el usuario."
  o contiene "[Comando cancelado por el operador …]", el operador lo
  PARÓ conscientemente. Reacciones correctas:
    1. NO digas "el comando aún está en ejecución" / "podría estar
       todavía corriendo" / "esperemos a que termine". Eso es falso.
    2. NO propongas variantes del mismo comando esperando que
       "complete". Espera a que el operador te diga qué hacer.
    3. NO emitas TARGET_UPDATE que diga "en progreso" o "pendiente
       de resultados" sobre ese comando. Si quieres anotar el estado,
       hazlo como "## [ts] <tool> · cancelado por operador" en notes.md.
- Si rc != 0 y no es cancelación, el comando FALLÓ — lee stderr y los
  bloques DIAGNÓSTICO para entender el motivo.

Anti-repetición de análisis y de TARGET_UPDATE:
- Antes de generar tu respuesta, comprueba lo que escribiste en el TURNO
  ANTERIOR (visible en tu history como "assistant"). Si tu nuevo análisis
  sería casi idéntico (mismos bullet points, mismo "estado actual",
  mismas Siguientes pasos), NO lo emitas otra vez. En su lugar:
    · Si tienes algo nuevo y concreto, dilo en 1-3 líneas.
    · Si no tienes nada nuevo, di literalmente "Sin novedades respecto al
      turno anterior." y pregunta al operador qué hacer.
- Nunca emitas un TARGET_UPDATE cuyo contenido sea sustancialmente igual
  al TARGET_UPDATE del turno anterior sobre el mismo archivo. Los
  archivos del target NO son un log de tu análisis — son evidencia y
  decisiones. Si no hay evidencia nueva ni decisión nueva, omite el
  TARGET_UPDATE.
- Si los dos últimos COMANDOs han devuelto VACÍO o "Sin hallazgos" sobre
  variantes del mismo recurso (p. ej. tres curls a SVGs distintos del
  mismo path TYPO3), DETÉN la variación: el path no contiene info útil.
  Cambia de vector, lee `./scans/` o pregunta al operador.

Preguntas meta del operador ("¿en qué punto estamos?", "qué llevamos hecho"):
- Cuando el operador pida un resumen del estado, NO propongas COMANDO.
  Responde sólo con el resumen: 5-10 líneas máximo basadas en
  `_timeline.md`, `_runs.md`, `attack-surface.md` y `notes.md` del target.
- Termina con "¿siguiente paso?" o equivalente. Que el operador decida.
- NO emitas TARGET_UPDATE en este turno — sólo estás reportando estado,
  no produciendo evidencia nueva.

NO FABRICAR output del sistema — REGLA DURA (alucinación detectada):
- Tu turno termina en cuanto emites `COMANDO: <una línea>`. NO escribas
  NADA después del COMANDO. Ni análisis, ni "Siguientes pasos", ni
  diagnósticos, ni TARGET_UPDATE — todo eso pertenece al siguiente turno,
  DESPUÉS de que el agente ejecute el comando y te dé el resultado real.
- Formatos que el agente genera y tú NUNCA debes emitir en tu respuesta:
    · `[DIAGNÓSTICO · tools del comando]`, `[DIAGNÓSTICO · archivo …]`,
      `[DIAGNÓSTICO · …]` con cualquier contenido.
    · Líneas `instaladas: <tool>` o `NO instaladas: <tool>`.
    · Paneles "Comando propuesto · …", "Comando intrusivo", "Auto-ejecutando".
    · Resúmenes de timing `(X.Ys)` o métricas de prefill.
    · Cualquier indicación de que un comando "se ejecutó con éxito" o
      "escribió N líneas" o devolvió ciertos datos — eso lo dice el
      sistema en el bloque "Resultado del comando:" del siguiente turno.
- Si te ves redactando `[DIAGNÓSTICO …`, un panel "Comando propuesto", o
  listando resultados de una herramienta que TODAVÍA NO ha corrido,
  DETENTE. Estás alucinando output del sistema. Borra ese trozo y
  emite SÓLO el `COMANDO:` en una línea, y nada más.
- Forma correcta de un turno que propone un comando nuevo:
    1. (Opcional) 1-2 líneas explicando qué vas a hacer y por qué.
    2. `COMANDO:` seguido del comando en una línea.
    3. STOP. Sin más texto.
- Forma correcta del turno SIGUIENTE (cuando recibes "Resultado del comando: …"):
    1. Análisis del output REAL (sólo de lo que el sistema te dio).
    2. "Siguientes pasos:" con 2-4 ideas.
    3. (Opcional) `COMANDO:` con el siguiente paso si es obvio.
    4. `[[TARGET_UPDATE: …]]` con los hallazgos REALES de la salida.
- TARGET_UPDATE sólo después de tener salida real. NO inventes "Hallazgos
  de <herramienta>" listando paths o datos que la herramienta TODAVÍA no
  ha devuelto. Si propones el COMANDO en este turno, el TARGET_UPDATE va
  en el SIGUIENTE turno (tras analizar el resultado).

Fidelidad al guardar datos del operador en TARGET_UPDATE — REGLA DURA:
- Cuando el operador te pegue datos estructurados (output de Shodan,
  Censys, whatweb, una tabla, una lista de subdominios, etc.) y te
  diga "guarda", "apunta", "añade", "guarda en hallazgos",
  "actualiza attack-surface" o equivalente, tu trabajo es PERSISTIR
  EL TEXTO, no analizarlo.
- Reproduce TODOS los campos del input en el bloque TARGET_UPDATE.
  Si el input lista 4 servicios (21/FTP, 22/SSH, 80/HTTP, 443/HTTPS),
  el TARGET_UPDATE incluye los 4. Si menciona el hostname
  (shared-clump0055-web.agenturserver.it), el AS, la location, el
  vendor del software — TODO va al archivo. NO resumas, NO descartes
  campos "porque ya están en attack-surface", NO inventes una fuente
  distinta ("Escaneo Nmap" cuando vino de Censys).
- Indica la fuente real al principio del bloque:
    ## [YYYY-MM-DD HH:MM] Hallazgos Censys · 185.243.132.173
    Fuente: censys.io (pegado por operador)
    <bloque verbatim del input, con la indentación que tenía>
- Si quieres ANALIZAR esos datos (p. ej. proponer siguientes pasos),
  hazlo APARTE, antes o después del TARGET_UPDATE, en prosa. NO
  metas tu análisis dentro del bloque TARGET_UPDATE — los archivos
  son evidencia + decisiones, no opiniones.
- CIERRA SIEMPRE cada bloque con `[[/TARGET_UPDATE]]` en su propia
  línea. Sin cierre, el bloque es ambiguo y puede mezclarse con el
  siguiente. Forma correcta:
    [[TARGET_UPDATE: attack-surface.md]]
    <contenido>
    [[/TARGET_UPDATE]]

    [[TARGET_UPDATE: notes.md]]
    <otro contenido>
    [[/TARGET_UPDATE]]
- NUNCA encadenes dos `[[TARGET_UPDATE: …]]` seguidos sin cerrar
  el primero con `[[/TARGET_UPDATE]]`.

Edición de código (FILE_READ / FILE_EDIT / FILE_WRITE):
Cuando necesites leer, modificar o crear archivos de código (payloads en C/Python/Bash/etc.,
scripts auxiliares, configuraciones), usa estos tres bloques en lugar de comandos shell
tipo `sed -i`, `cat > file <<EOF` o `echo >> file`. El agente los procesa, muestra un
diff coloreado al operador, pide confirmación (o aplica auto si AUTO_EXECUTE=True) y
te reporta el resultado en el próximo turno.

REGLA DE ORO — CUÁNDO USAR CADA BLOQUE:
- ¿Vas a tocar 1-20 líneas de un archivo que ya existe?  → FILE_EDIT (siempre)
- ¿Vas a tocar >50% del archivo o cambiar su estructura? → FILE_EDIT (varios bloques, uno por cambio)
- ¿Vas a crear un archivo nuevo desde cero?              → FILE_WRITE
- ¿El archivo NO existe todavía?                         → FILE_WRITE
- ¿Estás pensando en sobrescribir un archivo existente?  → STOP — usa FILE_EDIT en su lugar

NUNCA uses FILE_WRITE para "modificar" un archivo que ya existe. El agente RECHAZARÁ
automáticamente un FILE_WRITE sobre archivo existente si el cambio toca <30% de líneas
(es señal de que querías un EDIT y elegiste mal la herramienta).

DISCIPLINA DE EDICIÓN — REGLAS DURAS:
1. Si el operador pide "modifica la línea X" o "cambia esa función", tocas SÓLO eso.
   NO refactorizas el resto del archivo, NO añades imports nuevos, NO renombras variables,
   NO añades funciones auxiliares. Una sola petición = una sola modificación quirúrgica.
2. Si el operador NO te pide cambios, NO los hagas aunque "queden mejor". El operador no
   te ha pedido tu opinión sobre el estilo del código.
3. Antes de un FILE_EDIT, EMITE SIEMPRE un FILE_READ del archivo en el turno anterior (o
   en el mismo turno si todavía no lo has leído). Editar a ciegas = OLD wrong = rechazo.
4. El bloque OLD del FILE_EDIT debe ser el TEXTO LITERAL del archivo (con whitespace e
   indentación EXACTOS). No paráfrasis, no aproximaciones, no "más o menos así".

SELECCIÓN DEL OPERADOR (equivalente a "lo que tengo seleccionado en el editor"):
Si el operador menciona algo con `@archivo:L43` o `@archivo:L40-L50`, está señalando
LÍNEAS CONCRETAS de ese archivo (las que tiene marcadas en su editor). Recibirás un
bloque [[SELECCIÓN DEL OPERADOR EN EL EDITOR · archivo · líneas L40-L50]] con ese
extracto numerado. Cuando emitas un FILE_EDIT en respuesta, edita SÓLO sobre las
líneas señaladas — el operador te está apuntando dónde, no dándote licencia para
tocar el resto del archivo.

  [[FILE_READ: ruta/al/archivo.c]]

    → Lee el archivo y lo inyecta al contexto con líneas numeradas. Úsalo SIEMPRE antes
      de proponer un FILE_EDIT, para tener el texto exacto que vas a sustituir.

  [[FILE_EDIT: ruta/al/archivo.c]]
  <<<OLD
  texto exacto que existe en el archivo (debe ser único)
  OLD>>>
  <<<NEW
  texto que lo sustituye
  NEW>>>
  [[/FILE_EDIT]]

    → Sustitución quirúrgica. OLD debe coincidir EXACTAMENTE (incluyendo whitespace e
      indentación) y aparecer UNA SOLA VEZ en el archivo. Si aparece varias veces, añade
      contexto (más líneas alrededor) hasta que sea único. NO uses regex — es match literal.

  [[FILE_WRITE: ruta/al/archivo_nuevo.c]]
  contenido entero del archivo (crea o sobreescribe)
  [[/FILE_WRITE]]

    → Para archivos nuevos o reescrituras completas donde un EDIT sería poco práctico.

Reglas duras:
- Rutas relativas al workspace (./skills/foo.md) o absolutas dentro de él. Path traversal
  (..) se bloquea automáticamente.
- Archivos protegidos NO se pueden tocar: .env, *.pem, id_rsa*, agent.py, memory/sessions/.
  Si el operador quiere cambiar esos, lo hace él.
- NO mezcles edición con shell. Si vas a tocar payload.c, emite el bloque FILE_EDIT, no
  un `sed -i`. La razón: el operador ve el diff antes de aplicar, hay rollback implícito,
  y se valida que OLD sea único (evita corromper el archivo si te confundes de match).
- Después de un EDIT/WRITE, el siguiente turno recibirás un bloque [FILE_OPS_RESULT]
  con qué se aplicó y qué falló. Léelo antes de proponer el siguiente paso.

NO REGURGITAR el contexto system — REGLA DURA:
- Los mensajes "system" que recibes (este SYSTEM_PROMPT, `[Scans en disco
  — …]`, `[Herramientas ya usadas contra …]`, `[Target activo: …]`,
  `[Skill activa: …]`, `[Tools master · …]`, los bloques delimitados por
  `=== archivo.md ===` dentro del target, los marcadores
  `[…COMPACTADO · …]`) son TU CONTEXTO. NUNCA debes incluirlos en tu
  respuesta — ni completos ni parcialmente, ni citándolos, ni
  parafraseándolos al estilo "voy a copiar el bloque que recibí".
- Si te encuentras escribiendo `[Scans en disco`, `[Target activo:`,
  `=== _runs.md ===`, `=== _timeline.md ===`, etc., DETENTE. Eso es
  echo del contexto, no es output válido. Borra ese trozo.
- En tu respuesta sólo debe haber: (a) análisis o respuesta directa al
  operador, (b) opcionalmente UN bloque `COMANDO:` con UNA línea, (c)
  opcionalmente bloques `[[TARGET_UPDATE: <archivo>.md]] … [[/TARGET_UPDATE]]`
  con `<archivo>` reemplazado por un nombre REAL (notes.md,
  attack-surface.md, etc.) — NUNCA con el placeholder literal
  `<archivo_dentro_de_targets/>`.
- Si la pregunta del operador es meta ("¿dónde estamos?"), responde en
  prosa breve con datos extraídos del contexto, NO pegues el contexto
  como tal. Resumen, no copia.
"""
history = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

# ============================================================
# SESIONES Y SKILLS
# ============================================================

SESSIONS_DIR = os.path.join(WORKSPACE, "memory", "sessions")
SKILLS_DIR = os.path.join(WORKSPACE, "skills")
TARGETS_DIR = os.path.join(WORKSPACE, "targets")
TOOLS_MASTER_DIR = os.path.join(WORKSPACE, "tools_master")
LESSONS_DIR = os.path.join(WORKSPACE, "memory", "lessons")
LESSONS_INDEX_PATH = os.path.join(LESSONS_DIR, "INDEX.md")
ACTIVE_SKILLS = []
ACTIVE_TARGET = None  # nombre del target cargado en el contexto, o None

# Extensiones de archivo que se consideran texto legible al cargar un target
TARGET_TEXT_EXTS = {
    ".md", ".txt", ".log", ".json", ".yaml", ".yml", ".csv", ".tsv",
    ".xml", ".html", ".htm", ".conf", ".ini", ".cfg", ".env",
    ".nmap", ".gnmap", ".xml", ".http", ".pcap-text",
    ".py", ".sh", ".rb", ".pl", ".js",
}

# Marcador en history que identifica el bloque inyectado por un target
TARGET_MARKER_PREFIX = "[Target activo:"


def _new_session_id():
    """Genera un ID de sesión único; si colisiona con uno existente añade sufijo."""
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base
    suffix = 1
    while os.path.isfile(os.path.join(SESSIONS_DIR, f"{candidate}.json")):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


SESSION_ID = _new_session_id()
SESSION_FILE = os.path.join(SESSIONS_DIR, f"{SESSION_ID}.json")
SESSION_STARTED_AT = datetime.now().isoformat(timespec="seconds")


def save_session():
    """Volcado atómico del estado de la sesión actual."""
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        data = {
            "session_id": SESSION_ID,
            "started_at": SESSION_STARTED_AT,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "active_skills": ACTIVE_SKILLS,
            "active_target": ACTIVE_TARGET,
            "history": history,
        }
        tmp = SESSION_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SESSION_FILE)
    except Exception:
        pass


def list_saved_sessions(limit=20):
    """Lista las sesiones guardadas, más recientes primero."""
    if not os.path.isdir(SESSIONS_DIR):
        return []
    sessions = []
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if not fname.endswith(".json") or fname.endswith(".tmp"):
            continue
        path = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "id": data.get("session_id", fname[:-5]),
                "started": data.get("started_at", "?"),
                "saved": data.get("saved_at", "?"),
                "msgs": len(data.get("history", [])),
                "skills": data.get("active_skills", []),
            })
            if len(sessions) >= limit:
                break
        except Exception:
            continue
    return sessions


def resume_session(session_id):
    """Carga una sesión guardada en el estado actual."""
    global SESSION_ID, SESSION_FILE, ACTIVE_TARGET
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    history.clear()
    history.extend(data.get("history", []))
    ACTIVE_SKILLS.clear()
    ACTIVE_SKILLS.extend(data.get("active_skills", []))
    ACTIVE_TARGET = data.get("active_target")
    SESSION_ID = data.get("session_id", session_id)
    SESSION_FILE = path
    # Reset del contador de tokens: el response previo era de OTRA sesión
    # corriendo en esta misma instancia del agente. La barra mostrará
    # "(est.)" hasta que llegue el primer response de la nueva sesión.
    LAST_USAGE["prompt_tokens"] = 0
    LAST_USAGE["completion_tokens"] = 0
    LAST_USAGE["total_tokens"] = 0
    _CONTEXT_WARN_SHOWN["high"] = False
    _CONTEXT_WARN_SHOWN["full"] = False
    return True


def get_last_exchange():
    """Devuelve (last_user_prompt, last_assistant_answer) del history actual.
    Filtra los mensajes auto-inyectados que NO son input del operador:
      - "Resultado del comando:..." (lo emite el agente tras run_command)
      - prompts internos del orquestador / analysis_prompt
    Devuelve (None, None) si no hay intercambio real.
    """
    if not history:
        return (None, None)
    # El último mensaje user "real" del operador
    last_user = None
    last_user_idx = -1
    for i in range(len(history) - 1, -1, -1):
        m = history[i]
        if m.get("role") != "user":
            continue
        content = m.get("content", "") or ""
        # Filtros: mensajes auto-inyectados que no son input del operador
        if content.startswith("Resultado del comando:"):
            continue
        if content.startswith("OBLIGATORIO — Persistencia"):
            continue
        if "Analiza la salida anterior" in content[:200]:
            continue
        if content.startswith("Genera AHORA el informe técnico"):
            continue
        last_user = content
        last_user_idx = i
        break
    if last_user is None:
        return (None, None)
    # El primer assistant tras ese user
    last_assistant = None
    for j in range(last_user_idx + 1, len(history)):
        m = history[j]
        if m.get("role") == "assistant":
            last_assistant = m.get("content", "") or ""
            break
    return (last_user, last_assistant)


def start_new_session():
    """Reinicia la sesión a estado limpio (history solo con system_prompt).
    También resetea el contador de tokens (LAST_USAGE) y los avisos de
    contexto-lleno para que la nueva sesión empiece "en blanco" en la UI.
    """
    global SESSION_ID, SESSION_FILE, SESSION_STARTED_AT, ACTIVE_TARGET
    history.clear()
    history.append({"role": "system", "content": _build_system_content()})
    ACTIVE_SKILLS.clear()
    ACTIVE_TARGET = None
    SESSION_ID = _new_session_id()
    SESSION_FILE = os.path.join(SESSIONS_DIR, f"{SESSION_ID}.json")
    SESSION_STARTED_AT = datetime.now().isoformat(timespec="seconds")
    # Reset del contador de tokens (la cifra del response previo no aplica
    # a la sesión nueva — su history es solo el system prompt).
    LAST_USAGE["prompt_tokens"] = 0
    LAST_USAGE["completion_tokens"] = 0
    LAST_USAGE["total_tokens"] = 0
    # Reset de los warnings "contexto al X%" para que vuelvan a dispararse
    # en la nueva sesión si toca.
    _CONTEXT_WARN_SHOWN["high"] = False
    _CONTEXT_WARN_SHOWN["full"] = False


# ============================================================
# LECCIONES (memoria viva — correcciones del usuario)
# ============================================================
#
# Cuando el usuario corrige al agente o le da una regla de cómo actuar
# ("hazlo así", "no hagas X", "prefiero Y"), guardamos esa regla como
# archivo Markdown en memory/lessons/ y como entrada de una línea en
# memory/lessons/INDEX.md. El INDEX se inyecta como parte del system
# prompt en cada sesión (y se reinyecta tras cada `save_lesson`), así
# el agente arrastra todas las correcciones aprendidas a futuras
# sesiones automáticamente.
#
# Vías para crear lecciones:
#  - Usuario: comandos `aprende|recuerda|learn <texto>`.
#  - Modelo: meta-acción `COMANDO: agent:learn <texto>` (auto-aprendizaje
#    cuando detecta una corrección clara del usuario).
#
# Para borrar: `olvida|forget <id_o_fragmento>`.

def _ensure_lessons_dir():
    os.makedirs(LESSONS_DIR, exist_ok=True)
    if not os.path.exists(LESSONS_INDEX_PATH):
        with open(LESSONS_INDEX_PATH, "w", encoding="utf-8") as f:
            f.write(
                "# Lecciones aprendidas (memoria viva)\n\n"
                "<!-- Cada línea: '- [YYYY-MM-DD HH:MM] [archivo.md] regla resumida.' "
                "Se inyecta en el system prompt en cada sesión. -->\n\n"
            )


def _lessons_block_for_prompt():
    """Devuelve el bloque de texto a anexar al SYSTEM_PROMPT con las
    lecciones aprendidas. Devuelve cadena vacía si no hay ninguna."""
    try:
        with open(LESSONS_INDEX_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return ""
    # Detectar si hay alguna entrada real (no sólo cabecera/comentario).
    has_entry = any(
        line.strip().startswith("- ") for line in content.splitlines()
    )
    if not has_entry:
        return ""
    return (
        "\n\n=== LECCIONES APRENDIDAS (correcciones del usuario, persistentes entre sesiones) ===\n"
        "Estas son reglas que el usuario te ha dado en sesiones previas. "
        "Respétalas SIEMPRE. Si la situación actual encaja con alguna, "
        "aplícala sin que el usuario tenga que repetirla.\n\n"
        f"{content.strip()}\n"
        "=== FIN LECCIONES ===\n"
    )


def _build_system_content():
    """SYSTEM_PROMPT + bloque de lecciones (si hay)."""
    return SYSTEM_PROMPT + _lessons_block_for_prompt()


def _rebuild_system_message():
    """Sustituye in-place el primer mensaje system de history con la
    versión actualizada (SYSTEM_PROMPT + lecciones). Si history está
    vacío, lo inicializa."""
    new_content = _build_system_content()
    if history and history[0].get("role") == "system":
        history[0]["content"] = new_content
    else:
        history.insert(0, {"role": "system", "content": new_content})


def _slugify_lesson(text):
    """Convierte un texto libre en un slug apto para nombre de archivo."""
    import unicodedata
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_text = norm.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:60] or "leccion"


def save_lesson(text, tags=None):
    """Guarda una lección como archivo individual y la añade al INDEX.
    Devuelve el path del archivo creado, o None si `text` está vacío.
    Reinyecta el system prompt automáticamente."""
    text = (text or "").strip()
    if not text:
        return None
    _ensure_lessons_dir()
    now = datetime.now()
    slug = _slugify_lesson(text)
    base = f"{now.strftime('%Y%m%d-%H%M%S')}_{slug}"
    path = os.path.join(LESSONS_DIR, f"{base}.md")
    n = 2
    while os.path.exists(path):
        path = os.path.join(LESSONS_DIR, f"{base}_{n}.md")
        n += 1
    fname = os.path.basename(path)

    frontmatter_lines = [
        "---",
        f"name: {slug}",
        f"created: {now.strftime('%Y-%m-%dT%H:%M:%S')}",
    ]
    if tags:
        frontmatter_lines.append(f"tags: [{', '.join(tags)}]")
    frontmatter_lines.append("---")
    frontmatter = "\n".join(frontmatter_lines) + "\n\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter + text.rstrip() + "\n")

    # Entrada de una línea en INDEX (la primera línea de la lección,
    # acortada). Esto es lo que ve el modelo en su system prompt.
    first_line = text.split("\n", 1)[0].strip()[:240]
    entry = f"- [{now.strftime('%Y-%m-%d %H:%M')}] [{fname}] {first_line}\n"
    with open(LESSONS_INDEX_PATH, "a", encoding="utf-8") as f:
        f.write(entry)

    _rebuild_system_message()
    return path


def list_lessons_raw():
    """Devuelve el contenido bruto del INDEX (para mostrar al usuario)."""
    _ensure_lessons_dir()
    try:
        with open(LESSONS_INDEX_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _all_lesson_files():
    if not os.path.isdir(LESSONS_DIR):
        return []
    return sorted(
        f for f in os.listdir(LESSONS_DIR)
        if f.endswith(".md") and f != "INDEX.md"
    )


def forget_lesson(identifier):
    """Borra una lección por nombre exacto o fragmento del nombre.
    Devuelve:
      - None si no se encontró ninguna.
      - lista de matches si hay ambigüedad (no borra nada).
      - el nombre del archivo borrado si tuvo éxito.
    """
    _ensure_lessons_dir()
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    candidates = _all_lesson_files()
    if identifier in candidates:
        matches = [identifier]
    else:
        matches = [c for c in candidates if identifier.lower() in c.lower()]
    if not matches:
        return None
    if len(matches) > 1:
        return matches
    target = matches[0]
    full = os.path.join(LESSONS_DIR, target)
    try:
        os.remove(full)
    except OSError:
        return None
    # Re-escribir INDEX sin las líneas que mencionan ese archivo.
    try:
        with open(LESSONS_INDEX_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = [l for l in lines if target not in l]
        with open(LESSONS_INDEX_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except OSError:
        pass
    _rebuild_system_message()
    return target


def load_skill_content(name):
    """Lee skills/<name>/skill.md, devuelve None si no existe."""
    path = os.path.join(SKILLS_DIR, name, "skill.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def list_available_skills():
    """[(name, descripcion, has_skill_md)]"""
    if not os.path.isdir(SKILLS_DIR):
        return []
    result = []
    for entry in sorted(os.listdir(SKILLS_DIR)):
        skill_dir = os.path.join(SKILLS_DIR, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "skill.md")
        if os.path.isfile(skill_md):
            try:
                with open(skill_md, encoding="utf-8") as f:
                    first_line = f.readline().strip().lstrip("#").strip()
                result.append((entry, first_line or "(sin descripción)", True))
            except Exception:
                result.append((entry, "(error leyendo skill.md)", False))
        else:
            result.append((entry, "(falta skill.md)", False))
    return result


def _load_tools_master(name):
    """Si existe tools_master/<name>.md, devuelve su contenido. Si no, None.
    Permite que cada skill tenga una lista exhaustiva de herramientas
    asociada que el modelo debe recorrer durante la fase.
    """
    path = os.path.join(TOOLS_MASTER_DIR, f"{name}.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def activate_skill(name):
    """Carga skill.md como mensaje system adicional en el history.
    Si existe `tools_master/<name>.md`, lo añade como bloque adicional
    con instrucción de cobertura exhaustiva.
    """
    content = load_skill_content(name)
    if content is None:
        return False
    if name in ACTIVE_SKILLS:
        return True
    history.append({
        "role": "system",
        "content": f"[Skill activa: {name}]\n\n{content}"
    })

    # Cargar la lista maestra de herramientas asociada, si existe
    master = _load_tools_master(name)
    if master:
        instruction = (
            f"[Tools master · skill {name}]\n\n"
            f"Esta es la lista MAESTRA de herramientas para la fase '{name}'. "
            f"Trabajas con ella de forma EXHAUSTIVA y SISTEMÁTICA:\n"
            f"- Recorre la lista por categorías, una herramienta a la vez.\n"
            f"- Por cada herramienta: emite un COMANDO con ella (si aplica al "
            f"target y al alcance), o anota en notes.md vía TARGET_UPDATE por "
            f"qué la omites (ej: requiere API key que no está en .env, herramienta "
            f"comercial no disponible, redundante con otra ya usada).\n"
            f"- Una herramienta de la lista que ya hayas ejecutado figura en "
            f"`_timeline.md` del target — antes de proponer la siguiente, "
            f"comprueba mentalmente que esa no esté ya hecha.\n"
            f"- NO marques la fase como completa hasta que todas las herramientas "
            f"de la lista hayan sido (a) ejecutadas o (b) explícitamente "
            f"descartadas con motivo en notes.md.\n"
            f"- Cuando el usuario te diga 'haz recon', 'haz enumeración', etc., "
            f"empiezas a recorrer la lista — propón el primer COMANDO y espera "
            f"a que el usuario confirme/lo ejecute, luego el siguiente.\n\n"
            f"=== LISTA MAESTRA ===\n\n{master}"
        )
        history.append({
            "role": "system",
            "content": instruction,
        })

    ACTIVE_SKILLS.append(name)
    return True


def deactivate_skill(name):
    """Marca la skill como inactiva (no podemos eliminarla retroactivamente del history sin perder contexto)."""
    if name not in ACTIVE_SKILLS:
        return False
    ACTIVE_SKILLS.remove(name)
    history.append({
        "role": "system",
        "content": f"[Skill desactivada: {name}]"
    })
    return True


# ============================================================
# SUBAGENTES AUTÓNOMOS — mini-agentes LLM en paralelo
# ============================================================
# Un subagente es una sesión LLM independiente con:
#   - skill propia (puede diferir de la del agente principal)
#   - history aislado (no comparte conversación con el principal)
#   - target compartido (escribe a los MISMOS archivos del target activo)
#   - lessons globales aplicadas (vía SYSTEM_PROMPT)
#   - tarea concreta + autonomía completa (auto-ejecuta sus COMANDOs)
#
# Se ejecuta en un thread daemon. El operador puede tener hasta
# MAX_CONCURRENT_SUBAGENTS activos. Cuando termina, el agente principal
# muestra un panel de notificación al volver al prompt.

SUBAGENTS_DIR = os.path.join(WORKSPACE, "memory", "subagents")
MAX_CONCURRENT_SUBAGENTS = 3
SUBAGENT_DEFAULT_MAX_TURNS = 12
SUBAGENT_END_MARKER = "TAREA COMPLETA"

_subagents_lock = threading.Lock()
_subagents_registry = {}   # name → Subagent
_subagent_io_lock = threading.Lock()  # serializa escrituras a archivos target
_subagent_thread_marker = threading.local()


def _is_subagent_thread():
    """True si el código se ejecuta dentro de un thread de subagente."""
    return getattr(_subagent_thread_marker, "active", False)


def _q_print(*args, **kwargs):
    """`console.print` con silenciado automático en threads de subagente.
    El operador ve solo su flujo principal; los subagentes acumulan en su
    log file y se reportan en el panel-resumen final.
    """
    if _is_subagent_thread():
        return
    console.print(*args, **kwargs)


def _q_spinner(label):
    """Devuelve un contexto: spinner real si NO estamos en subagente,
    null-context si sí. Para que `with _q_spinner(...)` funcione tanto en
    main como en subagente sin imprimir el spinner."""
    if _is_subagent_thread():
        return contextlib.nullcontext()
    return _AnimatedSpinner(label)


# ============================================================
# Checklist de herramientas para subagentes (cobertura exhaustiva)
# ============================================================

# Mínima cobertura aceptada (% de tools del master tocadas) antes de
# permitir que un subagente declare TAREA COMPLETA. Si está por debajo,
# se le pide continuar.
SUBAGENT_MIN_COVERAGE_PCT = 0.60
# Intentos máximos de auto-recovery por herramienta antes de marcarla
# como "permanently failed" y permitir avanzar.
SUBAGENT_AUTO_RECOVERY_MAX_ATTEMPTS = 3
# Patrones que indican que el fallo del comando es por el proxy/Tor.
_PROXY_ERROR_PATTERNS = [
    re.compile(r"proxychains.*denied", re.I),
    re.compile(r"socks.*connection refused", re.I),
    re.compile(r"could not connect to 127\.0\.0\.1:9050", re.I),
    re.compile(r"tor.*not running", re.I),
    re.compile(r"timeout.*tor", re.I),
    re.compile(r"unable to connect to host", re.I),
    re.compile(r"network is unreachable", re.I),
]
# Patrones que indican timeout/rate-limit por velocidad excesiva.
_RATE_LIMIT_PATTERNS = [
    re.compile(r"timeout", re.I),
    re.compile(r"rate.?limit", re.I),
    re.compile(r"too many requests", re.I),
    re.compile(r"429", re.I),
    re.compile(r"connection reset", re.I),
    re.compile(r"context deadline exceeded", re.I),
]
# Patrones que indican que el comando es demasiado complejo / mal-formado.
_COMPLEXITY_ERROR_PATTERNS = [
    re.compile(r"unknown flag", re.I),
    re.compile(r"invalid argument", re.I),
    re.compile(r"unrecognized option", re.I),
    re.compile(r"syntax error", re.I),
    re.compile(r"usage:", re.I),
]


# Regex para extraer nombres de herramientas de la tabla del tools_master.
# Formato típico: `| **toolname** | install | command |`
_MASTER_TOOL_LINE_RE = re.compile(
    r"^\s*\|\s*\*\*(?P<name>[a-zA-Z][a-zA-Z0-9_\.\-]+(?:\s*[/+&,]\s*[a-zA-Z][a-zA-Z0-9_\.\-]+)*)\*\*",
    re.MULTILINE,
)


def _extract_tools_from_master(master_content):
    """Parsea el tools_master/<skill>.md y devuelve la lista de
    herramientas únicas (lowercase) declaradas en las tablas.
    """
    if not master_content:
        return []
    tools = []
    seen = set()
    for m in _MASTER_TOOL_LINE_RE.finditer(master_content):
        raw = m.group("name").strip()
        # Algunos nombres llevan modificadores tipo "nmap (UDP)" —
        # tomamos solo el primer token alfanumérico.
        # Y algunos son combos "a / b" — los dividimos.
        parts = re.split(r"[/+&,]", raw)
        for p in parts:
            p = p.strip().lower()
            # Quitar paréntesis y modificadores
            p = re.sub(r"\(.*?\)", "", p).strip()
            # Tomar primer token si hay espacios
            p = p.split()[0] if p else ""
            # Sanitización: solo letras/dígitos/_.-
            if p and re.match(r"^[a-zA-Z][a-zA-Z0-9_\.\-]*$", p) and p not in seen:
                seen.add(p)
                tools.append(p)
    return tools


def _extract_tool_from_command(command):
    """Extrae la herramienta principal de un comando shell. Reutiliza
    `_runs_first_tool_token` pero devuelve siempre lowercase.
    """
    tool = _runs_first_tool_token(command)
    return tool.lower() if tool else ""


def _classify_command_failure(stderr_text, rc):
    """Clasifica el motivo de fallo de un comando para guiar el
    auto-recovery. Devuelve uno de:
      'proxy', 'rate_limit', 'complexity', 'not_installed', 'other'.
    """
    text = (stderr_text or "")[:4000]
    if rc == -1:
        return "cancelled"
    # Tool not installed: ya hay detector en agent.py — lo dejamos a
    # `_detect_missing_tool` que llamamos aparte.
    for pat in _PROXY_ERROR_PATTERNS:
        if pat.search(text):
            return "proxy"
    for pat in _RATE_LIMIT_PATTERNS:
        if pat.search(text):
            return "rate_limit"
    for pat in _COMPLEXITY_ERROR_PATTERNS:
        if pat.search(text):
            return "complexity"
    return "other"


def _simplify_command(command, attempt):
    """Simplifica un comando según el número de intento de recovery.
    Devuelve None si no hay simplificación aplicable.

      attempt 1: bajar threads/rate. -t 50 → -t 10. --rate 5000 → --rate 1000.
      attempt 2: quitar opciones avanzadas. Cambiar wordlists grandes
                 por más pequeñas. Reducir timeouts.
      attempt 3: comando mínimo — tool + target básico.
    """
    if not command:
        return None
    cmd = command
    if attempt == 1:
        # Reducir threads / paralelismo
        cmd = re.sub(r"-t\s+\d+", "-t 5", cmd)
        cmd = re.sub(r"--threads[= ]\d+", "--threads 5", cmd)
        cmd = re.sub(r"--rate[= ]\d+", "--rate 100", cmd)
        cmd = re.sub(r"--max-rate[= ]\d+", "--max-rate 100", cmd)
        cmd = re.sub(r"-T[0-5]", "-T2", cmd)  # nmap timing
        if cmd != command:
            return cmd
    if attempt == 2:
        # Sustituir wordlists grandes por las más pequeñas conocidas
        big_lists = [
            r"directory-list-lowercase-2\.3-medium\.txt",
            r"directory-list-2\.3-medium\.txt",
            r"directory-list-lowercase-2\.3-big\.txt",
            r"rockyou\.txt",
        ]
        small_sub = "/usr/share/dirb/wordlists/common.txt"
        for bl in big_lists:
            if re.search(bl, cmd):
                cmd = re.sub(rf"\S*{bl}", small_sub, cmd)
        # Quitar opciones de output que pueden fallar por permisos
        cmd = re.sub(r"-o[NGXAS]?\s+\S+", "", cmd)
        cmd = re.sub(r"--output[= ]\S+", "", cmd)
        cmd = re.sub(r">\s*\S+\.(txt|json|xml)", "", cmd)
        cmd = re.sub(r"-rl\s+\d+", "-rl 30", cmd)  # nuclei rate-limit
        cmd = re.sub(r"\s+", " ", cmd).strip()
        if cmd != command:
            return cmd
    if attempt == 3:
        # Comando mínimo: tool + target detectado
        tool = _extract_tool_from_command(command)
        tokens = _runs_target_tokens(command)
        if tool and tokens:
            # Para tools comunes, comando mínimo conocido
            minimal = {
                "nmap":      f"nmap -sn {tokens[0]}",
                "nuclei":    f"nuclei -u {tokens[0]} -t cves/ -severity critical",
                "gobuster":  f"gobuster dir -u {tokens[0]} -w /usr/share/dirb/wordlists/common.txt -t 5",
                "ffuf":      f"ffuf -u {tokens[0]}/FUZZ -w /usr/share/dirb/wordlists/common.txt -t 5 -mc 200,301,302",
                "nikto":     f"nikto -h {tokens[0]} -Tuning x1",
                "whatweb":   f"whatweb {tokens[0]}",
                "wpscan":    f"wpscan --url {tokens[0]} --no-update",
                "curl":      f"curl -sI {tokens[0]}",
            }
            if tool in minimal:
                return minimal[tool]
    return None


def _looks_like_proxy_active():
    """True si PROXY_MODE no es 'off'."""
    return PROXY_MODE != "off"


class Subagent:
    """Estado de un subagente autónomo."""

    def __init__(self, name, skill, task, target, max_turns=None):
        self.name = name
        self.skill = skill
        self.task = task
        self.target = target  # snapshot del target al spawn
        self.max_turns = max_turns or SUBAGENT_DEFAULT_MAX_TURNS
        self.history = []
        self.status = "pending"  # pending → running → done|failed|killed|exhausted
        self.turns_used = 0
        self.commands_run = []   # [{cmd, rc, duration, tool}]
        self.target_updates_applied = []
        self.started_at = ""
        self.finished_at = ""
        self.summary = ""
        self.error = ""
        self.reported = False    # si el panel "terminado" ya se mostró
        # === Cobertura de herramientas ===
        # Cargado al spawn desde tools_master/<skill>.md
        self.tools_available = []      # lista canónica de tools del master
        self.tools_used = set()        # tools que ha invocado (al menos 1 vez)
        self.tools_failed_perm = {}    # {tool: motivo_final} — permanentemente fallidas
        self.tools_skipped = {}        # {tool: motivo} — descartadas por el subagente
        self.recovery_attempts = {}    # {tool: int} — número de auto-recovery
        self.coverage_warnings = 0     # rechazos de TAREA COMPLETA por baja cobertura
        self.proxy_was_disabled = False  # se desactivó proxy en este sub
        self.kill_flag = threading.Event()
        self.thread = None
        self.log_path = os.path.join(SUBAGENTS_DIR, f"{name}.log")
        os.makedirs(SUBAGENTS_DIR, exist_ok=True)

    def log(self, msg):
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    def coverage(self):
        """Devuelve (n_used + n_failed_perm + n_skipped, n_total, pct).
        Una herramienta se considera "cubierta" si fue usada, o si
        falló de forma permanente tras auto-recovery, o si el subagente
        la descartó explícitamente."""
        total = len(self.tools_available) or 1
        covered = (
            len(self.tools_used)
            + len(self.tools_failed_perm)
            + len(self.tools_skipped)
        )
        return (covered, total, covered / total)

    def coverage_summary_str(self):
        c, t, pct = self.coverage()
        return (
            f"{c}/{t} ({pct*100:.0f}%) · "
            f"usadas={len(self.tools_used)} · "
            f"falladas={len(self.tools_failed_perm)} · "
            f"skipped={len(self.tools_skipped)}"
        )

    def tools_pending(self):
        """Devuelve la lista de tools del master que NO han sido
        cubiertas todavía (ni usadas, ni falladas perm, ni skipped)."""
        cubierto = self.tools_used | set(self.tools_failed_perm.keys()) | set(self.tools_skipped.keys())
        return [t for t in self.tools_available if t not in cubierto]


def _subagent_init_log(sub):
    """Inicializa el archivo de log con un header."""
    try:
        with open(sub.log_path, "w", encoding="utf-8") as f:
            f.write(f"# Subagente '{sub.name}'\n")
            f.write(f"# Skill: {sub.skill}\n")
            f.write(f"# Target: {sub.target}\n")
            f.write(f"# Tarea: {sub.task}\n")
            f.write(f"# Iniciado: {datetime.now().isoformat(timespec='seconds')}\n\n")
    except Exception:
        pass


def _subagent_build_init_history(sub):
    """Construye los mensajes system iniciales del subagente."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    skill_content = load_skill_content(sub.skill)
    if skill_content:
        msgs.append({
            "role": "system",
            "content": f"[Skill activa: {sub.skill}]\n\n{skill_content}",
        })
        master = _load_tools_master(sub.skill)
        if master:
            # Extraer checklist canónica de herramientas del master
            sub.tools_available = _extract_tools_from_master(master)
            sub.log(
                f"Checklist cargada del tools_master/{sub.skill}.md: "
                f"{len(sub.tools_available)} herramientas únicas detectadas."
            )
            msgs.append({
                "role": "system",
                "content": (
                    f"[Tools master · skill {sub.skill}]\n\n"
                    f"Trabajas EXHAUSTIVAMENTE por esta lista para resolver el "
                    f"task. NO marques TAREA COMPLETA hasta cubrir lo necesario.\n\n"
                    f"COBERTURA MÍNIMA EXIGIDA: "
                    f"{int(SUBAGENT_MIN_COVERAGE_PCT*100)}% de las herramientas "
                    f"del master deben quedar (a) ejecutadas con éxito, "
                    f"(b) intentadas y permanentemente fallidas tras "
                    f"auto-recovery, o (c) descartadas explícitamente por ti "
                    f"con motivo claro. Si emites TAREA COMPLETA con cobertura "
                    f"inferior, el sistema rechazará la marca y te pedirá "
                    f"continuar.\n\n"
                    f"=== LISTA MAESTRA ===\n\n{master}"
                ),
            })
    if sub.target:
        files = _read_target_files(sub.target)
        if files:
            body = [
                f"[Target activo: {sub.target}]",
                "",
                f"Datos del target compartidos con el agente principal y otros "
                f"subagentes. Tus TARGET_UPDATE se escriben en ESTOS archivos "
                f"(con lock — no hay colisiones).",
                "",
                TARGET_UPDATE_INSTRUCTIONS,
                "",
            ]
            for fn, content in files:
                body.append(f"=== {fn} ===")
                body.append(content.rstrip())
                body.append("")
            msgs.append({"role": "system", "content": "\n".join(body).rstrip()})
    return msgs


def _subagent_call_llm(sub):
    """Una llamada LLM. Devuelve answer (str) o None si error."""
    msgs = _compact_messages_for_call(list(sub.history))
    try:
        resp = client.chat.completions.create(
            model=get_active_model(),
            messages=msgs,
            temperature=0.1,
            max_tokens=2048,
            frequency_penalty=0.4,
            presence_penalty=0.2,
            timeout=LLM_REQUEST_TIMEOUT,
        )
        answer = (resp.choices[0].message.content or "") if resp.choices else ""
    except Exception as e:
        sub.log(f"ERROR LLM: {e}")
        sub.error = f"LLM error: {e}"
        return None

    # Strip de regurgitación de contexto system (anti-eco)
    answer, regurg_cuts = _strip_context_regurgitation(answer)
    if regurg_cuts:
        sub.log(f"  ⚠ recortados {regurg_cuts} bloque(s) regurgitados")

    # Aplicar TARGET_UPDATE bloques (thread-safe sobre archivos del target)
    if sub.target:
        with _subagent_io_lock:
            updates = extract_target_updates(answer)
            for fname, content in updates:
                global ACTIVE_TARGET
                saved_active = ACTIVE_TARGET
                ACTIVE_TARGET = sub.target
                try:
                    result = apply_target_update(fname, content)
                    if result.get("ok"):
                        sub.target_updates_applied.append(fname)
                        sub.log(f"  ✓ TARGET_UPDATE → {fname}")
                    else:
                        sub.log(f"  ✗ TARGET_UPDATE FAILED → {fname}: "
                                f"{result.get('error', '?')}")
                finally:
                    ACTIVE_TARGET = saved_active
            if updates:
                answer = strip_target_updates(answer)

    sub.history.append({"role": "assistant", "content": answer})
    sub.log(f"--- TURNO {sub.turns_used} ---")
    preview = answer[:400].replace("\n", " ⤶ ")
    sub.log(f"ANSWER: {preview}{'…' if len(answer) > 400 else ''}")
    return answer


def _subagent_loop(sub):
    """Bucle autónomo del subagente (corre en thread daemon)."""
    _subagent_thread_marker.active = True
    try:
        sub.status = "running"
        sub.started_at = datetime.now().isoformat(timespec="seconds")
        _subagent_init_log(sub)
        sub.log("Subagente iniciado.")

        sub.history = _subagent_build_init_history(sub)
        sub.history.append({
            "role": "user",
            "content": (
                f"TAREA AUTÓNOMA: {sub.task}\n\n"
                f"Modo: AUTO-EJECUTAS tus COMANDOs (sin pedir confirmación al "
                f"operador). El agente principal sigue funcionando en paralelo. "
                f"Tus TARGET_UPDATE se aplican a los archivos compartidos del "
                f"target '{sub.target}'.\n\n"
                f"Límites de seguridad:\n"
                f"  · Máximo {sub.max_turns} turnos (LLM calls).\n"
                f"  · NO puedes ejecutar comandos destructivos — bloqueados.\n"
                f"  · El operador puede pararte con `subagent kill {sub.name}`.\n\n"
                f"Cuando hayas completado la tarea o llegado a un punto donde "
                f"necesites input humano, emite EXACTAMENTE en una línea:\n"
                f"  {SUBAGENT_END_MARKER}\n\n"
                f"Y opcionalmente una frase de resumen tras esa marca."
            ),
        })

        while sub.turns_used < sub.max_turns:
            if sub.kill_flag.is_set():
                sub.status = "killed"
                sub.log("Kill flag detectado.")
                return

            sub.turns_used += 1
            answer = _subagent_call_llm(sub)
            if answer is None:
                sub.status = "failed"
                return

            # Marcador de fin — VALIDACIÓN DE COBERTURA antes de aceptar
            if SUBAGENT_END_MARKER in answer:
                idx = answer.find(SUBAGENT_END_MARKER)
                tail = answer[idx + len(SUBAGENT_END_MARKER):].strip(" \n:-—\t").strip()
                covered, total, pct = sub.coverage()
                # Si tiene checklist Y la cobertura es baja, rechazamos
                # la marca y le pedimos continuar (máximo 3 rechazos).
                if (sub.tools_available
                        and pct < SUBAGENT_MIN_COVERAGE_PCT
                        and sub.coverage_warnings < 3):
                    sub.coverage_warnings += 1
                    pending = sub.tools_pending()
                    sample = pending[:15]
                    msg = (
                        f"⛔ TAREA COMPLETA RECHAZADA por cobertura "
                        f"insuficiente: {sub.coverage_summary_str()} "
                        f"(mínimo {int(SUBAGENT_MIN_COVERAGE_PCT*100)}%).\n\n"
                        f"Tools del master aún no cubiertas "
                        f"({len(pending)} pendientes, primeras 15): "
                        f"{', '.join(sample)}.\n\n"
                        f"Opciones:\n"
                        f"  · Ejecuta más herramientas relevantes para "
                        f"el task.\n"
                        f"  · Si una herramienta NO aplica al target, "
                        f"emite `[[TARGET_UPDATE: notes.md]]` con una "
                        f"línea '## [ts] <tool> · descartada: <motivo>' y "
                        f"añade `SKIP_TOOL: <tool> · <motivo>` al final "
                        f"de tu siguiente respuesta para confirmar el "
                        f"descarte.\n\n"
                        f"Continúa con el siguiente COMANDO o SKIP_TOOL."
                    )
                    sub.history.append({"role": "user", "content": msg})
                    sub.log(
                        f"  ⛔ TAREA COMPLETA rechazada (warning "
                        f"{sub.coverage_warnings}/3) — cobertura "
                        f"{sub.coverage_summary_str()}"
                    )
                    continue
                # Cobertura OK o sin checklist → aceptamos
                sub.summary = tail or "(sin resumen explícito tras la marca)"
                sub.status = "done"
                sub.log(
                    f"TAREA COMPLETA · cobertura "
                    f"{sub.coverage_summary_str()} · {sub.summary[:200]}"
                )
                return

            # Detección de SKIP_TOOL: el subagente descarta una herramienta
            # con motivo. Lo registramos para que cuente en la cobertura.
            skip_matches = re.findall(
                r"SKIP_TOOL:\s*([a-zA-Z][a-zA-Z0-9_\.\-]+)\s*[·:\-]\s*(.+?)(?=\n|$)",
                answer,
            )
            for skipped_tool, motivo in skip_matches:
                tool_l = skipped_tool.lower().strip()
                if tool_l in [t.lower() for t in sub.tools_available] and tool_l not in sub.tools_skipped:
                    sub.tools_skipped[tool_l] = motivo.strip()[:200]
                    sub.log(f"  ⊘ tool '{tool_l}' SKIPPED por subagente: {motivo[:80]}")

            command = extract_command(answer)
            if not command:
                # Si no hay COMANDO pero hubo SKIP_TOOL, dale feedback con
                # cobertura actualizada. Si no, ya es el caso normal.
                msg_extra = ""
                if skip_matches:
                    msg_extra = (
                        f"\n\nSKIP_TOOL registrados: "
                        f"{', '.join(t for t,_ in skip_matches)}. "
                        f"Cobertura actual: {sub.coverage_summary_str()}."
                    )
                sub.history.append({
                    "role": "user",
                    "content": (
                        f"Tu respuesta no incluyó `COMANDO:` ni la marca "
                        f"{SUBAGENT_END_MARKER}. Emite uno de los dos en el "
                        f"siguiente turno.{msg_extra}"
                    ),
                })
                continue

            # Safety: nunca destructivos
            category = classify_command(command)
            if category == "destructive":
                sub.history.append({
                    "role": "user",
                    "content": (
                        f"BLOQUEADO por seguridad: comando destructivo "
                        f"`{command}`. Los subagentes no pueden ejecutar "
                        f"comandos destructivos. Propón alternativa "
                        f"reversible o emite {SUBAGENT_END_MARKER}."
                    ),
                })
                sub.log(f"  ⛔ destructivo bloqueado: {command}")
                continue

            # Ejecutar (auto=True → sin confirmación)
            sub.log(f"COMANDO: {command}")
            t0 = time.time()
            result = run_command(command, auto=True)
            rc = LAST_COMMAND_RC
            duration = time.time() - t0
            current_tool = _extract_tool_from_command(command)
            sub.commands_run.append({
                "cmd": command, "rc": rc, "duration_s": round(duration, 1),
                "tool": current_tool,
            })
            sub.log(f"  rc={rc} duration={duration:.1f}s tool='{current_tool}'")

            # Si el rc==0, marcamos el tool como usado en la checklist.
            if rc == 0 and current_tool in [t.lower() for t in sub.tools_available]:
                sub.tools_used.add(current_tool)

            # AUTO-RECOVERY: si el comando falló (rc != 0, !=-1) y el tool
            # está en la checklist, intentamos rescate escalonado.
            recovery_log = ""
            if (rc not in (0, -1) and current_tool
                    and current_tool in [t.lower() for t in sub.tools_available]
                    and current_tool not in sub.tools_failed_perm):
                attempts_done = sub.recovery_attempts.get(current_tool, 0)
                # Extraer stderr aproximado del result (formato del agente)
                stderr_text = result
                failure_kind = _classify_command_failure(stderr_text, rc)
                sub.log(
                    f"  ⚠ tool '{current_tool}' falló (rc={rc}, "
                    f"kind={failure_kind}). Auto-recovery attempt "
                    f"{attempts_done+1}/{SUBAGENT_AUTO_RECOVERY_MAX_ATTEMPTS}"
                )

                recovery_cmd = None
                recovery_action = None

                # Estrategia por tipo
                if failure_kind == "proxy" and not sub.proxy_was_disabled:
                    # Desactivar proxy global y reintentar el mismo comando
                    global PROXY_MODE
                    prev_proxy = PROXY_MODE
                    PROXY_MODE = "off"
                    sub.proxy_was_disabled = True
                    recovery_action = (
                        f"proxy off (era {prev_proxy}) · reintento mismo cmd"
                    )
                    recovery_cmd = command
                elif failure_kind in ("rate_limit", "other") and attempts_done < SUBAGENT_AUTO_RECOVERY_MAX_ATTEMPTS:
                    # Simplificar el comando
                    simplified = _simplify_command(command, attempts_done + 1)
                    if simplified and simplified != command:
                        recovery_action = (
                            f"simplify cmd (attempt {attempts_done+1}): "
                            f"{simplified[:100]}"
                        )
                        recovery_cmd = simplified
                elif failure_kind == "complexity" and attempts_done < SUBAGENT_AUTO_RECOVERY_MAX_ATTEMPTS:
                    # Simplificar agresivamente saltando al attempt 2 directamente
                    simplified = _simplify_command(command, max(2, attempts_done + 1))
                    if simplified and simplified != command:
                        recovery_action = f"complexity simplify: {simplified[:100]}"
                        recovery_cmd = simplified

                if recovery_cmd:
                    sub.recovery_attempts[current_tool] = attempts_done + 1
                    sub.log(f"  ↻ auto-recovery: {recovery_action}")
                    t1 = time.time()
                    retry_result = run_command(recovery_cmd, auto=True)
                    retry_rc = LAST_COMMAND_RC
                    retry_duration = time.time() - t1
                    sub.commands_run.append({
                        "cmd": recovery_cmd, "rc": retry_rc,
                        "duration_s": round(retry_duration, 1),
                        "tool": current_tool, "recovery": True,
                    })
                    sub.log(
                        f"  ↻ recovery rc={retry_rc} "
                        f"duration={retry_duration:.1f}s"
                    )
                    if retry_rc == 0:
                        sub.tools_used.add(current_tool)
                        recovery_log = (
                            f"\n\n[AUTO-RECOVERY EXITOSA] El comando "
                            f"original falló pero el sistema lo "
                            f"recuperó: {recovery_action}. Resultado "
                            f"del retry abajo.\n"
                        )
                        # Sustituir el result por el del retry
                        result = (
                            f"[ORIGINAL CMD FAILED rc={rc} · "
                            f"recovered with: {recovery_action}]\n\n"
                            f"{retry_result}"
                        )
                        rc = 0
                    else:
                        # Si llegamos al límite, marcar como permanente
                        if sub.recovery_attempts[current_tool] >= SUBAGENT_AUTO_RECOVERY_MAX_ATTEMPTS:
                            sub.tools_failed_perm[current_tool] = (
                                f"Falló {SUBAGENT_AUTO_RECOVERY_MAX_ATTEMPTS} "
                                f"recoveries (último: {failure_kind}, rc={retry_rc})"
                            )
                            recovery_log = (
                                f"\n\n[AUTO-RECOVERY AGOTADA] tool "
                                f"'{current_tool}' marcada como "
                                f"PERMANENTEMENTE FALLIDA tras "
                                f"{SUBAGENT_AUTO_RECOVERY_MAX_ATTEMPTS} "
                                f"intentos. Pasa a otra herramienta.\n"
                            )
                            sub.log(
                                f"  ✗ tool '{current_tool}' marcada perm-failed"
                            )
                        else:
                            recovery_log = (
                                f"\n\n[AUTO-RECOVERY INTENTO "
                                f"{attempts_done+1} FALLIDO] "
                                f"Quedan {SUBAGENT_AUTO_RECOVERY_MAX_ATTEMPTS - sub.recovery_attempts[current_tool]} "
                                f"intentos antes de marcar como permanente. "
                                f"Puedes proponer otra variante o pasar a "
                                f"otra tool.\n"
                            )

            # Persistir en timeline y runs del target (con lock)
            if sub.target:
                with _subagent_io_lock:
                    global ACTIVE_TARGET
                    saved = ACTIVE_TARGET
                    ACTIVE_TARGET = sub.target
                    try:
                        append_timeline_entry(
                            f"[subagente {sub.name}] {command}", result
                        )
                        append_runs_entry(command, rc)
                    finally:
                        ACTIVE_TARGET = saved

            # Mensaje de feedback con estado de cobertura
            cov_str = sub.coverage_summary_str()
            sub.history.append({
                "role": "user",
                "content": (
                    f"Resultado del comando:\n{result}{recovery_log}\n\n"
                    f"Turno {sub.turns_used}/{sub.max_turns} · "
                    f"Cobertura tools: {cov_str}. "
                    f"Continúa con la siguiente acción del task o emite "
                    f"{SUBAGENT_END_MARKER} si has terminado (mínimo "
                    f"{int(SUBAGENT_MIN_COVERAGE_PCT*100)}% cobertura)."
                ),
            })

        # Salimos del while sin marca → agotó turnos
        sub.status = "exhausted"
        sub.summary = (
            f"Subagente agotó sus {sub.max_turns} turnos sin emitir "
            f"{SUBAGENT_END_MARKER}. Cobertura final: "
            f"{sub.coverage_summary_str()}. "
            f"Revisa el log para ver dónde se atascó."
        )
        sub.log(f"Exhausted (max_turns). Cobertura final: "
                f"{sub.coverage_summary_str()}")

    except Exception as e:
        sub.status = "failed"
        sub.error = str(e)
        sub.log(f"EXCEPCIÓN: {e}")
    finally:
        sub.finished_at = datetime.now().isoformat(timespec="seconds")
        _subagent_thread_marker.active = False


def spawn_subagent(name, skill, task):
    """Crea y lanza un subagente. Devuelve (Subagent, None) o (None, error)."""
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        return None, "el nombre debe ser alfanumérico (con - y _ permitidos)"
    with _subagents_lock:
        active = [s for s in _subagents_registry.values()
                  if s.status in ("pending", "running")]
        if len(active) >= MAX_CONCURRENT_SUBAGENTS:
            names = ", ".join(s.name for s in active)
            return None, (f"límite alcanzado ({MAX_CONCURRENT_SUBAGENTS} "
                          f"activos: {names}). Espera o `subagent kill <n>`")
        if name in _subagents_registry:
            existing = _subagents_registry[name]
            if existing.status in ("pending", "running"):
                return None, f"ya hay un subagente activo llamado '{name}'"
        if not load_skill_content(skill):
            return None, f"skill '{skill}' no existe (mira con `skills`)"
        if not ACTIVE_TARGET:
            return None, "no hay target activo (carga uno con `target <nombre>`)"
        sub = Subagent(name=name, skill=skill, task=task, target=ACTIVE_TARGET)
        _subagents_registry[name] = sub
    sub.thread = threading.Thread(
        target=_subagent_loop, args=(sub,),
        daemon=True, name=f"subagent-{name}",
    )
    sub.thread.start()
    return sub, None


def kill_subagent(name):
    """Marca el kill_flag. El loop chequea entre turnos. Devuelve bool."""
    with _subagents_lock:
        sub = _subagents_registry.get(name)
    if not sub or sub.status not in ("pending", "running"):
        return False
    sub.kill_flag.set()
    sub.log("Kill solicitado por el operador.")
    return True


def list_subagents():
    """Devuelve lista ordenada por started_at desc."""
    with _subagents_lock:
        subs = list(_subagents_registry.values())
    subs.sort(key=lambda s: s.started_at or "", reverse=True)
    return subs


def _print_subagent_finished_panel(sub):
    """Panel de notificación cuando un subagente termina."""
    status_colors = {
        "done": GREEN, "killed": "#fbbf24",
        "failed": RED, "exhausted": MAGENTA,
    }
    color = status_colors.get(sub.status, WHITE)
    lines = []
    lines.append(f"[bold]Estado:[/] [{color}]{sub.status.upper()}[/]")
    task_disp = sub.task[:120] + ("…" if len(sub.task) > 120 else "")
    lines.append(f"[bold]Tarea:[/] {task_disp}")
    lines.append(
        f"[bold]Skill:[/] {sub.skill}  ·  "
        f"Turnos: {sub.turns_used}/{sub.max_turns}  ·  "
        f"Target: [bold {PURPLE}]{sub.target}[/]"
    )
    # Cobertura de herramientas
    if sub.tools_available:
        _c, _t, pct = sub.coverage()
        cov_color = GREEN if pct >= SUBAGENT_MIN_COVERAGE_PCT else "#fbbf24"
        lines.append(
            f"[bold]Cobertura tools:[/] [{cov_color}]{sub.coverage_summary_str()}[/]"
        )
        if sub.tools_failed_perm:
            failed_short = list(sub.tools_failed_perm.keys())[:5]
            extra = f" (+{len(sub.tools_failed_perm)-5})" if len(sub.tools_failed_perm) > 5 else ""
            lines.append(
                f"  [dim]Falladas perm: {', '.join(failed_short)}{extra}[/]"
            )
        if sub.tools_skipped:
            skipped_short = list(sub.tools_skipped.keys())[:5]
            extra = f" (+{len(sub.tools_skipped)-5})" if len(sub.tools_skipped) > 5 else ""
            lines.append(
                f"  [dim]Skipped: {', '.join(skipped_short)}{extra}[/]"
            )
        if sub.proxy_was_disabled:
            lines.append(
                f"  [dim {ORANGE}]⚠ proxy fue desactivado por auto-recovery[/]"
            )
    if sub.commands_run:
        lines.append(f"[bold]Comandos ejecutados:[/] {len(sub.commands_run)}")
        for c in sub.commands_run[:5]:
            rc_color = "green" if c["rc"] == 0 else "red"
            cmd_short = c["cmd"][:90] + ("…" if len(c["cmd"]) > 90 else "")
            lines.append(
                f"  · [{rc_color}]rc={c['rc']}[/] [{CYAN}]{cmd_short}[/]"
            )
        if len(sub.commands_run) > 5:
            lines.append(f"  · … (+{len(sub.commands_run) - 5} más)")
    if sub.target_updates_applied:
        files = list(dict.fromkeys(sub.target_updates_applied))
        lines.append(
            f"[bold]TARGET_UPDATE aplicados:[/] {', '.join(files)}"
        )
    if sub.summary:
        lines.append("")
        lines.append(f"[bold]Resumen:[/]")
        lines.append(sub.summary)
    if sub.error:
        lines.append(f"[bold {RED}]Error:[/] {sub.error}")
    lines.append("")
    lines.append(
        f"[dim]Log completo: "
        f"{os.path.relpath(sub.log_path, WORKSPACE)}[/]"
    )
    console.print()
    console.print(Panel(
        "\n".join(lines),
        title=f"[bold {color}]» Subagente '{sub.name}' terminado[/]",
        border_style=color, box=ROUNDED, padding=(1, 2),
    ))


def _check_subagent_notifications():
    """Llamada desde el REPL antes del prompt. Muestra paneles para los
    subagentes recién terminados (no reportados)."""
    with _subagents_lock:
        pending = [s for s in _subagents_registry.values()
                   if s.status in ("done", "failed", "killed", "exhausted")
                   and not s.reported]
    for sub in pending:
        _print_subagent_finished_panel(sub)
        sub.reported = True


# ============================================================
# ORQUESTADOR DE OBJETIVOS — goal-driven multi-fase
# ============================================================
# Un GoalRun es un orquestador que recibe un objetivo en lenguaje natural y
# lo ejecuta en fases iterativas:
#   FASE k: el LLM-orquestador analiza el goal + el estado actual del target
#           y decide cuántos subagentes lanzar y la misión de cada uno.
#   Espera a que terminen TODOS los subagentes de la fase (no procede sin
#           sincronización — así una fase de análisis puede leer los outputs
#           de la fase de ejecución previa).
#   Re-evalúa: ¿goal cumplido? ¿bloqueado? ¿hace falta otra fase?
# Termina con uno de: done · blocked · exhausted (max_phases) · killed · failed.
#
# Sólo hay UN GoalRun activo a la vez (la coordinación se complica con varios
# orquestadores tocando los mismos archivos del target).

GOAL_MAX_PHASES = 5
GOAL_PHASE_TIMEOUT_S = 1800  # 30 min máximo por fase
GOAL_POLL_INTERVAL_S = 2

_active_goal_orch = None  # GoalRun | None
_goal_lock = threading.Lock()


class GoalRun:
    def __init__(self, goal_text, target, max_phases=GOAL_MAX_PHASES):
        self.id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.goal = goal_text
        self.target = target
        self.max_phases = max_phases
        self.current_phase = 0
        self.status = "pending"  # pending → running → done|blocked|exhausted|killed|failed
        self.phases = []  # [{n, subagent_names, summaries, started, finished}]
        self.outcome_reason = ""
        self.summary = ""
        self.started_at = ""
        self.finished_at = ""
        self.reported = False
        self.report_path = None  # path al informe auto-generado al cerrar
        self.resumed_from = None  # id de goal del que venimos si es resume
        self.kill_flag = threading.Event()
        self.thread = None
        self.log_path = os.path.join(SUBAGENTS_DIR, f"_goal-{self.id}.log")
        self.state_path = os.path.join(SUBAGENTS_DIR, f"_goal-{self.id}.state.json")
        os.makedirs(SUBAGENTS_DIR, exist_ok=True)

    def log(self, msg):
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    def to_dict(self):
        """Serializa el estado a dict (JSON-safe). NO incluye thread/kill_flag."""
        return {
            "id": self.id,
            "goal": self.goal,
            "target": self.target,
            "max_phases": self.max_phases,
            "current_phase": self.current_phase,
            "status": self.status,
            "phases": self.phases,
            "outcome_reason": self.outcome_reason,
            "summary": self.summary,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "report_path": self.report_path,
            "resumed_from": self.resumed_from,
            "log_path": self.log_path,
        }

    def save_state(self):
        """Vuelca el estado a disco de forma atómica (rename)."""
        try:
            data = self.to_dict()
            data["saved_at"] = datetime.now().isoformat(timespec="seconds")
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.state_path)
        except Exception:
            pass

    @classmethod
    def from_dict(cls, data):
        """Reconstruye un GoalRun desde dict. Recrea kill_flag (sin thread)."""
        gr = cls.__new__(cls)
        gr.id = data["id"]
        gr.goal = data["goal"]
        gr.target = data["target"]
        gr.max_phases = data.get("max_phases", GOAL_MAX_PHASES)
        gr.current_phase = data.get("current_phase", 0)
        gr.status = data.get("status", "pending")
        gr.phases = data.get("phases", [])
        gr.outcome_reason = data.get("outcome_reason", "")
        gr.summary = data.get("summary", "")
        gr.started_at = data.get("started_at", "")
        gr.finished_at = data.get("finished_at", "")
        gr.reported = False  # mostrar panel-resumen al resumir aunque ya se haya reportado antes
        gr.report_path = data.get("report_path")
        gr.resumed_from = data.get("resumed_from")
        gr.kill_flag = threading.Event()
        gr.thread = None
        gr.log_path = data.get("log_path") or os.path.join(
            SUBAGENTS_DIR, f"_goal-{gr.id}.log"
        )
        gr.state_path = os.path.join(SUBAGENTS_DIR, f"_goal-{gr.id}.state.json")
        return gr


# --- Parsing del plan emitido por el LLM-orquestador --------------------

# Bloque PLAN: -name/skill/task por subagente.
_GOAL_SUB_RE = re.compile(
    r"-\s*name:\s*(?P<name>[A-Za-z0-9_\-]+)\s*\n"
    r"\s*skill:\s*(?P<skill>[A-Za-z0-9_\-]+)\s*\n"
    r"\s*task:\s*(?P<task>.+?)(?=\n\s*-\s*name:|\nEND_PLAN|\Z)",
    re.DOTALL,
)


def _parse_orchestrator_response(text):
    """Parsea la respuesta del LLM-orquestador. Devuelve dict:
      {action: 'phase', subagents: [{name, skill, task}]}
      {action: 'done',  reason: str, summary: str}
      {action: 'blocked', reason: str}
      {action: 'parse_error', raw: str}
    """
    if not text:
        return {"action": "parse_error", "raw": ""}
    # Limpieza: quitar code fences markdown si el modelo envuelve el bloque
    cleaned = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text.strip(),
                     flags=re.MULTILINE)

    if "GOAL_DONE" in cleaned:
        m = re.search(
            r"GOAL_DONE:?\s*\n?\s*reason:\s*(?P<reason>.+?)"
            r"(?:\n\s*summary:\s*(?P<summary>.+?))?"
            r"(?:\nEND_GOAL_DONE|\Z)",
            cleaned, re.DOTALL,
        )
        if m:
            return {
                "action": "done",
                "reason": m.group("reason").strip(),
                "summary": (m.group("summary") or "").strip(),
            }
    if "GOAL_BLOCKED" in cleaned:
        m = re.search(
            r"GOAL_BLOCKED:?\s*\n?\s*reason:\s*(?P<reason>.+?)"
            r"(?:\nEND_GOAL_BLOCKED|\Z)",
            cleaned, re.DOTALL,
        )
        if m:
            return {"action": "blocked", "reason": m.group("reason").strip()}
    # PLAN: cierre por END_PLAN o por EOF (más tolerante)
    plan_match = re.search(
        r"PLAN:?\s*\n(?P<body>.*?)(?:\nEND_PLAN|\Z)",
        cleaned, re.DOTALL,
    )
    if plan_match:
        body = plan_match.group("body")
        subs = []
        for m in _GOAL_SUB_RE.finditer(body):
            subs.append({
                "name": m.group("name").strip(),
                "skill": m.group("skill").strip(),
                "task": m.group("task").strip(),
            })
        if subs:
            return {"action": "phase", "subagents": subs}
    return {"action": "parse_error", "raw": text[:500]}


_GOAL_FILE_CAP_CHARS = 2000       # tope por archivo del target inyectado
_GOAL_TOTAL_FILES_CAP = 8000      # tope global del bloque de archivos
# Excluidos por defecto: muy voluminosos y no necesarios para PLANIFICAR
# (sólo para auditoría). _timeline.md típico llega a 100-200 kB.
_GOAL_EXCLUDE_FILES = {"_timeline.md"}


def _read_target_files_for_orchestrator(target_name, minimal=False):
    """Lee los archivos relevantes del target y los devuelve en una lista
    [(filename, content_truncado)] con caps por archivo y total.

    Si `minimal=True`, devuelve solo attack-surface.md, notes.md e
    identities.md con head muy corto. Útil como fallback cuando el modelo
    devuelve respuesta vacía al primer intento (señal de que el prompt es
    demasiado grande para su context window real).
    """
    target_dir = os.path.join(TARGETS_DIR, target_name or "")
    if not target_name or not os.path.isdir(target_dir):
        return []

    if minimal:
        out = []
        for fn in ("attack-surface.md", "notes.md", "identities.md"):
            fp = os.path.join(target_dir, fn)
            if os.path.isfile(fp):
                try:
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        content = f.read()[:1200]
                    out.append((fn, content))
                except Exception:
                    pass
        return out

    # Orden de prioridad: lo importante primero
    priority = [
        "scope.md", "attack-surface.md", "infrastructure.md",
        "identities.md", "credentials.md", "wifi.md", "notes.md",
        "_runs.md",
    ]
    seen = set()
    ordered = []
    for fn in priority:
        if os.path.isfile(os.path.join(target_dir, fn)):
            ordered.append(fn)
            seen.add(fn)
    for fn in sorted(os.listdir(target_dir)):
        if fn in seen or fn in _GOAL_EXCLUDE_FILES:
            continue
        if os.path.isfile(os.path.join(target_dir, fn)):
            ordered.append(fn)

    out = []
    total = 0
    for fn in ordered:
        if fn in _GOAL_EXCLUDE_FILES:
            continue
        fp = os.path.join(target_dir, fn)
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue
        if len(content) > _GOAL_FILE_CAP_CHARS:
            half = _GOAL_FILE_CAP_CHARS // 2
            content = (
                content[:half]
                + f"\n\n[…{len(content) - _GOAL_FILE_CAP_CHARS} chars omitidos…]\n\n"
                + content[-half:]
            )
        if total + len(content) > _GOAL_TOTAL_FILES_CAP:
            out.append((fn, f"[archivo de {os.path.getsize(fp)} B — "
                            f"omitido por cap global del orquestador]"))
            continue
        out.append((fn, content))
        total += len(content)
    return out


def _goal_orchestrator_prompt(goal_run, available_skills, max_per_phase,
                              reinforced=False, minimal=False):
    """Construye el user prompt para que el LLM planifique la fase. Incluye
    el contenido (truncado) de los archivos del target para que el modelo
    NO necesite emitir COMANDO para leerlos.

    Si `minimal=True`, usa solo notes.md + attack-surface.md + identities.md
    con head muy corto. Útil cuando el primer intento devolvió respuesta
    vacía (señal de prompt demasiado grande para el modelo).
    """
    # Resumen de fases previas
    prev_summary = ""
    if goal_run.phases:
        lines = []
        for ph in goal_run.phases:
            lines.append(f"=== FASE {ph['n']} ===")
            for s in ph.get("subagent_summaries", []):
                lines.append(
                    f"  · subagente '{s['name']}' (skill {s['skill']}, "
                    f"status {s['status']}, {s['n_commands']} cmds, "
                    f"updates: {','.join(s['updates']) or '∅'}):"
                )
                summary = s["summary"] or "(sin resumen)"
                lines.append(f"    summary: {summary[:300]}")
        prev_summary = "\n".join(lines)

    # CONTENIDO de los archivos del target (no solo listado)
    target_files = _read_target_files_for_orchestrator(
        goal_run.target, minimal=minimal,
    )
    if target_files:
        file_blocks = []
        for fn, content in target_files:
            file_blocks.append(f"=== {fn} ===\n{content.rstrip()}")
        files_section = "\n\n".join(file_blocks)
    else:
        files_section = "(target sin archivos legibles)"

    skills_str = ", ".join(available_skills)

    reinforced_block = ""
    if reinforced:
        reinforced_block = (
            "\n\n⚠ ATENCIÓN: tu respuesta anterior NO siguió el formato. "
            "Esta vez emite EXACTAMENTE uno de los tres bloques sin texto "
            "antes ni después: PLAN / GOAL_DONE / GOAL_BLOCKED. NO emitas "
            "COMANDO — los archivos del target están abajo en el contexto, "
            "no necesitas leerlos vía shell."
        )

    user_msg = f"""ROL: Orquestador de un objetivo de pentesting.

GOAL DEL OPERADOR:
{goal_run.goal}

TARGET ACTIVO: {goal_run.target}

SKILLS DISPONIBLES para asignar a subagentes: {skills_str}

FASE ACTUAL: {goal_run.current_phase + 1} / {goal_run.max_phases}

HISTORIAL DE FASES YA EJECUTADAS:
{prev_summary or '(ninguna fase previa)'}

ARCHIVOS DEL TARGET (con contenido — ÚSALOS como única fuente de verdad,
NO emitas COMANDO para releerlos):

{files_section}

INSTRUCCIONES:
1. Analiza los archivos del target de arriba — esa es toda la evidencia
   actualizada. NO emitas COMANDO en este turno; tú no ejecutas shell aquí
   — sólo planificas. Los comandos los ejecutarán los subagentes que
   lances en la fase.

2. Decide UNA de estas tres salidas (sin texto antes ni después del bloque):

   A) GOAL_DONE — si el objetivo ya se cumplió según la evidencia:

         GOAL_DONE:
         reason: <una frase explicando por qué se cumplió>
         summary: <2-3 frases con lo conseguido>
         END_GOAL_DONE

   B) GOAL_BLOCKED — si no hay forma de avanzar (sin alcance, sin info,
      objetivo inalcanzable con lo disponible):

         GOAL_BLOCKED:
         reason: <una frase>
         END_GOAL_BLOCKED

   C) PLAN — para lanzar una nueva fase con 1 a {max_per_phase} subagentes
      en paralelo. Cada subagente recibe su propia history aislada pero
      escribe a los archivos compartidos del target. Forma EXACTA:

         PLAN:
         - name: <alfanum-corto>
           skill: <uno de las skills disponibles>
           task: <UN párrafo describiendo la misión concreta del subagente,
                  qué herramientas usar, qué archivos consultar/actualizar,
                  qué considerar "tarea completa">
         - name: <otro>
           skill: <skill>
           task: <misión>
         END_PLAN

3. Reglas de orquestación:
   - Si la fase anterior dejó subagentes "exhausted" o "failed", o si los
     summaries indican falta de información, NO repitas la misma estrategia.
     Replantea con otra aproximación.
   - Para fases de análisis sobre outputs de fase previa: 1 solo subagente
     que LEE archivos del target y propone pivots o valida hallazgos.
   - Para fases de verificación final, usa un subagente "tester".
   - NO repitas un nombre de subagente ya usado en una fase anterior.
   - NO inventes skills que no estén en la lista. NO emitas COMANDO ni
     TARGET_UPDATE en este turno — sólo el bloque PLAN / GOAL_DONE /
     GOAL_BLOCKED.{reinforced_block}
"""
    return user_msg


def _goal_request_plan(goal_run, available_skills, max_attempts=3):
    """Llama al LLM para planificar la fase siguiente. Estrategia escalonada:
      Attempt 1: prompt completo (todos los archivos del target hasta cap).
      Attempt 2: prompt reforzado, mismos archivos (si attempt 1 emitió
                 COMANDO o se desvió del formato).
      Attempt 3: prompt MINIMAL (sólo attack-surface + notes + identities,
                 head corto). Útil cuando el modelo devuelve VACÍO porque
                 el prompt completo supera su context window real.
    """
    last_raw = ""
    consecutive_empty = 0
    for attempt in range(max_attempts):
        # Usar prompt minimal si:
        #   · primer attempt ya devolvió vacío (modelo no puede con el tamaño)
        #   · es el último attempt y no hemos podido parsear nada
        use_minimal = (consecutive_empty >= 1) or (attempt == max_attempts - 1
                                                   and last_raw == "")
        user_prompt = _goal_orchestrator_prompt(
            goal_run, available_skills,
            max_per_phase=MAX_CONCURRENT_SUBAGENTS,
            reinforced=(attempt > 0),
            minimal=use_minimal,
        )
        msgs = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        prompt_chars = len(user_prompt)
        goal_run.log(f"--- PLAN attempt {attempt+1} · "
                     f"prompt={prompt_chars} chars · "
                     f"minimal={use_minimal} · reinforced={attempt > 0} ---")
        try:
            resp = client.chat.completions.create(
                model=get_active_model(),
                messages=msgs,
                temperature=0.2,
                max_tokens=2048,
                timeout=LLM_REQUEST_TIMEOUT,
            )
            text = (resp.choices[0].message.content or "") if resp.choices else ""
        except Exception as e:
            goal_run.log(f"ERROR llamada LLM-orquestador attempt {attempt+1}: {e}")
            return {"action": "parse_error", "raw": str(e)}
        last_raw = text
        goal_run.log(f"PLAN RAW response (len={len(text)}):")
        goal_run.log(text[:1500] if text else "(vacío — modelo no generó tokens)")
        if not text.strip():
            consecutive_empty += 1
            goal_run.log(f"  ⚠ respuesta vacía (consecutive_empty="
                         f"{consecutive_empty}). Próximo attempt con prompt "
                         f"minimal.")
            continue
        parsed = _parse_orchestrator_response(text)
        if parsed["action"] != "parse_error":
            return parsed
        # Si el modelo emitió COMANDO: lo detectamos explícitamente para el log
        if "COMANDO:" in text.upper() or text.lstrip().upper().startswith("COMANDO"):
            goal_run.log("  (modelo emitió COMANDO en lugar del bloque; "
                         "reintento con prompt reforzado)")

    # Tras agotar intentos. Si todas las respuestas fueron vacías, mensaje
    # específico (no es "no se pudo parsear" — es que el modelo no generó).
    if consecutive_empty == max_attempts:
        return {
            "action": "parse_error",
            "raw": (
                "Modelo devolvió respuesta VACÍA en los 3 intentos "
                "(incluido el prompt minimal). Probables causas: prompt "
                "demasiado grande para el context window del modelo, "
                "modelo sobrecargado o timeout interno de LM Studio. "
                "Revisa: tamaño del target, MAX_CONTEXT_TOKENS, modelo "
                "cargado en LM Studio."
            ),
        }
    return {"action": "parse_error", "raw": last_raw[:600]}


def _goal_wait_phase(subagent_names, kill_flag, timeout):
    """Polls until all subagents reach a terminal status or timeout. Devuelve
    dict con summaries de cada subagente."""
    start = time.time()
    while True:
        if kill_flag.is_set():
            return {"timed_out": False, "killed": True}
        if time.time() - start > timeout:
            return {"timed_out": True, "killed": False}
        with _subagents_lock:
            statuses = {
                n: _subagents_registry[n].status
                for n in subagent_names
                if n in _subagents_registry
            }
        terminal = all(s in ("done", "failed", "killed", "exhausted")
                       for s in statuses.values())
        if terminal:
            return {"timed_out": False, "killed": False}
        time.sleep(GOAL_POLL_INTERVAL_S)


def _collect_subagent_summaries(names):
    """Reúne info de los subagentes para alimentar al orquestador."""
    out = []
    with _subagents_lock:
        for n in names:
            s = _subagents_registry.get(n)
            if not s:
                continue
            out.append({
                "name": s.name,
                "skill": s.skill,
                "status": s.status,
                "n_commands": len(s.commands_run),
                "updates": list(dict.fromkeys(s.target_updates_applied)),
                "summary": s.summary or s.error or "",
            })
    return out


def _list_available_skills():
    """Devuelve skills con skill.md presente."""
    if not os.path.isdir(SKILLS_DIR):
        return []
    out = []
    for entry in sorted(os.listdir(SKILLS_DIR)):
        if os.path.isfile(os.path.join(SKILLS_DIR, entry, "skill.md")):
            out.append(entry)
    return out


def _goal_run_loop(goal_run):
    """Bucle del orquestador: planifica fases hasta done/blocked/exhausted.
    Tras cada fase completada y al cerrar, vuelca el estado a disco para
    permitir reanudación tras crash/cierre del agente.
    """
    _subagent_thread_marker.active = True  # silencia output a la consola
    is_resumed = goal_run.resumed_from is not None
    try:
        goal_run.status = "running"
        if not goal_run.started_at:
            goal_run.started_at = datetime.now().isoformat(timespec="seconds")
        if is_resumed:
            goal_run.log(f"GoalRun REANUDADO · target={goal_run.target} · "
                         f"continuando desde fase {goal_run.current_phase + 1}"
                         f"/{goal_run.max_phases}")
        else:
            goal_run.log(f"GoalRun iniciado · target={goal_run.target} · "
                         f"max_phases={goal_run.max_phases}")
        goal_run.log(f"GOAL: {goal_run.goal}")
        goal_run.save_state()

        available_skills = _list_available_skills()

        while goal_run.current_phase < goal_run.max_phases:
            if goal_run.kill_flag.is_set():
                goal_run.status = "killed"
                goal_run.outcome_reason = "Kill solicitado por el operador."
                return

            phase_n = goal_run.current_phase + 1
            goal_run.log(f"=== Planificando fase {phase_n} ===")
            plan = _goal_request_plan(goal_run, available_skills)
            goal_run.log(f"Plan decision: action={plan.get('action')}")

            if plan["action"] == "done":
                goal_run.status = "done"
                goal_run.outcome_reason = plan.get("reason", "")
                goal_run.summary = plan.get("summary", "")
                return

            if plan["action"] == "blocked":
                goal_run.status = "blocked"
                goal_run.outcome_reason = plan.get("reason", "")
                return

            if plan["action"] == "parse_error":
                goal_run.status = "failed"
                goal_run.outcome_reason = (
                    f"No se pudo parsear la respuesta del LLM-orquestador. "
                    f"Raw: {plan.get('raw', '')[:200]}"
                )
                return

            # action == "phase"
            subs_spec = plan["subagents"][:MAX_CONCURRENT_SUBAGENTS]
            spawned = []
            errors = []
            for spec in subs_spec:
                # nombre único: prefijo con fase para evitar colisiones
                name = f"p{phase_n}-{spec['name']}"[:48]
                _sub, err = spawn_subagent(name, spec["skill"], spec["task"])
                if err:
                    errors.append((name, err))
                    goal_run.log(f"  ✗ spawn fail '{name}': {err}")
                else:
                    spawned.append(name)
                    goal_run.log(
                        f"  ✓ spawned '{name}' skill={spec['skill']} "
                        f"task={spec['task'][:80]}..."
                    )

            if not spawned:
                goal_run.status = "failed"
                goal_run.outcome_reason = (
                    f"Ningún subagente lanzado en fase {phase_n}. "
                    f"Errores: {errors}"
                )
                return

            # Esperar a que terminen
            goal_run.log(f"Esperando fin de fase {phase_n} "
                         f"({len(spawned)} subagentes)...")
            wait_result = _goal_wait_phase(
                spawned, goal_run.kill_flag, GOAL_PHASE_TIMEOUT_S,
            )

            if wait_result["killed"]:
                # Matar los subagentes que aún estén corriendo
                for n in spawned:
                    kill_subagent(n)
                goal_run.status = "killed"
                goal_run.outcome_reason = "Goal cancelado durante fase."
                return

            if wait_result["timed_out"]:
                for n in spawned:
                    kill_subagent(n)
                goal_run.status = "failed"
                goal_run.outcome_reason = (
                    f"Fase {phase_n} excedió timeout ({GOAL_PHASE_TIMEOUT_S}s)."
                )
                return

            # Recoger summaries y guardar la fase
            summaries = _collect_subagent_summaries(spawned)
            goal_run.phases.append({
                "n": phase_n,
                "subagent_names": spawned,
                "subagent_summaries": summaries,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            })
            goal_run.current_phase += 1
            goal_run.log(f"=== Fase {phase_n} terminada · "
                         f"{len(summaries)} subagentes ===")
            # SNAPSHOT del estado tras cada fase completa. Esto es el punto
            # de checkpoint para reanudación tras crash.
            goal_run.save_state()

        # Si salimos del while sin done/blocked → última oportunidad de
        # declarar GOAL_DONE basado en la evidencia acumulada por todas
        # las fases (los subagentes de la última fase pueden haber escrito
        # TARGET_UPDATEs que SI cumplen el goal, pero el orquestador nunca
        # los re-evaluó porque entró en la fase siguiente). Hacemos una
        # llamada final de evaluación.
        if not goal_run.kill_flag.is_set():
            goal_run.log("=== Evaluación final tras agotar fases ===")
            final_eval = _goal_request_plan(
                goal_run, available_skills, max_attempts=2,
            )
            goal_run.log(f"Evaluación final: action={final_eval.get('action')}")
            if final_eval["action"] == "done":
                goal_run.status = "done"
                goal_run.outcome_reason = final_eval.get("reason", "")
                goal_run.summary = final_eval.get("summary", "")
            elif final_eval["action"] == "blocked":
                goal_run.status = "blocked"
                goal_run.outcome_reason = final_eval.get("reason", "")
            else:
                # parse_error o phase → mantenemos exhausted
                goal_run.status = "exhausted"
                goal_run.outcome_reason = (
                    f"Se agotaron las {goal_run.max_phases} fases sin "
                    f"alcanzar el goal. Revisa el INFORME AUTOMÁTICO "
                    f"para ver la evidencia recopilada — puede contener "
                    f"el vector aunque el orquestador no lo haya declarado."
                )
        else:
            goal_run.status = "killed"
            goal_run.outcome_reason = "Kill solicitado por el operador."

    except Exception as e:
        goal_run.status = "failed"
        goal_run.outcome_reason = f"Excepción: {e}"
        goal_run.log(f"EXCEPCIÓN: {e}")
    finally:
        goal_run.finished_at = datetime.now().isoformat(timespec="seconds")
        # INFORME AUTOMÁTICO sea cual sea el outcome. Sigue silenciado por
        # el thread marker para no interrumpir al operador.
        try:
            goal_run.log("=== Generando informe automático ===")
            rp = _generate_goal_report(goal_run)
            if rp:
                goal_run.report_path = rp
                goal_run.log(f"  ✓ informe: {rp}")
            else:
                goal_run.log("  ✗ informe no generado (ver log para causa)")
        except Exception as e:
            goal_run.log(f"  ✗ excepción generando informe: {e}")
        # SNAPSHOT FINAL con status terminal + report_path.
        goal_run.save_state()
        _subagent_thread_marker.active = False
        with _goal_lock:
            global _active_goal_orch
            if _active_goal_orch is goal_run:
                pass  # se queda referenciado hasta el próximo `goal new`


def start_goal(goal_text, max_phases=GOAL_MAX_PHASES):
    """Lanza un GoalRun en background. Devuelve (GoalRun, None) o (None, err)."""
    with _goal_lock:
        global _active_goal_orch
        if _active_goal_orch and _active_goal_orch.status in ("pending", "running"):
            return None, (
                f"ya hay un goal en curso (id={_active_goal_orch.id}, "
                f"fase {_active_goal_orch.current_phase + 1}/"
                f"{_active_goal_orch.max_phases}). "
                f"`goal kill` para detenerlo antes de lanzar otro"
            )
        if not ACTIVE_TARGET:
            return None, "no hay target activo (carga con `target <nombre>`)"
        if not goal_text or len(goal_text.strip()) < 8:
            return None, "describe el goal en al menos 8 caracteres"
        goal_run = GoalRun(goal_text=goal_text.strip(),
                           target=ACTIVE_TARGET,
                           max_phases=max_phases)
        _active_goal_orch = goal_run
    goal_run.thread = threading.Thread(
        target=_goal_run_loop, args=(goal_run,),
        daemon=True, name=f"goal-{goal_run.id}",
    )
    goal_run.thread.start()
    return goal_run, None


def list_persisted_goals():
    """Devuelve lista de dicts con todos los goals persistidos en disco
    (memory/subagents/_goal-*.state.json), ordenada por started_at DESC."""
    if not os.path.isdir(SUBAGENTS_DIR):
        return []
    out = []
    for fname in os.listdir(SUBAGENTS_DIR):
        if not fname.startswith("_goal-") or not fname.endswith(".state.json"):
            continue
        path = os.path.join(SUBAGENTS_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data["_state_path"] = path
            out.append(data)
        except Exception:
            continue
    out.sort(key=lambda d: d.get("started_at", ""), reverse=True)
    return out


def list_orphan_goals():
    """Goals que quedaron en estado pending/running (el proceso anterior
    terminó sin cerrarlos). Estos son los candidatos a resume."""
    return [g for g in list_persisted_goals()
            if g.get("status") in ("pending", "running")]


def resume_goal(goal_id):
    """Reanuda un GoalRun persistido en disco desde la última fase completa.
    El estado vuelve a 'running', se relanza el thread del loop. Las fases
    ya ejecutadas (en `phases[]`) NO se repiten — el loop continúa desde
    `current_phase`. Devuelve (GoalRun, None) o (None, err).
    """
    with _goal_lock:
        global _active_goal_orch
        if _active_goal_orch and _active_goal_orch.status in ("pending", "running"):
            return None, (
                f"ya hay un goal en curso (id={_active_goal_orch.id}). "
                f"Espera o `goal kill` antes de reanudar otro."
            )
        state_path = os.path.join(SUBAGENTS_DIR, f"_goal-{goal_id}.state.json")
        if not os.path.isfile(state_path):
            return None, f"no existe estado persistido para goal '{goal_id}'"
        try:
            with open(state_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return None, f"error leyendo estado: {e}"
        if data.get("status") in ("done", "blocked", "killed"):
            return None, (
                f"goal '{goal_id}' ya tiene estado terminal "
                f"({data['status']}). Lanza un nuevo `goal` si quieres "
                f"continuar el trabajo."
            )
        if not ACTIVE_TARGET:
            return None, (
                f"no hay target activo. Carga el target del goal "
                f"original (`target {data.get('target', '<nombre>')}`) "
                f"antes de reanudar."
            )
        if data.get("target") and data["target"] != ACTIVE_TARGET:
            return None, (
                f"target activo ('{ACTIVE_TARGET}') no coincide con el "
                f"target del goal ('{data['target']}'). Carga el "
                f"correcto con `target {data['target']}`."
            )
        gr = GoalRun.from_dict(data)
        # Marcamos como reanudado: el loop arranca limpiando status final
        # previo (exhausted/failed → running) y continúa desde current_phase.
        gr.status = "pending"
        gr.outcome_reason = ""
        gr.finished_at = ""
        gr.resumed_from = data.get("id")
        gr.log("=== RESUME desde disco ===")
        gr.log(f"current_phase={gr.current_phase}/{gr.max_phases} · "
               f"fases ya completadas: {len(gr.phases)}")
        gr.save_state()
        _active_goal_orch = gr
    gr.thread = threading.Thread(
        target=_goal_run_loop, args=(gr,),
        daemon=True, name=f"goal-{gr.id}-resumed",
    )
    gr.thread.start()
    return gr, None


def discard_goal_state(goal_id):
    """Borra el archivo .state.json de un goal persistido. El log queda."""
    state_path = os.path.join(SUBAGENTS_DIR, f"_goal-{goal_id}.state.json")
    if not os.path.isfile(state_path):
        return False
    try:
        os.remove(state_path)
        return True
    except OSError:
        return False


def check_orphan_goals_at_startup():
    """Detecta goals huérfanos al arrancar el agente. Muestra panel y
    sugiere `goal resume <id>` o `goal discard <id>`."""
    orphans = list_orphan_goals()
    if not orphans:
        return
    console.print()
    lines = [
        f"[bold {WHITE}]{len(orphans)} goal(s) huérfano(s) detectado(s) "
        f"de sesiones anteriores:[/]",
        "",
    ]
    for g in orphans[:5]:
        n_phases = len(g.get("phases", []))
        lines.append(
            f"  · [bold {CYAN}]{g['id']}[/]  "
            f"target=[bold {PURPLE}]{g.get('target', '?')}[/]  "
            f"fase=[bold]{g.get('current_phase', 0)}/{g.get('max_phases', '?')}[/]  "
            f"status=[yellow]{g.get('status', '?')}[/]"
        )
        goal_disp = g.get("goal", "")[:100]
        lines.append(f"    [dim]{goal_disp}{'…' if len(g.get('goal','')) > 100 else ''}[/]")
        if n_phases:
            last_phase_subs = ", ".join(g["phases"][-1].get("subagent_names", []))
            lines.append(f"    [dim]Última fase ejecutada: {last_phase_subs}[/]")
    if len(orphans) > 5:
        lines.append(f"  · … (+{len(orphans) - 5} más, usa `goal list` para ver todos)")
    lines.append("")
    lines.append(
        f"[dim]Reanudar: [bold]goal resume <id>[/]  ·  "
        f"Descartar: [bold]goal discard <id>[/]  ·  "
        f"Listar todos: [bold]goal list[/][/]"
    )
    console.print(Panel(
        "\n".join(lines),
        title=f"[bold {ORANGE}]⏸ Goals interrumpidos[/]",
        border_style=ORANGE, box=ROUNDED, padding=(1, 2),
    ))


def _read_full_target_for_report(target_name):
    """Lee TODOS los archivos del target SIN cap por archivo (excepto
    _timeline.md que se trunca a 12 kB porque suele ser enorme y narrativo).
    Para el informe final queremos toda la evidencia disponible.
    """
    target_dir = os.path.join(TARGETS_DIR, target_name or "")
    if not target_name or not os.path.isdir(target_dir):
        return []
    priority = [
        "scope.md", "attack-surface.md", "infrastructure.md",
        "identities.md", "credentials.md", "wifi.md", "notes.md",
        "_runs.md", "_timeline.md",
    ]
    seen = set()
    ordered = []
    for fn in priority:
        if os.path.isfile(os.path.join(target_dir, fn)):
            ordered.append(fn)
            seen.add(fn)
    for fn in sorted(os.listdir(target_dir)):
        if fn in seen:
            continue
        if os.path.isfile(os.path.join(target_dir, fn)):
            ordered.append(fn)
    out = []
    for fn in ordered:
        fp = os.path.join(target_dir, fn)
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue
        # _timeline.md trunca a head+tail 12 kB (es narrativo, no aporta entero)
        if fn == "_timeline.md" and len(content) > 12000:
            content = (content[:6000]
                       + f"\n\n[…{len(content) - 12000} chars omitidos…]\n\n"
                       + content[-6000:])
        out.append((fn, content))
    return out


def _extract_target_identity(target_name):
    """Extrae los identificadores únicos del target (cliente, dominios,
    IPs, sector) leyendo `scope.md`. Devuelve dict con campos clave para
    construir un banner anti-confusión en informes y prompts.
    """
    out = {
        "name": target_name,
        "cliente": "",
        "pais": "",
        "dominios": [],
        "ips": [],
        "razon_social": "",
    }
    scope_path = os.path.join(TARGETS_DIR, target_name, "scope.md")
    if not os.path.isfile(scope_path):
        return out
    try:
        with open(scope_path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return out
    # Razón social: la primera línea de la sección Cliente que tenga
    # "Razón social"
    m = re.search(r"Razón social[^:]*:\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        out["razon_social"] = m.group(1).strip().strip("`")
        out["cliente"] = out["razon_social"]
    m = re.search(r"País[^:]*:\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        out["pais"] = m.group(1).strip().strip("`")
    # Dominios desde tabla IN-SCOPE
    domain_matches = re.findall(
        r"\|\s*`?([a-z0-9][a-z0-9\-]+(?:\.[a-z0-9\-]+)+\.[a-z]{2,})`?\s*\|",
        text, re.IGNORECASE,
    )
    seen = set()
    for d in domain_matches:
        dl = d.lower().strip()
        if dl not in seen and not dl.startswith("<"):
            seen.add(dl)
            out["dominios"].append(dl)
    # IPs
    ip_matches = re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text)
    seen_ip = set()
    for ip in ip_matches:
        if ip not in seen_ip:
            seen_ip.add(ip)
            out["ips"].append(ip)
    return out


def _other_targets_for_contamination_check():
    """Lista nombres de los OTROS targets existentes para detectar
    contaminación cruzada (menciones de gc-heat en informe de htspa,
    etc.).
    """
    out = []
    if not os.path.isdir(TARGETS_DIR):
        return out
    for entry in os.listdir(TARGETS_DIR):
        full = os.path.join(TARGETS_DIR, entry)
        if not os.path.isdir(full):
            continue
        ident = _extract_target_identity(entry)
        out.append(ident)
    return out


def _generate_goal_report(goal_run):
    """Genera un informe técnico completo del goal y lo guarda en
    reports/informe-goal-<id>-<target>-<ts>.md. Devuelve path o None.
    """
    if not goal_run.target:
        return None

    target_files = _read_full_target_for_report(goal_run.target)
    files_section = "\n\n".join(
        f"=== {fn} ===\n{content.rstrip()}" for fn, content in target_files
    ) or "(target sin archivos legibles)"

    # Identidad del target ACTUAL + identidades de los OTROS targets
    # para construir reglas anti-contaminación explícitas.
    this_ident = _extract_target_identity(goal_run.target)
    all_idents = _other_targets_for_contamination_check()
    other_idents = [i for i in all_idents if i["name"] != goal_run.target]

    # Banner muy visible al inicio del prompt user
    banner_lines = [
        "═══════════════════════════════════════════════════════════════",
        f"║ INFORME PARA EL TARGET: '{goal_run.target}'",
    ]
    if this_ident["razon_social"]:
        banner_lines.append(
            f"║ CLIENTE (razón social): {this_ident['razon_social']}"
        )
    if this_ident["pais"]:
        banner_lines.append(f"║ PAÍS / JURISDICCIÓN: {this_ident['pais']}")
    if this_ident["dominios"]:
        banner_lines.append(
            f"║ DOMINIOS IN-SCOPE: {', '.join(this_ident['dominios'][:10])}"
        )
    if this_ident["ips"]:
        banner_lines.append(
            f"║ IPs IN-SCOPE: {', '.join(this_ident['ips'][:10])}"
        )
    banner_lines.append("═══════════════════════════════════════════════════════════════")
    banner = "\n".join(banner_lines)

    # Bloque anti-contaminación
    contamination_block = ""
    if other_idents:
        forbidden_lines = []
        for oid in other_idents:
            chunks = []
            if oid["cliente"]:
                chunks.append(f"cliente '{oid['cliente']}'")
            if oid["dominios"]:
                chunks.append(f"dominios {','.join(oid['dominios'][:5])}")
            if oid["ips"]:
                chunks.append(f"IPs {','.join(oid['ips'][:5])}")
            if chunks:
                forbidden_lines.append(
                    f"  · Target '{oid['name']}': {' · '.join(chunks)}"
                )
        if forbidden_lines:
            contamination_block = (
                f"\n=== ⛔ ENTIDADES PROHIBIDAS (de OTROS targets — NO confundir) ===\n"
                f"Este informe es ÚNICAMENTE sobre el target "
                f"'{goal_run.target}'"
                + (f" ({this_ident['razon_social']})" if this_ident['razon_social'] else "") +
                f". Hay OTROS targets en el workspace que NO debes "
                f"mencionar bajo NINGÚN concepto en este informe — son "
                f"clientes distintos, engagements distintos, "
                f"jurisdicciones distintas:\n\n"
                + "\n".join(forbidden_lines) +
                f"\n\nREGLA DURA: si el informe contiene cualquier "
                f"referencia a clientes/dominios/IPs de la lista de "
                f"arriba, está MAL — bórralo. Si tienes la duda, "
                f"verifica en la sección 'ARCHIVOS DEL TARGET' "
                f"(evidencia) — esa es la ÚNICA fuente de verdad para "
                f"este informe.\n"
            )

    # Resumen de subagentes lanzados y sus resultados
    subagent_lines = []
    for ph in goal_run.phases:
        subagent_lines.append(f"### Fase {ph['n']}")
        for s in ph.get("subagent_summaries", []):
            subagent_lines.append(
                f"- **{s['name']}** · skill `{s['skill']}` · "
                f"status `{s['status']}` · {s['n_commands']} comandos "
                f"· updates: {', '.join(s['updates']) or '∅'}"
            )
            if s.get("summary"):
                subagent_lines.append(f"  - Resumen: {s['summary']}")
    subagent_section = (
        "\n".join(subagent_lines)
        if subagent_lines else "_(ningún subagente registrado)_"
    )

    # Título del informe usando razón social si la hay
    title_target = (
        f"{this_ident['razon_social']} · {goal_run.target}"
        if this_ident["razon_social"] else goal_run.target
    )

    user_prompt = (
        f"{banner}\n\n"
        f"Eres el redactor del INFORME TÉCNICO FINAL de un engagement de "
        f"pentesting. El operador lanzó un goal-driven orchestrator y la "
        f"orquestación ha terminado. Tu trabajo: redactar un informe "
        f"completo, detallado, profesional, basado ESTRICTAMENTE en la "
        f"evidencia abajo.\n"
        f"{contamination_block}\n"
        f"=== GOAL ===\n{goal_run.goal}\n\n"
        f"=== OUTCOME DE LA ORQUESTACIÓN ===\n"
        f"Estado: {goal_run.status.upper()}\n"
        f"Motivo: {goal_run.outcome_reason or '(sin motivo registrado)'}\n"
        f"Resumen del orquestador: {goal_run.summary or '(no emitido)'}\n"
        f"Fases ejecutadas: {goal_run.current_phase}/{goal_run.max_phases}\n\n"
        f"=== SUBAGENTES POR FASE ===\n{subagent_section}\n\n"
        f"=== ARCHIVOS DEL TARGET '{goal_run.target}' (única evidencia válida) ===\n"
        f"{files_section}\n\n"
        f"=== INSTRUCCIONES DE REDACCIÓN ===\n"
        f"1. Devuelve el INFORME COMPLETO en Markdown. Primera línea: "
        f"`# Informe técnico · {title_target} · {goal_run.id}`.\n"
        f"2. Estructura obligatoria:\n"
        f"   - **Resumen ejecutivo** (3-6 frases: qué se buscaba, qué se "
        f"encontró, conclusión sobre el goal).\n"
        f"   - **Alcance y metodología** (scope del engagement, fases "
        f"ejecutadas, subagentes lanzados). El cliente es "
        f"'{this_ident['razon_social'] or goal_run.target}'; menciónalo "
        f"explícitamente al inicio de esta sección.\n"
        f"   - **Resumen de hallazgos** (tabla: ID · Título · Severidad · "
        f"Activo afectado).\n"
        f"   - **Detalle por hallazgo** — por cada uno: descripción, "
        f"activos afectados, reproducción, evidencia (cita archivos del "
        f"target), impacto, mitigación, referencias.\n"
        f"   - **Cadena de ataque / vector principal** — narrativa "
        f"end-to-end del vector más probable (basada en notes.md).\n"
        f"   - **Vectores alternativos** — otros caminos identificados.\n"
        f"   - **Recomendaciones** — priorizadas, accionables, técnicas.\n"
        f"   - **Anexos** — Subagentes lanzados con sus comandos y "
        f"resúmenes (puedes referenciar los logs).\n"
        f"3. NO inventes hallazgos que no estén en la evidencia. Si "
        f"algo no está confirmado, márcalo como \"A confirmar\" o "
        f"\"Informativa\".\n"
        f"4. NO emitas COMANDO, TARGET_UPDATE ni paneles del sistema. "
        f"Sólo Markdown puro del informe.\n"
        f"5. Si el goal terminó EXHAUSTED pero hay un vector identificado "
        f"en notes.md, ARGUMÉNTALO claramente y rebate la decisión del "
        f"orquestador en el resumen ejecutivo si la evidencia lo respalda.\n"
        f"6. CHEQUEO FINAL antes de emitir: relee tu informe. Si "
        f"aparece cualquier nombre/dominio/IP de los OTROS targets "
        f"listados arriba, BÓRRALO — eso es contaminación cruzada."
    )

    try:
        resp = client.chat.completions.create(
            model=get_active_model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=6000,
            timeout=LLM_REQUEST_TIMEOUT,
        )
        content = (resp.choices[0].message.content or "") if resp.choices else ""
    except Exception as e:
        goal_run.log(f"ERROR generando informe: {e}")
        return None

    if not content.strip():
        goal_run.log("Informe: modelo devolvió texto vacío.")
        return None

    # Limpieza: strip de regurgitación + TARGET_UPDATE si lo emitiera
    content, _ = _strip_context_regurgitation(content)
    content = strip_target_updates(content)

    # VALIDACIÓN ANTI-CONTAMINACIÓN: detectar menciones a OTROS targets
    contamination_hits = []
    content_lower = content.lower()
    for oid in other_idents:
        if oid["cliente"] and oid["cliente"].lower() in content_lower:
            contamination_hits.append(
                f"cliente '{oid['cliente']}' (de target '{oid['name']}')"
            )
        for d in oid["dominios"]:
            if d.lower() in content_lower:
                contamination_hits.append(
                    f"dominio '{d}' (de target '{oid['name']}')"
                )
                break
        for ip in oid["ips"]:
            if ip in content:
                contamination_hits.append(
                    f"IP '{ip}' (de target '{oid['name']}')"
                )
                break
    if contamination_hits:
        warn = (
            f"\n\n> ⚠ **AVISO DE CONTAMINACIÓN CRUZADA DETECTADA**: "
            f"el modelo incluyó referencias a OTROS targets en este "
            f"informe sobre '{goal_run.target}'. Hits: "
            f"{'; '.join(contamination_hits[:5])}. Revisa el informe "
            f"y elimina las menciones erróneas antes de entregarlo "
            f"al cliente.\n"
        )
        content = warn + content
        goal_run.log(
            f"⚠ contaminación cruzada detectada en informe: "
            f"{contamination_hits[:5]}"
        )

    reports_dir = os.path.join(WORKSPACE, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    fname = (
        f"informe-goal-{goal_run.id}-{goal_run.target}-"
        f"{datetime.now().strftime('%Y%m%d-%H%M')}.md"
    )
    report_path = os.path.join(reports_dir, fname)
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
    except OSError as e:
        goal_run.log(f"ERROR escribiendo informe: {e}")
        return None
    try:
        run_hook("on_report", _build_hook_ctx(
            report_path=report_path,
            report_name=fname,
        ))
    except Exception:
        pass
    goal_run.log(f"Informe generado: {report_path} "
                 f"({os.path.getsize(report_path)} B)")
    return report_path


def kill_goal():
    """Marca kill_flag del goal activo y de los subagentes en curso."""
    with _goal_lock:
        gr = _active_goal_orch
    if not gr or gr.status not in ("pending", "running"):
        return False
    gr.kill_flag.set()
    gr.log("Kill solicitado.")
    # También matamos los subagentes activos lanzados por la fase actual
    if gr.phases:
        last = gr.phases[-1]
        for n in last.get("subagent_names", []):
            kill_subagent(n)
    return True


def _print_goal_finished_panel(gr, ring_bell=False):
    """Panel resumen al terminar el orquestador.
    Si `ring_bell=True`, emite \\a al terminal para alerta sonora del
    operador (útil porque el subagente trabaja en background y el operador
    puede estar haciendo otra cosa).
    """
    status_colors = {
        "done": GREEN, "blocked": "#fbbf24",
        "exhausted": MAGENTA, "killed": "#fbbf24",
        "failed": RED,
    }
    status_emoji = {
        "done": "✅", "blocked": "⚠️", "exhausted": "⏱️",
        "killed": "✋", "failed": "❌",
    }
    color = status_colors.get(gr.status, WHITE)
    emoji = status_emoji.get(gr.status, "·")
    if ring_bell:
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

    lines = [
        f"[bold]Estado:[/] {emoji} [{color}]{gr.status.upper()}[/]",
        f"[bold]Goal:[/] {gr.goal[:200]}{'…' if len(gr.goal) > 200 else ''}",
        f"[bold]Target:[/] [bold {PURPLE}]{gr.target}[/]  ·  "
        f"Fases: {gr.current_phase}/{gr.max_phases}  ·  "
        f"Inicio: {gr.started_at}  ·  Fin: {gr.finished_at}",
    ]
    if gr.outcome_reason:
        lines.append(f"[bold]Motivo:[/] {gr.outcome_reason}")
    if gr.summary:
        lines.append("")
        lines.append(f"[bold]Resumen del orquestador:[/]")
        lines.append(gr.summary)
    if gr.phases:
        lines.append("")
        lines.append(f"[bold]Subagentes lanzados por fase:[/]")
        for ph in gr.phases:
            names = ph.get("subagent_names", [])
            lines.append(f"  · Fase {ph['n']}: {', '.join(names)}")
            for s in ph.get("subagent_summaries", []):
                if s.get("summary"):
                    sm = s["summary"][:150]
                    lines.append(
                        f"    └ [{CYAN}]{s['name']}[/] "
                        f"({s['status']}): {sm}"
                        + ("…" if len(s.get("summary", "")) > 150 else "")
                    )
    if gr.report_path:
        rel = os.path.relpath(gr.report_path, WORKSPACE)
        size_kb = os.path.getsize(gr.report_path) / 1024
        lines.append("")
        lines.append(
            f"[bold {GREEN}]📄 INFORME AUTOMÁTICO GENERADO:[/]"
        )
        lines.append(f"   [{WHITE}]{rel}[/] ({size_kb:.1f} KB)")
        lines.append(
            f"   [dim]Abrir: `cat {rel}` · "
            f"PDF: `pandoc {rel} -o {rel[:-3]}.pdf --pdf-engine=xelatex`[/]"
        )
    else:
        lines.append("")
        lines.append(f"[dim]Informe automático no se pudo generar — "
                     f"usa `informe` manualmente para reintentar.[/]")
    lines.append("")
    lines.append(f"[dim]Log orquestador: "
                 f"{os.path.relpath(gr.log_path, WORKSPACE)}[/]")
    console.print()
    console.print(Panel(
        "\n".join(lines),
        title=f"[bold {color}]» » Goal '{gr.id}' TERMINADO {emoji} «  «[/]",
        border_style=color, box=ROUNDED, padding=(1, 2),
    ))


def _check_goal_notifications():
    """Llamada desde el REPL antes del prompt. Muestra panel + bell al
    terminar un GoalRun (sólo una vez por goal)."""
    with _goal_lock:
        gr = _active_goal_orch
    if gr and gr.status in ("done", "blocked", "exhausted", "killed", "failed") \
            and not gr.reported:
        _print_goal_finished_panel(gr, ring_bell=True)
        gr.reported = True


# ============================================================
# TARGETS — contexto del objetivo
# ============================================================

def list_available_targets():
    """Devuelve [(name, n_files, size_bytes)] de targets/<*>/"""
    if not os.path.isdir(TARGETS_DIR):
        return []
    result = []
    for entry in sorted(os.listdir(TARGETS_DIR)):
        target_dir = os.path.join(TARGETS_DIR, entry)
        if not os.path.isdir(target_dir):
            continue
        n_files = 0
        size = 0
        for fname in os.listdir(target_dir):
            fpath = os.path.join(target_dir, fname)
            if os.path.isfile(fpath):
                n_files += 1
                try:
                    size += os.path.getsize(fpath)
                except OSError:
                    pass
        result.append((entry, n_files, size))
    return result


def _read_target_files(name):
    """Lee todos los archivos legibles de targets/<name>/ y devuelve una lista
    [(filename, content)]. Ignora binarios y archivos no decodificables como UTF-8.
    """
    target_dir = os.path.join(TARGETS_DIR, name)
    if not os.path.isdir(target_dir):
        return None
    files = []
    for fname in sorted(os.listdir(target_dir)):
        fpath = os.path.join(target_dir, fname)
        if not os.path.isfile(fpath):
            continue
        # Filtrado por extensión: si la lleva, debe estar en la lista; sin extensión también se acepta.
        _, ext = os.path.splitext(fname.lower())
        if ext and ext not in TARGET_TEXT_EXTS:
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        files.append((fname, content))
    return files


def _remove_target_messages():
    """Quita del history cualquier mensaje system inyectado por un target previo."""
    history[:] = [
        m for m in history
        if not (
            m.get("role") == "system"
            and m.get("content", "").startswith(TARGET_MARKER_PREFIX)
        )
    ]


TARGET_UPDATE_INSTRUCTIONS = """\
INSTRUCCIONES — ACTUALIZACIÓN AUTOMÁTICA DE ARCHIVOS DEL TARGET

Cuando obtengas datos NUEVOS y CONFIRMADOS por la salida de un comando o por el
usuario (puertos, hosts, subdominios, correos, hashes, hallazgos, decisiones),
emite al final de tu respuesta uno o varios bloques con este formato exacto:

[[TARGET_UPDATE: <archivo_dentro_de_targets/>]]
<contenido markdown ya formateado, listo para hacer append al archivo>
[[/TARGET_UPDATE]]

Reglas:
- Sólo CONFIRMADOS. Nada de suposiciones ni de rellenar plantillas vacías.
- Encabeza cada bloque con un heading que incluya fecha+origen, ej:
  ## [YYYY-MM-DD HH:MM] Hallazgos de nmap a 203.0.113.11
- Elige el archivo correcto:
  · IPs/puertos/servicios/endpoints/subdominios → attack-surface.md
  · DNS/ASN/hosting/tecnologías/certs → infrastructure.md
  · Correos/usuarios/repos/leaks → identities.md
  · SSIDs/BSSIDs/wifi → wifi.md
  · Decisiones, TODOs, hilos sueltos, atajos → notes.md
  · NUNCA escribas en scope.md (lo decide el usuario).
- El archivo no necesita existir; se crea si no está.
- Si la salida tiene varios datos relacionados, agrúpalos en UN bloque por archivo.
- Si no hay nada nuevo que guardar, NO emitas el bloque.
- El bloque se aplica como append al archivo. Tras aplicarlo, el contexto del
  target se recarga automáticamente para reflejar el cambio.
"""


def load_target(name):
    """Lee targets/<name>/* e inyecta el contenido como mensaje system.
    Devuelve (ok, info_dict) — info_dict contiene n_files, size, error si aplica.
    """
    global ACTIVE_TARGET

    files = _read_target_files(name)
    if files is None:
        return False, {"error": f"no existe la carpeta targets/{name}/"}
    if not files:
        return False, {"error": f"targets/{name}/ está vacía o sin archivos legibles"}

    # Limpiar target previo si lo había
    _remove_target_messages()

    body_parts = [
        f"{TARGET_MARKER_PREFIX} {name}]",
        "",
        f"El usuario ha cargado contexto sobre el objetivo '{name}'. Toma estos "
        f"datos como referencia operativa durante toda la sesión: alcance autorizado, "
        f"hosts, credenciales, hallazgos previos, notas. Si más adelante el usuario "
        f"recarga o cambia de target, te avisaré con un nuevo bloque [Target activo: ...].",
        "",
        TARGET_UPDATE_INSTRUCTIONS,
        "",
    ]
    total_size = 0
    for fname, content in files:
        body_parts.append(f"=== {fname} ===")
        body_parts.append(content.rstrip())
        body_parts.append("")
        total_size += len(content)

    history.append({
        "role": "system",
        "content": "\n".join(body_parts).rstrip(),
    })
    ACTIVE_TARGET = name
    return True, {"n_files": len(files), "size": total_size}


# --- Aplicación de updates emitidos por el modelo ---

# Regex tolerante a TARGET_UPDATE mal-cerrados. El modelo a veces olvida el
# `[[/TARGET_UPDATE]]` final o abre uno nuevo encadenado sin cerrar el
# anterior. Aceptamos tres cierres válidos:
#   (a) `[[/TARGET_UPDATE]]` explícito  (forma correcta)
#   (b) próximo `[[TARGET_UPDATE: ...]]` (cierre implícito por encadenado)
#   (c) fin del answer (cierre implícito por EOF)
TARGET_UPDATE_PATTERN = re.compile(
    r"\[\[TARGET_UPDATE:\s*([^\]]+?)\]\]\s*\n?"
    r"(.*?)"
    r"(?:\n?\[\[/TARGET_UPDATE\]\]|(?=\n?\[\[TARGET_UPDATE:)|\Z)",
    re.DOTALL,
)

# Para detectar opens-without-close y avisar al operador en pantalla aunque
# el contenido SÍ se haya guardado (gracias al cierre implícito de arriba).
_TARGET_UPDATE_OPEN_RE = re.compile(r"\[\[TARGET_UPDATE:\s*[^\]]+?\]\]")
_TARGET_UPDATE_CLOSE_RE = re.compile(r"\[\[/TARGET_UPDATE\]\]")

# Archivos protegidos: el modelo NO debe poder modificarlos vía TARGET_UPDATE
TARGET_PROTECTED_FILES = {
    "scope.md",      # alcance autorizado lo define el operador
    "_timeline.md",  # timeline auto-gestionada por el agente
}


def extract_target_updates(text):
    """Devuelve una lista [(filename, content)] con los bloques TARGET_UPDATE
    encontrados en el texto."""
    if not text:
        return []
    return [
        (m.group(1).strip(), m.group(2))
        for m in TARGET_UPDATE_PATTERN.finditer(text)
    ]


def strip_target_updates(text):
    """Elimina los bloques TARGET_UPDATE del texto (para no mostrarlos al
    usuario ni meterlos en el history como ruido)."""
    if not text:
        return text
    return TARGET_UPDATE_PATTERN.sub("", text).strip()


def apply_target_update(filename, content):
    """Append `content` al archivo targets/<ACTIVE_TARGET>/<filename>.
    Devuelve dict con resultado: ok, file (ruta absoluta) o error.
    """
    if not ACTIVE_TARGET:
        return {"ok": False, "filename": filename, "error": "no hay target activo"}

    fname = (filename or "").strip()
    if not fname:
        return {"ok": False, "filename": filename, "error": "nombre vacío"}

    # Reglas de saneado: prohibir absolutos, traversal, caracteres raros
    if fname.startswith("/") or ".." in fname.split("/"):
        return {"ok": False, "filename": fname, "error": "ruta no permitida"}
    if not re.match(r"^[A-Za-z0-9._\-/]+$", fname):
        return {"ok": False, "filename": fname, "error": "caracteres no permitidos"}

    # Bloquear archivos protegidos (scope.md por defecto)
    base = os.path.basename(fname)
    if base in TARGET_PROTECTED_FILES:
        return {"ok": False, "filename": fname, "error": f"archivo protegido ({base})"}

    target_root = os.path.realpath(os.path.join(TARGETS_DIR, ACTIVE_TARGET))
    full = os.path.realpath(os.path.join(target_root, fname))
    # Verificar que el path resuelto sigue dentro de la carpeta del target
    if not (full == target_root or full.startswith(target_root + os.sep)):
        return {"ok": False, "filename": fname, "error": "ruta fuera del target"}

    # Crear subdirs si hace falta
    parent = os.path.dirname(full)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Append con separación si el archivo ya tiene contenido
    body = content.rstrip() + "\n"
    sep = ""
    if os.path.exists(full) and os.path.getsize(full) > 0:
        sep = "\n\n"

    try:
        with open(full, "a", encoding="utf-8") as f:
            f.write(sep + body)
    except OSError as e:
        return {"ok": False, "filename": fname, "error": f"OSError: {e}"}

    # Preview = primera línea no vacía del contenido aplicado
    preview = ""
    for line in body.splitlines():
        if line.strip():
            preview = line.strip()
            break

    return {
        "ok": True,
        "filename": fname,
        "file": full,
        "added_lines": body.count("\n"),
        "added_bytes": len(body) + len(sep),
        "preview": preview,
    }


# ============================================================
# FILE_READ / FILE_EDIT / FILE_WRITE — edición de código por el modelo
# ============================================================
# El modelo puede emitir tres tipos de bloque al final de su respuesta:
#
#   [[FILE_READ: ruta/al/archivo.c]]               ← sin cuerpo
#   [[FILE_READ: ruta/al/archivo.c L10-L40]]       ← rango opcional
#
#   [[FILE_EDIT: ruta/al/archivo.c]]
#   <<<OLD
#   texto exacto que existe en el archivo (debe ser único)
#   OLD>>>
#   <<<NEW
#   texto que lo sustituye
#   NEW>>>
#   [[/FILE_EDIT]]
#
#   [[FILE_WRITE: ruta/al/archivo.c]]
#   contenido entero del archivo (crea o sobreescribe)
#   [[/FILE_WRITE]]
#
# Reglas:
#   - Las rutas son siempre relativas al WORKSPACE o absolutas dentro de él.
#   - Path traversal y ficheros protegidos (.env, privkey, agent.py…) se
#     bloquean a nivel de validación.
#   - FILE_EDIT requiere que `OLD` sea único en el archivo (anti-ambigüedad).
#   - Antes de aplicar EDIT/WRITE se muestra un panel diff coloreado al
#     operador. Si AUTO_EXECUTE=True se aplica directo; si no, se pide y/n.
#   - FILE_READ inyecta el contenido al history con líneas numeradas para
#     que el modelo lo "vea" en el siguiente turno.
# ============================================================

FILE_READ_PATTERN = re.compile(
    r"\[\[FILE_READ:\s*([^\]]+?)\]\]",
    re.IGNORECASE,
)

FILE_EDIT_PATTERN = re.compile(
    r"\[\[FILE_EDIT:\s*([^\]]+?)\]\]\s*\n"
    r"\s*<<<OLD\s*\n(.*?)\n\s*OLD>>>\s*\n"
    r"\s*<<<NEW\s*\n(.*?)\n\s*NEW>>>\s*\n?"
    r"\s*\[\[/FILE_EDIT\]\]",
    re.DOTALL | re.IGNORECASE,
)

FILE_WRITE_PATTERN = re.compile(
    r"\[\[FILE_WRITE:\s*([^\]]+?)\]\]\s*\n"
    r"(.*?)"
    r"\n?\[\[/FILE_WRITE\]\]",
    re.DOTALL | re.IGNORECASE,
)

# Rutas y nombres que el modelo NUNCA puede tocar — defensa contra prompt
# injection y errores. Match exacto contra el basename O prefijo de path
# normalizado relativo al WORKSPACE.
FILE_PROTECTED_BASENAMES = {
    ".env", ".env.local", "privkey.pem", "id_rsa", "id_rsa.pub",
    "id_ed25519", "id_ed25519.pub",
}
FILE_PROTECTED_PREFIXES = (
    ".git/", "venv/", ".venv/", "__pycache__/",
    "memory/sessions/",  # las sesiones las gestiona el agente
)

# Tamaño máximo razonable para leer al contexto (evita inundar el LLM).
FILE_READ_MAX_BYTES = 200_000
FILE_READ_MAX_LINES = 2000


def _validate_workspace_path(path):
    """Resuelve `path` dentro del WORKSPACE y comprueba protecciones.
    Devuelve (ok, absolute_path_or_error_msg, relative_or_error_msg).
    """
    if not path or not isinstance(path, str):
        return (False, "ruta vacía", "")
    raw = path.strip()
    if not raw:
        return (False, "ruta vacía", "")
    # Soportar tanto rutas relativas (al workspace) como absolutas dentro
    # del workspace. Path traversal y simlinks se cortan con realpath.
    if os.path.isabs(raw):
        full = os.path.realpath(raw)
    else:
        full = os.path.realpath(os.path.join(WORKSPACE, raw))
    workspace_root = os.path.realpath(WORKSPACE)
    if not (full == workspace_root or full.startswith(workspace_root + os.sep)):
        return (False, f"ruta fuera del workspace: {raw}", "")
    rel = os.path.relpath(full, workspace_root)
    # Protecciones
    base = os.path.basename(full)
    if base in FILE_PROTECTED_BASENAMES:
        return (False, f"archivo protegido: {base}", "")
    rel_with_slash = rel.replace(os.sep, "/")
    for pref in FILE_PROTECTED_PREFIXES:
        if rel_with_slash == pref.rstrip("/") or rel_with_slash.startswith(pref):
            return (False, f"ruta protegida: {pref}", "")
    # agent.py: el modelo no se modifica a sí mismo.
    if rel_with_slash == "agent.py":
        return (False, "agent.py es modificable solo por el operador, no por el modelo", "")
    return (True, full, rel_with_slash)


def extract_file_reads(text):
    """Devuelve lista de strings con las rutas a leer."""
    if not text:
        return []
    return [m.group(1).strip() for m in FILE_READ_PATTERN.finditer(text)]


def extract_file_edits(text):
    """Devuelve lista de tuplas (path, old_string, new_string)."""
    if not text:
        return []
    return [
        (m.group(1).strip(), m.group(2), m.group(3))
        for m in FILE_EDIT_PATTERN.finditer(text)
    ]


def extract_file_writes(text):
    """Devuelve lista de tuplas (path, content)."""
    if not text:
        return []
    return [
        (m.group(1).strip(), m.group(2))
        for m in FILE_WRITE_PATTERN.finditer(text)
    ]


def strip_file_blocks(text):
    """Elimina los bloques FILE_* del texto (para no meterlos en el history
    como ruido — los resultados se inyectan aparte)."""
    if not text:
        return text
    out = FILE_EDIT_PATTERN.sub("", text)
    out = FILE_WRITE_PATTERN.sub("", out)
    out = FILE_READ_PATTERN.sub("", out)
    return out.strip()


def _guess_syntax_lexer(path):
    """Devuelve el nombre de lexer Pygments según extensión (para syntax
    highlight). None si no se conoce — se mostrará como texto plano."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    mapping = {
        "py": "python", "c": "c", "cpp": "cpp", "cc": "cpp", "h": "c",
        "hpp": "cpp", "rs": "rust", "go": "go", "js": "javascript",
        "ts": "typescript", "tsx": "tsx", "jsx": "jsx",
        "sh": "bash", "bash": "bash", "zsh": "bash",
        "rb": "ruby", "pl": "perl", "java": "java", "kt": "kotlin",
        "cs": "csharp", "php": "php", "swift": "swift",
        "html": "html", "xml": "xml", "css": "css", "scss": "scss",
        "yml": "yaml", "yaml": "yaml", "toml": "toml", "ini": "ini",
        "json": "json", "md": "markdown", "sql": "sql",
        "Dockerfile": "dockerfile",
    }
    return mapping.get(ext)


def _read_file_with_line_numbers(full_path, max_lines=FILE_READ_MAX_LINES,
                                  max_bytes=FILE_READ_MAX_BYTES):
    """Lee el archivo y devuelve dict {ok, content, total_lines, truncated, error}.
    El contenido viene con líneas numeradas estilo `cat -n` (ancho 5)."""
    try:
        st = os.stat(full_path)
    except OSError as e:
        return {"ok": False, "error": f"stat: {e}"}
    if st.st_size > max_bytes:
        return {"ok": False, "error": f"archivo demasiado grande ({st.st_size} bytes, máx {max_bytes})"}
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return {"ok": False, "error": f"read: {e}"}
    total = len(lines)
    truncated = False
    if total > max_lines:
        lines = lines[:max_lines]
        truncated = True
    numbered = "".join(
        f"{i+1:>5}\t{line.rstrip(chr(10))}\n" for i, line in enumerate(lines)
    )
    return {
        "ok": True,
        "content": numbered,
        "total_lines": total,
        "shown_lines": len(lines),
        "truncated": truncated,
    }


def apply_file_read(path):
    """Lee el archivo y devuelve un dict con el contenido numerado para
    inyectarlo al history. NO ejecuta side-effects aparte de stat/read."""
    ok, full, rel = _validate_workspace_path(path)
    if not ok:
        return {"ok": False, "path": path, "error": full}
    if not os.path.isfile(full):
        return {"ok": False, "path": path, "error": "no es un archivo regular o no existe"}
    res = _read_file_with_line_numbers(full)
    if not res["ok"]:
        return {"ok": False, "path": path, "error": res["error"]}
    return {
        "ok": True,
        "path": rel,
        "abs_path": full,
        "content": res["content"],
        "total_lines": res["total_lines"],
        "shown_lines": res["shown_lines"],
        "truncated": res["truncated"],
    }


def _count_occurrences(haystack, needle):
    """Cuenta cuántas veces aparece needle (substring exacto) en haystack."""
    if not needle:
        return 0
    return haystack.count(needle)


def apply_file_edit(path, old_string, new_string):
    """Sustitución quirúrgica de `old_string` por `new_string` en el archivo.
    Requiere que old_string aparezca EXACTAMENTE UNA VEZ en el archivo
    (anti-ambigüedad, igual que el Edit de Claude Code).

    Devuelve dict {ok, path, error, old_string, new_string, diff_lines}.
    """
    ok, full, rel = _validate_workspace_path(path)
    if not ok:
        return {"ok": False, "path": path, "error": full}
    if not os.path.isfile(full):
        return {"ok": False, "path": path, "error": "no existe; usa FILE_WRITE para crearlo"}
    if old_string == new_string:
        return {"ok": False, "path": rel, "error": "OLD y NEW son idénticos"}
    try:
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        return {"ok": False, "path": rel, "error": f"read: {e}"}
    n = _count_occurrences(content, old_string)
    if n == 0:
        return {
            "ok": False, "path": rel,
            "error": "OLD no se encuentra en el archivo (revisa whitespace exacto)",
        }
    if n > 1:
        return {
            "ok": False, "path": rel,
            "error": f"OLD aparece {n} veces; añade más contexto para que sea único",
        }
    new_content = content.replace(old_string, new_string, 1)
    try:
        with open(full, "w", encoding="utf-8") as f:
            f.write(new_content)
    except OSError as e:
        return {"ok": False, "path": rel, "error": f"write: {e}"}
    diff_lines = list(difflib.unified_diff(
        content.splitlines(keepends=False),
        new_content.splitlines(keepends=False),
        fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3,
    ))
    return {
        "ok": True, "path": rel, "abs_path": full,
        "old_string": old_string, "new_string": new_string,
        "diff_lines": diff_lines,
        "old_content": content, "new_content": new_content,
    }


def apply_file_write(path, content):
    """Crea o sobreescribe el archivo entero. Útil para archivos nuevos o
    reescrituras grandes donde un EDIT sería poco práctico.

    Devuelve dict {ok, path, created, error, diff_lines}."""
    ok, full, rel = _validate_workspace_path(path)
    if not ok:
        return {"ok": False, "path": path, "error": full}
    pre_exists = os.path.exists(full)
    old_content = ""
    if pre_exists:
        try:
            with open(full, "r", encoding="utf-8") as f:
                old_content = f.read()
        except (OSError, UnicodeDecodeError):
            old_content = ""
    parent = os.path.dirname(full)
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as e:
            return {"ok": False, "path": rel, "error": f"mkdir: {e}"}
    # Normalizamos: el contenido siempre acaba con \n (UNIX-friendly)
    body = content if content.endswith("\n") else content + "\n"
    try:
        with open(full, "w", encoding="utf-8") as f:
            f.write(body)
    except OSError as e:
        return {"ok": False, "path": rel, "error": f"write: {e}"}
    diff_lines = list(difflib.unified_diff(
        old_content.splitlines(keepends=False),
        body.splitlines(keepends=False),
        fromfile=f"a/{rel}" if pre_exists else "/dev/null",
        tofile=f"b/{rel}", n=3,
    ))
    return {
        "ok": True, "path": rel, "abs_path": full,
        "created": not pre_exists,
        "diff_lines": diff_lines,
        "old_content": old_content, "new_content": body,
    }


def render_file_diff_panel(path, diff_lines, kind="edit"):
    """Pinta un panel rich con el diff unificado coloreado.
    `kind` ∈ {'edit', 'write', 'create'} solo afecta al título.
    """
    if not diff_lines:
        body = Text("(sin cambios visibles)", style="grey50")
    else:
        body = Text()
        for line in diff_lines:
            if line.startswith("+++") or line.startswith("---"):
                body.append(line + "\n", style=f"bold {WHITE}")
            elif line.startswith("@@"):
                body.append(line + "\n", style=f"bold {CYAN}")
            elif line.startswith("+"):
                body.append(line + "\n", style=GREEN)
            elif line.startswith("-"):
                body.append(line + "\n", style=RED)
            else:
                body.append(line + "\n", style="grey50")
    label = {"edit": "FILE_EDIT", "write": "FILE_WRITE",
             "create": "FILE_WRITE (nuevo)"}.get(kind, "FILE_*")
    title = f"[bold {ORANGE}]{label}[/]  ·  [{WHITE}]{path}[/]"
    return Panel(body, title=title, border_style=ORANGE, box=ROUNDED, padding=(1, 2))


def process_file_blocks(answer):
    """Procesa todos los bloques FILE_READ/FILE_EDIT/FILE_WRITE de la
    respuesta del modelo. Renderiza paneles, pide confirmación si AUTO_EXECUTE
    es False, aplica las operaciones, y devuelve dict con:

      - any:            True si había al menos un bloque FILE_*
      - read_messages:  lista de strings para inyectar al history (uno por
                        FILE_READ exitoso) con el contenido del archivo.
      - op_summary:     string con el resumen de EDITs/WRITEs (errores y
                        confirmaciones) para inyectar al history y que el
                        modelo lo vea en el próximo turno.
    """
    reads = extract_file_reads(answer)
    edits = extract_file_edits(answer)
    writes = extract_file_writes(answer)
    if not (reads or edits or writes):
        return {"any": False, "read_messages": [], "op_summary": ""}

    read_messages = []
    op_lines = []

    # --- FILE_READ: sin confirmación, solo lectura ---
    for raw_path in reads:
        r = apply_file_read(raw_path)
        if r["ok"]:
            console.print()
            console.print(Panel(
                Text(f"{r['shown_lines']}/{r['total_lines']} líneas"
                     + (" (truncado)" if r["truncated"] else ""), style="grey50"),
                title=f"[bold {ORANGE}]FILE_READ[/]  ·  [{WHITE}]{r['path']}[/]",
                border_style=ORANGE, box=ROUNDED, padding=(0, 2),
            ))
            read_messages.append(
                f"[FILE_READ: {r['path']}  ({r['shown_lines']}/{r['total_lines']} líneas"
                + (", truncado" if r["truncated"] else "") + ")]\n"
                + r["content"]
                + f"[/FILE_READ: {r['path']}]"
            )
            op_lines.append(f"✓ FILE_READ {r['path']} → {r['shown_lines']} líneas inyectadas al contexto")
        else:
            console.print()
            console.print(Panel(
                f"[{RED}]error:[/] {r['error']}",
                title=f"[bold {RED}]FILE_READ FAILED[/]  ·  [{WHITE}]{raw_path}[/]",
                border_style=RED, box=ROUNDED, padding=(0, 2),
            ))
            op_lines.append(f"✗ FILE_READ {raw_path} → {r['error']}")

    # --- FILE_EDIT: preview + confirmación + apply ---
    for raw_path, old_s, new_s in edits:
        # Pre-validación SIN escribir: comprobamos path y unicidad.
        ok_path, full_or_err, rel = _validate_workspace_path(raw_path)
        if not ok_path:
            console.print(Panel(
                f"[{RED}]ruta inválida:[/] {full_or_err}",
                title=f"[bold {RED}]FILE_EDIT REJECTED[/]  ·  [{WHITE}]{raw_path}[/]",
                border_style=RED, box=ROUNDED,
            ))
            op_lines.append(f"✗ FILE_EDIT {raw_path} → {full_or_err}")
            continue

        # Generar diff preview SIN escribir todavía.
        try:
            with open(full_or_err, "r", encoding="utf-8") as f:
                pre_content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            console.print(Panel(
                f"[{RED}]no se puede leer el archivo:[/] {e}",
                title=f"[bold {RED}]FILE_EDIT REJECTED[/]  ·  [{WHITE}]{rel}[/]",
                border_style=RED, box=ROUNDED,
            ))
            op_lines.append(f"✗ FILE_EDIT {rel} → read: {e}")
            continue
        n = pre_content.count(old_s) if old_s else 0
        if n == 0:
            console.print(Panel(
                f"[{RED}]OLD no se encuentra en el archivo[/] (revisa whitespace).",
                title=f"[bold {RED}]FILE_EDIT REJECTED[/]  ·  [{WHITE}]{rel}[/]",
                border_style=RED, box=ROUNDED,
            ))
            op_lines.append(f"✗ FILE_EDIT {rel} → OLD no encontrado")
            continue
        if n > 1:
            console.print(Panel(
                f"[{RED}]OLD aparece {n} veces — añade más contexto para que sea único.[/]",
                title=f"[bold {RED}]FILE_EDIT REJECTED[/]  ·  [{WHITE}]{rel}[/]",
                border_style=RED, box=ROUNDED,
            ))
            op_lines.append(f"✗ FILE_EDIT {rel} → OLD ambiguo ({n} matches)")
            continue
        post_content = pre_content.replace(old_s, new_s, 1)
        diff_lines = list(difflib.unified_diff(
            pre_content.splitlines(keepends=False),
            post_content.splitlines(keepends=False),
            fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3,
        ))
        console.print()
        console.print(render_file_diff_panel(rel, diff_lines, kind="edit"))

        # Confirmación
        if AUTO_EXECUTE:
            console.print(f"[dim]» AUTOPILOT — aplicando edit sin confirmación[/]")
            apply = True
        else:
            try:
                resp = input(f"[?] aplicar este FILE_EDIT a {rel}? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                resp = "n"
            apply = resp in ("", "y", "yes", "s", "si", "sí")

        if not apply:
            console.print(f"[dim]cancelado por el operador[/]")
            op_lines.append(f"✗ FILE_EDIT {rel} → cancelado por operador")
            continue

        r = apply_file_edit(rel, old_s, new_s)
        if r["ok"]:
            console.print(f"[bold {GREEN}]✓ aplicado[/] {rel}")
            console.print(
                f"[dim]   ↺ si tu editor (VSCode/Cursor/...) no refresca, "
                f"usa Ctrl+Shift+P → 'Revert File' o cierra y reabre la pestaña[/]"
            )
            op_lines.append(f"✓ FILE_EDIT {rel} aplicado")
        else:
            console.print(f"[bold {RED}]✗ fallo:[/] {r['error']}")
            op_lines.append(f"✗ FILE_EDIT {rel} → {r['error']}")

    # --- FILE_WRITE: preview + confirmación + apply ---
    for raw_path, content in writes:
        ok_path, full_or_err, rel = _validate_workspace_path(raw_path)
        if not ok_path:
            console.print(Panel(
                f"[{RED}]ruta inválida:[/] {full_or_err}",
                title=f"[bold {RED}]FILE_WRITE REJECTED[/]  ·  [{WHITE}]{raw_path}[/]",
                border_style=RED, box=ROUNDED,
            ))
            op_lines.append(f"✗ FILE_WRITE {raw_path} → {full_or_err}")
            continue
        pre_exists = os.path.exists(full_or_err)
        old_content = ""
        if pre_exists:
            try:
                with open(full_or_err, "r", encoding="utf-8") as f:
                    old_content = f.read()
            except (OSError, UnicodeDecodeError):
                old_content = ""
        body = content if content.endswith("\n") else content + "\n"

        # GUARDRAIL: si el archivo existe Y el cambio toca <30% de líneas,
        # esto es señal de que el modelo eligió mal la herramienta — debería
        # haber usado FILE_EDIT. Rechazamos automáticamente para forzarle a
        # razonar mejor y evitar reescrituras enteras con cambios "fantasma"
        # que el operador no ha pedido.
        if pre_exists and old_content:
            old_lines = old_content.splitlines()
            new_lines = body.splitlines()
            sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
            ratio_unchanged = sm.ratio()  # 0..1, 1 = idénticos
            ratio_changed = 1.0 - ratio_unchanged
            FILE_WRITE_MIN_CHANGE_RATIO = 0.30
            if ratio_changed < FILE_WRITE_MIN_CHANGE_RATIO:
                pct = int(ratio_changed * 100)
                console.print(Panel(
                    f"[{RED}]FILE_WRITE rechazado por guardrail anti-reescritura.[/]\n\n"
                    f"El archivo [bold]{rel}[/] ya existe y el cambio propuesto sólo "
                    f"toca el [bold]{pct}%[/] de las líneas (umbral: "
                    f"{int(FILE_WRITE_MIN_CHANGE_RATIO*100)}%).\n\n"
                    f"Para cambios pequeños usa [bold]FILE_EDIT[/] con bloques "
                    f"<<<OLD/<<<NEW. FILE_WRITE es sólo para crear archivos nuevos "
                    f"o sustituirlos por completo.\n\n"
                    f"[dim]Razón: una reescritura completa con un cambio pequeño suele "
                    f"introducir modificaciones que el operador no ha pedido.[/]",
                    title=f"[bold {RED}]GUARDRAIL · FILE_WRITE REJECTED[/]  ·  "
                          f"[{WHITE}]{rel}[/]",
                    border_style=RED, box=ROUNDED, padding=(1, 2),
                ))
                op_lines.append(
                    f"✗ FILE_WRITE {rel} → REJECTED por guardrail "
                    f"(cambio {pct}% < {int(FILE_WRITE_MIN_CHANGE_RATIO*100)}%); "
                    f"usa FILE_EDIT en su lugar"
                )
                continue

        diff_lines = list(difflib.unified_diff(
            old_content.splitlines(keepends=False),
            body.splitlines(keepends=False),
            fromfile=f"a/{rel}" if pre_exists else "/dev/null",
            tofile=f"b/{rel}", n=3,
        ))
        console.print()
        kind = "write" if pre_exists else "create"
        console.print(render_file_diff_panel(rel, diff_lines, kind=kind))

        # FILE_WRITE sobre archivo existente SIEMPRE pide confirmación,
        # incluso con AUTO_EXECUTE=True. Es destructivo (sobreescribe) y
        # merece más cuidado que un EDIT. Archivos nuevos sí pueden ir auto.
        if AUTO_EXECUTE and not pre_exists:
            console.print(f"[dim]» AUTOPILOT — creando archivo sin confirmación[/]")
            apply = True
        else:
            verb = "sobrescribir (archivo EXISTE)" if pre_exists else "crear"
            extra = f" [{ORANGE}](confirmación obligatoria por sobrescritura)[/]" if pre_exists and AUTO_EXECUTE else ""
            try:
                resp = input(f"[?] {verb} {rel}?{extra} [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                resp = "n"
            # Para WRITE sobre existente, el default seguro es 'n'.
            default_safe = pre_exists
            if default_safe:
                apply = resp in ("y", "yes", "s", "si", "sí")
            else:
                apply = resp in ("", "y", "yes", "s", "si", "sí")

        if not apply:
            console.print(f"[dim]cancelado por el operador[/]")
            op_lines.append(f"✗ FILE_WRITE {rel} → cancelado por operador")
            continue

        r = apply_file_write(rel, content)
        if r["ok"]:
            label = "creado" if r["created"] else "sobreescrito"
            console.print(f"[bold {GREEN}]✓ {label}[/] {rel}")
            console.print(
                f"[dim]   ↺ si tu editor (VSCode/Cursor/...) no refresca, "
                f"usa Ctrl+Shift+P → 'Revert File' o cierra y reabre la pestaña[/]"
            )
            op_lines.append(f"✓ FILE_WRITE {rel} {label}")
        else:
            console.print(f"[bold {RED}]✗ fallo:[/] {r['error']}")
            op_lines.append(f"✗ FILE_WRITE {rel} → {r['error']}")

    op_summary = ""
    if op_lines:
        op_summary = "[FILE_OPS_RESULT]\n" + "\n".join(op_lines) + "\n[/FILE_OPS_RESULT]"

    return {
        "any": True,
        "read_messages": read_messages,
        "op_summary": op_summary,
    }


def unload_target():
    """Elimina del history el bloque del target activo y limpia el marcador."""
    global ACTIVE_TARGET
    if not ACTIVE_TARGET:
        return False
    _remove_target_messages()
    history.append({
        "role": "system",
        "content": f"[Target descargado: {ACTIVE_TARGET}]",
    })
    ACTIVE_TARGET = None
    return True


# Máximo de líneas de output a preservar por entrada en _timeline.md.
# Más alto = más contexto para el informe, más tokens en cada reload.
TIMELINE_OUTPUT_LINES_MAX = 40


def append_timeline_entry(command, result):
    """Añade una entrada al `_timeline.md` del target activo con info del
    comando ejecutado. Es MECÁNICO — no depende del modelo. Se ejecuta tras
    cada `run_command` para garantizar que nada se pierde entre turnos.
    """
    if not ACTIVE_TARGET:
        return None

    target_dir = os.path.join(TARGETS_DIR, ACTIVE_TARGET)
    if not os.path.isdir(target_dir):
        return None

    timeline_path = os.path.join(target_dir, "_timeline.md")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Truncar output para no inundar el contexto del modelo (lo carga
    # con el resto de archivos del target en cada reload).
    text = (result or "").rstrip()
    lines = text.split("\n")
    if len(lines) > TIMELINE_OUTPUT_LINES_MAX:
        head = "\n".join(lines[:TIMELINE_OUTPUT_LINES_MAX])
        truncated_note = f"\n… (truncado, {len(lines) - TIMELINE_OUTPUT_LINES_MAX} líneas más)"
        body = head + truncated_note
    else:
        body = text or "(sin salida)"

    # Crear con header si no existe
    if not os.path.exists(timeline_path):
        header = (
            f"# {ACTIVE_TARGET} — Timeline automática\n\n"
            f"Bitácora cronológica de TODOS los comandos ejecutados por el agente "
            f"durante el engagement. **Se rellena solo por el agente, no por el modelo.** "
            f"Útil como fuente de verdad para el informe final y para auditoría "
            f"de la actividad.\n"
        )
        with open(timeline_path, "w", encoding="utf-8") as f:
            f.write(header)

    entry = (
        f"\n## [{ts}] `{command}`\n\n"
        f"```\n{body}\n```\n"
    )
    with open(timeline_path, "a", encoding="utf-8") as f:
        f.write(entry)

    return timeline_path


# ============================================================
# REGISTRO DE SCANS  (anti-duplicación cross-sesión)
# ============================================================
#
# `_timeline.md` es un bitácora cronológica para informes — útil pero ruidoso
# para el modelo. `_runs.md` es la versión estructurada y CHECKLIST: una
# línea por comando ejecutado, agrupado por herramienta. Está pensado para
# que el modelo lo LEA antes de proponer un escaneo y NO repita trabajo.
#
#  - Lo mantiene el agente automáticamente tras cada `run_command` con
#    target activo, igual que `_timeline.md`.
#  - El compactador NUNCA lo trunca (ver _compact_target_section).
#  - Se persiste en disco bajo `targets/<name>/_runs.md`, así que sobrevive
#    a sesiones diferentes.
#  - Sólo se registran herramientas de NETWORK_TOOLS (scans reales). `ls`,
#    `cat`, `which`, etc. no ensucian el registro.

def _runs_first_tool_token(command):
    """Devuelve el primer binario del comando (saltando env vars y `sudo`).
    Sirve para clasificar el run en su sección de _runs.md."""
    if not command:
        return None
    tokens = command.strip().split()
    if not tokens:
        return None
    first = tokens[0]
    # Saltar `VAR=valor`
    i = 0
    while i < len(tokens) and "=" in tokens[i] and not tokens[i].startswith("-"):
        i += 1
        if i >= len(tokens):
            return None
        first = tokens[i]
    if first == "sudo" and i + 1 < len(tokens):
        first = tokens[i + 1]
    return first.split("/")[-1]


# Extensiones que NO son TLD aunque el token parezca un dominio. Sin esto,
# `passwords.txt` o `wordlist.md` se clasifican como host y rompen tanto la
# detección de duplicados como la descripción del spinner.
_NOT_A_TLD = {
    "txt", "md", "json", "xml", "yaml", "yml", "csv", "tsv", "log",
    "pdf", "sh", "py", "rb", "pl", "js", "html", "htm", "css", "conf",
    "ini", "cfg", "env", "lock", "tmpl",
    "nmap", "gnmap", "http", "pcap", "har", "har1",
    "gz", "zip", "tar", "bz2", "xz", "7z",
    "nse", "wordlist", "list", "dic", "bak", "swp", "tmp",
    "key", "pem", "crt", "cer", "pfx", "p12", "jks", "der",
    "db", "sqlite", "sqlite3", "rdb", "ldb",
    "png", "jpg", "jpeg", "gif", "bmp", "svg", "webp", "ico",
    "mp3", "mp4", "wav", "ogg", "avi", "mov",
}


def _runs_target_tokens(command):
    """Heurística para extraer hosts/IPs/dominios del comando. Mira tokens
    que parecen IPv4, hostnames o URLs. Excluye archivos con extensión
    conocida. Suficiente para emparejar runs duplicados sin ser exacto."""
    if not command:
        return []
    tokens = re.split(r"\s+", command)
    out = []
    for t in tokens:
        t = t.strip("`'\"")
        if not t or t.startswith("-"):
            continue
        # Descartar si parece path absoluto/relativo
        if t.startswith("/") or t.startswith("./") or t.startswith("../"):
            continue
        # IPv4 (opcional /CIDR)
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?", t):
            out.append(t)
            continue
        # URL con cualquier esquema (http, https, ssh, ftp, rdp, mysql…)
        m = re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://([^/\s]+)", t)
        if m:
            host = m.group(1)
            # quita user:pass@ y :puerto
            host = re.sub(r"^[^@]+@", "", host)
            host = re.sub(r":\d+$", "", host)
            out.append(host)
            continue
        # Hostname con TLD (puntos y al menos dos letras al final)
        if re.fullmatch(
            r"[A-Za-z0-9]([A-Za-z0-9\-\.]*[A-Za-z0-9])?\.[A-Za-z]{2,}", t
        ):
            # Filtrar si el "TLD" es en realidad una extensión de archivo.
            last_part = t.rsplit(".", 1)[-1].lower()
            if last_part in _NOT_A_TLD:
                continue
            out.append(t)
    # Deduplicar preservando orden
    seen = set()
    uniq = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


# Marcador de inicio de sección por herramienta en _runs.md
_RUNS_TOOL_HEADER_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)


def _read_runs_file(target):
    """Devuelve el contenido bruto de targets/<target>/_runs.md o '' si no existe."""
    if not target:
        return ""
    path = os.path.join(TARGETS_DIR, target, "_runs.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def parse_runs(target):
    """Lee `_runs.md` y devuelve una lista de dicts con los runs registrados.
    Cada dict: {ts, tool, rc, command, output_files, target_tokens}."""
    raw = _read_runs_file(target)
    if not raw:
        return []
    runs = []
    current_tool = None
    line_re = re.compile(
        r"^- \[(?P<ts>[^\]]+)\] \[rc=(?P<rc>-?\d+)\] `(?P<cmd>.+?)`"
        r"(?:\s+→\s+(?P<files>.+))?$"
    )
    for line in raw.splitlines():
        line = line.rstrip()
        m_header = _RUNS_TOOL_HEADER_RE.match(line)
        if m_header:
            current_tool = m_header.group(1).strip()
            continue
        m = line_re.match(line)
        if not m:
            continue
        cmd = m.group("cmd")
        runs.append({
            "ts": m.group("ts"),
            "rc": int(m.group("rc")),
            "tool": current_tool or _runs_first_tool_token(cmd),
            "command": cmd,
            "output_files": (
                [x.strip() for x in m.group("files").split(",")]
                if m.group("files") else []
            ),
            "target_tokens": _runs_target_tokens(cmd),
        })
    return runs


def _runs_fingerprint(tool, target_tokens, command):
    """Huella corta para emparejar runs duplicados. Considera:
      - herramienta (tool)
      - hosts/dominios mencionados (sorted)
      - argumentos clave (-p, -sV, --script, -u, -d, -tags, -t, -w)
    Ignora paths de output (-o, -oN, …) y nombres de archivos."""
    arg_re = re.compile(
        r"(?:^|\s)(?P<flag>-p|-sV|-sC|-A|-O|--script|-u|-d|-tags|-t|-w|-r)"
        r"(?:[=\s]+(?P<val>\S+))?"
    )
    args = []
    for m in arg_re.finditer(command or ""):
        flag = m.group("flag")
        val = m.group("val") or ""
        # Para --script y -p el valor matter mucho; para otros también.
        args.append(f"{flag}={val}")
    return (
        (tool or "").lower(),
        tuple(sorted(set(target_tokens))),
        tuple(sorted(args)),
    )


def find_duplicate_runs(command, target):
    """Devuelve la lista de runs previos en `_runs.md` que comparten
    fingerprint con `command`. Vacía si nada coincide o si target/tool no
    aplica."""
    if not target or not command:
        return []
    tool = _runs_first_tool_token(command)
    if not tool or tool not in NETWORK_TOOLS:
        return []
    tokens = _runs_target_tokens(command)
    if not tokens:
        # Sin tokens de target, no podemos comparar de forma fiable.
        return []
    fp_new = _runs_fingerprint(tool, tokens, command)
    matches = []
    for r in parse_runs(target):
        if r["tool"] != tool:
            continue
        fp_old = _runs_fingerprint(r["tool"], r["target_tokens"], r["command"])
        if fp_new == fp_old:
            matches.append(r)
    return matches


def append_runs_entry(command, rc):
    """Añade una línea a `targets/<ACTIVE_TARGET>/_runs.md` SI la herramienta
    está en NETWORK_TOOLS. Idempotente: si la huella ya existe en el archivo,
    no la duplica. Devuelve el path o None."""
    if not ACTIVE_TARGET:
        return None
    tool = _runs_first_tool_token(command)
    if not tool or tool not in NETWORK_TOOLS:
        return None

    target_dir = os.path.join(TARGETS_DIR, ACTIVE_TARGET)
    if not os.path.isdir(target_dir):
        return None
    runs_path = os.path.join(target_dir, "_runs.md")

    # Idempotencia: si la huella ya está, no añadimos
    for r in parse_runs(ACTIVE_TARGET):
        if r["command"] == command:
            return runs_path

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    output_files = _detect_output_files(command)
    files_part = (
        " → " + ", ".join(output_files)
        if output_files else ""
    )
    entry_line = f"- [{ts}] [rc={rc}] `{command}`{files_part}\n"

    # Asegurar header + sección de herramienta
    if not os.path.exists(runs_path):
        with open(runs_path, "w", encoding="utf-8") as f:
            f.write(
                f"# {ACTIVE_TARGET} — Scans ejecutados (autogenerado)\n\n"
                f"Lista estructurada de comandos de escaneo ya ejecutados "
                f"contra este target. **No editar a mano** — lo mantiene el "
                f"agente tras cada ejecución. Consúltalo antes de proponer "
                f"un nuevo escaneo: si ya está aquí, NO lo repitas salvo "
                f"que el usuario lo pida explícitamente.\n"
            )

    # ¿Existe ya la sección para esa herramienta?
    with open(runs_path, "r", encoding="utf-8") as f:
        content = f.read()
    section_header = f"## {tool}"
    if section_header in content.splitlines():
        # Insertar la línea al final de esa sección (antes del próximo `## ` o EOF)
        lines = content.splitlines(keepends=True)
        new_lines = []
        inserted = False
        in_section = False
        for line in lines:
            if line.rstrip() == section_header:
                in_section = True
                new_lines.append(line)
                continue
            if in_section and line.startswith("## "):
                # fin de sección — insertar antes
                new_lines.append(entry_line)
                inserted = True
                in_section = False
            new_lines.append(line)
        if in_section and not inserted:
            # llegó al EOF estando en la sección
            new_lines.append(entry_line)
            inserted = True
        with open(runs_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    else:
        # Crear sección nueva al final
        with open(runs_path, "a", encoding="utf-8") as f:
            if not content.endswith("\n"):
                f.write("\n")
            f.write(f"\n{section_header}\n\n{entry_line}")
    return runs_path


# ============================================================
# DETECCIÓN DINÁMICA
# ============================================================

def get_lmstudio_models():
    try:
        response = requests.get(f"{LMSTUDIO_BASE_URL}/models", timeout=3)
        response.raise_for_status()

        data = response.json()
        models = []

        for item in data.get("data", []):
            model_id = item.get("id")
            if model_id:
                models.append(model_id)

        return models if models else [MODEL_NAME_FALLBACK]

    except Exception:
        return [MODEL_NAME_FALLBACK]


def get_active_model():
    models = get_lmstudio_models()
    return models[0] if models else MODEL_NAME_FALLBACK


def get_mullvad_status():
    if shutil.which("mullvad") is None:
        return "Mullvad CLI no instalado"

    try:
        result = subprocess.run(
            ["mullvad", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )

        output = result.stdout.strip()

        if not output:
            return "Estado desconocido"

        return output.splitlines()[0]

    except Exception:
        return "No se pudo consultar Mullvad"


def get_tailscale_status():
    """Devuelve un string corto con el estado del cliente Tailscale.

    Estados posibles:
      - "no instalado"
      - "detenido / sin login"
      - "conectado · <ip> (<hostname>)"            ← caso normal
      - "conectado · <ip> · LM Studio en tailnet ✓" ← si la URL de LM Studio
                                                     apunta a un peer del tailnet
    """
    if shutil.which("tailscale") is None:
        return "no instalado"

    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return "detenido / sin login"

        data = json.loads(result.stdout)

        backend = data.get("BackendState", "")
        if backend != "Running":
            # NeedsLogin, NoState, Stopped, Starting, ...
            return f"{backend.lower() or 'desconocido'} (sin conexión al tailnet)"

        self_node = data.get("Self") or {}
        ips = self_node.get("TailscaleIPs") or []
        ipv4 = next((ip for ip in ips if ":" not in ip), ips[0] if ips else "?")
        dns_name = (self_node.get("DNSName") or "").rstrip(".")
        # Acorta hostname.tailXXXX.ts.net → hostname.ts.net si es muy largo.
        short_host = dns_name.split(".")[0] if dns_name else (self_node.get("HostName") or "")

        # ¿El LM Studio configurado vive dentro del tailnet?
        lm_in_tailnet = _lmstudio_in_tailnet(data)

        suffix = "LM Studio en tailnet ✓" if lm_in_tailnet else short_host
        if suffix:
            return f"conectado · {ipv4} · {suffix}"
        return f"conectado · {ipv4}"

    except Exception:
        return "no disponible"


def _lmstudio_in_tailnet(ts_data: dict) -> bool:
    """True si LMSTUDIO_BASE_URL apunta a una IP/hostname dentro del tailnet
    descrito por `ts_data` (output de `tailscale status --json`)."""
    try:
        from urllib.parse import urlparse
        host = urlparse(LMSTUDIO_BASE_URL).hostname or ""
        if not host:
            return False
        host = host.lower()

        # Conjuntos de IPs y nombres del tailnet (Self + Peers).
        nodes = [ts_data.get("Self") or {}]
        nodes.extend((ts_data.get("Peer") or {}).values())

        tailnet_ips = set()
        tailnet_names = set()
        for n in nodes:
            for ip in n.get("TailscaleIPs") or []:
                tailnet_ips.add(ip.lower())
            dns = (n.get("DNSName") or "").rstrip(".").lower()
            if dns:
                tailnet_names.add(dns)
            hn = (n.get("HostName") or "").lower()
            if hn:
                tailnet_names.add(hn)

        if host in tailnet_ips or host in tailnet_names:
            return True
        # Match parcial por hostname corto (kali-pc vs kali-pc.tailXXXX.ts.net)
        host_short = host.split(".")[0]
        return any(host_short == n.split(".")[0] for n in tailnet_names if n)
    except Exception:
        return False


TOOL_CATALOG = [
    ("Port scan & host discovery", [
        "nmap", "masscan", "rustscan", "naabu", "unicornscan", "zmap",
        "arp-scan", "arping", "fping", "netdiscover", "hping3",
    ]),
    ("Service fingerprinting", [
        "amap", "nc", "ncat", "whatweb", "httpx", "wafw00f", "webanalyze",
        "wappalyzer",
    ]),
    ("DNS recon", [
        "dig", "host", "dnsx", "dnsrecon", "dnsenum", "fierce", "dnsmap",
        "dnstwist", "puredns", "shuffledns", "massdns", "subfinder",
        "assetfinder", "amass", "findomain", "sublist3r",
    ]),
    ("Web fuzzing & crawling", [
        "ffuf", "feroxbuster", "gobuster", "dirb", "dirsearch", "wfuzz",
        "arjun", "paramspider", "katana", "hakrawler", "gospider",
        "waybackurls", "gau",
    ]),
    ("Web vuln scan & CMS", [
        "nuclei", "nikto", "wpscan", "joomscan", "droopescan", "wapiti",
        "skipfish", "searchsploit",
    ]),
    ("SSL/TLS", [
        "sslscan", "sslyze", "testssl.sh", "openssl",
    ]),
    ("SMB / NetBIOS / AD", [
        "enum4linux", "enum4linux-ng", "smbclient", "smbmap", "rpcclient",
        "nbtscan", "nmblookup", "netexec", "crackmapexec", "evil-winrm",
        "responder",
    ]),
    ("LDAP & Kerberos", [
        "ldapsearch", "ldapdomaindump", "kerbrute",
        "bloodhound-python",
        "impacket-GetNPUsers", "impacket-GetUserSPNs",
        "impacket-secretsdump", "impacket-smbexec", "impacket-wmiexec",
        "impacket-psexec", "impacket-mssqlclient",
    ]),
    ("SNMP / SMTP / FTP / SSH", [
        "snmpwalk", "snmp-check", "onesixtyone", "braa",
        "smtp-user-enum", "swaks", "ssh-keyscan",
    ]),
    ("Databases", [
        "mysql", "psql", "redis-cli", "mongosh",
    ]),
    ("RDP / VNC", [
        "xfreerdp", "rdesktop",
    ]),
    ("VoIP / Wireless / Bluetooth", [
        "svmap", "airodump-ng", "kismet", "wifite", "bluetoothctl",
        "hcitool", "bluelog", "btscanner",
    ]),
    ("Brute force / Passwords", [
        "hydra", "medusa", "patator", "john", "hashcat",
    ]),
    ("Exploitation", [
        "sqlmap", "msfconsole", "msfvenom",
    ]),
    ("OSINT / APIs", [
        "shodan", "censys", "theHarvester", "spiderfoot", "recon-ng",
        "holehe", "h8mail", "sherlock", "maigret", "exiftool",
    ]),
    ("Sniffing & Network", [
        "tcpdump", "tshark", "wireshark", "proxychains4",
    ]),
    ("Utilidades", [
        "curl", "wget", "jq", "ssh", "whois", "traceroute", "mtr",
        "anew", "unfurl", "qsreplace", "aquatone", "gowitness",
    ]),
]


def detect_installed_tools():
    """Comprueba qué herramientas del catálogo están instaladas.
    Devuelve (installed_list, missing_list) — listas planas para retro-
    compatibilidad. La estructura categorizada está en `TOOL_CATALOG`.
    """
    tools = []
    seen = set()
    for _cat, names in TOOL_CATALOG:
        for n in names:
            if n not in seen:
                tools.append(n)
                seen.add(n)

    installed = []
    missing = []

    for tool in tools:
        if shutil.which(tool):
            installed.append(tool)
        else:
            missing.append(tool)

    return installed, missing


def detect_folders(path):
    full_path = os.path.expanduser(path)

    if not os.path.exists(full_path):
        return []

    items = []

    for item in os.listdir(full_path):
        item_path = os.path.join(full_path, item)

        if os.path.isdir(item_path):
            items.append(item)
        elif item.endswith(".py"):
            items.append(item.replace(".py", ""))

    return sorted(items)


def format_list(items, max_items=8):
    if not items:
        return "ninguno"

    visible = items[:max_items]
    output = ", ".join(visible)

    if len(items) > max_items:
        output += f", +{len(items) - max_items} más"

    return output


# ============================================================
# ARTE ANSI: ESCUDO + CALAVERA
# ============================================================

EMBLEM_PATH = os.path.expanduser("~/ai-agent-kali/assets/emblem_clean.png")


def is_kitty_terminal():
    return (
        os.environ.get("TERM") == "xterm-kitty"
        or "KITTY_WINDOW_ID" in os.environ
    )


def render_kitty_emblem_raw(width=60, height=32):
    """Devuelve los bytes raw del protocolo kitty graphics, o None si falla."""
    if shutil.which("chafa") is None or not os.path.isfile(EMBLEM_PATH):
        return None, 0, 0
    try:
        result = subprocess.run(
            [
                "chafa",
                f"--size={width}x{height}",
                "--format=kitty",
                "--polite=on",
                EMBLEM_PATH,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout:
            return None, 0, 0
        return result.stdout, width, height
    except Exception:
        return None, 0, 0


def display_kitty_emblem_inline():
    """
    Renderiza el emblema usando 'kitten icat' nativo de kitty.
    icat hereda stdout del proceso padre y escribe escapes directamente al
    terminal — sin buffers intermedios que rompan los códigos APC.
    """
    if not os.path.isfile(EMBLEM_PATH):
        return False
    if shutil.which("kitty") is None:
        return False
    try:
        # Forzar flush de todo lo que rich tenga pendiente antes
        console.file.flush()
        sys.stdout.flush()

        # Limpiar env vars que harían a icat envolver los escapes en passthrough
        # de tmux/screen (rompe el render cuando el terminal real es kitty puro).
        env = os.environ.copy()
        for var in ("TMUX", "TMUX_PANE", "STY"):
            env.pop(var, None)
        if env.get("TERM", "").startswith(("screen", "tmux")):
            env["TERM"] = "xterm-kitty"

        result = subprocess.run(
            [
                "kitty", "+kitten", "icat",
                "--align=center",
                EMBLEM_PATH,
            ],
            timeout=10,
            check=False,
            env=env,
        )
        return result.returncode == 0
    except Exception:
        return False


def render_emblem_with_chafa(width=64, height=34, symbols="block+vhalf+hhalf+space", canvas_width=68):
    if shutil.which("chafa") is None or not os.path.isfile(EMBLEM_PATH):
        return None
    try:
        kitty = is_kitty_terminal()
        if kitty:
            cmd = [
                "chafa",
                f"--size={width}x{height}",
                "--format=kitty",
                "--polite=on",
                EMBLEM_PATH,
            ]
        else:
            cmd = [
                "chafa",
                f"--size={width}x{height}",
                f"--symbols={symbols}",
                "--colors=truecolor",
                "--polite=on",
                "--dither=none",
                "--optimize=9",
                EMBLEM_PATH,
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0 or not result.stdout:
            return None

        pad_left = max(0, (canvas_width - width) // 2) * " "
        out = Text()
        for raw_line in result.stdout.rstrip("\n").split("\n"):
            out.append(pad_left)
            if kitty:
                # Modo kitty: preservar bytes raw (escapes APC) sin parsear
                out.append(raw_line)
            else:
                # Modo símbolos: parsear SGR para extraer colores
                out.append(Text.from_ansi(raw_line))
            out.append("\n")
        return out
    except Exception:
        return None


def build_skull_shield_art():
    chafa_art = render_emblem_with_chafa()
    if chafa_art is not None:
        wrapped = Text()
        wrapped.append(chafa_art)
        wrapped.append("\n")
        wrapped.append("POWER YOUR OPS".center(60), style=ORANGE_BRIGHT)
        return wrapped

    art = Text()

    W = 60
    INNER = 40
    PAD = (W - INNER - 2) // 2

    def add_centered(text, style):
        art.append(text.center(W), style=style)
        art.append("\n")

    def shield_v(*segments):
        total = sum(len(t) for t, _ in segments)
        ipad = max(0, INNER - total)
        left = ipad // 2
        right = ipad - left
        art.append(" " * PAD)
        art.append("│", style=ORANGE)
        if left:
            art.append(" " * left)
        for t, s in segments:
            if s:
                art.append(t, style=s)
            else:
                art.append(t)
        if right:
            art.append(" " * right)
        art.append("│", style=ORANGE)
        art.append(" " * PAD)
        art.append("\n")

    # ─────────────────────────────────────────────
    # ESCUDO OCTOGONAL CERRADO CON CALAVERA PUNISHER
    # ─────────────────────────────────────────────

    # Decoración superior
    add_centered(" ".join("·" * 21), ORANGE_DARK)

    # Tope chaflanado
    add_centered("╱" + "─" * 36 + "╲", ORANGE)
    add_centered("╱" + " " * 38 + "╲", ORANGE)

    # Borde interno punteado superior
    shield_v((" ┌" + "╌" * 34 + "┐ ", ORANGE_DARK))

    # ── Calavera Punisher (compacta) ──
    shield_v(("    ▄▄████████████████████▄▄    ", WHITE))
    shield_v(("  ▄████████████████████████████▄  ", WHITE))
    shield_v((" ████████████████████████████████ ", WHITE))

    # Cuencas oculares alargadas (4 cols × 4 filas)
    shield_v(
        ("█████  ", WHITE), ("▄▄▄▄", ORANGE_DARK), ("      ", WHITE),
        ("▄▄▄▄", ORANGE_DARK), ("  █████", WHITE),
    )
    shield_v(
        ("█████  ", WHITE), ("████", ORANGE_DARK), ("      ", WHITE),
        ("████", ORANGE_DARK), ("  █████", WHITE),
    )
    shield_v(
        ("█████  ", WHITE), ("████", ORANGE_DARK), ("      ", WHITE),
        ("████", ORANGE_DARK), ("  █████", WHITE),
    )
    shield_v(
        ("█████  ", WHITE), ("▀▀▀▀", ORANGE_DARK), ("      ", WHITE),
        ("▀▀▀▀", ORANGE_DARK), ("  █████", WHITE),
    )

    # Nariz
    shield_v(
        ("██████      ", WHITE), ("▼▼", ORANGE_BRIGHT), ("      ██████", WHITE),
    )

    # Dientes alargados (2 filas con barras dobles)
    shield_v(
        ("  █████ ", WHITE),
        ("█▌", ORANGE_BRIGHT), ("█▌", ORANGE_BRIGHT), ("█▌", ORANGE_BRIGHT),
        ("█▌", ORANGE_BRIGHT), ("█▌", ORANGE_BRIGHT), ("█", ORANGE_BRIGHT),
        (" █████  ", WHITE),
    )
    shield_v(
        ("  █████ ", WHITE),
        ("█▌", ORANGE_BRIGHT), ("█▌", ORANGE_BRIGHT), ("█▌", ORANGE_BRIGHT),
        ("█▌", ORANGE_BRIGHT), ("█▌", ORANGE_BRIGHT), ("█", ORANGE_BRIGHT),
        (" █████  ", WHITE),
    )

    # Mandíbula compacta (3 filas)
    shield_v(("   █████          █████   ", WHITE))
    shield_v(("    █████        █████    ", WHITE))
    shield_v(("      ████████████████      ", WHITE))
    shield_v(("        ▀▀▀▀▀▀▀▀▀▀        ", WHITE))

    # Borde interno punteado inferior
    shield_v((" └" + "╌" * 34 + "┘ ", ORANGE_DARK))

    # Base chaflanada cerrada (mirror del top, sin punta)
    add_centered("╲" + " " * 38 + "╱", ORANGE)
    add_centered("╲" + "─" * 36 + "╱", ORANGE)

    # Decoración inferior
    add_centered(" ".join("·" * 21), ORANGE_DARK)

    # Tagline
    add_centered("POWER YOUR OPS", ORANGE_BRIGHT)

    return art

# ============================================================
# SPLASH ANSI DINÁMICO
# ============================================================

def render_title(cols):
    try:
        fig = Figlet(font="ansi_shadow", width=cols)
        maxiwatt = fig.renderText("MAXIWATT")
        agent = fig.renderText("AGENT")
    except Exception:
        try:
            fig = Figlet(font="doom", width=cols)
            maxiwatt = fig.renderText("MAXIWATT")
            agent = fig.renderText("AGENT")
        except Exception:
            maxiwatt = "MAXIWATT"
            agent = "AGENT"

    m_lines = maxiwatt.rstrip("\n").split("\n")
    a_lines = agent.rstrip("\n").split("\n")

    h = max(len(m_lines), len(a_lines))
    while len(m_lines) < h:
        m_lines.insert(0, "")
    while len(a_lines) < h:
        a_lines.insert(0, "")

    m_w = max((len(l) for l in m_lines), default=0)
    a_w = max((len(l) for l in a_lines), default=0)

    title_text = Text()
    for ml, al in zip(m_lines, a_lines):
        title_text.append(ml.ljust(m_w), style=f"bold {CYAN}")
        title_text.append("  ")
        title_text.append(al.ljust(a_w), style=f"bold {PURPLE}")
        title_text.append("\n")

    return Align.center(title_text)


def make_section(rows):
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left", style=ORANGE, no_wrap=True)
    table.add_column(justify="right", style=f"bold {ORANGE}", no_wrap=True)
    table.add_column(justify="left", style=WHITE)

    for label, value in rows:
        table.add_row("▸", label, value)

    return table


def build_commands_panel():
    """Panel compacto con los comandos generales agrupados por categoría."""

    sections = [
        ("General", [
            ("help / ayuda",            "Ayuda extendida"),
            ("comandos / commands",     "Esta tabla de comandos"),
            ("models / modelos",        "Modelos en LM Studio"),
            ("tools / herramientas",    "Herramientas instaladas"),
            ("proxy [on/off/status]",   "Control de Tor/proxychains"),
            ("sudo [set/refresh/clear]", "Cachea contraseña sudo (subagentes)"),
            ("timeout [<N>|large|…]",   "Timeout de ejecución de comandos"),
            ("compact / compactar",     "Compacta history (acelera prefill)"),
            ("refresh / refrescar",     "Redibuja el splash"),
            ("clear / limpiar",         "Igual que refresh"),
            ("exit / salir / quit",     "Cierra el agente"),
        ]),
        ("Skills", [
            ("skills / habilidades",    "Lista skills · ●○✗"),
            ("tools_master",            "Listas exhaustivas por fase"),
            ("use / usar <skill>",      "Activa skill + master list"),
            ("unuse / quitar <skill>",  "Desactiva una skill"),
        ]),
        ("Subagentes", [
            ("subagent new <n> <skill> <tarea>", "Lanza mini-agente autónomo"),
            ("subagent list",           "Lista subagentes y su estado"),
            ("subagent show <n>",       "Resumen / log de un subagente"),
            ("subagent kill <n>",       "Detiene un subagente activo"),
        ]),
        ("Orquestación", [
            ("goal <descripción>",      "Orquesta fases hasta cumplir el objetivo"),
            ("goal status",             "Estado del goal en curso"),
            ("goal show",               "Panel resumen del goal"),
            ("goal list",               "Lista goals persistidos en disco"),
            ("goal resume [<id>]",      "Reanuda goal interrumpido"),
            ("goal discard <id>",       "Borra estado persistido"),
            ("goal kill",               "Detiene la orquestación"),
        ]),
        ("Targets", [
            ("target / objetivo",       "Lista targets · ●=activo"),
            ("target <nombre>",         "Carga targets/<nombre>/"),
            ("target reload",           "Recarga el target activo"),
            ("target unload",           "Quita el target del contexto"),
            ("report / informe",        "Genera informe técnico del target"),
        ]),
        ("Sesiones", [
            ("sessions / sesiones",     "Últimas sesiones guardadas"),
            ("resume / retomar",        "Retoma la última sesión"),
            ("resume / retomar <id>",   "Retoma una sesión por ID"),
            ("new / nueva",             "Sesión limpia"),
        ]),
        ("Lecciones", [
            ("aprende / learn <regla>", "Guarda lección en memory/lessons/"),
            ("lecciones / lessons",     "Lista las lecciones guardadas"),
            ("olvida / forget <frag>",  "Borra una lección por fragmento"),
        ]),
    ]

    blocks = []
    for title, rows in sections:
        sub = Table.grid(padding=(0, 1))
        sub.add_column(justify="left",  style=f"bold {CYAN}", no_wrap=True)
        sub.add_column(justify="left",  style=WHITE)
        for cmd, desc in rows:
            sub.add_row(cmd, desc)

        block = Group(
            Text(title, style=f"bold {PURPLE}"),
            Rule(style=CYAN_DARK),
            sub,
        )
        blocks.append(block)

    grid = Columns(blocks, expand=True, equal=True, padding=(0, 2))

    hint = Text.from_markup(
        f"[dim]Cualquier otro texto se envía al modelo · "
        f"prefijo '/' opcional (ej: /skills, /resume, /use recon)[/]"
    )

    return Panel(
        Group(grid, Text(""), Align.center(hint)),
        title=f"[bold {ORANGE}]Quick Commands[/bold {ORANGE}]",
        border_style=ORANGE,
        box=ROUNDED,
        padding=(1, 2),
    )


# Por debajo de este ancho de columnas, el banner "MAXIWATT AGENT" en
# ansi_shadow + el panel "Cyber Emblem" no caben y la pantalla queda
# rota. En ese caso usamos un splash compacto: solo "MAXIWATT" pequeño,
# Agent Runtime panel y commands panel — sin skull/shield ni paneles
# tools/skills (que ya son consultables con `tools`, `skills`).
SPLASH_LITE_THRESHOLD_COLS = 130


def _render_lite_title(cols):
    """Devuelve un Text/Align con solo 'MAXIWATT' en figlet, eligiendo la
    fuente más grande que quepa cómodamente en `cols`."""
    fonts_by_max_cols = (
        # (cols mínimas, fuente pyfiglet)
        (100, "small"),       # ~47 chars
        (60,  "cybermedium"), # ~36 chars
        (0,   "mini"),        # ~27 chars (cabe en pantallas de ~30)
    )
    rendered = None
    for min_cols, font in fonts_by_max_cols:
        if cols >= min_cols:
            try:
                fig = Figlet(font=font, width=max(cols, 32))
                rendered = fig.renderText("MAXIWATT").rstrip("\n")
                break
            except Exception:
                continue
    if rendered is None:
        rendered = "MAXIWATT"
    txt = Text()
    for line in rendered.split("\n"):
        txt.append(line + "\n", style=f"bold {CYAN}")
    return Align.center(txt)


def _render_splash_lite(active_model, vpn_status, tailscale_status,
                       session_id, workspace, cols):
    """Splash compacto para pantallas estrechas (IDE side-panel, ventanas
    SSH pequeñas). Sin emblema, sin skull/shield, sin paneles tools/skills.
    Sólo: título 'MAXIWATT', subtítulo, Agent Runtime panel, commands panel,
    footer minimalista."""
    console.print(_render_lite_title(cols))

    subtitle = (
        f"[bold {ORANGE}]Offensive Security[/]  "
        f"[{WHITE}]·[/]  "
        f"[bold {ORANGE}]Local LLM[/]  "
        f"[{WHITE}]·[/]  "
        f"[bold {ORANGE}]Kali[/]"
    )
    console.print(Align.center(subtitle))
    console.print()

    # Runtime info esencial — sin tools/skills (consultables con `tools`,
    # `skills`) y sin format_list de "Models exposed" para ahorrar líneas.
    runtime_section = make_section([
        ("Model",        active_model),
        ("Backend",      LMSTUDIO_BASE_URL),
        ("VPN",          vpn_status),
        ("Tailscale",    tailscale_status),
        ("Scope Memory", "Enabled"),
    ])
    console.print(Panel(
        runtime_section,
        title=f"[bold {ORANGE}]Agent Runtime[/]",
        border_style=ORANGE, box=ROUNDED, padding=(1, 2),
        width=min(cols - 2, 100),
    ))
    console.print()

    # Quick panel de comandos
    console.print(build_commands_panel())
    console.print()

    # Footer en una sola línea (sin panel ni columnas — caben pocas cols)
    console.print(
        f"[bold {ORANGE}]Session[/] {session_id}  "
        f"[{WHITE}]·[/]  "
        f"[bold {WHITE}]Workspace[/] {workspace}  "
        f"[{WHITE}]·[/]  "
        f"[bold {GREEN}]Ready[/]"
    )
    console.print()
    console.print(
        f"[bold {ORANGE}]>_[/]  "
        f"[{WHITE}]maxiwatt-agent initialized successfully.[/]"
    )
    console.print()


def show_splash():
    console.clear()

    models = get_lmstudio_models()
    active_model = models[0] if models else MODEL_NAME_FALLBACK
    vpn_status = get_mullvad_status()
    tailscale_status = get_tailscale_status()

    session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    workspace = os.getcwd()

    term = shutil.get_terminal_size((160, 45))
    cols = term.columns

    # Pantalla estrecha → splash lite (sin skull/shield ni paneles laterales).
    if cols < SPLASH_LITE_THRESHOLD_COLS:
        _render_splash_lite(active_model, vpn_status, tailscale_status,
                            session_id, workspace, cols)
        return

    # Pantalla amplia: ruta original (con todos los paneles).
    installed_tools, missing_tools = detect_installed_tools()
    skills = detect_folders("~/ai-agent-kali/skills")
    plugins = detect_folders("~/ai-agent-kali/plugins")
    hooks = detect_folders("~/ai-agent-kali/hooks")

    # Título
    console.print(render_title(cols))

    subtitle = (
        f"[bold {ORANGE}]Offensive Security Assistant[/bold {ORANGE}]  "
        f"[{WHITE}]•[/]  "
        f"[bold {ORANGE}]Local LLM[/bold {ORANGE}]  "
        f"[{WHITE}]•[/]  "
        f"[bold {ORANGE}]Kali Linux[/bold {ORANGE}]"
    )

    console.print(Align.center(subtitle))
    console.print()

    kitty_mode = is_kitty_terminal()

    # Panel izquierdo (solo si NO estamos en kitty)
    if not kitty_mode:
        left_content = Group(
            Align.center(Text("MAXIWATT OPS", style=f"bold {ORANGE}")),
            Align.center(build_skull_shield_art()),
        )

        left_panel = Panel(
            left_content,
            title=f"[bold {ORANGE}]Cyber Emblem[/bold {ORANGE}]",
            border_style=ORANGE,
            box=ROUNDED,
            width=72,
            padding=(1, 1)
        )

    # Panel derecho
    runtime_section = make_section([
        ("Model", active_model),
        ("Models exposed", format_list(models, 4)),
        ("Backend", LMSTUDIO_BASE_URL),
        ("VPN", vpn_status),
        ("Tailscale", tailscale_status),
        ("Scope Memory", "Enabled"),
    ])

    tools_section = make_section([
        ("Available Tools", format_list(installed_tools, 10)),
        ("Missing Tools", format_list(missing_tools, 8)),
    ])

    skills_section = make_section([
        ("Available Skills", format_list(skills, 8)),
        ("Plugins", format_list(plugins, 8)),
        ("Hooks", format_list(hooks, 8)),
    ])

    right_group = Group(
        runtime_section,
        Rule(style=ORANGE),
        tools_section,
        Rule(style=ORANGE),
        skills_section,
    )

    if kitty_mode:
        # FASE 1 — emblema gráfico + lemas (lo primero que ve el ojo)
        console.print(Align.center(Text("MAXIWATT OPS", style=f"bold {CYAN}")))
        console.print()

        # icat escribe directamente al terminal, sin pasar por rich/python buffers
        display_kitty_emblem_inline()

        console.print()
        console.print(Align.center(Text("POWER YOUR OPS", style=f"bold {MAGENTA}")))
        console.print()

        # Pausa para que el usuario perciba el emblema antes del scroll
        time.sleep(SPLASH_STAGE_DELAY)

        # FASE 2 — paneles informativos
        right_panel = Panel(
            right_group,
            title=f"[bold {ORANGE}]Agent Runtime[/bold {ORANGE}]",
            border_style=ORANGE,
            box=ROUNDED,
            padding=(1, 2),
        )
        console.print(right_panel)
        console.print()
    else:
        # FASE 1 (no-kitty) — título y subtítulo ya están en pantalla.
        # Pausa antes de imprimir dashboard + chafa emblem.
        time.sleep(SPLASH_STAGE_DELAY)

        # FASE 2
        right_width = max(70, min(cols - 78, 115))

        right_panel = Panel(
            right_group,
            title=f"[bold {ORANGE}]Agent Runtime[/bold {ORANGE}]",
            border_style=ORANGE,
            box=ROUNDED,
            width=right_width,
            padding=(1, 2)
        )

        dashboard = Table.grid(expand=False)
        dashboard.add_column()
        dashboard.add_column()
        dashboard.add_row(left_panel, right_panel)

        console.print(Align.center(dashboard))
        console.print()

    # Comandos disponibles (panel visible en el splash)
    console.print(build_commands_panel())
    console.print()

    # Footer
    footer = Table.grid(expand=True)
    footer.add_column(justify="left")
    footer.add_column(justify="center")
    footer.add_column(justify="right")

    footer.add_row(
        f"[bold {ORANGE}]Session[/bold {ORANGE}] : {session_id}",
        f"[bold {WHITE}]Workspace[/bold {WHITE}] : {workspace}",
        f"[bold {GREEN}]Status[/bold {GREEN}] : Ready",
    )

    console.print(
        Panel(
            footer,
            border_style=ORANGE,
            box=ROUNDED,
            padding=(0, 1)
        )
    )

    console.print(
        Panel(
            f"[bold {ORANGE}]>_[/]  [{WHITE}]maxiwatt-agent initialized successfully.[/]",
            border_style=ORANGE,
            box=ROUNDED,
            padding=(0, 1)
        )
    )

    console.print()


# ============================================================
# LLM
# ============================================================

# Regex para detectar separadores de archivos dentro del bloque de target:
#   === filename.md ===
_TARGET_SECTION_RE = re.compile(r"^=== (.+?) ===$", re.MULTILINE)


def _head_tail_truncate(text, head_n, tail_n, label):
    """Helper: si text excede head_n+tail_n, devuelve head + marcador + tail."""
    cap = head_n + tail_n
    if len(text) <= cap:
        return text
    omitted = len(text) - cap
    return (
        text[:head_n]
        + f"\n\n[…COMPACTADO · {omitted:,} chars de {label} omitidos del medio "
        f"por la rutina de compactación de prompt (el archivo original sigue "
        f"intacto en disco).…]\n\n"
        + text[-tail_n:]
    )


def _compact_target_section(fname, section_text):
    """Aplica política específica por archivo dentro del bloque de target."""
    fname_lower = (fname or "").lower()
    is_timeline = (
        fname_lower == "_timeline.md"
        or fname_lower.endswith("/_timeline.md")
    )
    # _runs.md es CRÍTICO para anti-duplicación: nunca lo truncamos. Su
    # formato es estructurado y compacto por diseño (una línea por scan).
    is_runs = (
        fname_lower == "_runs.md"
        or fname_lower.endswith("/_runs.md")
    )
    if is_runs:
        return section_text
    if is_timeline:
        return _head_tail_truncate(
            section_text,
            COMPACT_TIMELINE_HEAD,
            COMPACT_TIMELINE_TAIL,
            f"{fname}",
        )
    # Resto de archivos del target: cap moderado simétrico.
    half = COMPACT_TARGET_FILE_MAX // 2
    return _head_tail_truncate(section_text, half, half, f"{fname}")


def _compact_target_block(content):
    """Trocea un mensaje [Target activo: ...] por secciones === archivo === y
    aplica compactación por archivo. El header anterior a la primera sección
    se preserva tal cual."""
    matches = list(_TARGET_SECTION_RE.finditer(content))
    if not matches:
        # Sin secciones identificables: cap global.
        half = COMPACT_TARGET_FILE_MAX // 2
        return _head_tail_truncate(content, half, half, "target")

    parts = [content[:matches[0].start()]]
    for i, m in enumerate(matches):
        fname = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section = content[start:end]
        parts.append(_compact_target_section(fname, section))
    return "".join(parts)


def _compact_system_message(content):
    """Compacta un mensaje system grande (target, skill activa, tools_master).
    No se llama sobre history[0] (system prompt principal con lecciones)."""
    if not content:
        return content
    if content.startswith(TARGET_MARKER_PREFIX):
        return _compact_target_block(content)
    if content.startswith("[Skill activa:") or content.startswith("[Tools master"):
        half = COMPACT_SKILL_MAX // 2
        return _head_tail_truncate(content, half, half, "skill/tools_master")
    return content


def _compact_message_content(content):
    """Trunca el contenido de un mensaje antiguo manteniendo head+tail."""
    if not content:
        return content
    is_result = content.startswith("Resultado del comando:")
    if is_result:
        head_n, tail_n = COMPACT_RESULT_HEAD, COMPACT_RESULT_TAIL
    else:
        half = COMPACT_OTHER_MSG_CAP // 2
        head_n, tail_n = half, half
    cap = head_n + tail_n
    if len(content) <= cap:
        return content
    omitted = len(content) - head_n - tail_n
    return (
        content[:head_n]
        + f"\n\n[…COMPACTADO · {omitted:,} caracteres del medio omitidos "
        f"por la rutina de compactación. Si necesitas releer este trozo, "
        f"pide al usuario que recupere el output completo desde "
        f"`_timeline.md` del target.…]\n\n"
        + content[-tail_n:]
    )


def _compact_messages_for_call(messages):
    """Devuelve una COPIA compactada de `messages` para enviar al modelo.

    Dos políticas:

    1) Mensajes SYSTEM grandes (target, skill, tools_master) — se compactan
       SIEMPRE si COMPACT_SYSTEM_BLOCKS está activo. Crecen sin parar
       (_timeline.md sobre todo) y son la causa principal de prefill lento
       en modelos locales. history[0] (SYSTEM_PROMPT principal con
       lecciones) NUNCA se toca.

    2) Mensajes USER/ASSISTANT antiguos — sólo se truncan si la estimación
       global del prompt supera COMPACT_TRIGGER_PCT * MAX_CONTEXT_TOKENS y
       caen fuera de la ventana de recencia (COMPACT_KEEP_LAST_TURNS pares).

    No modifica `messages` ni `history` in-place.
    """
    if not PROMPT_COMPACTION or not messages:
        return messages

    est_before = estimate_tokens(messages)

    # Punto de corte de la ventana de recencia para user/assistant.
    user_indices = [
        i for i, m in enumerate(messages) if m.get("role") == "user"
    ]
    if len(user_indices) > COMPACT_KEEP_LAST_TURNS:
        cutoff = user_indices[-COMPACT_KEEP_LAST_TURNS]
    else:
        cutoff = len(messages)  # nada cae fuera de recencia todavía

    do_user_compact = (
        est_before >= MAX_CONTEXT_TOKENS * COMPACT_TRIGGER_PCT
        and cutoff < len(messages)
    )

    sys_touched = 0
    user_touched = 0
    compacted = []
    for i, m in enumerate(messages):
        role = m.get("role")
        original = m.get("content", "") or ""

        # 1) Mensajes SYSTEM (no el principal): compactación SIEMPRE.
        if i != 0 and role == "system" and COMPACT_SYSTEM_BLOCKS:
            new_content = _compact_system_message(original)
            if len(new_content) < len(original):
                sys_touched += 1
                nm = dict(m)
                nm["content"] = new_content
                compacted.append(nm)
                continue

        # 2) USER/ASSISTANT antiguos: compactación condicional.
        if (do_user_compact and i != 0 and role != "system"
                and i < cutoff):
            new_content = _compact_message_content(original)
            if len(new_content) < len(original):
                user_touched += 1
                nm = dict(m)
                nm["content"] = new_content
                compacted.append(nm)
                continue

        # 3) Resto: tal cual.
        compacted.append(m)

    if sys_touched == 0 and user_touched == 0:
        return messages

    est_after = estimate_tokens(compacted)
    saved = est_before - est_after
    if saved > 0:
        bits = []
        if sys_touched:
            bits.append(f"{sys_touched} system (target/skill)")
        if user_touched:
            bits.append(f"{user_touched} user/assistant antiguos")
        console.print(
            f"[dim {CYAN}]› prompt compactado · {', '.join(bits)} · "
            f"~{saved:,} tokens ahorrados ({est_before:,}→{est_after:,})[/]"
        )
    return compacted


# Patrones que SÓLO produce el agente tras ejecutar un comando. Si el
# modelo los emite en su respuesta, está fabricando output del sistema.
_HALLUC_SYSTEM_PATTERNS = [
    (re.compile(r"\[DIAGN[ÓO]STICO\s*·\s*tools del comando\]", re.IGNORECASE),
     "[DIAGNÓSTICO · tools del comando] (lo emite el agente, no tú)"),
    (re.compile(r"\[DIAGN[ÓO]STICO\s*·\s*archivo", re.IGNORECASE),
     "[DIAGNÓSTICO · archivo …] (lo emite el agente tras la ejecución)"),
    (re.compile(r"^\s*instaladas:\s", re.MULTILINE),
     "líneas `instaladas: <tool>` (formato del agente)"),
    (re.compile(r"^\s*NO\s+instaladas:\s", re.MULTILINE),
     "líneas `NO instaladas: <tool>` (formato del agente)"),
    (re.compile(r"Comando propuesto\s*·", re.IGNORECASE),
     "panel `Comando propuesto · …` (lo renderiza run_command)"),
    (re.compile(r"»\s*AUTOPILOT\s*—", re.IGNORECASE),
     "tag `» AUTOPILOT —` (lo emite el agente, no tú)"),
    (re.compile(r"^\s*Comando\s+intrusivo\.\s*¿Ejecutar\?", re.MULTILINE | re.IGNORECASE),
     "prompt `Comando intrusivo. ¿Ejecutar? [s/N]:` (lo emite el agente)"),
    # Regurgitación del contexto system del agente
    (re.compile(r"\[Scans en disco\s*—", re.IGNORECASE),
     "bloque `[Scans en disco — …]` (es contexto system, NO tu output)"),
    (re.compile(r"\[Herramientas ya usadas contra\s+'", re.IGNORECASE),
     "bloque `[Herramientas ya usadas contra …]` (contexto system)"),
    (re.compile(r"\[Target activo:\s*", re.IGNORECASE),
     "bloque `[Target activo: …]` (contexto system)"),
    (re.compile(r"\[Skill activa:\s*", re.IGNORECASE),
     "bloque `[Skill activa: …]` (contexto system)"),
    (re.compile(r"\[Tools master\s*·", re.IGNORECASE),
     "bloque `[Tools master · …]` (contexto system)"),
    (re.compile(r"^===\s+[^=]+\s+===\s*$", re.MULTILINE),
     "separador `=== <archivo>.md ===` (delimitador interno del target block)"),
    (re.compile(r"\[…COMPACTADO\s*·", re.IGNORECASE),
     "marcador `[…COMPACTADO · …]` (lo inserta la compactación del agente)"),
    (re.compile(r"<archivo_dentro_de_targets/>", re.IGNORECASE),
     "placeholder `<archivo_dentro_de_targets/>` (es la plantilla, sustitúyelo por un nombre real)"),
]


def _detect_system_output_hallucination(answer):
    """Detecta si el modelo ha fabricado formatos de output del sistema en
    su respuesta. Devuelve una lista de descripciones de patrones detectados,
    o lista vacía si todo limpio.
    """
    if not answer:
        return []
    findings = []
    for pat, desc in _HALLUC_SYSTEM_PATTERNS:
        if pat.search(answer):
            findings.append(desc)
    return findings


# Markers de regurgitación. Si encontramos uno de éstos en el answer,
# truncamos el answer desde la PRIMERA aparición hasta el final. Razón:
# una vez el modelo empieza a copiar el contexto system, lo normal es que
# siga copiando bloque tras bloque hasta agotar max_tokens.
_REGURGITATION_MARKERS = [
    re.compile(r"\[Scans en disco\s*—", re.IGNORECASE),
    re.compile(r"\[Herramientas ya usadas contra\s+'", re.IGNORECASE),
    re.compile(r"\[Target activo:\s*", re.IGNORECASE),
    re.compile(r"\[Skill activa:\s*", re.IGNORECASE),
    re.compile(r"\[Tools master\s*·", re.IGNORECASE),
    re.compile(r"^===\s+_(?:timeline|runs)\.md\s+===", re.MULTILINE | re.IGNORECASE),
    re.compile(r"\[…COMPACTADO\s*·", re.IGNORECASE),
]


def _strip_context_regurgitation(answer):
    """Trunca el answer desde la primera marca de regurgitación del contexto
    system. Devuelve (answer_truncado, n_marcas_detectadas).
    """
    if not answer:
        return answer, 0
    first_idx = None
    hits = 0
    for pat in _REGURGITATION_MARKERS:
        m = pat.search(answer)
        if m:
            hits += 1
            if first_idx is None or m.start() < first_idx:
                first_idx = m.start()
    if first_idx is None:
        return answer, 0
    # Cortar todo desde la primera marca. Si lo que quede es muy corto,
    # dejar una nota explicativa visible.
    cleaned = answer[:first_idx].rstrip()
    if len(cleaned) < 40:
        cleaned = (
            "[Respuesta del modelo descartada: regurgitó contexto system "
            "en lugar de responder. Reformula tu pregunta o usa `compact` "
            "para reducir el contexto.]"
        )
    return cleaned, hits


_TOOL_SATURATION_THRESHOLD = 3


def _build_tool_runs_summary(target_name):
    """Resumen de uso de herramientas en `_runs.md` del target. Indica cuáles
    están SATURADAS (≥_TOOL_SATURATION_THRESHOLD runs) para que el modelo
    deje de proponerlas. Devuelve "" si no hay runs.
    """
    if not target_name:
        return ""
    runs = parse_runs(target_name)
    if not runs:
        return ""
    by_tool = {}
    for r in runs:
        tool = (r.get("tool") or "?").lower()
        by_tool.setdefault(tool, []).append(r)
    if not by_tool:
        return ""
    lines = [
        f"[Herramientas ya usadas contra '{target_name}' (_runs.md)]",
        "",
        f"Recordatorio antes de proponer un COMANDO de red — uso acumulado:",
        "",
    ]
    saturated = []
    for tool, entries in sorted(by_tool.items(), key=lambda kv: -len(kv[1])):
        n = len(entries)
        last = entries[-1]
        rc_summary = ", ".join(f"rc={e['rc']}" for e in entries[-3:])
        flag = ""
        if n >= _TOOL_SATURATION_THRESHOLD:
            flag = f"  ⛔ SATURADA (≥{_TOOL_SATURATION_THRESHOLD} runs)"
            saturated.append(tool)
        elif n == _TOOL_SATURATION_THRESHOLD - 1:
            flag = "  ⚠ próxima a saturar"
        lines.append(
            f"- `{tool}`: {n} run{'s' if n != 1 else ''} · "
            f"último [{last['ts']}] · últimos rc: {rc_summary}{flag}"
        )
    if saturated:
        lines.append("")
        lines.append(
            f"⛔ PROHIBIDO proponer otro COMANDO que empiece por "
            f"{', '.join(f'`{t}`' for t in saturated)} contra los mismos "
            f"hosts. Avanza por OTRA categoría del tools_master cargado "
            f"(fingerprinting web, fuzzing, SMB enum, vuln scan, etc.). "
            f"Si crees tener una justificación válida (UDP no probado, "
            f"NSE category nueva, host nuevo), enúnciala en una línea "
            f"explícita antes del COMANDO."
        )
    return "\n".join(lines)


def _tool_is_saturated(command, target_name):
    """True si el comando empieza por una herramienta con ≥threshold runs en
    _runs.md del target. Devuelve (saturated_bool, tool_name, count)."""
    if not command or not target_name:
        return (False, None, 0)
    tool = _runs_first_tool_token(command)
    if not tool or tool not in NETWORK_TOOLS:
        return (False, None, 0)
    runs = parse_runs(target_name)
    count = sum(1 for r in runs if (r.get("tool") or "").lower() == tool)
    return (count >= _TOOL_SATURATION_THRESHOLD, tool, count)


_SCANS_OVERVIEW_CAP = 2500
_SCANS_OVERVIEW_MAX_FILES = 25
_FQDN_RE = re.compile(r"\b[a-z0-9][a-z0-9\-]*\.[a-z0-9][a-z0-9\-]*(?:\.[a-z]{2,})+\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_FQDN_BAD_SUFFIX = (".md", ".txt", ".json", ".xml", ".html", ".htm", ".log",
                    ".csv", ".tsv", ".yml", ".yaml", ".pdf", ".gnmap", ".nmap")


def _scans_target_tokens(target_name):
    """Devuelve un set de tokens (lowercased) que probablemente aparezcan en
    nombres de archivo de `./scans/` relevantes al target: el nombre del target,
    IPv4s y FQDNs encontrados en scope.md / attack-surface.md / infrastructure.md.
    """
    tokens = set()
    if not target_name:
        return tokens
    tokens.add(target_name.lower())
    target_dir = os.path.join(TARGETS_DIR, target_name)
    if not os.path.isdir(target_dir):
        return tokens
    for fname in ("scope.md", "attack-surface.md", "infrastructure.md"):
        fpath = os.path.join(target_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                text = f.read().lower()
        except Exception:
            continue
        for ip in _IPV4_RE.findall(text):
            tokens.add(ip)
            tokens.add(ip.replace(".", "_"))
        for host in _FQDN_RE.findall(text):
            if host.endswith(_FQDN_BAD_SUFFIX):
                continue
            tokens.add(host)
            parts = host.split(".")
            if len(parts) >= 2:
                # raíz (ej. "gc-heat.de") — coincide con archivos tipo
                # "nmap_gc-heat.txt"
                tokens.add(".".join(parts[-2:]))
                tokens.add(parts[-2])  # "gc-heat"
    return {t for t in tokens if t and len(t) >= 3}


def _build_scans_overview(target_name):
    """Construye un resumen del directorio `./scans/` filtrado y ranqueado por
    relevancia para el target activo. Devuelve el string para inyectar como
    mensaje system efímero, o "" si no aplica.

    Política:
      - Si hay archivos cuyo nombre contiene un token del target → sólo esos
        (máx _SCANS_OVERVIEW_MAX_FILES, orden: relevancia ↓ luego mtime ↓).
      - Si no hay coincidencias por token → top-15 archivos más recientes.
      - Tope global de caracteres = _SCANS_OVERVIEW_CAP.
      - Por archivo: nombre, tamaño, fecha, preview de hasta 2 líneas (~160c).
    """
    if not target_name:
        return ""
    scans_dir = os.path.join(WORKSPACE, "scans")
    if not os.path.isdir(scans_dir):
        return ""

    tokens = _scans_target_tokens(target_name)

    entries = []
    for fname in os.listdir(scans_dir):
        fpath = os.path.join(scans_dir, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            st = os.stat(fpath)
        except OSError:
            continue
        fname_lower = fname.lower()
        score = sum(1 for t in tokens if t in fname_lower)
        entries.append((score, st.st_mtime, fname, st.st_size))

    if not entries:
        return ""

    entries.sort(key=lambda x: (-x[0], -x[1]))
    relevant = [e for e in entries if e[0] > 0][:_SCANS_OVERVIEW_MAX_FILES]
    if not relevant:
        relevant = entries[:15]

    header = [
        f"[Scans en disco — relevantes a '{target_name}']",
        "",
        f"Carpeta `./scans/` con outputs persistidos. ANTES de proponer un "
        f"COMANDO de red, comprueba si la información ya está en uno de "
        f"estos archivos: si la respuesta a tu pregunta está aquí, propón "
        f"`cat`/`head`/`grep` en lugar de un nuevo escaneo.",
        "",
    ]
    body = []
    total = sum(len(l) + 1 for l in header)
    truncated = 0
    for idx, (score, mtime, fname, size) in enumerate(relevant):
        ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        if size >= 1024:
            size_str = f"{size // 1024} kB"
        else:
            size_str = f"{size} B"
        preview = ""
        try:
            with open(os.path.join(scans_dir, fname), encoding="utf-8",
                      errors="ignore") as f:
                head_chunk = f.read(400)
            head_lines = [l.strip() for l in head_chunk.splitlines() if l.strip()][:2]
            if head_lines:
                preview_raw = " ¦ ".join(head_lines)
                if len(preview_raw) > 160:
                    preview_raw = preview_raw[:157] + "…"
                preview = " · " + preview_raw
        except Exception:
            pass
        line = f"- `./scans/{fname}` ({size_str}, {ts}){preview}"
        if total + len(line) + 1 > _SCANS_OVERVIEW_CAP:
            truncated = len(relevant) - idx
            break
        body.append(line)
        total += len(line) + 1

    if truncated:
        body.append(f"- … (+{truncated} archivos relevantes más, no listados por tope)")

    footer = [
        "",
        "Si la herramienta que ibas a lanzar coincide con un prefijo de uno "
        "de estos archivos (`nmap_*`, `nuclei_*`, `whatweb_*`, `gobuster_*`, "
        "`subfinder_*`, …) sobre el mismo host, NO la repitas: lee primero "
        "el archivo existente. Sólo propón un nuevo escaneo si (a) el "
        "archivo está vacío o truncado, (b) cubre otro host, o (c) usa "
        "flags claramente distintos.",
    ]
    return "\n".join(header + body + footer)


def ask_model(user_input):
    """Envía `user_input` al modelo y devuelve la respuesta. Si STREAM_OUTPUT,
    imprime cada chunk en directo a medida que llega (sin renderizar Markdown).
    Procesa bloques TARGET_UPDATE al final.
    """
    history.append({"role": "user", "content": user_input})

    model = get_active_model()

    # Inyectamos la fecha y hora actuales como mensaje system EFÍMERO (no se
    # guarda en el history). Así el modelo siempre sabe qué día es y los
    # timestamps que genere (en TARGET_UPDATE, en notas, etc.) son correctos.
    now = datetime.now()
    date_msg = {
        "role": "system",
        "content": (
            f"Fecha y hora actuales (zona local): {now.strftime('%Y-%m-%d %H:%M')}. "
            f"Usa SIEMPRE esta fecha cuando generes timestamps o headings con fecha "
            f"(p. ej. en bloques [[TARGET_UPDATE]] o en notas)."
        ),
    }
    # Mensaje system EFÍMERO con el resumen de `./scans/` relevante al target
    # activo. Se reconstruye en cada turno (refleja archivos creados en el
    # turno anterior). Si no hay target o no hay carpeta scans, se omite.
    ephemeral = [date_msg]
    if ACTIVE_TARGET:
        scans_overview = _build_scans_overview(ACTIVE_TARGET)
        if scans_overview:
            ephemeral.append({"role": "system", "content": scans_overview})
        # Resumen de herramientas ya usadas (_runs.md) — incluye marcadores de
        # saturación para que el modelo deje de proponer nmap por cuarta vez.
        runs_summary = _build_tool_runs_summary(ACTIVE_TARGET)
        if runs_summary:
            ephemeral.append({"role": "system", "content": runs_summary})

    # Insertamos justo después del system_prompt principal (índice 1).
    messages_for_call = [history[0]] + ephemeral + history[1:]

    # Compactación pre-envío: trunca resultados de comandos antiguos para
    # acelerar el prefill del modelo local. NO toca history en memoria.
    messages_for_call = _compact_messages_for_call(messages_for_call)

    common_kwargs = dict(
        model=model,
        messages=messages_for_call,
        temperature=0.1,
        # Cinturón anti-bucle: tope duro de tokens + penalización de repetición.
        max_tokens=4096,
        frequency_penalty=0.4,
        presence_penalty=0.2,
        # Timeout per-request (segundos). Redundante con el del cliente pero
        # blindamos por si la versión del SDK no lo propaga al streaming.
        timeout=LLM_REQUEST_TIMEOUT,
    )

    if STREAM_MODEL_OUTPUT:
        answer = _ask_model_streaming(common_kwargs)
    else:
        answer = _ask_model_batch(common_kwargs)

    # DETECCIÓN DE ALUCINACIÓN — el modelo fabrica output del sistema.
    # Si emite un bloque que SÓLO produce el agente tras ejecutar el
    # comando (DIAGNÓSTICO, panel "Comando propuesto", etc.), avisamos
    # al operador y registramos en notes.md para futuras lecciones.
    halluc_signals = _detect_system_output_hallucination(answer)
    if halluc_signals:
        console.print()
        console.print(Panel(
            f"[bold {RED}]⚠ Alucinación de output del sistema detectada[/]\n\n"
            f"[{WHITE}]El modelo ha emitido formatos que SÓLO produce el "
            f"agente tras ejecutar un comando:[/]\n"
            + "\n".join(f"  · {s}" for s in halluc_signals) +
            f"\n\n[dim]Esos bloques son falsos — la herramienta aún no ha "
            f"corrido. El COMANDO real (si lo hay) se ejecutará a "
            f"continuación.[/]",
            border_style=RED,
            box=ROUNDED,
            padding=(1, 2),
        ))

    # STRIP de regurgitación del contexto system. Si el modelo ha copiado
    # bloques tipo [Scans en disco …], [Target activo: …], === _runs.md ===,
    # los recortamos del answer ANTES de guardarlo en history. Razón: si
    # los dejamos, el siguiente turno los verá como ejemplo y reforzará la
    # regurgitación. El answer rendererizado al usuario también se beneficia.
    answer, regurg_cuts = _strip_context_regurgitation(answer)
    if regurg_cuts:
        console.print(
            f"[dim]› {regurg_cuts} bloque(s) de contexto system "
            f"regurgitado(s) por el modelo · recortados del history[/]"
        )

    # Avisar si el modelo emitió TARGET_UPDATE sin cierre `[[/TARGET_UPDATE]]`.
    # El regex actual ya los recupera (cierre implícito por encadenado o EOF),
    # pero conviene avisar al operador para que el modelo aprenda.
    n_opens = len(_TARGET_UPDATE_OPEN_RE.findall(answer or ""))
    n_closes = len(_TARGET_UPDATE_CLOSE_RE.findall(answer or ""))
    if n_opens > n_closes:
        console.print(
            f"[dim]› ⚠ {n_opens - n_closes} bloque(s) TARGET_UPDATE sin "
            f"`[[/TARGET_UPDATE]]` final · recuperados con cierre implícito[/]"
        )

    # Procesar bloques TARGET_UPDATE emitidos por el modelo
    applied = []
    if ACTIVE_TARGET:
        updates = extract_target_updates(answer)
        for fname, content in updates:
            applied.append(apply_target_update(fname, content))
        if applied:
            # Quitamos los bloques del answer guardado para evitar ruido en el history.
            answer = strip_target_updates(answer)
            # Recargamos el target para que el contexto refleje los archivos
            # actualizados en el siguiente turno.
            load_target(ACTIVE_TARGET)

    # ────────────────────────────────────────────────────────
    # Procesar bloques FILE_READ / FILE_EDIT / FILE_WRITE
    # ────────────────────────────────────────────────────────
    file_results = process_file_blocks(answer)
    if file_results["any"]:
        # Limpiar bloques del answer guardado (igual que TARGET_UPDATE).
        answer = strip_file_blocks(answer)

    history.append({"role": "assistant", "content": answer})
    save_session()

    if applied:
        _print_target_updates_panel(applied)

    # Inyectar resultados de FILE_READ al history para que el modelo "vea"
    # los archivos en el próximo turno.
    if file_results["read_messages"]:
        for msg in file_results["read_messages"]:
            history.append({"role": "system", "content": msg})
        save_session()

    # Inyectar feedback de FILE_EDIT/WRITE al history (errores + confirmaciones)
    if file_results["op_summary"]:
        history.append({"role": "system", "content": file_results["op_summary"]})
        save_session()

    return answer


def _fmt_elapsed(seconds):
    """Formatea segundos como:
        '12.4s'        (< 60s, con 1 decimal)
        '1m 23s'       (≥ 60s y < 1 h)
        '1h 23m 04s'   (≥ 1 h)
    """
    if seconds is None:
        return "?"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds - m * 60)
        return f"{m}m {s:02d}s"
    h = int(seconds // 3600)
    rem = seconds - h * 3600
    m = int(rem // 60)
    s = int(rem - m * 60)
    return f"{h}h {m:02d}m {s:02d}s"


def _ask_model_batch(kwargs):
    """Modo no-streaming: spinner animado mientras espera, render Markdown
    al terminar. El contador de tiempo en vivo está en el spinner."""
    with _AnimatedSpinner("Pensando"):
        response = client.chat.completions.create(**kwargs)

    if getattr(response, "usage", None):
        LAST_USAGE["prompt_tokens"] = response.usage.prompt_tokens or 0
        LAST_USAGE["completion_tokens"] = response.usage.completion_tokens or 0
        LAST_USAGE["total_tokens"] = response.usage.total_tokens or 0

    answer = response.choices[0].message.content
    console.print()
    console.print(f"[bold {ORANGE}]Agente:[/bold {ORANGE}]")
    # El strip de TARGET_UPDATE pasa después en ask_model; aquí mostramos el answer
    # tal cual viene (los bloques siguen presentes y el usuario los verá).
    console.print(Markdown(answer))
    return answer


def _ask_model_streaming(kwargs):
    """Modo streaming. Imprime cada delta del modelo según llega (raw, sin Markdown).
    Durante el prefill (antes del primer token) mostramos un spinner con
    contador de tiempo en vivo. Al recibir el primer token, cerramos el
    spinner y empezamos a escribir los tokens.
    """
    stream_kwargs = dict(kwargs)
    stream_kwargs["stream"] = True
    # LM Studio reciente soporta esto para meter usage en el último chunk.
    stream_kwargs["stream_options"] = {"include_usage": True}

    t0 = time.time()
    console.print()

    chunks = []
    final_usage = None
    first_token_at = None

    try:
        stream = client.chat.completions.create(**stream_kwargs)
    except TypeError:
        # Si el cliente/servidor no soporta stream_options, retry sin él.
        stream_kwargs.pop("stream_options", None)
        stream = client.chat.completions.create(**stream_kwargs)

    # Spinner durante el prefill. Se cierra automáticamente al recibir el
    # primer token, antes de empezar a escribir a stdout.
    spinner = _AnimatedSpinner("Pensando")
    spinner.__enter__()
    spinner_active = True

    try:
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage:
                final_usage = usage

            if not getattr(chunk, "choices", None):
                continue

            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None) if delta else None
            if text:
                if first_token_at is None:
                    first_token_at = time.time()
                    # Cerramos el spinner ANTES de escribir el primer token
                    # para no mezclar la barra animada con la salida del modelo.
                    if spinner_active:
                        spinner.__exit__(None, None, None)
                        spinner_active = False
                        # Header "Agente:" tras cerrar el spinner.
                        console.print(f"[bold {ORANGE}]Agente:[/bold {ORANGE}]")
                chunks.append(text)
                sys.stdout.write(text)
                sys.stdout.flush()
    finally:
        if spinner_active:
            spinner.__exit__(None, None, None)

    # newline final si el modelo no lo metió
    if chunks and not chunks[-1].endswith("\n"):
        sys.stdout.write("\n")

    elapsed = time.time() - t0
    ttft = (first_token_at - t0) if first_token_at else None
    if ttft is not None:
        gen_time = elapsed - ttft
        console.print(
            f"[dim]› primer token en {_fmt_elapsed(ttft)} · "
            f"generación {_fmt_elapsed(gen_time)} · "
            f"total {_fmt_elapsed(elapsed)}[/]"
        )
    else:
        console.print(
            f"[dim]› sin tokens (¿modelo cancelado?) · "
            f"{_fmt_elapsed(elapsed)}[/]"
        )
    sys.stdout.flush()

    if final_usage:
        LAST_USAGE["prompt_tokens"] = getattr(final_usage, "prompt_tokens", 0) or 0
        LAST_USAGE["completion_tokens"] = getattr(final_usage, "completion_tokens", 0) or 0
        LAST_USAGE["total_tokens"] = getattr(final_usage, "total_tokens", 0) or 0

    return "".join(chunks)


def _print_target_updates_panel(applied):
    """Muestra un panel resumen con los TARGET_UPDATE aplicados (o errores).
    Incluye ruta absoluta y preview del contenido para que el usuario pueda
    verificar que realmente se ha escrito lo que dice."""
    table = Table.grid(padding=(0, 1))
    table.add_column(no_wrap=True)
    table.add_column(style=CYAN, no_wrap=True)
    table.add_column(style=WHITE)

    for r in applied:
        if r.get("ok"):
            mark = f"[bold {GREEN}]✓[/]"
            full = r.get("file") or r.get("filename")
            detail = (
                f"+{r.get('added_lines', 0)} líneas · "
                f"{_human_size(r.get('added_bytes', 0))} · "
                f"[dim]{full}[/]"
            )
            preview = (r.get("preview") or "").strip()
            if preview:
                preview = preview.replace("\n", " ⏎ ")
                if len(preview) > 110:
                    preview = preview[:107] + "…"
                detail += f"\n   [dim]preview:[/] [italic]{preview}[/]"
        else:
            mark = f"[bold {RED}]✗[/]"
            detail = f"[{RED}]{r.get('error', '?')}[/]"
        table.add_row(mark, r.get("filename", "?"), detail)

    console.print()
    console.print(
        Panel(
            table,
            title=f"[bold {ORANGE}]Target updates aplicados[/]",
            border_style=ORANGE,
            box=ROUNDED,
            padding=(0, 1),
        )
    )


def estimate_tokens(messages):
    """Estimación gruesa: 1 token ≈ 4 caracteres + overhead por mensaje."""
    total = 0
    for m in messages:
        content = m.get("content", "") or ""
        total += len(content) // 4 + 4
    return total


def get_context_used():
    """Tokens en uso ahora mismo. Usa datos reales del último response si los hay."""
    if LAST_USAGE["prompt_tokens"] > 0:
        # prompt_tokens es lo que se envió, + completion_tokens es lo que el modelo añadió al history
        return LAST_USAGE["prompt_tokens"] + LAST_USAGE["completion_tokens"]
    return estimate_tokens(history)


# Aviso único de contexto al cruzar el umbral crítico en cada sesión.
_CONTEXT_WARN_SHOWN = {"high": False, "full": False}


def render_context_bar():
    """Barra visual de uso de contexto, retorna un Rich Text.
    La barra se clampa a 20 bloques (no se desborda visualmente) pero el
    porcentaje sí refleja la realidad cuando se excede el budget configurado.
    """
    used = get_context_used()
    pct = (used / MAX_CONTEXT_TOKENS * 100) if MAX_CONTEXT_TOKENS > 0 else 0

    if pct < 50:
        color = GREEN
    elif pct < 80:
        color = "#fbbf24"
    elif pct < 100:
        color = RED
    else:
        color = MAGENTA  # ≥100% → magenta para indicar overflow

    bar_width = 20
    # Clamp visual a 100% (la barra no se sale del rail aunque pct sea 130%).
    pct_visual = min(pct, 100)
    filled = min(bar_width, int(round(bar_width * pct_visual / 100)))
    bar = "█" * filled + "░" * (bar_width - filled)

    turns = sum(1 for m in history if m["role"] == "user")
    skills_str = f"{len(ACTIVE_SKILLS)} skill" + ("s" if len(ACTIVE_SKILLS) != 1 else "")
    estimated = LAST_USAGE["prompt_tokens"] == 0
    suffix = " (est.)" if estimated else ""

    overflow_marker = ""
    if pct >= 100:
        overflow_marker = "  ⚠ OVERFLOW"
    elif pct >= 95:
        overflow_marker = "  ⚠ CRÍTICO"
    elif pct >= 85:
        overflow_marker = "  ⚠ alto"

    text = Text()
    text.append("│ ", style=f"{color}")
    text.append(bar, style=f"{color}")
    text.append(f" {pct:>5.1f}%", style=f"bold {color}")
    text.append(f"  {used:,} / {MAX_CONTEXT_TOKENS:,} tokens{suffix}", style=GRAY)
    text.append(f"  ·  {turns} turnos  ·  {skills_str}", style=GRAY)
    if ACTIVE_TARGET:
        text.append(f"  ·  target: ", style=GRAY)
        text.append(ACTIVE_TARGET, style=f"bold {PURPLE}")
    if overflow_marker:
        text.append(overflow_marker, style=f"bold {color}")

    # Aviso explícito una sola vez al cruzar 95% y al cruzar 100%.
    if pct >= 100 and not _CONTEXT_WARN_SHOWN["full"]:
        _CONTEXT_WARN_SHOWN["full"] = True
        console.print(Panel(
            f"[bold {MAGENTA}]⚠ Contexto del modelo EXCEDIDO ({pct:.1f}%)[/]\n\n"
            f"[{WHITE}]Los mensajes más antiguos del history se están "
            f"compactando automáticamente (head+tail) para caber en el "
            f"budget del modelo. La evidencia en `targets/{ACTIVE_TARGET or '<target>'}/` "
            f"está a salvo — son archivos en disco, no se pierden.[/]\n\n"
            f"[bold {WHITE}]Qué olvida el modelo:[/]\n"
            f"  · Detalles del medio de turnos antiguos (cuerpo de outputs "
            f"largos, conversación intermedia).\n"
            f"  · NO olvida: SYSTEM_PROMPT, skill activa, tools_master,\n"
            f"    bloque de target (notes.md, attack-surface.md, _timeline.md, "
            f"_runs.md), los últimos 3 turnos completos.\n\n"
            f"[bold {WHITE}]Recomendaciones:[/]\n"
            f"  1. `compact` — fuerza compactación adicional ahora mismo.\n"
            f"  2. `sessions` → iniciar una nueva sesión con el mismo target "
            f"cargado: el modelo arranca con history limpio pero toda la "
            f"evidencia recuperable desde los archivos del target. Es lo "
            f"más recomendable para engagements largos.\n"
            f"  3. Subir `MAX_CONTEXT_TOKENS` en agent.py si tu modelo "
            f"local soporta más contexto del configurado.",
            title=f"[bold {MAGENTA}]Context window agotado[/]",
            border_style=MAGENTA,
            box=ROUNDED,
            padding=(1, 2),
        ))
    elif pct >= 95 and not _CONTEXT_WARN_SHOWN["high"] and pct < 100:
        _CONTEXT_WARN_SHOWN["high"] = True
        console.print(
            f"[bold {RED}]⚠ Contexto al {pct:.1f}% — "
            f"considera `compact` o nueva sesión.[/]"
        )

    return text


# ============================================================
# EJECUCIÓN DE COMANDOS
# ============================================================

# Clasificación de comandos por nivel de impacto.
# safe       → solo lectura / informativo / no toca objetivo
# intrusive  → toca objetivo de forma reversible (escaneos activos, fuzzing)
# destructive→ explotación, brute-force, escritura en sistema, cambios persistentes

SAFE_TOOLS = {
    "ip", "ifconfig", "route", "arp", "netstat", "ss", "iw", "iwconfig",
    "dig", "nslookup", "whois", "host", "drill",
    "ls", "cat", "head", "tail", "less", "more", "wc", "file", "stat", "tree",
    "grep", "egrep", "fgrep", "ag", "rg",
    "find", "locate", "which", "type", "command",
    "ps", "top", "htop", "pgrep", "pidof", "lsof",
    "id", "whoami", "groups", "uname", "hostname", "uptime",
    "df", "du", "free", "lsblk", "lscpu", "lspci", "lsusb",
    "echo", "pwd", "date", "env", "printenv", "history",
    "searchsploit", "exploit-db",
    "git",
    "ping", "ping6", "tracepath", "traceroute", "mtr",
    "whatweb",
    "cut", "awk", "sed", "sort", "uniq", "tr", "xargs", "tee",
    "jq", "yq", "xmllint",
}

INTRUSIVE_TOOLS = {
    "nmap", "masscan", "rustscan", "unicornscan",
    "gobuster", "feroxbuster", "ffuf", "dirb", "dirbuster", "wfuzz", "dirsearch",
    "nikto", "nuclei", "wapiti", "skipfish",
    "enum4linux", "enum4linux-ng", "smbmap", "smbclient", "rpcclient",
    "wpscan", "joomscan", "droopescan",
    "snmpwalk", "snmpcheck", "onesixtyone",
    "showmount", "ldapsearch",
    "amass", "subfinder", "assetfinder", "sublist3r", "knockpy",
    "sslscan", "sslyze", "testssl",
}

DESTRUCTIVE_TOOLS = {
    "rm", "dd", "mkfs", "shred", "fdisk", "parted", "wipefs",
    "sqlmap", "metasploit", "msfconsole", "msfvenom",
    "hydra", "medusa", "patator", "ncrack",
    "john", "hashcat",
    "crackmapexec", "netexec", "cme",
    "aircrack-ng", "airodump-ng", "aireplay-ng", "airbase-ng",
    "responder", "mitm6", "ettercap", "bettercap",
    "impacket-secretsdump", "impacket-psexec", "impacket-wmiexec",
    "evil-winrm", "smbexec",
    "useradd", "userdel", "usermod", "passwd", "chpasswd",
    "iptables", "ip6tables", "nft", "ufw", "firewalld",
    "systemctl", "service",
    "apt", "apt-get", "dpkg", "pacman", "yum", "dnf", "snap", "flatpak",
    "pip", "pip3", "npm", "yarn", "gem", "cargo",
    "mount", "umount", "swapoff", "swapon",
    "kill", "killall", "pkill",
    "reboot", "shutdown", "poweroff", "halt",
}

DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-[rRf]+",
    r"\bsudo\s+rm\b",
    r">\s*/(etc|usr|bin|sbin|boot|var|root)/",
    r">>\s*/(etc|usr|bin|sbin|boot|var|root)/",
    r"\bchmod\s+(-R\s+)?777\b",
    r"\bchown\s+-R\b",
    r"\beval\s+",
    r"\b(curl|wget)\b[^|]*\|\s*(sh|bash|zsh)",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",
    r"\bdd\s+if=.*\s+of=/dev/",
    r"\b/dev/(sd[a-z]|nvme|mmcblk)",
]


# Herramientas que envían tráfico a un destino remoto. Cualquier comando cuya
# PRIMERA palabra esté aquí se envuelve automáticamente con el proxy si
# PROXY_MODE != "off" y hay binario disponible.
NETWORK_TOOLS = {
    # Scanning
    "nmap", "masscan", "rustscan", "naabu", "unicornscan", "zmap",
    # Recon DNS / subdomains
    "subfinder", "assetfinder", "amass", "findomain", "shuffledns",
    "dnsx", "dnsrecon", "dnsenum", "fierce", "puredns", "altdns",
    # HTTP recon
    "httpx", "httprobe", "whatweb", "wappalyzer", "wafw00f", "katana",
    "waybackurls", "gau", "hakrawler",
    # Web fuzzing
    "gobuster", "ffuf", "feroxbuster", "dirb", "dirsearch", "wfuzz",
    # Web vuln scan
    "nikto", "nuclei", "wpscan", "joomscan", "droopescan", "sslyze",
    "testssl", "testssl.sh",
    # Exploitation
    "sqlmap", "hydra", "medusa", "ncrack", "patator", "metasploit",
    "msfconsole", "msfvenom",
    # SMB / Net / AD
    "smbclient", "smbmap", "enum4linux", "enum4linux-ng",
    "crackmapexec", "nxc", "netexec", "rpcclient",
    "responder", "ntlmrelayx.py", "secretsdump.py", "GetUserSPNs.py",
    "GetNPUsers.py", "psexec.py", "smbexec.py", "wmiexec.py",
    "bloodhound-python", "certipy", "kerbrute",
    # OSINT APIs
    "shodan", "censys", "theHarvester", "spiderfoot", "recon-ng",
    # Genéricos
    "curl", "wget", "nc", "ncat", "netcat", "telnet", "ssh", "scp",
    "sftp", "ftp", "tftp", "rdesktop", "xfreerdp", "rsync",
    "openssl",
    # SNMP
    "snmpwalk", "snmpget", "snmp-check", "onesixtyone",
    # LDAP / Kerberos
    "ldapsearch", "ldapdomaindump",
    # WHOIS / DNS
    "whois", "dig", "host", "drill",
    # Misc red
    "ping", "hping3", "fping", "arping", "traceroute", "mtr",
}

PROXY_WRAPPERS = {
    "proxychains", "proxychains4", "torify", "torsocks", "tsocks",
}


def _proxy_binary():
    """Binario disponible según PROXY_MODE. None si no hay (o modo off)."""
    if PROXY_MODE == "off":
        return None
    if PROXY_MODE == "proxychains":
        for b in ("proxychains4", "proxychains"):
            if shutil.which(b):
                return b
    if PROXY_MODE == "torify":
        for b in ("torify", "torsocks"):
            if shutil.which(b):
                return b
    return None


def _is_network_command(command):
    """¿Algún subcomando de la cadena usa una herramienta de red?
    Trocea por separadores de shell (&&, ||, ;, |, &) y mira la PRIMERA
    palabra de cada subcomando (saltando `sudo` y prefijos `VAR=val`).
    """
    cmd = command.strip()
    if not cmd:
        return False
    first = cmd.split(maxsplit=1)[0]
    if os.path.basename(first) in PROXY_WRAPPERS:
        return False  # ya está envuelto explícitamente

    # Separadores de comando en shell. `&&` y `||` van antes que `&` y `|`
    # para que la alternancia los priorice.
    subcommands = re.split(r"(?:&&|\|\||;|\||&)", cmd)
    for sub in subcommands:
        sub = sub.strip()
        if not sub:
            continue
        for token in sub.split():
            # Saltar `sudo`
            if token == "sudo":
                continue
            # Saltar VAR=val (asignaciones de entorno previas al binario)
            if "=" in token.split("/")[-1] and not token.startswith("-"):
                continue
            base = os.path.basename(token)
            if base in NETWORK_TOOLS:
                return True
            # La primera palabra "real" del subcomando manda — no seguimos
            # buscando en argumentos posteriores (evita falsos positivos
            # tipo `grep "nmap" file`).
            break
    return False


def maybe_wrap_with_proxy(command):
    """Devuelve (comando_efectivo, binario_proxy_usado_o_None).
    Si el comando es de red y hay proxy disponible, lo envuelve en una subshell
    para que la cadena entera (con && ; |) herede el LD_PRELOAD."""
    if not _is_network_command(command):
        return command, None
    binary = _proxy_binary()
    if not binary:
        return command, None
    if binary in ("proxychains4", "proxychains"):
        return f"{binary} -q bash -c {shlex.quote(command)}", binary
    if binary in ("torify", "torsocks"):
        return f"{binary} bash -c {shlex.quote(command)}", binary
    return command, None


def _check_tor_running():
    """Comprobación rápida: ¿hay algo escuchando en 127.0.0.1:9050? Devuelve bool."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        rc = s.connect_ex(("127.0.0.1", 9050))
        s.close()
        return rc == 0
    except Exception:
        return False


def classify_command(command):
    import re

    cmd = command.strip()
    if not cmd:
        return "safe"

    # Patrones destructivos en cualquier parte del comando
    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd):
            return "destructive"

    # Primer token (binario invocado)
    first_token = cmd.split()[0]
    # Quitar variables de entorno tipo `FOO=bar tool ...`
    while "=" in first_token and len(cmd.split()) > 1:
        cmd = cmd.split(None, 1)[1]
        first_token = cmd.split()[0]
    # Quitar prefijo sudo
    if first_token == "sudo" and len(cmd.split()) > 1:
        rest = cmd.split(None, 1)[1]
        # sudo + cualquier cosa eleva privilegios → al menos intrusivo
        sub_category = classify_command(rest)
        if sub_category == "safe":
            return "intrusive"
        return sub_category
    # Eliminar ruta absoluta
    tool = first_token.split("/")[-1]

    if tool in DESTRUCTIVE_TOOLS:
        return "destructive"
    if tool in INTRUSIVE_TOOLS:
        return "intrusive"
    if tool in SAFE_TOOLS:
        return "safe"

    # curl/wget: GET puro = safe; con escritura/POST/upload = intrusivo
    if tool in ("curl", "wget"):
        write_flags = (" -O", " --output", " -o ", " -d ", " --data",
                       " --form", " -F ", " -X POST", " -X PUT", " -X DELETE",
                       " --upload", " -T ")
        if any(f in cmd for f in write_flags):
            return "intrusive"
        return "safe"

    # Por defecto, comando desconocido → tratamos como intrusivo (más seguro)
    return "intrusive"


def extract_command(answer):
    marker = "COMANDO:"

    if marker not in answer:
        return None

    command_block = answer.split(marker, 1)[1].strip()

    if not command_block:
        return None

    command = command_block.splitlines()[0].strip()

    if command.startswith("```"):
        return None

    return command


# Detección de herramienta faltante en stderr. Cubre:
#   bash: dnsx: command not found
#   bash: line 1: dnsx: command not found
#   bash: línea 1: dnsx: no se encontró la orden
#   /bin/sh: 1: dnsx: not found
#   /usr/bin/env: 'subfinder': No such file or directory
#   env: 'subfinder': No such file or directory
MISSING_TOOL_PATTERNS = [
    # Shell tradicional con "line N:" / "línea N:" opcional
    re.compile(
        r"(?:bash|sh|zsh|/bin/\S+):"
        r"(?:\s*(?:line|l[ií]nea)\s+\d+:)?"
        r"\s*([\w.\-]+):\s*"
        r"(?:command not found|no se encontró la orden|orden no encontrada|comando no encontrado|not found)",
        re.IGNORECASE,
    ),
    # Forma "/bin/sh: 1: dnsx: not found" (POSIX sh)
    re.compile(
        r"/bin/\S+:\s*\d+:\s*([\w.\-]+):\s*not found",
        re.IGNORECASE,
    ),
    # env: 'subfinder': No such file or directory  (shebang #!/usr/bin/env <tool>)
    re.compile(
        r"(?:/usr/bin/)?env:\s*['\"]?([\w.\-]+)['\"]?:\s*No such file or directory",
        re.IGNORECASE,
    ),
]


def _detect_missing_tool(stderr, returncode):
    """Si la salida indica una herramienta faltante, devuelve su nombre. Si no, None."""
    if returncode == 0 or not stderr:
        return None
    for pat in MISSING_TOOL_PATTERNS:
        m = pat.search(stderr)
        if m:
            return m.group(1)
    return None


def _try_install_tool(tool):
    """Ejecuta `sudo apt-get install -y <tool>`. Usa `_sudo_run` para
    respetar la password almacenada (`sudo set`) y NO bloquear el tty
    cuando se invoca desde un subagente. Devuelve dict {ok, log}.
    """
    # Sanitización: sólo letras, números, punto, guion, underscore.
    if not re.match(r"^[A-Za-z0-9._\-]+$", tool or ""):
        return {"ok": False, "log": f"nombre de herramienta no válido: {tool!r}"}

    install_cmd = f"apt-get install -y {tool}" if _running_as_root() \
        else f"sudo apt-get install -y {tool}"
    _q_print()
    _q_print(Panel(
        f"[bold {ORANGE}]Auto-install[/]  ·  [{WHITE}]{install_cmd}[/]",
        border_style=ORANGE,
        box=ROUNDED,
    ))

    rc, _stdout, stderr = _sudo_run(
        ["apt-get", "install", "-y", tool],
        timeout=600,
    )
    if rc == 0:
        return {"ok": True, "log": f"apt-get install -y {tool} → OK"}
    if rc == 124:
        return {"ok": False, "log": "timeout (>600s) en apt-get install"}
    detail = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    return {
        "ok": False,
        "log": (
            f"apt-get install -y {tool} → exit {rc}"
            + (f" · {detail}" if detail else "")
        ),
    }


# Mapa tool → frase corta que se muestra en el spinner mientras se ejecuta.
# Cualquier tool no listada cae al fallback genérico "Ejecutando <tool>…".
_COMMAND_DESCRIPTIONS = {
    # Scanning
    "nmap": "Realizando escaneo nmap",
    "masscan": "Realizando escaneo masscan",
    "rustscan": "Realizando escaneo rustscan",
    "naabu": "Escaneando puertos con naabu",
    "unicornscan": "Realizando escaneo unicornscan",
    # Recon DNS / subdomains
    "subfinder": "Buscando subdominios con subfinder",
    "assetfinder": "Buscando subdominios con assetfinder",
    "amass": "Enumerando DNS con amass",
    "findomain": "Buscando subdominios con findomain",
    "dnsx": "Resolviendo DNS con dnsx",
    "dnsrecon": "Recon DNS con dnsrecon",
    "dnsenum": "Enumerando DNS con dnsenum",
    "fierce": "Recon DNS con fierce",
    "puredns": "Resolviendo con puredns",
    # HTTP recon
    "httpx": "Probando endpoints HTTP con httpx",
    "httprobe": "Probando endpoints HTTP con httprobe",
    "whatweb": "Identificando tecnologías con whatweb",
    "wappalyzer": "Identificando tecnologías con wappalyzer",
    "wafw00f": "Detectando WAF con wafw00f",
    "katana": "Crawleando con katana",
    "waybackurls": "Recopilando URLs de Wayback",
    "gau": "Recopilando URLs con gau",
    "hakrawler": "Crawleando con hakrawler",
    # Web fuzzing
    "gobuster": "Fuzzing con gobuster",
    "ffuf": "Fuzzing con ffuf",
    "feroxbuster": "Fuzzing con feroxbuster",
    "dirb": "Fuzzing con dirb",
    "dirsearch": "Fuzzing con dirsearch",
    "wfuzz": "Fuzzing con wfuzz",
    # Web vuln scan
    "nikto": "Escaneando vulnerabilidades web con nikto",
    "nuclei": "Escaneando vulnerabilidades con nuclei",
    "wpscan": "Escaneando WordPress con wpscan",
    "joomscan": "Escaneando Joomla con joomscan",
    "droopescan": "Escaneando CMS con droopescan",
    "wapiti": "Escaneando con wapiti",
    "skipfish": "Escaneando con skipfish",
    # TLS/SSL
    "sslscan": "Analizando TLS con sslscan",
    "sslyze": "Analizando TLS con sslyze",
    "testssl": "Analizando TLS con testssl",
    # SMB / AD / network services
    "enum4linux": "Enumerando SMB con enum4linux",
    "enum4linux-ng": "Enumerando SMB con enum4linux-ng",
    "smbmap": "Enumerando shares SMB con smbmap",
    "smbclient": "Conectando a SMB",
    "rpcclient": "Conectando RPC con rpcclient",
    "ldapsearch": "Consultando LDAP",
    "snmpwalk": "Walking SNMP",
    "snmpcheck": "Verificando SNMP",
    "onesixtyone": "Brute-forcing community SNMP",
    "showmount": "Listando NFS exports",
    "crackmapexec": "Ejecutando crackmapexec",
    "netexec": "Ejecutando netexec",
    "cme": "Ejecutando cme",
    "responder": "Lanzando Responder",
    "mitm6": "Lanzando mitm6",
    # Brute force / credenciales
    "hydra": "Probando credenciales con hydra",
    "medusa": "Probando credenciales con medusa",
    "ncrack": "Probando credenciales con ncrack",
    "patator": "Probando credenciales con patator",
    "john": "Crackeando hashes con john",
    "hashcat": "Crackeando hashes con hashcat",
    # Exploitation
    "sqlmap": "Escaneando SQL injection con sqlmap",
    "metasploit": "Lanzando metasploit",
    "msfconsole": "Lanzando metasploit",
    "msfvenom": "Generando payload con msfvenom",
    "searchsploit": "Consultando exploit-db",
    # WiFi
    "aircrack-ng": "Procesando captura WiFi",
    "airodump-ng": "Capturando tráfico WiFi",
    "aireplay-ng": "Inyectando paquetes WiFi",
    # OSINT
    "theharvester": "Recopilando OSINT con theHarvester",
    "shodan": "Consultando Shodan",
    "censys": "Consultando Censys",
    # HTTP genérico
    "curl": "Realizando petición HTTP",
    "wget": "Descargando con wget",
    # DNS / red básica
    "dig": "Consultando DNS",
    "nslookup": "Resolviendo DNS",
    "host": "Resolviendo DNS",
    "drill": "Consultando DNS",
    "whois": "Consultando whois",
    "ping": "Probando conectividad",
    "ping6": "Probando conectividad IPv6",
    "traceroute": "Trazando ruta",
    "tracepath": "Trazando ruta",
    "mtr": "Diagnóstico de red con mtr",
    # Sistema / gestión
    "apt": "Gestionando paquetes apt",
    "apt-get": "Instalando paquetes apt",
    "dpkg": "Consultando paquetes dpkg",
    "pip": "Instalando con pip",
    "pip3": "Instalando con pip",
    "systemctl": "Gestionando servicio systemctl",
    "service": "Gestionando servicio",
    # Búsqueda / inspección
    "find": "Buscando archivos",
    "locate": "Buscando con locate",
    "grep": "Buscando en archivos",
    "ls": "Listando contenido",
    "cat": "Leyendo archivo",
    "head": "Leyendo cabecera",
    "tail": "Leyendo cola",
    "which": "Resolviendo binario",
}


# Frames de animación de "puntos en movimiento" detrás de la frase. Se
# alterna cada `frame_interval_s` segundos. Si tu terminal tiene problemas
# de parpadeo, sube el interval; si te resulta "lento", bájalo.
_SPINNER_ANIM_FRAMES = [
    "    ",
    ".   ",
    "..  ",
    "... ",
    "....",
    " ...",
    "  ..",
    "   .",
]


class _AnimatedSpinner:
    """Context manager: combina un `console.status` de Rich (spinner braille
    a la izquierda) con una animación de puntos suspensivos viajeros DENTRO
    del texto, gestionada por un hilo daemon.

    Uso:
        with _AnimatedSpinner("Realizando escaneo nmap · 1.2.3.4"):
            stdout, stderr, rc = _execute_shell(...)
    """

    def __init__(self, description, style=None, spinner_name="dots",
                 frame_interval_s=0.18, show_elapsed=True):
        # Si la descripción ya trae "…" o puntos finales, los quitamos para
        # añadir nosotros la animación sin duplicar.
        self._base = (description or "").rstrip(" .…·")
        self._style = style or CYAN
        self._spinner_name = spinner_name
        self._frame_interval_s = frame_interval_s
        self._show_elapsed = show_elapsed
        self._t0 = None
        self._status = None
        self._stop_event = None
        self._thread = None

    def _render(self, frame_idx):
        suffix = _SPINNER_ANIM_FRAMES[frame_idx % len(_SPINNER_ANIM_FRAMES)]
        elapsed_str = ""
        if self._show_elapsed and self._t0 is not None:
            elapsed = time.time() - self._t0
            elapsed_str = f"  [dim]({_fmt_elapsed(elapsed)})[/]"
        return (
            f"[bold {self._style}]{self._base}[/]"
            f"[{self._style}]{suffix}[/]"
            f"{elapsed_str}"
        )

    def _loop(self):
        i = 1
        while not self._stop_event.wait(self._frame_interval_s):
            try:
                self._status.update(self._render(i))
            except Exception:
                return
            i += 1

    def __enter__(self):
        self._t0 = time.time()
        self._status = console.status(
            self._render(0),
            spinner=self._spinner_name,
            spinner_style=self._style,
        )
        self._status.__enter__()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if self._status:
            return self._status.__exit__(exc_type, exc_val, exc_tb)
        return False


def _describe_command(command):
    """Devuelve una frase corta de 1 línea describiendo qué hace `command`.
    Usada en el spinner mientras la herramienta se ejecuta sin streaming."""
    tool = _runs_first_tool_token(command) or ""
    tool_lower = tool.lower()
    if tool_lower in _COMMAND_DESCRIPTIONS:
        base = _COMMAND_DESCRIPTIONS[tool_lower]
    elif tool:
        base = f"Ejecutando {tool}"
    else:
        return "Ejecutando comando…"
    # Si el comando tiene un target obvio (IP/host/URL) lo anexamos en dim.
    tokens = _runs_target_tokens(command)
    if tokens:
        return f"{base} · {tokens[0]}…"
    return f"{base}…"


def _execute_shell(command, timeout=300, stream=None):
    """Ejecuta `command` con shell=True y devuelve (stdout, stderr, returncode).
    Si `stream` es True (o STREAM_OUTPUT True por defecto), imprime stdout/stderr
    en directo línea a línea mientras los recolecta para devolverlos al modelo.

    En modo no-stream, fijamos stdin=DEVNULL para que herramientas que requieren
    input interactivo (sudo sin password cacheada, prompts de tools) fallen
    rápido en vez de colgar bloqueadas esperando teclas que no van a llegar.
    """
    if stream is None:
        stream = STREAM_OUTPUT

    if not stream:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return (proc.stdout or "").rstrip(), (proc.stderr or "").rstrip(), proc.returncode

    # Modo streaming con select() sobre los descriptores de los pipes
    import select

    proc = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    stdout_buf = []
    stderr_buf = []
    streams = {
        proc.stdout: ("stdout", stdout_buf),
        proc.stderr: ("stderr", stderr_buf),
    }
    start = time.monotonic()
    timed_out = False

    while streams:
        if time.monotonic() - start > timeout:
            proc.kill()
            timed_out = True
            break
        readable, _, _ = select.select(list(streams.keys()), [], [], 0.5)
        if not readable:
            # poll periódico: si el proceso ya terminó y no hay más datos, salimos
            if proc.poll() is not None:
                for s in list(streams.keys()):
                    remaining = s.read()
                    if remaining:
                        kind, buf = streams[s]
                        buf.append(remaining)
                        _stream_write(remaining, kind)
                    streams.pop(s)
            continue
        for s in readable:
            line = s.readline()
            if not line:
                streams.pop(s, None)
                continue
            kind, buf = streams[s]
            buf.append(line)
            _stream_write(line, kind)

    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout)

    return ("".join(stdout_buf).rstrip(),
            "".join(stderr_buf).rstrip(),
            proc.returncode)


def _stream_write(text, kind):
    """Escribe `text` al terminal en directo. stderr se pinta atenuado en rojo."""
    if kind == "stderr":
        # ANSI: rojo atenuado, reset al final. No usamos rich aquí para no
        # interpretar markup que pueda venir en la salida real.
        sys.stderr.write("\x1b[2;31m" + text + "\x1b[0m")
        sys.stderr.flush()
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


def _format_command_output(stdout, stderr):
    parts = []
    if stdout:
        parts.append(f"STDOUT:\n{stdout}")
    if stderr:
        parts.append(f"STDERR:\n{stderr}")
    if not parts:
        parts.append("Comando ejecutado sin salida.")
    return "\n\n".join(parts)


# Tokens shell built-in que no son binarios y no hace falta verificar en PATH.
_SHELL_BUILTINS = {
    "bash", "sh", "zsh", "if", "then", "else", "elif", "fi", "for", "do",
    "done", "while", "until", "case", "esac", "in", "function", "test",
    "[", "[[", "echo", "cd", "exit", "return", "true", "false",
    "{", "}", "(", ")", ":",
    "set", "unset", "export", "source", ".", "alias", "read", "trap",
}


def _check_tools_in_command(command):
    """Devuelve una lista [(tool, installed_bool)] con los tokens-de-comando
    (binarios reales) detectados en `command`. Útil para informar al modelo
    qué herramientas del comando no están en PATH."""
    seen = []
    seen_set = set()
    subcommands = re.split(r"(?:&&|\|\||;|\||&)", command)
    for sub in subcommands:
        sub = sub.strip()
        if not sub:
            continue
        for token in sub.split():
            if token == "sudo":
                continue
            # VAR=val (asignaciones de entorno previas al binario)
            if "=" in token.split("/")[-1] and not token.startswith("-"):
                continue
            base = os.path.basename(token)
            if base in PROXY_WRAPPERS:
                continue
            if base in _SHELL_BUILTINS:
                continue
            if base in seen_set:
                break
            seen_set.add(base)
            seen.append((base, shutil.which(base) is not None))
            break  # sólo la primera palabra del subcomando es comando
    return seen


def _command_uses_sudo(command):
    """True si el comando ejecuta `sudo` como binario (no como argumento).
    Cubre `sudo X`, `... && sudo X`, `; sudo X`, `| sudo X`, además de
    asignaciones de entorno previas (`VAR=val sudo X`).

    Si el agente corre como root, devolvemos False: no hay sudo que gestionar,
    el comando se ejecutará directamente (y se le quitará el prefijo `sudo`
    si lo tuviera, vía `_strip_sudo_prefix`).
    """
    if not command:
        return False
    if _running_as_root():
        return False
    parts = re.split(r"(?:&&|\|\||;|\|)", command)
    for p in parts:
        tokens = p.strip().split()
        for tok in tokens:
            # Saltar asignaciones VAR=val que pueden preceder al binario
            if "=" in tok.split("/")[-1] and not tok.startswith("-"):
                continue
            # Primer token "real" → es el binario que se va a ejecutar
            if tok == "sudo" or tok.endswith("/sudo"):
                return True
            break  # el primer no-asignación de este subcomando ya se evaluó
    return False


# Contraseña sudo almacenada SOLO en memoria del proceso (nunca a disco).
# Se carga con `sudo set`, se borra con `sudo clear` o al salir del proceso.
# Cuando está presente, _ensure_sudo_credentials() puede refrescar el caché
# de sudo de forma no-interactiva (útil para subagentes y autopilot).
_STORED_SUDO_PASSWORD = None
_sudo_password_lock = threading.Lock()


def _running_as_root():
    """True si el proceso del agente corre como root (uid 0).
    Caso típico: VPS donde la cuenta es root y sudo ni está instalado."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False  # No-Unix (no debería pasar, agente es Linux-only)


def _strip_sudo_prefix(command):
    """Devuelve el comando sin el prefijo `sudo` (y sus flags) de cada
    subcomando. Útil cuando ya eres root: `sudo apt install foo` → `apt
    install foo`. Maneja también flags comunes de sudo: -E, -H, -u user, -k.

    Cubre comandos compuestos con &&, ||, ;, | tratando cada parte por
    separado.
    """
    if not command or "sudo" not in command:
        return command

    def _strip_one(part):
        # Preservar el whitespace de inicio para no perder formato.
        leading = len(part) - len(part.lstrip())
        prefix = part[:leading]
        tokens = part.split()
        # Recopilar asignaciones de entorno previas (VAR=val) — hay que
        # mantenerlas, son semánticas (DEBIAN_FRONTEND=noninteractive, etc.).
        i = 0
        assignments = []
        while i < len(tokens) and "=" in tokens[i].split("/")[-1] \
                and not tokens[i].startswith("-"):
            assignments.append(tokens[i])
            i += 1
        if i >= len(tokens):
            return part
        if tokens[i] != "sudo" and not tokens[i].endswith("/sudo"):
            return part
        # Saltar el binario sudo
        i += 1
        # Saltar flags de sudo: -E, -H, -k, -i, -s, -n
        while i < len(tokens) and tokens[i] in {"-E", "-H", "-k", "-i", "-s", "-n"}:
            i += 1
        # Saltar -u USER y -g GROUP (consumen el siguiente token)
        while i < len(tokens) and tokens[i] in {"-u", "-g"} and i + 1 < len(tokens):
            i += 2
        # Reconstruir: asignaciones preservadas + resto sin sudo.
        return prefix + " ".join(assignments + tokens[i:])

    # Separar por &&, ||, ;, | preservando los separadores.
    parts = re.split(r"(\s*(?:&&|\|\||;|\|)\s*)", command)
    out = []
    for chunk in parts:
        if re.match(r"^\s*(?:&&|\|\||;|\|)\s*$", chunk):
            out.append(chunk)
        else:
            out.append(_strip_one(chunk))
    return "".join(out)


def _sudo_cache_valid():
    """True si el caché de timestamp de sudo está vigente (no se pedirá pwd).
    También True si el usuario tiene NOPASSWD: ese caso `sudo -n true` retorna 0.
    """
    try:
        r = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        return r.returncode == 0
    except Exception:
        return False


def _sudo_refresh_with_stored_password():
    """Si hay password almacenada, refresca el caché vía `sudo -S -v`.
    Devuelve True si OK, False si no hay password o falló."""
    with _sudo_password_lock:
        pw = _STORED_SUDO_PASSWORD
    if not pw:
        return False
    try:
        r = subprocess.run(
            ["sudo", "-S", "-v"],
            input=(pw + "\n").encode("utf-8"),
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def _validate_sudo_password(pw):
    """Intenta autenticar con la password dada vía `sudo -S true`. No
    almacena nada — sólo valida."""
    if not pw:
        return False
    try:
        r = subprocess.run(
            ["sudo", "-k", "-S", "true"],
            input=(pw + "\n").encode("utf-8"),
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def _set_stored_sudo_password(pw):
    """Almacena la password en memoria SI valida correctamente. Devuelve bool."""
    global _STORED_SUDO_PASSWORD
    if not _validate_sudo_password(pw):
        return False
    with _sudo_password_lock:
        _STORED_SUDO_PASSWORD = pw
    return True


def _sudo_run(sudo_args, timeout=60, allow_tty_fallback=True):
    """Ejecuta `sudo <args>` honrando la password almacenada y el contexto
    (main thread vs subagente). Devuelve (rc, stdout, stderr).

    Estrategia, en orden:
      1. Si el caché de sudo es válido → `sudo -n <args>` (no-interactive).
      2. Si hay password almacenada (`sudo set`) → `sudo -S <args>` con
         la password vía stdin. NO toca el tty.
      3. Si estamos en un thread de subagente y nada de lo anterior →
         falla con rc=1 y mensaje claro. NUNCA bloquea el tty del operador.
      4. Si main thread y `allow_tty_fallback=True` → refresca caché con
         `_ensure_sudo_credentials()` (prompt interactivo), luego `sudo -n`.
      5. Si main thread y `allow_tty_fallback=False` → falla.
    """
    if not sudo_args:
        return (1, "", "_sudo_run: sudo_args vacío")
    args = list(sudo_args)

    # Si somos root, no necesitamos sudo: ejecutamos el binario directo.
    if _running_as_root():
        try:
            proc = subprocess.run(
                args,
                capture_output=True, text=True, timeout=timeout,
            )
            return (proc.returncode,
                    (proc.stdout or "").rstrip(),
                    (proc.stderr or "").rstrip())
        except subprocess.TimeoutExpired:
            return (124, "", f"timeout ({timeout}s)")
        except Exception as e:
            return (1, "", str(e))

    if _sudo_cache_valid():
        try:
            proc = subprocess.run(
                ["sudo", "-n"] + args,
                capture_output=True, text=True, timeout=timeout,
            )
            return (proc.returncode,
                    (proc.stdout or "").rstrip(),
                    (proc.stderr or "").rstrip())
        except subprocess.TimeoutExpired:
            return (124, "", f"timeout ({timeout}s)")
        except Exception as e:
            return (1, "", str(e))

    with _sudo_password_lock:
        stored = _STORED_SUDO_PASSWORD
    if stored:
        try:
            proc = subprocess.run(
                ["sudo", "-S"] + args,
                input=(stored + "\n").encode("utf-8"),
                capture_output=True, timeout=timeout,
            )
            stdout = (proc.stdout or b"").decode("utf-8", errors="replace").rstrip()
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace").rstrip()
            return (proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            return (124, "", f"timeout ({timeout}s)")
        except Exception as e:
            return (1, "", str(e))

    if _is_subagent_thread():
        return (1, "",
                "sudo requiere password pero el caché no es vigente y no "
                "hay password almacenada. Ejecuta `sudo set` antes de "
                "lanzar subagentes que necesiten sudo.")

    if not allow_tty_fallback:
        return (1, "", "sudo no autenticado (allow_tty_fallback=False)")

    # Main thread, sin caché ni stored → prompt interactivo, luego sudo -n
    if not _ensure_sudo_credentials():
        return (1, "", "sudo: autenticación cancelada o fallida")
    try:
        proc = subprocess.run(
            ["sudo", "-n"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        return (proc.returncode,
                (proc.stdout or "").rstrip(),
                (proc.stderr or "").rstrip())
    except Exception as e:
        return (1, "", str(e))


def _clear_stored_sudo_password():
    """Wipea la password almacenada."""
    global _STORED_SUDO_PASSWORD
    with _sudo_password_lock:
        _STORED_SUDO_PASSWORD = None


def _ensure_sudo_credentials():
    """Asegura caché de sudo vigente antes de ejecutar un comando con sudo.
    Orden de intentos:
      0. Si somos root → True inmediato (no hay sudo que gestionar).
      1. Si el caché ya es válido → True.
      2. Si hay password almacenada (`sudo set`) → refresca con ella.
      3. Si estamos en main thread → prompt interactivo `sudo -v`.
      4. Si estamos en subagente y todo lo anterior falla → False (el
         comando se aborta limpiamente, el subagente busca alternativa).
    """
    if _running_as_root():
        return True
    if _sudo_cache_valid():
        return True

    # 2) password almacenada → no requiere interacción (sirve para subagentes)
    if _sudo_refresh_with_stored_password():
        return True

    # 3) main thread → prompt interactivo. Subagente → fail.
    if _is_subagent_thread():
        return False

    console.print()
    console.print(Panel(
        f"[bold {ORANGE}]🔐 Este comando usa sudo[/]\n\n"
        f"[{WHITE}]Introduce tu contraseña abajo. Sudo cachea por unos "
        f"minutos (default 15) y no la volverá a pedir durante ese tiempo.\n\n"
        f"Tip: ejecuta [bold]sudo set[/] desde el REPL para almacenar la "
        f"password en memoria — así los subagentes y el autopilot pueden "
        f"usar sudo sin pedirte cada vez.[/]\n\n"
        f"[dim]Pulsa Ctrl+C para abortar.[/]",
        border_style=ORANGE,
        box=ROUNDED,
        padding=(1, 2),
    ))
    try:
        rc = subprocess.call(["sudo", "-v"])
        if rc == 0:
            console.print(f"[bold {GREEN}]✓ sudo autenticado.[/]")
            return True
        console.print(f"[{RED}]› sudo -v devolvió rc={rc}, comando abortado.[/]")
        return False
    except KeyboardInterrupt:
        console.print()
        console.print(f"[{RED}]› autenticación de sudo cancelada por el operador.[/]")
        return False
    except Exception as e:
        console.print(f"[{RED}]› error invocando sudo -v: {e}[/]")
        return False


# Captura el path del wordlist tras flags estándar de tools que las consumen:
#   -w / -W / --wordlist / --wordlists  (gobuster, ffuf, feroxbuster, wfuzz, dirb)
#   -P / -L                              (hydra, medusa, patator, kerbrute, ncrack)
# Tolera = o espacio entre flag y valor. Filtra falsos positivos por
# existencia del archivo (`_count_file_lines` retorna None si no existe).
_WORDLIST_FLAG_RE = re.compile(
    r"(?:^|\s)(?:-w|-W|--wordlist|--wordlists|-P|-L)"
    r"(?:\s+|=)"
    r"(?P<path>\"[^\"]+\"|'[^']+'|[^\s|&;<>]+)"
)


def _detect_wordlist_paths(command):
    """Devuelve la lista de paths de wordlists usados en el comando.
    Quita comillas y resuelve a ruta absoluta cuando aplica."""
    if not command:
        return []
    paths = []
    seen = set()
    for m in _WORDLIST_FLAG_RE.finditer(command):
        p = m.group("path").strip("'\"")
        if not p or p in seen:
            continue
        seen.add(p)
        paths.append(p)
    return paths


def _count_file_lines(path):
    """Cuenta líneas de un archivo de texto. Devuelve None si no existe o no
    se puede leer."""
    if not path:
        return None
    abs_path = path if os.path.isabs(path) else os.path.abspath(path)
    if not os.path.isfile(abs_path):
        return None
    try:
        n = 0
        with open(abs_path, "rb") as f:
            for _ in f:
                n += 1
        return n
    except Exception:
        return None


def _compute_timeout_for_command(command):
    """Calcula el timeout apropiado para `command` según los wordlists que
    use. Devuelve (timeout_segundos, motivo_str_o_None) donde motivo se
    imprime al operador cuando se aplica el timeout extendido.
    """
    wordlists = _detect_wordlist_paths(command)
    if not wordlists:
        return COMMAND_TIMEOUT_S, None
    max_lines = 0
    biggest = None
    for p in wordlists:
        n = _count_file_lines(p)
        if n is not None and n > max_lines:
            max_lines = n
            biggest = p
    if max_lines >= WORDLIST_MEDIUM_THRESHOLD_LINES:
        reason = (
            f"wordlist `{biggest}` con {max_lines:,} líneas "
            f"(≥{WORDLIST_MEDIUM_THRESHOLD_LINES:,}) "
            f"→ timeout extendido a {COMMAND_TIMEOUT_S_LARGE}s "
            f"({COMMAND_TIMEOUT_S_LARGE // 60} min)"
        )
        return COMMAND_TIMEOUT_S_LARGE, reason
    return COMMAND_TIMEOUT_S, None


_STDERR_SUPPRESSION_PATTERNS = [
    # 2>/dev/null, 2>>/dev/null
    re.compile(r'\s*2>>?\s*/dev/null\b'),
    # &>/dev/null, &>>/dev/null  (suprime stdout y stderr)
    re.compile(r'\s*&>>?\s*/dev/null\b'),
    # >/dev/null 2>&1
    re.compile(r'\s*>>?\s*/dev/null\s+2>&1\b'),
    # 2>&1 >/dev/null
    re.compile(r'\s*2>&1\s+>>?\s*/dev/null\b'),
]


def _strip_stderr_suppression(command):
    """Elimina patrones que silencian stderr (2>/dev/null, &>/dev/null, etc.)
    para preservar el diagnóstico. Devuelve (cleaned, was_changed)."""
    cleaned = command
    for pat in _STDERR_SUPPRESSION_PATTERNS:
        cleaned = pat.sub('', cleaned)
    cleaned = cleaned.strip()
    return cleaned, cleaned != command


def _split_at_and_chain(command):
    """Divide `command` por operadores `&&` a nivel raíz, respetando comillas
    simples/dobles. Devuelve la lista de sub-comandos (sin espacios sobrantes).
    Si no hay `&&` a nivel raíz, devuelve una lista de un solo elemento.

    No divide por `;` ni por `||` — sólo `&&`, que es el patrón que el
    autopilot necesita aislar (corta al primer fallo)."""
    if not command:
        return []
    parts = []
    buf = []
    in_single = False
    in_double = False
    i = 0
    n = len(command)
    while i < n:
        c = command[i]
        if c == "\\" and i + 1 < n and not in_single:
            buf.append(c)
            buf.append(command[i + 1])
            i += 2
            continue
        if c == "'" and not in_double:
            in_single = not in_single
            buf.append(c)
        elif c == '"' and not in_single:
            in_double = not in_double
            buf.append(c)
        elif (c == '&' and not in_single and not in_double
              and i + 1 < n and command[i + 1] == '&'):
            parts.append("".join(buf).strip())
            buf = []
            i += 2
            continue
        else:
            buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


_OUTPUT_FILE_PATTERNS = [
    # Redirecciones de shell: > file, >> file, &> file, 2> file
    re.compile(r'(?:\d?>>?|&>)\s*([^\s|&;<>"\']+|"[^"]+"|\'[^\']+\')'),
    # -o / --output / --output-file <file>  (separados por espacio)
    re.compile(r'(?:^|\s)(?:-o|-O|--output|--output-file)\s+([^\s|&;<>"\']+)'),
    # nmap -oN/-oG/-oX/-oA/-oS <file>
    re.compile(r'-o[NGXAS]\s+([^\s|&;<>"\']+)'),
    # --output=file, -o=file
    re.compile(r'(?:-o|--output|--output-file)=([^\s|&;<>"\']+)'),
]


def _detect_output_files(command):
    """Detecta paths a los que el comando intenta escribir.
    Cubre redirecciones de shell (>, >>, &>) y flags habituales (-o, --output)."""
    files = []
    seen = set()
    for pat in _OUTPUT_FILE_PATTERNS:
        for m in pat.finditer(command):
            f = m.group(1).strip("\"'")
            if not f or f == "/dev/null" or f.startswith("/dev/"):
                continue
            if f in seen:
                continue
            seen.add(f)
            files.append(f)
    return files


def _enrich_output_with_diagnostics(command, output):
    """Añade bloques DIAGNÓSTICO al final del output para que el modelo tenga
    contexto factual en lugar de tener que adivinar:
      - Estado de cada herramienta del comando (instalada o no).
      - Por cada archivo al que el comando intentaba escribir: existe, tamaño,
        preview de las primeras líneas o aviso si está vacío.
    """
    extras = []

    # 1) Estado de herramientas
    tools = _check_tools_in_command(command)
    if tools:
        installed = [t for t, ok in tools if ok]
        missing = [t for t, ok in tools if not ok]
        rows = []
        if installed:
            rows.append("instaladas: " + ", ".join(installed))
        if missing:
            rows.append("NO instaladas: " + ", ".join(missing))
        if rows:
            extras.append(f"[DIAGNÓSTICO · tools del comando]\n" + "\n".join(rows))

    # 2) Estado de archivos de salida
    output_files = _detect_output_files(command)
    for f in output_files:
        abs_path = os.path.abspath(f)
        if not os.path.exists(abs_path):
            extras.append(
                f"[DIAGNÓSTICO · archivo `{f}`]\n"
                f"NO existe tras la ejecución (la herramienta no llegó a escribirlo)."
            )
            continue
        try:
            size = os.path.getsize(abs_path)
        except OSError as e:
            extras.append(f"[DIAGNÓSTICO · `{f}`] error stat: {e}")
            continue
        if size == 0:
            extras.append(
                f"[DIAGNÓSTICO · archivo `{f}`]\n"
                f"creado pero VACÍO (0 bytes) — la herramienta no produjo datos."
            )
            continue
        try:
            with open(abs_path, encoding="utf-8", errors="replace") as fp:
                lines = fp.readlines()
            n = len(lines)
            preview = "".join(lines[:20]).rstrip()
            if n > 20:
                preview += f"\n... (truncado, {n - 20} líneas más)"
            extras.append(
                f"[DIAGNÓSTICO · archivo `{f}` ({_human_size(size)}, {n} líneas)]\n"
                f"{preview}"
            )
        except OSError as e:
            extras.append(f"[DIAGNÓSTICO · `{f}` ({_human_size(size)})] no se pudo leer: {e}")

    if extras:
        return f"{output}\n\n" + "\n\n".join(extras)
    return output


def _handle_agent_meta_action(fix_cmd):
    """Si fix_cmd es una meta-acción del agente (no un comando de shell real),
    ejecuta la acción y devuelve un dict descriptivo. Si no, devuelve None.

    Disponible TANTO en el autopilot como en turnos normales (run_command la
    detecta antes de tratar el comando como shell).

    Meta-acciones soportadas:
      agent:proxy off            → PROXY_MODE = "off"
      agent:proxy on             → PROXY_MODE = "proxychains"
      agent:proxy proxychains    → PROXY_MODE = "proxychains"
      agent:proxy torify         → PROXY_MODE = "torify"
      agent:tor start            → arranca el servicio tor (sudo)
      agent:tor stop             → detiene el servicio tor (sudo)
      agent:tor restart          → reinicia el servicio tor (sudo)
      agent:learn <texto>        → guarda <texto> como lección persistente
    """
    global PROXY_MODE
    raw = (fix_cmd or "").strip()
    norm = raw.lower()
    if not norm.startswith("agent:"):
        return None

    # agent:learn — guarda una corrección/regla en memory/lessons/
    if norm.startswith("agent:learn "):
        # Preservar el texto original (mayúsculas/acentos), no `norm`.
        parts = raw.split(maxsplit=1)
        lesson_text = parts[1].strip() if len(parts) > 1 else ""
        if not lesson_text:
            return {"action": "learn", "ok": False,
                    "log": "agent:learn requiere texto tras el comando"}
        path = save_lesson(lesson_text)
        if not path:
            return {"action": "learn", "ok": False,
                    "log": "agent:learn no pudo guardar (texto vacío)"}
        rel = os.path.relpath(path, WORKSPACE)
        return {"action": "learn", "ok": True, "path": path,
                "log": f"lección guardada en {rel}"}

    if norm in ("agent:proxy off", "agent:proxy=off"):
        prev = PROXY_MODE
        PROXY_MODE = "off"
        return {"action": "proxy", "from": prev, "to": "off",
                "log": f"PROXY_MODE: {prev} → off (siguiente reintento sin proxy)"}
    if norm in ("agent:proxy on", "agent:proxy=on", "agent:proxy proxychains"):
        prev = PROXY_MODE
        PROXY_MODE = "proxychains"
        return {"action": "proxy", "from": prev, "to": "proxychains",
                "log": f"PROXY_MODE: {prev} → proxychains"}
    if norm in ("agent:proxy torify", "agent:proxy=torify"):
        prev = PROXY_MODE
        PROXY_MODE = "torify"
        return {"action": "proxy", "from": prev, "to": "torify",
                "log": f"PROXY_MODE: {prev} → torify"}

    if norm.startswith("agent:tor "):
        sub = norm.split(maxsplit=1)[1]
        if sub in ("start", "stop", "restart"):
            try:
                proc = subprocess.run(
                    ["sudo", "systemctl", sub, "tor"],
                    timeout=20,
                )
                ok = (proc.returncode == 0)
                tor_alive = _check_tor_running() if sub != "stop" else None
                msg = f"systemctl {sub} tor → rc={proc.returncode}"
                if tor_alive is not None:
                    msg += f" · puerto 9050 {'OK' if tor_alive else 'no responde aún'}"
                return {"action": "tor", "sub": sub, "ok": ok, "log": msg}
            except Exception as e:
                return {"action": "tor", "sub": sub, "ok": False,
                        "log": f"error tor {sub}: {e}"}

    return None


def troubleshoot_loop(failed_command, failed_output):
    """Bucle de auto-fix sin confirmación.

    En cada intento el modelo puede emitir:
      1. Un comando de shell normal (instalar paquete, descargar wordlist, etc.).
      2. Un comando de info-gathering tipo `tool --help`, `which tool`,
         `man tool | head -200`, `ls /usr/share/.../`, `find ... -name X`,
         `locate <pattern>` para descubrir nombres reales de scripts, rutas
         o flags antes de corregir.
      3. Una META-ACCIÓN del agente: `agent:proxy off|on|torify`,
         `agent:tor start|stop|restart`.
    Tras cada fix se reintenta el comando original con auto=True.

    Cadenas `&&`: si el comando original es una cadena (`a && b && c`), se
    aísla en sub-comandos y el RETRY ejecuta cada parte por separado en
    secuencia. Las partes ya resueltas no se vuelven a ejecutar; si una
    parte falla, ésa pasa a ser el nuevo `failed_command` para la siguiente
    iteración del bucle (el fix se centra en la parte concreta que falla,
    no en la cadena entera).
    """
    attempts = []
    current_output = failed_output

    pending_parts = _split_at_and_chain(failed_command)
    is_chain = len(pending_parts) > 1
    original_chain = list(pending_parts) if is_chain else None
    # `failed_command` siempre apunta a la parte concreta que falla en el
    # momento actual del bucle (al inicio, la primera parte de la cadena si
    # es cadena, o el comando entero si no lo es).
    if is_chain:
        failed_command = pending_parts[0]

    console.print()
    console.print(Panel(
        f"[bold {ORANGE}]Autopilot de troubleshooting[/]\n"
        f"[{WHITE}]El comando ha fallado. El agente intentará resolverlo "
        f"sin pedirte confirmación, hasta [bold]{TROUBLESHOOT_MAX_ATTEMPTS}[/] intentos.\n"
        f"Si quieres cortar el ciclo: [bold]Ctrl+C[/].[/]",
        border_style=ORANGE,
        box=ROUNDED,
        padding=(0, 1),
    ))

    if is_chain:
        chain_lines = "\n".join(
            f"  [{i+1}] {p}" for i, p in enumerate(original_chain)
        )
        console.print()
        console.print(Panel(
            f"[bold {PURPLE}]Cadena `&&` detectada[/]\n"
            f"[{WHITE}]Sub-comandos:[/]\n{chain_lines}\n\n"
            f"[dim]El retry ejecutará las partes por separado; el fix se "
            f"centrará en la parte que falla.[/]",
            border_style=PURPLE,
            box=ROUNDED,
            padding=(0, 1),
        ))

    for attempt in range(1, TROUBLESHOOT_MAX_ATTEMPTS + 1):
        console.print()
        console.print(f"[bold {CYAN}]── Intento {attempt}/{TROUBLESHOOT_MAX_ATTEMPTS} ──[/]")

        chain_block = ""
        if is_chain:
            pending_lines = "\n".join(
                f"    - {p}" for p in pending_parts
            ) or "    (ninguno · todos resueltos)"
            chain_block = (
                f"\nCONTEXTO de la cadena `&&` original:\n"
                f"  Cadena completa: {' && '.join(original_chain)}\n"
                f"  Sub-comando que falla AHORA: {failed_command}\n"
                f"  Sub-comandos pendientes (incluido el que falla):\n"
                f"{pending_lines}\n"
                f"  Nota: el retry ejecuta los pendientes UNO A UNO (no `&&`). "
                f"Centra el fix en el sub-comando que falla; los pendientes "
                f"posteriores se intentarán por separado tras el fix.\n"
            )

        fix_prompt = (
            f"AUTOPILOT — Resolución automática de problemas.\n\n"
            f"El comando `{failed_command}` ha fallado. Salida (última iteración):\n\n"
            f"{(current_output or '')[:4000]}\n"
            f"{chain_block}\n"
            f"Diagnostica y propón UN ÚNICO comando para avanzar. Restricciones:\n"
            f"- El fix debe ser LOCAL (no tocar el target).\n"
            f"- NO repitas el comando original con cambios mínimos sin saber por qué.\n"
            f"- Sólo el bloque COMANDO: con UNA línea. Sin texto explicativo.\n"
            f"- Intento {attempt}/{TROUBLESHOOT_MAX_ATTEMPTS}.\n\n"
            f"OPCIONES VÁLIDAS para el COMANDO:\n"
            f"a) **Info-gathering**: si el error parece de sintaxis o flag, "
            f"propón `<tool> --help` o `<tool> -h` para ver los flags reales "
            f"de TU versión. En la siguiente iteración corriges el original.\n"
            f"b) **Inspección de instalación**: `which <tool>`, `<tool> --version`, "
            f"`dpkg -l | grep <tool>` para confirmar versión y rutas.\n"
            f"c) **Búsqueda en el filesystem**: cuando el error indica que un "
            f"script/recurso 'did not match a category, filename, or directory' "
            f"(p.ej. NSE de nmap), o que falta un archivo, NAVEGA el filesystem "
            f"para descubrir el nombre real antes de adivinar. Ejemplos:\n"
            f"   - `ls /usr/share/nmap/scripts/ | grep -i ssh` (scripts NSE)\n"
            f"   - `ls /usr/share/nmap/scripts/ | grep -i <protocolo>`\n"
            f"   - `find /usr/share -maxdepth 3 -iname '*ssh*enum*'`\n"
            f"   - `locate <patrón>` (si `mlocate`/`plocate` está instalado)\n"
            f"   - `ls /usr/share/wordlists/`, `ls /usr/share/seclists/...`\n"
            f"   - `find / -name '<archivo>' -type f 2>&1 | head -40`\n"
            f"   La cwd del agente es ~/ai-agent-kali; navega también ahí si "
            f"buscas outputs propios (`ls ./scans/`).\n"
            f"d) **Fix concreto**: instalar paquete (`sudo apt install -y X`), "
            f"actualizar templates (`nuclei -ut`), reparar permisos (`chmod`), "
            f"crear directorio (`mkdir -p`), descargar wordlist (`wget`).\n"
            f"e) **META-acciones del agente** (sin shell, son directivas):\n"
            f"   - `COMANDO: agent:proxy off` — desactiva proxychains para el "
            f"siguiente reintento. Útil cuando una tool Go (assetfinder, "
            f"subfinder, findomain) ignora LD_PRELOAD o cuando el SOCKS5 "
            f"de Tor bloquea SNI/DNS hijack y la tool da timeout/sin resultados.\n"
            f"   - `COMANDO: agent:proxy on` — vuelve a activar proxychains.\n"
            f"   - `COMANDO: agent:tor restart` — reinicia el servicio tor "
            f"(si sospechas circuito Tor caído).\n\n"
            f"NO uses `COMANDO: noop` salvo que hayas agotado info-gathering "
            f"(incluida búsqueda en filesystem) Y comprobación de instalación "
            f"Y meta-acciones. Investigar es barato — tienes "
            f"{TROUBLESHOOT_MAX_ATTEMPTS - attempt + 1} intentos restantes."
        )

        try:
            answer = ask_model(fix_prompt)
        except KeyboardInterrupt:
            attempts.append({"attempt": attempt, "interrupted": True})
            console.print(f"[bold {RED}]⚠ Autopilot interrumpido por el usuario.[/]")
            break

        fix_cmd = extract_command(answer)
        if not fix_cmd or fix_cmd.strip().lower() in ("noop", ":", "true"):
            attempts.append({
                "attempt": attempt,
                "fix": None,
                "note": "modelo no propuso fix viable, fin del bucle",
            })
            break

        # ¿Es una meta-acción del agente? Si sí, manejarla aquí sin lanzar shell.
        meta = _handle_agent_meta_action(fix_cmd)
        is_meta = meta is not None
        if is_meta:
            console.print(f"[bold {ORANGE}]» Meta-acción:[/] {meta['log']}")
            fix_result = f"[Meta-acción aplicada · {meta['log']}]"
            fix_rc = 0
            if ACTIVE_TARGET:
                append_timeline_entry(f"[autopilot meta] {fix_cmd}", fix_result)
        else:
            # Ejecutar el fix como shell normal, sin confirmación
            try:
                fix_result = run_command(fix_cmd, auto=True)
            except KeyboardInterrupt:
                attempts.append({"attempt": attempt, "fix": fix_cmd, "interrupted": True})
                console.print(f"[bold {RED}]⚠ Autopilot interrumpido por el usuario.[/]")
                break
            fix_rc = LAST_COMMAND_RC
            if ACTIVE_TARGET:
                append_timeline_entry(f"[autopilot fix] {fix_cmd}", fix_result)

        # Reintentar el/los comando(s) original(es).
        # Si era una cadena `&&`, ejecutamos cada parte pendiente por
        # separado; las partes que ya pasaron no se vuelven a ejecutar.
        # Al primer fallo, esa parte se convierte en el nuevo failed_command
        # y el bucle continúa centrado en ella.
        retry_outputs = []
        retry_rc = 0
        first_failing_part = None

        try:
            if is_chain and pending_parts:
                console.print()
                console.print(
                    f"[dim]› Reintentando {len(pending_parts)} sub-comando(s) "
                    f"pendiente(s) por separado…[/]"
                )
                survivors = []
                for idx, part in enumerate(pending_parts):
                    console.print(
                        f"[dim]›  [{idx+1}/{len(pending_parts)}] {part[:80]}[/]"
                    )
                    sub_result = run_command(part, auto=True)
                    sub_rc = LAST_COMMAND_RC
                    retry_outputs.append(
                        f"[sub-comando rc={sub_rc}] {part}\n{sub_result}"
                    )
                    if ACTIVE_TARGET:
                        append_timeline_entry(
                            f"[autopilot retry · sub-comando] {part}", sub_result
                        )
                    if sub_rc != 0:
                        retry_rc = sub_rc
                        first_failing_part = part
                        # El resto (incluido este) queda pendiente para la
                        # próxima iteración del bucle.
                        survivors = pending_parts[idx:]
                        break
                else:
                    survivors = []
                pending_parts = survivors
                retry_result = "\n\n".join(retry_outputs)
            else:
                console.print()
                console.print(f"[dim]› Reintentando comando original…[/]")
                retry_result = run_command(failed_command, auto=True)
                retry_rc = LAST_COMMAND_RC
                if ACTIVE_TARGET:
                    append_timeline_entry(
                        f"[autopilot retry] {failed_command}", retry_result
                    )
        except KeyboardInterrupt:
            attempts.append({
                "attempt": attempt, "fix": fix_cmd, "fix_rc": fix_rc,
                "interrupted": True,
            })
            console.print(f"[bold {RED}]⚠ Autopilot interrumpido por el usuario.[/]")
            break

        attempt_record = {
            "attempt": attempt,
            "fix": fix_cmd, "fix_rc": fix_rc, "fix_output": fix_result,
            "retry_rc": retry_rc, "retry_output": retry_result,
        }
        if is_meta:
            attempt_record["meta"] = meta
        if is_chain:
            attempt_record["chain_pending_after"] = list(pending_parts)
            if first_failing_part:
                attempt_record["chain_failing_part"] = first_failing_part
        attempts.append(attempt_record)

        if retry_rc == 0 and not pending_parts:
            return {
                "resolved": True,
                "attempts": attempts,
                "final_output": retry_result,
            }
        current_output = retry_result
        # Si era cadena y una parte falló, esa parte pasa a ser el
        # failed_command para la siguiente iteración (el fix se centra en ella).
        if is_chain and first_failing_part:
            failed_command = first_failing_part

    return {
        "resolved": False,
        "attempts": attempts,
        "final_output": current_output,
    }


def _print_troubleshoot_summary(result):
    """Panel resumen del flujo de autopilot."""
    if result["resolved"]:
        title = f"[bold {GREEN}]Autopilot — resuelto[/]"
        border = GREEN
        mark = f"[bold {GREEN}]✓[/]"
    else:
        title = f"[bold {RED}]Autopilot — sin resolver[/]"
        border = RED
        mark = f"[bold {RED}]✗[/]"

    rows = []
    for a in result["attempts"]:
        n = a["attempt"]
        if a.get("interrupted"):
            rows.append(f"  [{n}] [bold {RED}]interrumpido por el usuario[/]")
            continue
        if not a.get("fix"):
            rows.append(f"  [{n}] [dim]{a.get('note', 'sin fix')}[/]")
            continue
        rc_retry = a.get("retry_rc", "?")
        if a.get("meta"):
            meta = a["meta"]
            rows.append(
                f"  [{n}] [bold {PURPLE}]meta[/]: {meta.get('log', '?')}\n"
                f"      └─ reintento rc={rc_retry}"
            )
        else:
            rc_fix = a.get("fix_rc", "?")
            rows.append(
                f"  [{n}] fix: [cyan]{a['fix'][:80]}[/]\n"
                f"      └─ fix rc={rc_fix} · reintento rc={rc_retry}"
            )

    body = (
        f"{mark} {len(result['attempts'])}/"
        f"{TROUBLESHOOT_MAX_ATTEMPTS} intentos\n\n"
        + "\n".join(rows) if rows else f"{mark} sin intentos"
    )

    console.print()
    console.print(Panel(
        body,
        title=title,
        border_style=border,
        box=ROUNDED,
        padding=(1, 2),
    ))


def run_command(command, auto=False):
    """Ejecuta `command`. Si `auto=True` se salta TODAS las confirmaciones
    (modo autopilot de troubleshooting). En condiciones normales mantiene la
    lógica de clasificación y AUTO_EXECUTE.

    Antes de cualquier procesamiento:
    1) Detecta meta-acciones `agent:proxy …` / `agent:tor …` y las aplica
       sin lanzar shell.
    2) Detecta el wrapper `agent:noproxy <comando>` y ejecuta el comando
       interno sin envolverlo en proxychains (single-shot bypass).
    3) Elimina patrones de supresión de stderr (2>/dev/null, &>/dev/null,
       2>&1 >/dev/null) para preservar el diagnóstico.
    """
    global LAST_COMMAND_RC

    # 1) META-ACCIONES — sin shell, devolución inmediata
    meta = _handle_agent_meta_action(command)
    if meta:
        LAST_COMMAND_RC = 0
        _q_print()
        _q_print(Panel(
            f"[bold {PURPLE}]» Meta-acción del agente[/]\n\n"
            f"[{WHITE}]{command}[/]\n\n"
            f"[dim]{meta.get('log', '')}[/]",
            border_style=PURPLE,
            box=ROUNDED,
        ))
        return f"[Meta-acción aplicada · {meta.get('log', '?')}]"

    # 2) BYPASS DE PROXY PARA UN COMANDO (single-shot)
    no_proxy_single = False
    if command.lower().startswith("agent:noproxy "):
        inner = command[len("agent:noproxy "):].strip()
        if inner:
            _q_print(
                f"[dim]› [bold {PURPLE}]agent:noproxy[/] · este comando "
                f"se ejecuta sin proxychains (single-shot)[/]"
            )
            command = inner
            no_proxy_single = True

    # 3) STRIP DE SUPPRESSION DE STDERR
    command, was_stripped = _strip_stderr_suppression(command)
    if was_stripped:
        _q_print(
            f"[dim]› supresión de stderr eliminada para preservar diagnóstico "
            f"(2>/dev/null / &>/dev/null / etc.)[/]"
        )

    category = classify_command(command)

    category_meta = {
        "safe":        ("Seguro / lectura",        GREEN),
        "intrusive":   ("Intrusivo",               "#fbbf24"),  # amarillo ámbar
        "destructive": ("Destructivo / Alto riesgo", RED),
    }
    label, color = category_meta[category]

    # ANTI-DUPLICACIÓN: si hay target activo y el comando es una herramienta
    # de NETWORK_TOOLS contra ese target, comprobamos `_runs.md`. Si ya hay
    # un run con la misma huella (tool + tokens + flags clave), avisamos.
    # En modo NO-autopilot: degradamos auto-execute (pedimos confirmación).
    # En autopilot: sólo loguamos (el autopilot decide reintentar o no).
    duplicate_runs = []
    saturated_tool = None
    saturated_count = 0
    if ACTIVE_TARGET:
        duplicate_runs = find_duplicate_runs(command, ACTIVE_TARGET)
        is_sat, sat_tool, sat_count = _tool_is_saturated(command, ACTIVE_TARGET)
        if is_sat:
            saturated_tool = sat_tool
            saturated_count = sat_count
    if duplicate_runs:
        prev = duplicate_runs[-1]  # el más reciente
        files_str = (
            ", ".join(prev["output_files"])
            if prev["output_files"] else "(sin archivos de output detectados)"
        )
        _q_print()
        _q_print(Panel(
            f"[bold {RED}]⚠ ESCANEO YA REALIZADO[/]\n\n"
            f"[{WHITE}]Mismo tool + target + flags clave detectados en "
            f"`targets/{ACTIVE_TARGET}/_runs.md`.[/]\n\n"
            f"[bold {WHITE}]Run anterior:[/] [{prev['ts']}] · "
            f"rc={prev['rc']}\n"
            f"[bold {WHITE}]Comando:[/] [{CYAN}]{prev['command']}[/]\n"
            f"[bold {WHITE}]Archivos:[/] {files_str}\n\n"
            f"[dim]Si los resultados ya están en disco, lee el archivo en "
            f"vez de re-escanear. Si quieres forzar el rescan (cambió la "
            f"infra, nueva ventana de tiempo, etc.), confirma manualmente.[/]",
            border_style=RED,
            box=ROUNDED,
            padding=(1, 2),
        ))
    elif saturated_tool:
        # Tool saturada: ya hay ≥3 runs con esta herramienta contra el target
        # (aunque los flags difieran). Aviso fuerte para que el operador
        # corte el bucle antes de seguir.
        _q_print()
        _q_print(Panel(
            f"[bold {MAGENTA}]⚠ HERRAMIENTA SATURADA[/]\n\n"
            f"[{WHITE}]`{saturated_tool}` ya tiene "
            f"[bold]{saturated_count}[/] runs en "
            f"`targets/{ACTIVE_TARGET}/_runs.md` (umbral: "
            f"{_TOOL_SATURATION_THRESHOLD}). El modelo propone otra "
            f"variante, pero la regla anti-loop dice que el siguiente "
            f"paso debería ser de OTRA categoría del tools_master.[/]\n\n"
            f"[dim]Si crees que esta variante aporta info nueva (UDP, NSE "
            f"category nueva, host nuevo), confírmalo manualmente. Si no, "
            f"di [bold]N[/] y pide al modelo que pase a la siguiente "
            f"categoría (fingerprinting web, CMS scanner, SMB enum, etc.).[/]",
            border_style=MAGENTA,
            box=ROUNDED,
            padding=(1, 2),
        ))

    # Si somos root, quitar el prefijo `sudo` del comando (en VPS minimalistas
    # `sudo` ni está instalado; siempre que somos root es redundante).
    if _running_as_root():
        command = _strip_sudo_prefix(command)

    # Envolver con proxy si aplica (a menos que sea single-shot bypass).
    if no_proxy_single:
        effective_command, proxy_used = command, None
    else:
        effective_command, proxy_used = maybe_wrap_with_proxy(command)
    proxy_note = ""
    if proxy_used:
        if proxy_used in ("proxychains4", "proxychains") and not _check_tor_running():
            proxy_note = (
                f"\n[bold {RED}]⚠ {proxy_used} configurado pero no se detecta "
                f"Tor escuchando en 127.0.0.1:9050.[/] "
                f"Arranca con [bold]sudo systemctl start tor[/] o el comando "
                f"fallará al conectar."
            )
        else:
            proxy_note = f"\n[dim]→ enrutado vía [bold]{proxy_used}[/] (Tor)[/]"

    auto_tag = f"\n[bold {ORANGE}]» AUTOPILOT — sin confirmación[/]" if auto else ""

    _q_print()
    _q_print(Panel(
        f"[bold {ORANGE}]Comando propuesto[/bold {ORANGE}] "
        f"[bold {color}]· {label}[/]\n\n[{WHITE}]{command}[/]"
        f"{proxy_note}{auto_tag}",
        border_style=color,
        box=ROUNDED
    ))

    # Degradar auto-execute si detectamos duplicado o saturación (excepto en
    # autopilot, donde el bucle de troubleshooting puede legítimamente reintentar).
    duplicate_block_auto = (bool(duplicate_runs) or bool(saturated_tool)) and not auto

    if (auto or (AUTO_EXECUTE and category == "safe")) and not duplicate_block_auto:
        msg = "auto-ejecutando (autopilot)" if auto else f"Auto-ejecutando (categoría: seguro)"
        _q_print(f"[bold {GREEN}]» {msg}…[/]")
    else:
        if duplicate_runs:
            prompt_msg = (
                "⚠ El escaneo ya está hecho según _runs.md. "
                "¿Re-ejecutar de todos modos? [s/N]: "
            )
        elif saturated_tool:
            prompt_msg = (
                f"⚠ `{saturated_tool}` saturada ({saturated_count} runs). "
                f"¿Ejecutar de todos modos? [s/N]: "
            )
        elif category == "destructive":
            prompt_msg = f"⚠ Comando DESTRUCTIVO. ¿Estás seguro? [s/N]: "
        elif category == "intrusive":
            prompt_msg = "Comando intrusivo. ¿Ejecutar? [s/N]: "
        else:
            prompt_msg = "¿Ejecutar este comando? [s/N]: "
        confirm = input(prompt_msg).strip().lower()
        if confirm != "s":
            LAST_COMMAND_RC = -1  # cancelado
            return "Comando cancelado por el usuario."

    # HOOK before_command — puede abortar la ejecución vía HookAbort.
    try:
        run_hook("before_command", _build_hook_ctx(
            command=command,
            category=category,
            auto=bool(auto),
        ))
    except HookAbort as e:
        LAST_COMMAND_RC = -1
        _q_print(
            f"[bold {RED}]› hook before_command abortó la ejecución: {e}[/]"
        )
        return f"Comando cancelado por hook before_command: {e}"

    final_stdout, final_stderr, final_rc = "", "", 0
    final_output = ""

    def _exec_with_spinner(eff_cmd, timeout_s):
        """Lanza _execute_shell con spinner descriptivo si NO hay streaming.
        En threads de subagente, salta el spinner y la cabecera dim para no
        ensuciar la salida del operador principal.
        Devuelve (stdout, stderr, rc)."""
        in_sub = _is_subagent_thread()
        if STREAM_COMMAND_OUTPUT and not in_sub:
            # Modo streaming (sólo en main): cabecera dim + _execute_shell
            # pinta las líneas en directo.
            _q_print(f"[dim]› {_describe_command(command)}[/]")
            return _execute_shell(eff_cmd, timeout=timeout_s, stream=True)
        # Batch en main → spinner animado. Subagente → sin spinner, captura
        # directa para devolver el output al loop autónomo.
        with _q_spinner(_describe_command(command)):
            return _execute_shell(eff_cmd, timeout=timeout_s, stream=False)

    # Calcular timeout dinámico: si el comando usa un wordlist medio/grande,
    # subimos automáticamente a COMMAND_TIMEOUT_S_LARGE (30 min por defecto).
    timeout_s, timeout_reason = _compute_timeout_for_command(command)
    if timeout_reason:
        _q_print(f"[dim]› {timeout_reason}[/]")

    # Si el comando usa sudo, asegurarnos de tener credenciales cacheadas.
    # `_execute_shell` ejecuta con stdin=DEVNULL (anti-bloqueo), lo que
    # impediría a sudo pedir password. Aquí pedimos la password vía
    # `sudo -v` ANTES (interactivo), y sudo cachea durante ~15 min.
    if _command_uses_sudo(command):
        if not _ensure_sudo_credentials():
            LAST_COMMAND_RC = -1
            return (
                "Comando abortado: sudo necesitaba contraseña y no se "
                "pudo autenticar (cancelado por el operador o credenciales "
                "incorrectas)."
            )

    try:
        t0 = time.time()
        stdout, stderr, rc = _exec_with_spinner(effective_command, timeout_s)
        duration = round(time.time() - t0, 3)
        LAST_COMMAND_RC = rc
        final_stdout, final_stderr, final_rc = stdout, stderr, rc

        # ¿Falló por herramienta faltante? Auto-install + reintento (1 vez).
        missing = _detect_missing_tool(stderr, rc) if AUTO_INSTALL_MISSING_TOOLS else None
        if missing:
            chain = [
                f"[Comando original devolvió exit {rc} — herramienta '{missing}' no instalada]",
            ]
            install = _try_install_tool(missing)
            chain.append(f"[Auto-install: {install['log']}]")

            if install["ok"]:
                # Reintento del comando original (también vía proxy si aplica)
                try:
                    t1 = time.time()
                    stdout2, stderr2, rc2 = _exec_with_spinner(
                        effective_command, timeout_s
                    )
                    duration = round(time.time() - t0 + (time.time() - t1), 3)
                    LAST_COMMAND_RC = rc2
                    final_stdout, final_stderr, final_rc = stdout2, stderr2, rc2
                    chain.append(f"[Reintento tras instalar '{missing}' · exit {rc2}]")
                    chain.append(_format_command_output(stdout2, stderr2))
                except subprocess.TimeoutExpired:
                    LAST_COMMAND_RC = 124  # timeout convencional
                    final_rc = 124
                    chain.append("Error: el reintento superó el tiempo máximo.")
                except Exception as e:
                    LAST_COMMAND_RC = 1
                    final_rc = 1
                    chain.append(f"Error en reintento: {e}")
            else:
                LAST_COMMAND_RC = rc
                final_rc = rc
                chain.append(
                    f"⚠ No se pudo instalar '{missing}' automáticamente. "
                    f"Prueba manual: `sudo apt-get install -y {missing}`"
                )
                # Conservamos también la salida original para que el modelo la vea
                chain.append(_format_command_output(stdout, stderr))

            final_output = _enrich_output_with_diagnostics(
                command, "\n\n".join(chain)
            )
        else:
            final_output = _enrich_output_with_diagnostics(
                command, _format_command_output(stdout, stderr)
            )

    except subprocess.TimeoutExpired as e:
        LAST_COMMAND_RC = 124
        final_rc = 124
        duration = float(getattr(e, "timeout", timeout_s) or timeout_s)
        # Preservar el output capturado HASTA el timeout. Sin esto, los
        # findings parciales de herramientas largas (gobuster, ffuf,
        # nuclei, masscan…) se perderían y el modelo creería que la
        # herramienta no encontró nada.
        captured_out = e.stdout if e.stdout is not None else ""
        captured_err = e.stderr if e.stderr is not None else ""
        if isinstance(captured_out, bytes):
            captured_out = captured_out.decode("utf-8", errors="replace")
        if isinstance(captured_err, bytes):
            captured_err = captured_err.decode("utf-8", errors="replace")
        final_stdout = captured_out.rstrip()
        final_stderr = captured_err.rstrip()
        timeout_banner = (
            f"[Comando interrumpido por timeout tras {duration:.0f}s — "
            f"output parcial preservado. Si la herramienta seguía "
            f"encontrando datos, sube el timeout o pasa otro wordlist más corto.]"
        )
        partial = _format_command_output(final_stdout, final_stderr)
        final_output = _enrich_output_with_diagnostics(
            command,
            f"{timeout_banner}\n\n{partial}" if partial.strip() else timeout_banner,
        )
    except Exception as e:
        LAST_COMMAND_RC = 1
        final_rc = 1
        duration = locals().get("duration", 0.0)
        final_output = f"Error ejecutando comando: {e}"

    # HOOKS posteriores — siempre se invocan (éxito o fallo), nunca rompen
    # el flujo aunque tiren excepción (run_hook las captura salvo HookAbort,
    # que aquí ya no aplica).
    output_files = _detect_output_files(command)
    after_ctx = _build_hook_ctx(
        command=command,
        rc=final_rc,
        duration_s=duration,
        stdout_len=len(final_stdout or ""),
        stderr_len=len(final_stderr or ""),
        output_files=output_files,
        auto=bool(auto),
    )
    run_hook("after_command", after_ctx)

    if final_rc not in (0, -1):
        run_hook("on_error", _build_hook_ctx(
            command=command,
            rc=final_rc,
            stderr=final_stderr,
            output_files=output_files,
            auto=bool(auto),
        ))

    return final_output


# ============================================================
# COMANDOS INTERNOS
# ============================================================

def print_help():
    help_text = f"""
[bold {ORANGE}]Comandos internos[/bold {ORANGE}]
[dim](todos aceptan prefijo opcional '/' — ej. /skills, /resume, /use recon)[/dim]

[bold {WHITE}]help / ayuda[/bold {WHITE}]            Muestra esta ayuda.
[bold {WHITE}]comandos / commands[/bold {WHITE}]     Tabla compacta con todos los comandos.
[bold {WHITE}]refresh / refrescar[/bold {WHITE}]     Redibuja el splash.
[bold {WHITE}]clear / limpiar[/bold {WHITE}]         Igual que refresh.
[bold {WHITE}]models / modelos[/bold {WHITE}]        Lista los modelos expuestos por LM Studio.
[bold {WHITE}]tools / herramientas[/bold {WHITE}]    Herramientas instaladas y faltantes.
[bold {WHITE}]proxy [on/off/status][/bold {WHITE}]   Estado y control del enrutado por Tor/proxychains.
[bold {WHITE}]salir / exit / quit[/bold {WHITE}]     Cierra el agente.

[bold {ORANGE}]Skills[/bold {ORANGE}]

[bold {WHITE}]skills / habilidades[/bold {WHITE}]    Lista skills disponibles (●=activa, ○=disponible, ✗=falta skill.md).
[bold {WHITE}]tools_master / master[/bold {WHITE}]   Lista las listas exhaustivas de herramientas en tools_master/.
[bold {WHITE}]use / usar <skill>[/bold {WHITE}]      Activa una skill (inyecta su contenido + su lista master si existe).
[bold {WHITE}]unuse / quitar <skill>[/bold {WHITE}]  Desactiva una skill activa.

[bold {ORANGE}]Targets (contexto del objetivo)[/bold {ORANGE}]

[bold {WHITE}]target / objetivo[/bold {WHITE}]            Lista los targets disponibles en targets/.
[bold {WHITE}]target <nombre>[/bold {WHITE}]              Carga targets/<nombre>/ en el contexto (lee todos los archivos de texto).
[bold {WHITE}]target reload[/bold {WHITE}]                Recarga el target activo (tras añadir/cambiar archivos).
[bold {WHITE}]target unload[/bold {WHITE}]                Quita el target del contexto.
[bold {WHITE}]report / informe[/bold {WHITE}]             Genera informe técnico del target activo en reports/informe-<target>-<ts>.md.

[bold {ORANGE}]Sesiones[/bold {ORANGE}]

[bold {WHITE}]sessions / sesiones[/bold {WHITE}]     Lista sesiones guardadas en memory/sessions/.
[bold {WHITE}]resume / retomar[/bold {WHITE}]        Retoma la última sesión guardada.
[bold {WHITE}]resume / retomar <id>[/bold {WHITE}]   Retoma una sesión concreta por su ID.
[bold {WHITE}]new / nueva[/bold {WHITE}]             Cierra el contexto actual y empieza una sesión limpia.

[bold {ORANGE}]Lecciones (memoria viva)[/bold {ORANGE}]

[bold {WHITE}]aprende / learn / recuerda <regla>[/bold {WHITE}]  Guarda una regla en memory/lessons/ y la inyecta en el system prompt.
[bold {WHITE}]lecciones / lessons[/bold {WHITE}]                Lista las lecciones guardadas.
[bold {WHITE}]olvida / forget <fragmento>[/bold {WHITE}]         Elimina la lección cuyo nombre contiene el fragmento.

El modelo también puede guardar lecciones por su cuenta cuando te corrijas
o le des una regla, mediante `agent:learn <texto>`.

[bold {ORANGE}]Contexto / rendimiento[/bold {ORANGE}]

[bold {WHITE}]compact / compactar[/bold {WHITE}]                Trunca resultados de comandos antiguos del history (mantiene los últimos {COMPACT_KEEP_LAST_TURNS} turnos completos). Acelera el prefill del modelo en sesiones largas.
[bold {WHITE}]timeout [<N>|large <N>|threshold <N>|default|status][/bold {WHITE}]   Configura el timeout de ejecución de comandos. Sin argumentos muestra estado. `timeout <N>` cambia el base (300s default). `timeout large <N>` cambia el extendido que se aplica automáticamente cuando el comando usa un wordlist con ≥{WORDLIST_MEDIUM_THRESHOLD_LINES:,} líneas (default 1800s = 30 min). `timeout threshold <N>` cambia el umbral de líneas. `timeout default` restaura todo a los valores de fábrica.

La compactación también se aplica automáticamente al enviar al modelo cuando
el prompt estimado supera el {int(COMPACT_TRIGGER_PCT*100)}% del context window; en ese caso `history` en
memoria queda intacto y sólo se compacta la copia enviada.

[bold {ORANGE}]Uso recomendado[/bold {ORANGE}]

Define primero el alcance autorizado. Ejemplo:

  El alcance autorizado para esta sesión es 192.168.1.0/24 y 192.168.1.20. Guárdalo
  y no me vuelvas a preguntar por autorización mientras las tareas estén dentro de
  ese alcance.

Después puedes activar la skill que necesites y pedir tareas:

  use recon
  Haz reconocimiento inicial no intrusivo dentro del alcance autorizado.
"""
    console.print(Panel(help_text, border_style=ORANGE, box=ROUNDED))


def print_commands():
    """Tabla compacta con todos los comandos disponibles, agrupados por categoría."""

    rows = [
        # (categoria, comando, descripción)
        ("General",  "help / ayuda",            "Muestra la ayuda extendida con ejemplos de uso"),
        ("General",  "comandos / commands",     "Esta tabla con todos los comandos disponibles"),
        ("General",  "refresh / refrescar",     "Limpia pantalla y redibuja el splash"),
        ("General",  "clear / limpiar",         "Igual que refresh"),
        ("General",  "models / modelos",        "Lista los modelos expuestos por LM Studio"),
        ("General",  "tools / herramientas",    "Tabla de herramientas instaladas vs faltantes"),
        ("General",  "proxy [on/off/status]",   "Estado y control del enrutado por Tor/proxychains"),
        ("General",  "sudo [status|refresh|set|clear]", "Gestiona la password sudo. `sudo refresh` refresca el caché (15 min). `sudo set` almacena la password en memoria (no a disco) para que subagentes/autopilot la usen sin pedirla. `sudo clear` la borra."),
        ("General",  "timeout [<N>|large <N>|threshold <N>|default|status]", "Configura el timeout de ejecución de comandos (auto-sube a 30 min con wordlists grandes)"),
        ("General",  "compact / compactar",     "Compacta resultados antiguos del history (acelera prefill)"),
        ("General",  "salir / exit / quit",     "Cierra el agente (auto-guarda la sesión antes)"),

        ("Skills",   "skills / habilidades",    "Lista skills disponibles · ●=activa ○=disponible ✗=falta skill.md"),
        ("Skills",   "tools_master / master",   "Lista las listas exhaustivas de herramientas (tools_master/)"),
        ("Skills",   "use / usar <skill>",      "Activa skill + carga tools_master/<skill>.md si existe"),
        ("Skills",   "unuse / quitar <skill>",  "Desactiva una skill activa"),

        ("Subagentes", "subagent new <nombre> <skill> <tarea>", f"Lanza un mini-agente autónomo (max {MAX_CONCURRENT_SUBAGENTS} simultáneos)"),
        ("Subagentes", "subagent list",                         "Tabla con todos los subagentes (activos + terminados)"),
        ("Subagentes", "subagent show <nombre>",                "Muestra el panel-resumen de un subagente"),
        ("Subagentes", "subagent kill <nombre>",                "Detiene un subagente en ejecución"),

        ("Orquestación", "goal <descripción del objetivo>",     f"Lanza orquestador goal-driven (max {GOAL_MAX_PHASES} fases, hasta {MAX_CONCURRENT_SUBAGENTS} subagentes/fase). El LLM planifica, ejecuta, evalúa y replanifica hasta cumplir o bloquear."),
        ("Orquestación", "goal status",                         "Muestra el estado del goal activo (fase, subagentes lanzados, motivo)"),
        ("Orquestación", "goal show",                           "Panel-resumen completo del goal en curso o último terminado"),
        ("Orquestación", "goal list",                           "Lista todos los goals persistidos en disco (incl. terminados y huérfanos)"),
        ("Orquestación", "goal resume [<id>]",                  "Reanuda un goal interrumpido por crash/cierre del agente (continúa desde la última fase guardada)"),
        ("Orquestación", "goal discard <id>",                   "Borra el estado persistido de un goal (el log queda)"),
        ("Orquestación", "goal kill",                           "Detiene el goal y los subagentes de su fase actual"),

        ("Targets",  "target / objetivo",            "Lista los targets disponibles · ●=activo"),
        ("Targets",  "target <nombre>",              "Carga targets/<nombre>/ en el contexto"),
        ("Targets",  "target reload / recargar",     "Recarga el target activo (tras tocar archivos)"),
        ("Targets",  "target unload / descargar",    "Quita el target del contexto"),
        ("Targets",  "report / informe [extras]",    "Genera informe técnico → reports/informe-<target>-<ts>.md"),

        ("Sesiones", "sessions / sesiones",     "Lista las últimas sesiones guardadas"),
        ("Sesiones", "resume / retomar",        "Retoma la última sesión guardada"),
        ("Sesiones", "resume / retomar <id>",   "Retoma una sesión concreta por su ID"),
        ("Sesiones", "new / nueva",             "Cierra contexto actual y empieza una sesión limpia"),

        ("Lecciones", "aprende / learn / recuerda <regla>",  "Guarda regla persistente en memory/lessons/ (se inyecta en TODAS las sesiones)"),
        ("Lecciones", "lecciones / lessons",                 "Lista las lecciones guardadas"),
        ("Lecciones", "olvida / forget <fragmento>",         "Borra la lección cuyo nombre contiene el fragmento"),
    ]

    table = Table(
        title=f"[bold {CYAN}]Comandos disponibles[/]",
        border_style=CYAN,
        box=ROUNDED,
        show_lines=False,
        title_justify="left",
    )
    table.add_column("Categoría", style=PURPLE, no_wrap=True)
    table.add_column("Comando", style=f"bold {CYAN}", no_wrap=True)
    table.add_column("Descripción", style=WHITE)

    last_cat = None
    for cat, cmd, desc in rows:
        cat_cell = cat if cat != last_cat else ""
        table.add_row(cat_cell, cmd, desc)
        last_cat = cat

    console.print(table)
    console.print(
        f"[dim]Cualquier otro texto se envía al modelo. "
        f"Los comandos también funcionan con prefijo '/' (ej: /skills, /resume, /use recon).[/]"
    )


def print_models():
    models = get_lmstudio_models()

    table = Table(title="Modelos expuestos por LM Studio", border_style=ORANGE)
    table.add_column("Modelo", style=WHITE)

    for model in models:
        table.add_row(model)

    console.print(table)


def _print_proxy_status():
    """Estado actual del enrutado por proxy (Tor)."""
    binary = _proxy_binary()
    tor = _check_tor_running()

    table = Table.grid(padding=(0, 2))
    table.add_column(style=PURPLE, no_wrap=True)
    table.add_column(style=WHITE)

    table.add_row("Modo", PROXY_MODE)
    if binary:
        table.add_row("Binario", f"[bold {GREEN}]{binary}[/]")
    else:
        table.add_row("Binario", f"[{RED}]no encontrado en PATH[/]")
    table.add_row(
        "Tor 127.0.0.1:9050",
        f"[bold {GREEN}]escuchando[/]" if tor else f"[{RED}]NO escuchando[/]",
    )
    table.add_row(
        "Comandos envueltos",
        f"{len(NETWORK_TOOLS)} herramientas de red conocidas"
    )

    hint_lines = []
    if PROXY_MODE != "off" and not tor:
        hint_lines.append(
            f"[{RED}]⚠ Tor no responde. Arranca con:[/] [bold]sudo systemctl start tor[/]"
        )
    if PROXY_MODE != "off" and not binary:
        hint_lines.append(
            f"[{RED}]⚠ Instala con:[/] [bold]sudo apt install proxychains4 tor[/]"
        )
    hint = "\n".join(hint_lines) if hint_lines else ""

    console.print(
        Panel(
            table if not hint else Group(table, Text(""), Text.from_markup(hint)),
            title=f"[bold {ORANGE}]Estado del proxy[/]",
            border_style=ORANGE,
            box=ROUNDED,
            padding=(0, 1),
        )
    )


def print_tools():
    """Tabla categorizada de herramientas. ●=instalada · ○=faltante.
    El catálogo completo está en `TOOL_CATALOG` (módulo)."""
    # Comprobar PATH una sola vez por herramienta única
    seen = set()
    for _cat, names in TOOL_CATALOG:
        for n in names:
            seen.add(n)
    presence = {n: bool(shutil.which(n)) for n in seen}

    total = len(seen)
    n_installed = sum(1 for v in presence.values() if v)

    table = Table(
        title=(
            f"Herramientas conocidas por categoría · "
            f"{n_installed}/{total} instaladas"
        ),
        border_style=ORANGE, box=ROUNDED,
        show_lines=False, title_justify="left",
    )
    table.add_column("Categoría", style=PURPLE, no_wrap=True)
    table.add_column("Instaladas", style=GREEN)
    table.add_column("Faltantes", style=GRAY)

    for cat, names in TOOL_CATALOG:
        inst = [n for n in names if presence.get(n)]
        miss = [n for n in names if not presence.get(n)]
        inst_str = "  ".join(f"●  {n}" for n in inst) if inst else "[dim](ninguna)[/]"
        miss_str = "  ".join(f"○  {n}" for n in miss) if miss else "[dim]—[/]"
        table.add_row(cat, inst_str, miss_str)

    console.print(table)
    console.print(
        f"[dim]Las faltantes se pueden auto-instalar cuando el modelo "
        f"intente usarlas (apt-get install). Para más control, "
        f"ejecuta directamente: [bold]sudo apt install <tool>[/].[/]"
    )

    # Compatibilidad con código antiguo que llamaba a print_tools y luego
    # quería las listas planas — devolvemos None (la API pública es
    # detect_installed_tools()).


def _print_tools_master_menu():
    """Muestra las listas exhaustivas disponibles en tools_master/."""
    if not os.path.isdir(TOOLS_MASTER_DIR):
        console.print(f"[{CYAN_DARK}]No existe {TOOLS_MASTER_DIR}/[/]")
        return

    entries = []
    for fname in sorted(os.listdir(TOOLS_MASTER_DIR)):
        if not fname.endswith(".md") or fname == "README.md":
            continue
        skill_name = fname[:-3]
        path = os.path.join(TOOLS_MASTER_DIR, fname)
        size = os.path.getsize(path)
        # Contar líneas y filas de tabla para una idea aproximada de cobertura
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().split("\n")
        except Exception:
            lines = []
        tool_rows = sum(
            1 for ln in lines
            if ln.strip().startswith("|") and "**" in ln and "---" not in ln
        )
        skill_md_exists = os.path.isfile(os.path.join(SKILLS_DIR, skill_name, "skill.md"))
        entries.append((skill_name, size, tool_rows, skill_md_exists))

    if not entries:
        console.print(
            f"[{CYAN_DARK}]No hay listas en {TOOLS_MASTER_DIR}/[/]\n"
            f"[dim]Crea una con el nombre exacto de la skill, ej:[/]\n"
            f"  [bold]cp mi_lista_exploit.md {TOOLS_MASTER_DIR}/exploitation.md[/]"
        )
        return

    table = Table(title="Tools master (listas exhaustivas por fase)", border_style=CYAN)
    table.add_column("Skill asociada", style=CYAN, no_wrap=True)
    table.add_column("Herramientas (~)", justify="right", style=WHITE)
    table.add_column("Tamaño", justify="right", style=WHITE)
    table.add_column("Skill", no_wrap=True)
    table.add_column("Estado", no_wrap=True)

    for name, size, n_tools, has_skill in entries:
        active = f"[bold {GREEN}]● activa[/]" if name in ACTIVE_SKILLS else "○ disponible"
        skill_cell = "[bold green]✓[/]" if has_skill else f"[{RED}]falta skill.md[/]"
        table.add_row(name, str(n_tools), _human_size(size), skill_cell, active)

    console.print(table)
    console.print(
        f"[dim]Se cargan automáticamente al hacer [bold]use <skill>[/] si "
        f"existe `tools_master/<skill>.md`.[/]"
    )


def print_skills_menu():
    skills = list_available_skills()
    if not skills:
        console.print(f"[{RED}]No hay skills disponibles en {SKILLS_DIR}[/]")
        return

    table = Table(title="Skills disponibles", border_style=CYAN)
    table.add_column("", width=3)
    table.add_column("Nombre", style=CYAN, no_wrap=True)
    table.add_column("Tools master", style=PURPLE, no_wrap=True)
    table.add_column("Descripción", style=WHITE)

    for name, desc, has_md in skills:
        if name in ACTIVE_SKILLS:
            marker = f"[bold {GREEN}]●[/]"
        elif not has_md:
            marker = f"[{RED}]✗[/]"
        else:
            marker = "○"

        master_path = os.path.join(TOOLS_MASTER_DIR, f"{name}.md")
        if os.path.isfile(master_path):
            size = os.path.getsize(master_path)
            master_cell = f"[bold {PURPLE}]✓[/] {_human_size(size)}"
        else:
            master_cell = "[dim]—[/]"

        table.add_row(marker, name, master_cell, desc)

    console.print(table)
    console.print(
        f"[dim]Activar: [bold]use <skill>[/]  ·  Desactivar: [bold]unuse <skill>[/]  ·  "
        f"●=activa  ○=disponible  ✗=falta skill.md  ·  "
        f"Tools master = lista exhaustiva cargada con la skill (tools_master/<skill>.md)[/]"
    )


def _human_size(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def print_targets_menu():
    targets = list_available_targets()
    if not targets:
        console.print(
            f"[{CYAN_DARK}]No hay targets en {TARGETS_DIR}/[/]\n"
            f"[dim]Crea una carpeta por objetivo y mete archivos de texto:[/]\n"
            f"  [bold]mkdir -p {TARGETS_DIR}/empresa1[/]\n"
            f"  [bold]echo 'Alcance: 192.168.1.0/24' > {TARGETS_DIR}/empresa1/scope.md[/]"
        )
        return

    table = Table(title="Targets disponibles", border_style=CYAN)
    table.add_column("", width=3)
    table.add_column("Nombre", style=CYAN, no_wrap=True)
    table.add_column("Archivos", justify="right", style=WHITE)
    table.add_column("Tamaño", justify="right", style=WHITE)

    for name, n_files, size in targets:
        marker = f"[bold {GREEN}]●[/]" if name == ACTIVE_TARGET else "○"
        table.add_row(marker, name, str(n_files), _human_size(size))

    console.print(table)
    console.print(
        f"[dim]Cargar: [bold]target <nombre>[/]  ·  "
        f"Recargar: [bold]target reload[/]  ·  "
        f"Descargar: [bold]target unload[/]  ·  "
        f"●=activo  ○=disponible[/]"
    )


def print_sessions_menu():
    sessions = list_saved_sessions()
    if not sessions:
        console.print(f"[{CYAN_DARK}]No hay sesiones guardadas todavía.[/]")
        return

    table = Table(title="Sesiones guardadas", border_style=CYAN)
    table.add_column("ID", style=CYAN, no_wrap=True)
    table.add_column("Iniciada", no_wrap=True)
    table.add_column("Última actividad", no_wrap=True)
    table.add_column("Msgs", justify="right")
    table.add_column("Skills", style=PURPLE)

    for s in sessions:
        marker = f"  [bold {GREEN}]← actual[/]" if s["id"] == SESSION_ID else ""
        table.add_row(
            s["id"] + marker,
            s["started"][:19] if s["started"] != "?" else "?",
            s["saved"][:19] if s["saved"] != "?" else "?",
            str(s["msgs"]),
            ", ".join(s["skills"]) or "-"
        )

    console.print(table)
    console.print(
        f"[dim]Retomar la última: [bold]resume[/]  ·  "
        f"Retomar una en concreto: [bold]resume <id>[/]  ·  "
        f"Empezar limpia: [bold]new[/][/]"
    )


# ============================================================
# HOOKS (extensión por archivos en hooks/)
# ============================================================
#
# Los archivos hooks/<name>.py son módulos Python sueltos que el agente
# carga dinámicamente y llama en momentos concretos del ciclo de vida.
# Cada hook expone una función `run(ctx)` que recibe un dict con todo
# el contexto disponible y NO devuelve nada (o lanza HookAbort para
# cancelar la acción cuando aplique).
#
# Eventos disponibles:
#   - before_command : antes de ejecutar un comando shell. Puede abortar.
#   - after_command  : tras ejecutar un comando (éxito o fallo).
#   - on_error       : sólo cuando rc != 0 (y no cancelado). Tras after_command.
#   - on_report      : tras escribir reports/informe-<target>-<ts>.md.
#
# Reglas operativas:
#   - Si un hook falla con excepción NO bloquea al agente. Se loguea
#     en consola en modo dim para no contaminar la salida pero queda
#     constancia. Excepción: HookAbort, que sí cancela el comando.
#   - Los hooks se cachean tras la primera carga (importlib).
#   - Si añades un hook nuevo, basta con dejarlo como hooks/<event>.py
#     con una función `run(ctx)`. No hay que tocar agent.py.

HOOKS_DIR = os.path.join(WORKSPACE, "hooks")
_HOOK_MODULE_CACHE = {}
_HOOK_MTIME_CACHE = {}


class HookAbort(Exception):
    """Lánzala desde un hook `before_command` para cancelar la ejecución."""


def _load_hook_module(name):
    """Carga (o recarga si cambió el mtime) el módulo hooks/<name>.py.
    Devuelve el módulo o None si no existe o está vacío.
    """
    path = os.path.join(HOOKS_DIR, f"{name}.py")
    if not os.path.isfile(path):
        return None
    try:
        if os.path.getsize(path) == 0:
            return None
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    cached_mtime = _HOOK_MTIME_CACHE.get(name)
    if name in _HOOK_MODULE_CACHE and cached_mtime == mtime:
        return _HOOK_MODULE_CACHE[name]

    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(f"hooks.{name}", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        console.print(
            f"[dim {RED}]› hook {name}: error al cargar — {e}[/]"
        )
        return None

    _HOOK_MODULE_CACHE[name] = mod
    _HOOK_MTIME_CACHE[name] = mtime
    return mod


def run_hook(name, ctx):
    """Invoca el hook `name` con `ctx`. Captura excepciones y las loguea
    en dim, salvo HookAbort que se re-lanza para que el caller pueda
    decidir abortar."""
    mod = _load_hook_module(name)
    if mod is None:
        return
    fn = getattr(mod, "run", None)
    if not callable(fn):
        return
    try:
        fn(ctx)
    except HookAbort:
        raise
    except Exception as e:
        console.print(
            f"[dim {RED}]› hook {name}: excepción ignorada — {e}[/]"
        )


def _build_hook_ctx(**extra):
    """Construye el dict base que reciben los hooks. Cualquier hook
    puede leer las claves que necesite e ignorar el resto."""
    ctx = {
        "workspace": WORKSPACE,
        "session_id": SESSION_ID,
        "target": ACTIVE_TARGET,
        "skills": list(ACTIVE_SKILLS),
        "proxy_mode": PROXY_MODE,
    }
    ctx.update(extra)
    return ctx


# ============================================================
# MENCIONES @archivo  (selector de contexto)
# ============================================================

# Pattern: @ precedido de inicio de línea o espacio (no de cualquier otro
# carácter no-whitespace; así no se dispara en strings tipo "user@host" o
# emails). Token = chars de path razonables.
_AT_MENTION_RE = re.compile(r"(?<!\S)@([\w./\-]+)")

# Sintaxis extendida: `@archivo:L43` o `@archivo:L40-L50` para señalar un
# rango específico de líneas (equivalente a "lo que tengo seleccionado en
# el editor"). Compatible con la forma `@archivo` simple — si no hay rango,
# se adjunta el archivo entero.
_AT_MENTION_RANGE_RE = re.compile(
    r"(?<!\S)@([\w./\-]+):L(\d+)(?:-L?(\d+))?(?!\w)",
    re.IGNORECASE,
)

# Directorios que NO recorremos al buscar coincidencias (ruido o muy grandes).
_AT_MENTION_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn",
    "venv", ".venv", "env", ".env.d",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".tox", "build", "dist",
}

# Tamaño máximo de archivo a inyectar (en bytes). Si excede, truncamos con
# un aviso explícito al final del bloque inyectado.
_AT_MENTION_MAX_BYTES = 200 * 1024
# Tope de coincidencias mostradas al usuario para elegir.
_AT_MENTION_MAX_RESULTS = 20


def _search_files_for_mention(token):
    """Busca recursivamente en WORKSPACE archivos cuyo nombre/path contiene
    `token` (case-insensitive). Si el token tiene `/`, matchea contra el
    path relativo; si no, contra el basename. Devuelve lista de paths
    absolutos, ordenada por relevancia (exacto > prefijo > substring).
    """
    if not token:
        return []
    token_lower = token.lower()
    is_path = "/" in token
    matches = []
    try:
        for root, dirs, files in os.walk(WORKSPACE):
            dirs[:] = [
                d for d in dirs
                if d not in _AT_MENTION_EXCLUDE_DIRS and not d.startswith(".")
            ]
            for fname in files:
                if fname.startswith("."):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, WORKSPACE)
                hay = rel.lower() if is_path else fname.lower()
                if token_lower in hay:
                    matches.append(full)
                if len(matches) >= 500:
                    break
            if len(matches) >= 500:
                break
    except OSError:
        pass

    def score(p):
        bn = os.path.basename(p).lower()
        rel = os.path.relpath(p, WORKSPACE).lower()
        if is_path:
            target = rel
        else:
            target = bn
            # Bonus si el path entero coincide exactamente con el token (raro
            # sin `/`, pero contemplado).
            if rel == token_lower:
                return (0, len(rel))
        if target == token_lower:
            return (0, len(rel))
        if target.startswith(token_lower):
            return (1, len(rel))
        if token_lower in target:
            return (2, len(rel))
        return (3, len(rel))

    matches.sort(key=score)
    # Deduplicar preservando orden
    seen = set()
    uniq = []
    for m in matches:
        if m in seen:
            continue
        seen.add(m)
        uniq.append(m)
    return uniq[:_AT_MENTION_MAX_RESULTS]


def _prompt_pick_file(token, matches):
    """Muestra la lista de coincidencias y pide al usuario que elija una.
    Devuelve el path elegido o None si cancela."""
    console.print()
    console.print(Panel(
        f"[bold {ORANGE}]@{token}[/]  ·  [{WHITE}]{len(matches)} "
        f"coincidencia(s)[/]\n[dim]Selecciona el archivo a inyectar como "
        f"contexto.[/]",
        border_style=ORANGE,
        box=ROUNDED,
        padding=(0, 1),
    ))
    for i, p in enumerate(matches, 1):
        rel = os.path.relpath(p, WORKSPACE)
        try:
            size = os.path.getsize(p)
            size_str = f"{size}B" if size < 1024 else f"{size/1024:.1f}KB"
        except OSError:
            size_str = "?"
        console.print(f"  [bold {CYAN}]{i:>2}[/] · {rel}  [dim]({size_str})[/]")
    console.print(f"  [bold {CYAN}] 0[/] · [dim]cancelar (omitir @{token})[/]")
    console.print()
    try:
        sel = input(
            f"Elige número para @{token} (0-{len(matches)}): "
        ).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None
    if not sel.isdigit():
        console.print(f"[dim]› selección no válida; @{token} se omite.[/]")
        return None
    idx = int(sel)
    if idx == 0 or not (1 <= idx <= len(matches)):
        return None
    return matches[idx - 1]


def _load_mention_content(path):
    """Lee el archivo apuntado por una mención. Trunca si excede el tope y
    devuelve (contenido, was_truncated, error_or_none)."""
    try:
        os.path.getsize(path)
    except OSError as e:
        return "", False, f"no se pudo stat: {e}"
    truncated = False
    try:
        with open(path, "rb") as f:
            raw = f.read(_AT_MENTION_MAX_BYTES + 1)
        if len(raw) > _AT_MENTION_MAX_BYTES:
            raw = raw[:_AT_MENTION_MAX_BYTES]
            truncated = True
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
    except OSError as e:
        return "", False, f"error de lectura: {e}"
    return text, truncated, None


# ============================================================
# VSCode/Cursor bridge — `<WORKSPACE>/.maxiwatt/state.json`
# ============================================================
# La extensión `maxiwatt-agent` para VSCode/Cursor escribe el estado del
# editor (archivo activo + selección) en ese JSON cada vez que cambia.
# El agente lo lee ANTES de cada prompt para:
#   1. Mostrar un badge "📎 In foo.py" o "📋 N líneas seleccionadas".
#   2. Auto-prepender la selección como contexto al enviar al modelo
#      (equivalente a haber escrito @foo.py:L43-L45 a mano).
# Si la extensión no está instalada el archivo simplemente no existe y
# todo el bloque es no-op — sin overhead, sin warnings.

_VSCODE_STATE_FILENAME = os.path.join(".maxiwatt", "state.json")
_VSCODE_STATE_MAX_AGE_S = 120  # info más vieja que esto se ignora


def _read_vscode_state(max_age_seconds=_VSCODE_STATE_MAX_AGE_S):
    """Devuelve el dict del state.json escrito por la extensión, o None si
    no existe, está caducado o está malformado."""
    path = os.path.join(WORKSPACE, _VSCODE_STATE_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    updated = data.get("updatedAt") or ""
    if updated:
        try:
            from datetime import datetime, timezone
            # ISO 8601 con o sin 'Z'
            ts = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > max_age_seconds:
                return None
        except (ValueError, TypeError):
            return None
    return data


def render_vscode_badge():
    """Devuelve un string rich-friendly con el badge a pintar antes del
    prompt `Tú >`. Vacío si no hay info útil."""
    state = _read_vscode_state()
    if not state:
        return ""
    rel = state.get("relativeFile") or state.get("activeFile")
    sel = state.get("selection") or {}
    if rel and sel and not sel.get("empty"):
        ln_a = sel.get("startLine")
        ln_b = sel.get("endLine")
        count = sel.get("lineCount") or 1
        range_str = f"L{ln_a}" if ln_a == ln_b else f"L{ln_a}-L{ln_b}"
        return (
            f"  [bold {ORANGE}]📋 {count} línea{'' if count == 1 else 's'} "
            f"seleccionada{'' if count == 1 else 's'}[/]  "
            f"[{CYAN}]en[/] [bold]{rel}:{range_str}[/]"
        )
    if rel:
        return (
            f"  [bold {CYAN}]📎 In[/]  [bold]{rel}[/]  "
            f"[dim](sin selección activa)[/]"
        )
    return ""


# Marcador local: una vez intentada la instalación, no la reintentamos
# en subsiguientes arranques. Vive en ~/.maxiwatt-vscode-install.marker
_VSCODE_INSTALL_MARKER = os.path.expanduser("~/.maxiwatt-vscode-install.marker")
# Nombre completo de la extensión en VSCode (publisher.name)
_VSCODE_EXTENSION_ID = "maxiwatt.maxiwatt-agent"
# URL del .vsix dentro del repo (versionada — se actualiza en cada release)
_VSCODE_EXTENSION_VSIX_URL = (
    "https://github.com/AlejandroMaxiwatt/ai-agent-kali/releases/download/"
    "v0.3.0/maxiwatt-agent-0.3.0.vsix"
)


def _in_vscode_terminal():
    """True si el agente corre dentro de un terminal integrado de
    VSCode/Cursor/Codium (detectado por env vars que setean al lanzar
    el terminal)."""
    return os.environ.get("TERM_PROGRAM", "").lower() in {"vscode", "cursor"}


def maybe_install_vscode_extension():
    """Instala la extensión maxiwatt-agent en VSCode/Cursor si:
      - estamos en un terminal de VSCode/Cursor, Y
      - la extensión NO está instalada todavía, Y
      - no la hemos intentado instalar antes (marker file).
    No bloquea ni revienta si algo falla — la instalación es opcional."""
    if not _in_vscode_terminal():
        return
    if os.path.exists(_VSCODE_INSTALL_MARKER):
        return  # ya intentamos antes; no spammear al usuario
    code_bin = shutil.which("code") or shutil.which("cursor") or shutil.which("codium")
    if not code_bin:
        return  # sin CLI no podemos instalar

    # ¿Ya instalada?
    try:
        proc = subprocess.run(
            [code_bin, "--list-extensions"],
            capture_output=True, text=True, timeout=10,
        )
        installed = [line.strip() for line in (proc.stdout or "").splitlines()]
        if _VSCODE_EXTENSION_ID in installed:
            # Crear marker para no volver a listar en cada arranque.
            try:
                open(_VSCODE_INSTALL_MARKER, "a").close()
            except OSError:
                pass
            return
    except (subprocess.TimeoutExpired, OSError):
        return

    # Confirmar con el operador (es código que correrá en su editor).
    console.print()
    console.print(Panel(
        f"[bold {CYAN}]MAXIWATT detecta que estás en un terminal de "
        f"VSCode/Cursor.[/]\n\n"
        f"Hay una extensión opcional ([bold]{_VSCODE_EXTENSION_ID}[/]) que "
        f"hace que el agente vea automáticamente qué archivo tienes abierto "
        f"y qué tienes seleccionado — igual que Claude Code muestra "
        f"'📎 In file.py' y '📋 N lines selected'.\n\n"
        f"[dim]Se descarga e instala UNA SOLA VEZ. Sin telemetría, sin "
        f"acceso a red. Solo escribe un JSON en .maxiwatt/ del workspace.[/]",
        title=f"[bold {ORANGE}]Extensión VSCode/Cursor[/]",
        border_style=ORANGE, box=ROUNDED, padding=(1, 2),
    ))
    try:
        resp = input("[?] Instalar maxiwatt-agent? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        resp = "n"
    # Marker se crea pase lo que pase para no volver a preguntar.
    try:
        open(_VSCODE_INSTALL_MARKER, "a").close()
    except OSError:
        pass
    if resp not in ("", "y", "yes", "s", "si", "sí"):
        console.print(f"[dim]› skip (puedes instalarla más tarde con: "
                      f"code --install-extension <vsix>)[/]")
        return

    # Descargar el .vsix a /tmp e instalar
    import tempfile, urllib.request
    try:
        with tempfile.NamedTemporaryFile(suffix=".vsix", delete=False) as f:
            vsix_path = f.name
        console.print(f"[dim]› descargando {_VSCODE_EXTENSION_VSIX_URL}[/]")
        urllib.request.urlretrieve(_VSCODE_EXTENSION_VSIX_URL, vsix_path)
        proc = subprocess.run(
            [code_bin, "--install-extension", vsix_path],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            console.print(
                f"[bold {GREEN}]✓ extensión instalada[/] "
                f"({_VSCODE_EXTENSION_ID})"
            )
            console.print(
                f"[dim]   Recarga la ventana de VSCode (Ctrl+Shift+P → "
                f"'Reload Window') para activarla.[/]"
            )
        else:
            console.print(
                f"[bold {RED}]✗ fallo instalando la extensión[/] "
                f"(rc={proc.returncode}): {proc.stderr.strip()[:200]}"
            )
        try:
            os.unlink(vsix_path)
        except OSError:
            pass
    except Exception as e:
        console.print(f"[bold {RED}]✗ no se pudo descargar/instalar:[/] {e}")


def vscode_auto_attach(user_input):
    """Si hay selección activa en VSCode y el operador NO ha mencionado ya
    ese archivo con `@`, auto-prepende la mención al user_input.
    Devuelve (effective_input, attached_bool)."""
    state = _read_vscode_state()
    if not state:
        return user_input, False
    rel = state.get("relativeFile")
    sel = state.get("selection") or {}
    if not rel or not sel or sel.get("empty"):
        return user_input, False
    # Si ya está mencionado a mano, no duplicamos.
    if f"@{rel}" in (user_input or ""):
        return user_input, False
    ln_a = sel.get("startLine")
    ln_b = sel.get("endLine")
    range_str = f"L{ln_a}" if ln_a == ln_b else f"L{ln_a}-L{ln_b}"
    auto_mention = f"@{rel}:{range_str}"
    new_input = f"{auto_mention} {user_input}".strip()
    return new_input, True


def resolve_at_mentions(user_input):
    """Detecta menciones `@token` en `user_input`, busca archivos coincidentes
    en el workspace y resuelve cada una a un archivo (o la omite). Devuelve
    (effective_user_input, attachments).

    `effective_user_input` es lo que se envía al modelo: lleva al principio
    un bloque por cada adjunto y conserva el texto original del usuario
    debajo (con las menciones intactas para que el modelo entienda a qué
    se refiere).

    Las menciones duplicadas (mismo token) sólo se resuelven una vez.
    """
    if not user_input or "@" not in user_input:
        return user_input, []

    # Primero: detectamos rangos `@archivo:L43-L50` para excluir las posiciones
    # cubiertas del barrido genérico de _AT_MENTION_RE (que cortaría el token
    # justo en `:` y trataría el archivo entero).
    range_matches = []  # lista de (token, line_start, line_end_or_none, span)
    consumed_spans = []
    for m in _AT_MENTION_RANGE_RE.finditer(user_input):
        tok = m.group(1)
        ln_a = int(m.group(2))
        ln_b = int(m.group(3)) if m.group(3) else ln_a
        if ln_a > ln_b:
            ln_a, ln_b = ln_b, ln_a
        range_matches.append((tok, ln_a, ln_b, m.span()))
        consumed_spans.append(m.span())

    # Tokens "archivo entero" — los que NO están dentro de un span ya consumido
    # por una mención de rango.
    tokens = []  # lista de (token, line_start_or_None, line_end_or_None)
    seen = set()
    for tok, a, b, _span in range_matches:
        key = (tok, a, b)
        if key in seen:
            continue
        seen.add(key)
        tokens.append((tok, a, b))

    for m in _AT_MENTION_RE.finditer(user_input):
        # Saltar si está dentro de un rango ya capturado
        ms, me = m.span()
        inside_range = any(s <= ms and me <= e for (s, e) in consumed_spans)
        if inside_range:
            continue
        tok = m.group(1)
        key = (tok, None, None)
        if key in seen:
            continue
        seen.add(key)
        tokens.append((tok, None, None))

    if not tokens:
        return user_input, []

    attachments = []
    for tok, ln_a, ln_b in tokens:
        matches = _search_files_for_mention(tok)
        display_mention = f"@{tok}" + (f":L{ln_a}" + (f"-L{ln_b}" if ln_b and ln_b != ln_a else "") if ln_a else "")
        if not matches:
            console.print(
                f"[bold {RED}]{display_mention}[/] · sin coincidencias en el "
                f"workspace; se ignora la mención."
            )
            continue
        if len(matches) == 1:
            chosen = matches[0]
            rel = os.path.relpath(chosen, WORKSPACE)
            console.print(
                f"[dim]› [bold]{display_mention}[/] → {rel} "
                f"(única coincidencia)[/]"
            )
        else:
            chosen = _prompt_pick_file(tok, matches)
            if chosen is None:
                continue
        content, truncated, err = _load_mention_content(chosen)
        if err:
            console.print(f"[bold {RED}]{display_mention}[/] · {err}; se omite.")
            continue

        # Si hay rango, recortamos solo esas líneas con numeración estilo
        # `cat -n`, igual que FILE_READ — así el modelo puede luego emitir
        # un FILE_EDIT preciso sobre lo que el operador estaba mirando.
        is_selection = ln_a is not None
        if is_selection:
            all_lines = content.splitlines()
            start = max(1, ln_a) - 1
            end = (ln_b or ln_a)
            sel_lines = all_lines[start:end]
            numbered = "".join(
                f"{(start + i + 1):>5}\t{line}\n"
                for i, line in enumerate(sel_lines)
            )
            content = numbered
            truncated = False  # ya está acotado al rango

        attachments.append({
            "mention": display_mention,
            "path": chosen,
            "rel": os.path.relpath(chosen, WORKSPACE),
            "content": content,
            "truncated": truncated,
            "is_selection": is_selection,
            "line_start": ln_a,
            "line_end": ln_b,
        })

    if not attachments:
        return user_input, []

    blocks = []
    any_selection = False
    for a in attachments:
        if a.get("is_selection"):
            any_selection = True
            ln_a = a["line_start"]; ln_b = a["line_end"] or ln_a
            range_label = f"L{ln_a}" if ln_a == ln_b else f"L{ln_a}-L{ln_b}"
            header = (
                f"[[SELECCIÓN DEL OPERADOR EN EL EDITOR · "
                f"{a['rel']} · líneas {range_label}]]"
            )
            footer = f"[[FIN SELECCIÓN · {a['rel']}]]"
        else:
            header = f"[[ARCHIVO ADJUNTO · {a['mention']} → {a['rel']}]]"
            footer = f"[[FIN ARCHIVO · {a['rel']}]]"
        body = a["content"]
        if a["truncated"]:
            body += (
                f"\n\n[[…archivo truncado a {_AT_MENTION_MAX_BYTES} bytes; "
                f"si necesitas el resto, pide al usuario el fragmento concreto.]]"
            )
        blocks.append(f"{header}\n{body}\n{footer}")

    if any_selection:
        intro = (
            "El operador te está SEÑALANDO líneas concretas de archivos "
            "(equivalente a 'esto que tengo seleccionado en el editor'). "
            "Cuando emitas un FILE_EDIT, edita SOLO sobre las líneas señaladas "
            "salvo que el operador pida lo contrario explícitamente."
        )
    else:
        intro = (
            "El usuario ha referenciado los siguientes archivos del workspace "
            "como contexto. Léelos y trabaja sobre ellos en tu respuesta:"
        )
    effective = (
        f"{intro}\n\n"
        + "\n\n".join(blocks)
        + "\n\n"
        + f"Petición del usuario:\n{user_input}"
    )

    # Panel de resumen para el usuario
    def _row(a):
        marker = "⟫ selección" if a.get("is_selection") else "archivo"
        suffix = " [dim](truncado)[/]" if a["truncated"] else ""
        return f"  · [bold]{a['mention']}[/] → {a['rel']} [dim]({marker})[/]{suffix}"
    rows = "\n".join(_row(a) for a in attachments)
    console.print()
    console.print(Panel(
        f"[bold {GREEN}]Contexto adjuntado[/]\n{rows}",
        border_style=GREEN,
        box=ROUNDED,
        padding=(0, 1),
    ))

    return effective, attachments


# ============================================================
# MAIN
# ============================================================

def main():
    os.makedirs(os.path.join(WORKSPACE, "skills"), exist_ok=True)
    os.makedirs(os.path.join(WORKSPACE, "plugins"), exist_ok=True)
    os.makedirs(os.path.join(WORKSPACE, "hooks"), exist_ok=True)
    os.makedirs(os.path.join(WORKSPACE, "logs"), exist_ok=True)
    os.makedirs(os.path.join(WORKSPACE, "reports"), exist_ok=True)
    os.makedirs(os.path.join(WORKSPACE, "scans"), exist_ok=True)
    os.makedirs(os.path.join(WORKSPACE, "evidence"), exist_ok=True)
    os.makedirs(os.path.join(WORKSPACE, "memory"), exist_ok=True)
    os.makedirs(os.path.join(WORKSPACE, "targets"), exist_ok=True)

    # Importante: anclar la cwd al workspace para que cualquier ruta relativa
    # propuesta por el modelo (`./scans/`, `./reports/`, `./evidence/`) caiga
    # dentro del proyecto, no en $HOME del usuario.
    try:
        os.chdir(WORKSPACE)
    except OSError:
        pass

    # Cargar lecciones aprendidas en sesiones previas e inyectarlas en el
    # system prompt antes de la primera interacción.
    _ensure_lessons_dir()
    _rebuild_system_message()

    # Auto-instalación de la extensión VSCode/Cursor (one-time, no-op si
    # ya está instalada o si no estamos dentro de un terminal de editor).
    try:
        maybe_install_vscode_extension()
    except Exception as e:
        # Nunca abortar el agente por un fallo del bridge — es opcional.
        console.print(f"[dim]› bridge VSCode auto-install: omitido ({e})[/]")

    show_splash()

    # Detectar goals que quedaron en estado "running"/"pending" por
    # un cierre anterior del agente y avisar al operador.
    check_orphan_goals_at_startup()

    while True:
        try:
            # Notificación de subagentes y goal-orchestrator terminados
            _check_subagent_notifications()
            _check_goal_notifications()
            console.print(render_context_bar())
            # Badge de archivo/selección activa en VSCode/Cursor (si la
            # extensión maxiwatt-agent está instalada y activa).
            vbadge = render_vscode_badge()
            if vbadge:
                console.print(vbadge)
            console.print()
            user_input = input("Tú > ").strip()
        except KeyboardInterrupt:
            print()
            break

        if not user_input:
            continue

        # Aceptar comandos también con prefijo "/" (estilo slash-command)
        if user_input.startswith("/"):
            user_input = user_input[1:].lstrip()
            if not user_input:
                continue

        cmd_lower = user_input.lower()
        # Primera palabra (para comandos con argumentos: "use <skill>", "resume <id>")
        first_word = cmd_lower.split(maxsplit=1)[0] if cmd_lower else ""

        if cmd_lower in ("salir", "exit", "quit"):
            break

        if cmd_lower in ("help", "ayuda"):
            print_help()
            continue

        if cmd_lower in ("comandos", "commands"):
            print_commands()
            continue

        if cmd_lower in ("refresh", "refrescar", "clear", "limpiar"):
            show_splash()
            continue

        if cmd_lower in ("models", "modelos"):
            print_models()
            continue

        if cmd_lower in ("tools", "herramientas"):
            print_tools()
            continue

        # Comandos de edición de archivos (operador) — `view`, `edit`, `diff`.
        # Las tres operaciones que el modelo puede hacer vía FILE_*, ahora
        # también disponibles para el operador desde el REPL.
        if first_word in ("view", "ver", "cat"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                console.print(f"[{ORANGE}]uso: view <ruta>[/]")
                continue
            r = apply_file_read(parts[1].strip())
            if r["ok"]:
                lexer = _guess_syntax_lexer(r["path"]) or "text"
                # Reconstruir contenido sin las líneas numeradas (Syntax las pone)
                lines = [
                    ln.split("\t", 1)[1] if "\t" in ln else ln
                    for ln in r["content"].splitlines()
                ]
                console.print(Panel(
                    Syntax("\n".join(lines), lexer, line_numbers=True,
                           theme="dracula", word_wrap=False),
                    title=f"[bold {ORANGE}]view[/]  ·  [{WHITE}]{r['path']}[/]  "
                          f"[grey50]({r['shown_lines']}/{r['total_lines']} líneas"
                          + (", truncado" if r["truncated"] else "") + ")[/]",
                    border_style=ORANGE, box=ROUNDED, padding=(0, 0),
                ))
            else:
                console.print(f"[bold {RED}]✗[/] {r['error']}")
            continue

        if first_word in ("diff",):
            # diff <path1> <path2>: diff entre dos archivos del workspace
            parts = user_input.split()
            if len(parts) != 3:
                console.print(f"[{ORANGE}]uso: diff <ruta1> <ruta2>[/]")
                continue
            ok1, full1, rel1 = _validate_workspace_path(parts[1])
            ok2, full2, rel2 = _validate_workspace_path(parts[2])
            if not ok1:
                console.print(f"[bold {RED}]✗[/] {full1}"); continue
            if not ok2:
                console.print(f"[bold {RED}]✗[/] {full2}"); continue
            try:
                with open(full1, encoding="utf-8") as f: c1 = f.read()
                with open(full2, encoding="utf-8") as f: c2 = f.read()
            except (OSError, UnicodeDecodeError) as e:
                console.print(f"[bold {RED}]✗[/] read: {e}"); continue
            dl = list(difflib.unified_diff(
                c1.splitlines(), c2.splitlines(),
                fromfile=f"a/{rel1}", tofile=f"b/{rel2}", n=3,
            ))
            console.print(render_file_diff_panel(f"{rel1} ↔ {rel2}", dl, kind="edit"))
            continue

        if first_word in ("edit", "editar"):
            # edit <ruta>: prompt interactivo old/new (multilínea con `EOF`)
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                console.print(f"[{ORANGE}]uso: edit <ruta>  (luego pegas OLD, EOF, NEW, EOF)[/]")
                continue
            path = parts[1].strip()
            console.print(f"[dim]» pega el texto OLD (línea con solo 'EOF' para terminar):[/]")
            old_lines = []
            try:
                while True:
                    line = input()
                    if line.strip() == "EOF": break
                    old_lines.append(line)
            except (EOFError, KeyboardInterrupt):
                console.print(f"[dim]cancelado[/]"); continue
            console.print(f"[dim]» pega el texto NEW (línea con solo 'EOF' para terminar):[/]")
            new_lines = []
            try:
                while True:
                    line = input()
                    if line.strip() == "EOF": break
                    new_lines.append(line)
            except (EOFError, KeyboardInterrupt):
                console.print(f"[dim]cancelado[/]"); continue
            old_s = "\n".join(old_lines)
            new_s = "\n".join(new_lines)
            # Reutilizamos el wire-up del modelo: construimos un answer "ficticio"
            # con el bloque FILE_EDIT y lo procesamos.
            synthetic = (
                f"[[FILE_EDIT: {path}]]\n"
                f"<<<OLD\n{old_s}\nOLD>>>\n"
                f"<<<NEW\n{new_s}\nNEW>>>\n"
                f"[[/FILE_EDIT]]"
            )
            process_file_blocks(synthetic)
            continue

        if first_word in ("write", "escribir"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2:
                console.print(f"[{ORANGE}]uso: write <ruta>  (luego pegas contenido, EOF para terminar)[/]")
                continue
            path = parts[1].strip()
            console.print(f"[dim]» pega el contenido (línea con solo 'EOF' para terminar):[/]")
            lines = []
            try:
                while True:
                    line = input()
                    if line.strip() == "EOF": break
                    lines.append(line)
            except (EOFError, KeyboardInterrupt):
                console.print(f"[dim]cancelado[/]"); continue
            synthetic = (
                f"[[FILE_WRITE: {path}]]\n"
                + "\n".join(lines) + "\n"
                + f"[[/FILE_WRITE]]"
            )
            process_file_blocks(synthetic)
            continue

        if first_word in ("sudo", "sudopass", "password"):
            parts = user_input.split(maxsplit=1)
            sub = parts[1].strip().lower() if len(parts) > 1 else "status"

            if sub in ("status", "estado", ""):
                cache_ok = _sudo_cache_valid()
                with _sudo_password_lock:
                    has_stored = _STORED_SUDO_PASSWORD is not None
                console.print(Panel(
                    f"[bold]Caché de sudo:[/] "
                    + (f"[bold {GREEN}]vigente[/] (no pedirá password "
                       f"durante ~15 min)" if cache_ok else
                       f"[bold {RED}]expirado/no vigente[/]") + "\n"
                    f"[bold]Password almacenada en memoria:[/] "
                    + (f"[bold {GREEN}]sí[/] (subagentes y autopilot la usan "
                       f"automáticamente)" if has_stored else
                       f"[bold {GRAY}]no[/]") + "\n\n"
                    f"[dim]Subcomandos:[/]\n"
                    f"[dim]  sudo refresh   · pide password ahora y refresca el caché (15 min)[/]\n"
                    f"[dim]  sudo set       · pide password y la almacena en memoria del proceso[/]\n"
                    f"[dim]                  (no se persiste a disco; subagentes pueden usarla)[/]\n"
                    f"[dim]  sudo clear     · borra la password almacenada[/]\n"
                    f"[dim]  sudo status    · esta vista[/]",
                    title=f"[bold {ORANGE}]Sudo[/]",
                    border_style=ORANGE, box=ROUNDED, padding=(1, 2),
                ))
                continue

            if sub in ("refresh", "refrescar", "v"):
                console.print(
                    f"[dim]› Pidiendo password para refrescar el caché de sudo…[/]"
                )
                try:
                    rc = subprocess.call(["sudo", "-v"])
                    if rc == 0:
                        console.print(
                            f"[bold {GREEN}]✓ Caché de sudo refrescado. "
                            f"Vigente ~15 min.[/]"
                        )
                    else:
                        console.print(
                            f"[{RED}]✗ sudo -v devolvió rc={rc}.[/]"
                        )
                except KeyboardInterrupt:
                    console.print()
                    console.print(f"[{RED}]› cancelado.[/]")
                continue

            if sub in ("set", "guardar", "almacenar"):
                try:
                    pw = getpass.getpass(
                        "Password sudo (no se guarda a disco, solo en memoria): "
                    )
                except (EOFError, KeyboardInterrupt):
                    console.print(f"\n[{RED}]› cancelado.[/]")
                    continue
                if not pw:
                    console.print(f"[{RED}]› password vacía, no se almacena.[/]")
                    continue
                console.print(f"[dim]› Validando…[/]")
                if _set_stored_sudo_password(pw):
                    console.print(
                        f"[bold {GREEN}]✓ Password validada y almacenada en "
                        f"memoria.[/]\n"
                        f"[dim]Subagentes y autopilot la usarán automáticamente "
                        f"cuando un comando requiera sudo. `sudo clear` para "
                        f"borrarla. Se pierde al salir del agente.[/]"
                    )
                else:
                    console.print(
                        f"[bold {RED}]✗ Password incorrecta o sudo rechazó la "
                        f"autenticación.[/] No se almacenó nada."
                    )
                continue

            if sub in ("clear", "limpiar", "borrar", "forget"):
                _clear_stored_sudo_password()
                # También invalidamos el caché por completo
                try:
                    subprocess.run(["sudo", "-k"], capture_output=True, timeout=3)
                except Exception:
                    pass
                console.print(
                    f"[bold {CYAN}]Password borrada de memoria · "
                    f"caché de sudo invalidado.[/]"
                )
                continue

            console.print(
                f"[{RED}]Uso: sudo [status|refresh|set|clear][/]"
            )
            continue

        if first_word in ("timeout",):
            parts = user_input.split(maxsplit=2)
            sub = parts[1].strip().lower() if len(parts) > 1 else "status"
            global COMMAND_TIMEOUT_S, COMMAND_TIMEOUT_S_LARGE, WORDLIST_MEDIUM_THRESHOLD_LINES
            if sub in ("status", "estado", ""):
                console.print(
                    f"[bold {WHITE}]Timeout de ejecución de comandos:[/]\n"
                    f"  · base: [bold]{COMMAND_TIMEOUT_S}s[/] "
                    f"({COMMAND_TIMEOUT_S // 60}min {COMMAND_TIMEOUT_S % 60}s)\n"
                    f"  · extendido para wordlists ≥ "
                    f"{WORDLIST_MEDIUM_THRESHOLD_LINES:,} líneas: "
                    f"[bold]{COMMAND_TIMEOUT_S_LARGE}s[/] "
                    f"({COMMAND_TIMEOUT_S_LARGE // 60}min)\n\n"
                    f"[dim]Uso:[/]\n"
                    f"[dim]  timeout <segundos>     · cambia el base (10–7200)[/]\n"
                    f"[dim]  timeout large <N>      · cambia el extendido (60–14400)[/]\n"
                    f"[dim]  timeout threshold <N>  · cambia el umbral de líneas (≥100)[/]\n"
                    f"[dim]  timeout default        · restaura 300/1800/5000[/]"
                )
            elif sub in ("default", "reset", "restaurar"):
                COMMAND_TIMEOUT_S = 300
                COMMAND_TIMEOUT_S_LARGE = 1800
                WORDLIST_MEDIUM_THRESHOLD_LINES = 5000
                console.print(
                    f"[bold {GREEN}]✓ Timeouts reseteados:[/] "
                    f"base=300s · extendido=1800s · umbral=5000 líneas."
                )
            elif sub in ("large", "extendido"):
                if len(parts) < 3:
                    console.print(
                        f"[{RED}]Uso: timeout large <segundos> (60–14400)[/]"
                    )
                else:
                    try:
                        v = int(parts[2].strip())
                        if v < 60 or v > 14400:
                            console.print(
                                f"[{RED}]Rango válido: 60–14400s. Recibido: {v}[/]"
                            )
                        else:
                            COMMAND_TIMEOUT_S_LARGE = v
                            console.print(
                                f"[bold {GREEN}]✓ Timeout extendido → {v}s "
                                f"({v // 60}min).[/]"
                            )
                    except ValueError:
                        console.print(f"[{RED}]Debe ser un entero. Recibido: '{parts[2]}'[/]")
            elif sub in ("threshold", "umbral"):
                if len(parts) < 3:
                    console.print(
                        f"[{RED}]Uso: timeout threshold <líneas> (mínimo 100)[/]"
                    )
                else:
                    try:
                        v = int(parts[2].strip())
                        if v < 100:
                            console.print(f"[{RED}]Mínimo 100 líneas. Recibido: {v}[/]")
                        else:
                            WORDLIST_MEDIUM_THRESHOLD_LINES = v
                            console.print(
                                f"[bold {GREEN}]✓ Umbral wordlist → {v:,} líneas. "
                                f"A partir de ese tamaño se aplica el timeout extendido.[/]"
                            )
                    except ValueError:
                        console.print(f"[{RED}]Debe ser un entero. Recibido: '{parts[2]}'[/]")
            else:
                # `timeout <N>` → cambia el base
                try:
                    v = int(sub)
                    if v < 10 or v > 7200:
                        console.print(
                            f"[{RED}]Rango válido para timeout base: 10–7200s. "
                            f"Recibido: {v}[/]"
                        )
                    else:
                        COMMAND_TIMEOUT_S = v
                        console.print(
                            f"[bold {GREEN}]✓ Timeout base → {v}s "
                            f"({v // 60}min {v % 60}s).[/]"
                        )
                except ValueError:
                    console.print(
                        f"[{RED}]Uso: timeout [<segundos> | large <N> | "
                        f"threshold <N> | default | status][/]"
                    )
            continue

        if first_word in ("goal", "objetivo"):
            tokens = user_input.split(maxsplit=1)
            rest = tokens[1].strip() if len(tokens) > 1 else ""

            if rest.lower() in ("", "status", "estado"):
                with _goal_lock:
                    gr = _active_goal_orch
                if not gr:
                    console.print(
                        f"[dim]No hay goal activo. Lanza uno con `goal "
                        f"<descripción del objetivo>`.[/]"
                    )
                else:
                    status_color = {
                        "running": "yellow", "done": GREEN,
                        "blocked": "#fbbf24", "exhausted": MAGENTA,
                        "killed": "#fbbf24", "failed": RED, "pending": CYAN,
                    }.get(gr.status, "white")
                    console.print(Panel(
                        f"[bold]Goal:[/] {gr.goal}\n"
                        f"[bold]Estado:[/] [{status_color}]{gr.status}[/]  ·  "
                        f"Fase: {gr.current_phase}/{gr.max_phases}\n"
                        f"[bold]Target:[/] [bold {PURPLE}]{gr.target}[/]  ·  "
                        f"Started: {gr.started_at}\n"
                        f"[bold]Subagentes por fase:[/] "
                        + " · ".join(
                            f"F{ph['n']}={len(ph.get('subagent_names', []))}"
                            for ph in gr.phases
                        ) + (
                            f"\n[bold]Motivo:[/] {gr.outcome_reason}"
                            if gr.outcome_reason else ""
                        ) + (
                            f"\n[dim]Log: "
                            f"{os.path.relpath(gr.log_path, WORKSPACE)}[/]"
                        ),
                        title=f"[bold {PURPLE}]Goal orchestrator[/]",
                        border_style=PURPLE, box=ROUNDED, padding=(1, 2),
                    ))
                continue

            if rest.lower() in ("kill", "stop", "parar", "abort"):
                if kill_goal():
                    console.print(
                        f"[bold {CYAN}]Kill solicitado al goal activo. "
                        f"Terminará tras la fase actual.[/]"
                    )
                else:
                    console.print(
                        f"[{RED}]No hay goal activo para detener.[/]"
                    )
                continue

            if rest.lower() in ("show", "ver", "log"):
                with _goal_lock:
                    gr = _active_goal_orch
                if not gr:
                    console.print(f"[{RED}]No hay goal activo.[/]")
                else:
                    _print_goal_finished_panel(gr)
                continue

            # `goal list` — lista todos los goals persistidos en disco
            if rest.lower() in ("list", "listar", "ls"):
                persisted = list_persisted_goals()
                if not persisted:
                    console.print(
                        f"[dim]No hay goals persistidos en "
                        f"memory/subagents/.[/]"
                    )
                    continue
                table = Table(
                    title=f"Goals persistidos ({len(persisted)})",
                    border_style=PURPLE, box=ROUNDED,
                )
                table.add_column("ID", style=CYAN, no_wrap=True)
                table.add_column("Status", no_wrap=True)
                table.add_column("Target", style=PURPLE, no_wrap=True)
                table.add_column("Fase", no_wrap=True)
                table.add_column("Started", style=GRAY, no_wrap=True)
                table.add_column("Goal", style=WHITE)
                color_map = {
                    "running": "yellow", "pending": "yellow",
                    "done": GREEN, "blocked": "#fbbf24",
                    "exhausted": MAGENTA, "killed": "#fbbf24",
                    "failed": RED,
                }
                for g in persisted[:30]:
                    c = color_map.get(g.get("status", ""), "white")
                    goal_short = g.get("goal", "")[:60]
                    if len(g.get("goal", "")) > 60:
                        goal_short += "…"
                    table.add_row(
                        g.get("id", "?"),
                        f"[{c}]{g.get('status', '?')}[/]",
                        g.get("target", "?"),
                        f"{g.get('current_phase', 0)}/{g.get('max_phases', '?')}",
                        g.get("started_at", "?")[:16],
                        goal_short,
                    )
                console.print(table)
                console.print(
                    f"[dim]Resumir: [bold]goal resume <id>[/]  ·  "
                    f"Borrar estado: [bold]goal discard <id>[/][/]"
                )
                continue

            # `goal resume [id]` — reanuda un goal interrumpido
            if rest.lower().startswith("resume") or rest.lower().startswith("reanudar") or rest.lower().startswith("retomar"):
                parts_r = rest.split(maxsplit=1)
                if len(parts_r) > 1:
                    target_id = parts_r[1].strip()
                else:
                    orphans = list_orphan_goals()
                    if not orphans:
                        console.print(
                            f"[dim]No hay goals huérfanos para reanudar. "
                            f"Usa `goal list` para ver todos los persistidos.[/]"
                        )
                        continue
                    target_id = orphans[0].get("id")
                    console.print(
                        f"[dim]› Reanudando el huérfano más reciente: "
                        f"[bold]{target_id}[/][/]"
                    )
                gr, err = resume_goal(target_id)
                if err:
                    console.print(f"[{RED}]✗ {err}[/]")
                else:
                    n_done = len(gr.phases)
                    n_left = gr.max_phases - gr.current_phase
                    console.print()
                    console.print(Panel(
                        f"[bold {GREEN}]✓ Goal '{gr.id}' reanudado[/]\n\n"
                        f"[bold {WHITE}]Goal:[/] {gr.goal[:200]}"
                        f"{'…' if len(gr.goal) > 200 else ''}\n"
                        f"[bold {WHITE}]Target:[/] {gr.target}\n"
                        f"[bold {WHITE}]Fases completadas previamente:[/] "
                        f"{n_done} ({', '.join('F'+str(p['n']) for p in gr.phases) or 'ninguna'})\n"
                        f"[bold {WHITE}]Fases restantes:[/] {n_left}\n\n"
                        f"[dim]El orquestador continúa desde fase "
                        f"{gr.current_phase + 1}. Las fases ya ejecutadas NO "
                        f"se repiten — su evidencia ya está en los archivos "
                        f"del target.[/]",
                        title=f"[bold {GREEN}]» Goal reanudado[/]",
                        border_style=GREEN, box=ROUNDED, padding=(1, 2),
                    ))
                continue

            # `goal discard <id>` — borra el estado persistido
            if rest.lower().startswith("discard") or rest.lower().startswith("descartar"):
                parts_d = rest.split(maxsplit=1)
                if len(parts_d) < 2:
                    console.print(
                        f"[{RED}]Uso: goal discard <id>[/]"
                    )
                    continue
                gid = parts_d[1].strip()
                if discard_goal_state(gid):
                    console.print(
                        f"[bold {CYAN}]Estado del goal '{gid}' descartado. "
                        f"El log de ejecución sigue en disco.[/]"
                    )
                else:
                    console.print(
                        f"[{RED}]No existe estado persistido para goal '{gid}'.[/]"
                    )
                continue

            # `goal <texto>` → lanzar
            goal_run, err = start_goal(rest)
            if err:
                console.print(f"[{RED}]✗ {err}[/]")
            else:
                console.print()
                console.print(Panel(
                    f"[bold {GREEN}]✓ Goal lanzado · id {goal_run.id}[/]\n\n"
                    f"[bold {WHITE}]Goal:[/] {goal_run.goal[:300]}"
                    f"{'…' if len(goal_run.goal) > 300 else ''}\n"
                    f"[bold {WHITE}]Target:[/] {goal_run.target}\n"
                    f"[bold {WHITE}]Max fases:[/] {goal_run.max_phases}  ·  "
                    f"[bold {WHITE}]Max subagentes por fase:[/] "
                    f"{MAX_CONCURRENT_SUBAGENTS}\n\n"
                    f"[dim]El orquestador planifica fase a fase, "
                    f"lanza subagentes en paralelo, espera y replanifica. "
                    f"Te aviso cuando termine.\n"
                    f"`goal status` para ver estado · "
                    f"`goal kill` para detener.\n"
                    f"Log: {os.path.relpath(goal_run.log_path, WORKSPACE)}[/]",
                    title=f"[bold {GREEN}]» Goal-driven orchestration[/]",
                    border_style=GREEN, box=ROUNDED, padding=(1, 2),
                ))
            continue

        if first_word in ("subagent", "subagente", "sub"):
            tokens = user_input.split(maxsplit=3)
            action = tokens[1].strip().lower() if len(tokens) > 1 else "list"

            if action in ("list", "ls", "status", "estado"):
                subs = list_subagents()
                if not subs:
                    console.print(f"[dim]No hay subagentes.[/]")
                else:
                    table = Table(
                        title="Subagentes",
                        border_style=PURPLE, box=ROUNDED,
                    )
                    table.add_column("Nombre", style=WHITE, no_wrap=True)
                    table.add_column("Status", no_wrap=True)
                    table.add_column("Skill", style=PURPLE, no_wrap=True)
                    table.add_column("Turnos", style=GRAY, no_wrap=True)
                    table.add_column("Cmds", style=GRAY, no_wrap=True)
                    table.add_column("Tarea", style=WHITE)
                    color_map = {
                        "running": "yellow", "done": GREEN,
                        "failed": RED, "killed": "#fbbf24",
                        "exhausted": MAGENTA, "pending": CYAN,
                    }
                    for s in subs:
                        c = color_map.get(s.status, "white")
                        table.add_row(
                            s.name,
                            f"[{c}]{s.status}[/]",
                            s.skill,
                            f"{s.turns_used}/{s.max_turns}",
                            str(len(s.commands_run)),
                            (s.task[:60] + "…") if len(s.task) > 60 else s.task,
                        )
                    console.print(table)
                continue

            if action in ("new", "spawn", "crear", "lanzar"):
                # Uso: subagent new <name> <skill> "<tarea>"
                if len(tokens) < 4:
                    console.print(
                        f"[{RED}]Uso: subagent new <nombre> <skill> "
                        f"<descripción de la tarea>[/]"
                    )
                    continue
                sname = tokens[2].strip()
                rest = tokens[3].strip()
                # Separar skill de la tarea (skill es la primera palabra)
                rest_tokens = rest.split(maxsplit=1)
                if len(rest_tokens) < 2:
                    console.print(
                        f"[{RED}]Falta la descripción de la tarea. "
                        f"Uso: subagent new <nombre> <skill> "
                        f"<descripción>[/]"
                    )
                    continue
                sskill, stask = rest_tokens[0].strip(), rest_tokens[1].strip()
                stask = stask.strip('"\'')
                sub, err = spawn_subagent(sname, sskill, stask)
                if err:
                    console.print(f"[{RED}]✗ {err}[/]")
                else:
                    console.print()
                    console.print(Panel(
                        f"[bold {GREEN}]✓ Subagente '{sname}' lanzado[/]\n\n"
                        f"[bold {WHITE}]Skill:[/] {sskill}\n"
                        f"[bold {WHITE}]Target:[/] {ACTIVE_TARGET}\n"
                        f"[bold {WHITE}]Max turnos:[/] {sub.max_turns}\n"
                        f"[bold {WHITE}]Tarea:[/] {stask[:200]}"
                        f"{'…' if len(stask) > 200 else ''}\n\n"
                        f"[dim]Trabaja en background. Te aviso cuando "
                        f"termine. `subagent list` para ver progreso, "
                        f"`subagent kill {sname}` para pararlo.\n"
                        f"Log: {os.path.relpath(sub.log_path, WORKSPACE)}[/]",
                        border_style=GREEN, box=ROUNDED, padding=(1, 2),
                    ))
                continue

            if action in ("kill", "stop", "parar", "abort"):
                if len(tokens) < 3:
                    console.print(f"[{RED}]Uso: subagent kill <nombre>[/]")
                    continue
                sname = tokens[2].strip()
                if kill_subagent(sname):
                    console.print(
                        f"[bold {CYAN}]Kill solicitado a '{sname}'. "
                        f"Terminará tras el turno actual.[/]"
                    )
                else:
                    console.print(
                        f"[{RED}]No hay subagente activo con nombre '{sname}'.[/]"
                    )
                continue

            if action in ("show", "ver", "log"):
                if len(tokens) < 3:
                    console.print(f"[{RED}]Uso: subagent show <nombre>[/]")
                    continue
                sname = tokens[2].strip()
                with _subagents_lock:
                    sub = _subagents_registry.get(sname)
                if not sub:
                    console.print(f"[{RED}]No existe subagente '{sname}'.[/]")
                    continue
                _print_subagent_finished_panel(sub)
                continue

            console.print(
                f"[{RED}]Acciones: new <nombre> <skill> <tarea> · "
                f"list · show <nombre> · kill <nombre>[/]"
            )
            continue

        if first_word in ("proxy",):
            parts = user_input.split(maxsplit=1)
            sub = parts[1].strip().lower() if len(parts) > 1 else "status"
            global PROXY_MODE
            if sub in ("status", "estado", ""):
                _print_proxy_status()
            elif sub in ("on", "proxychains"):
                PROXY_MODE = "proxychains"
                console.print(f"[bold {GREEN}]✓ Proxy ON (proxychains).[/]")
                _print_proxy_status()
            elif sub in ("torify", "torsocks"):
                PROXY_MODE = "torify"
                console.print(f"[bold {GREEN}]✓ Proxy ON (torify).[/]")
                _print_proxy_status()
            elif sub in ("off", "no"):
                PROXY_MODE = "off"
                console.print(f"[bold {CYAN}]Proxy OFF — los comandos van directos.[/]")
            else:
                console.print(
                    f"[{RED}]Uso: proxy [on|off|status|proxychains|torify][/]"
                )
            continue

        if cmd_lower in ("skills", "habilidades"):
            print_skills_menu()
            continue

        if cmd_lower in ("compact", "compactar"):
            est_before = estimate_tokens(history)
            new_history = _compact_messages_for_call(list(history))
            # _compact_messages_for_call respeta el threshold automático.
            # Para el comando manual lo forzamos saltándonos el threshold:
            if new_history is history or estimate_tokens(new_history) == est_before:
                # Forzar truncado independientemente del % usado
                user_indices = [
                    i for i, m in enumerate(history) if m.get("role") == "user"
                ]
                if len(user_indices) <= COMPACT_KEEP_LAST_TURNS:
                    console.print(
                        f"[dim]Sin turnos suficientes para compactar "
                        f"(necesitas > {COMPACT_KEEP_LAST_TURNS} pares user/assistant).[/]"
                    )
                    continue
                cutoff = user_indices[-COMPACT_KEEP_LAST_TURNS]
                new_history = []
                touched = 0
                for i, m in enumerate(history):
                    if i == 0 or m.get("role") == "system" or i >= cutoff:
                        new_history.append(m)
                        continue
                    original = m.get("content", "") or ""
                    new_content = _compact_message_content(original)
                    if len(new_content) < len(original):
                        nm = dict(m)
                        nm["content"] = new_content
                        new_history.append(nm)
                        touched += 1
                    else:
                        new_history.append(m)
                if touched == 0:
                    console.print(f"[dim]No había nada que compactar.[/]")
                    continue
            est_after = estimate_tokens(new_history)
            saved = est_before - est_after
            history.clear()
            history.extend(new_history)
            save_session()
            console.print()
            console.print(Panel(
                f"[bold {GREEN}]✓ History compactado[/]\n"
                f"[{WHITE}]{est_before:,} → {est_after:,} tokens "
                f"(~{saved:,} ahorrados, {saved/max(est_before,1)*100:.1f}%)[/]\n\n"
                f"[dim]Los últimos {COMPACT_KEEP_LAST_TURNS} turnos quedan intactos. "
                f"Los resultados de comandos anteriores se mantienen sólo con "
                f"head+tail (medio sustituido por marcador). El _timeline.md "
                f"del target sigue guardando el original.[/]",
                border_style=GREEN,
                box=ROUNDED,
                padding=(1, 2),
            ))
            continue

        if first_word in ("aprende", "learn", "recuerda"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                console.print(
                    f"[{RED}]Uso: aprende <regla a recordar>[/]\n"
                    f"[dim]Ejemplo: aprende Cuando uses subfinder, "
                    f"desactiva proxychains con `agent:proxy off` antes; "
                    f"LD_PRELOAD lo ignora.[/]"
                )
                continue
            path = save_lesson(parts[1].strip())
            if not path:
                console.print(f"[bold {RED}]No se pudo guardar la lección.[/]")
                continue
            rel = os.path.relpath(path, WORKSPACE)
            console.print()
            console.print(Panel(
                f"[bold {GREEN}]✓ Lección guardada[/]\n\n"
                f"[{WHITE}]{parts[1].strip()}[/]\n\n"
                f"[dim]→ {rel}[/]\n"
                f"[dim]Se inyecta en el system prompt; el agente la "
                f"respetará en lo sucesivo.[/]",
                border_style=GREEN,
                box=ROUNDED,
                padding=(1, 2),
            ))
            continue

        if cmd_lower in ("lecciones", "lessons"):
            content = list_lessons_raw()
            has_entry = any(
                line.strip().startswith("- ")
                for line in content.splitlines()
            )
            if not has_entry:
                console.print(
                    f"[dim]Sin lecciones guardadas todavía. "
                    f"Usa `aprende <regla>` o el modelo lo hará con "
                    f"`agent:learn <regla>`.[/]"
                )
                continue
            console.print()
            console.print(Panel(
                Markdown(content),
                title=f"[bold {ORANGE}]Lecciones aprendidas[/]",
                border_style=ORANGE,
                box=ROUNDED,
                padding=(1, 2),
            ))
            continue

        if first_word in ("olvida", "forget"):
            parts = user_input.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                console.print(
                    f"[{RED}]Uso: olvida <fragmento_del_nombre_de_archivo>[/]\n"
                    f"[dim]Lista los nombres con `lecciones`.[/]"
                )
                continue
            result = forget_lesson(parts[1].strip())
            if result is None:
                console.print(
                    f"[bold {RED}]Sin coincidencias para "
                    f"'{parts[1].strip()}'.[/]"
                )
            elif isinstance(result, list):
                console.print(
                    f"[bold {ORANGE}]Varias coincidencias — sé más específico:[/]"
                )
                for m in result:
                    console.print(f"  · {m}")
            else:
                console.print(
                    f"[bold {GREEN}]✓ Lección olvidada:[/] {result}"
                )
            continue

        if first_word in ("tools_master", "master"):
            _print_tools_master_menu()
            continue

        if first_word in ("target", "objetivo"):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 1:
                # `target` sin args → menú
                print_targets_menu()
                continue

            sub = parts[1].strip()
            sub_lower = sub.lower()

            if sub_lower in ("reload", "recargar"):
                if not ACTIVE_TARGET:
                    console.print(f"[{RED}]No hay target activo para recargar.[/]")
                    continue
                ok, info = load_target(ACTIVE_TARGET)
                if ok:
                    console.print(
                        f"[bold {GREEN}]✓ Target '{ACTIVE_TARGET}' recargado[/] "
                        f"({info['n_files']} archivos, {_human_size(info['size'])})."
                    )
                    save_session()
                else:
                    console.print(f"[{RED}]Error al recargar: {info.get('error', '?')}[/]")
                continue

            if sub_lower in ("unload", "descargar"):
                if not ACTIVE_TARGET:
                    console.print(f"[{CYAN_DARK}]No hay target activo.[/]")
                    continue
                prev = ACTIVE_TARGET
                unload_target()
                console.print(f"[bold {CYAN}]Target '{prev}' descargado del contexto.[/]")
                save_session()
                continue

            # `target <nombre>` → cargar
            ok, info = load_target(sub)
            if ok:
                console.print(
                    f"[bold {GREEN}]✓ Target '{sub}' cargado[/] "
                    f"({info['n_files']} archivos, {_human_size(info['size'])})."
                )
                save_session()
            else:
                console.print(f"[{RED}]Error: {info.get('error', '?')}[/]")
            continue

        if first_word in ("use", "usar"):
            # `use <skill>` activa la skill.
            # `use <skill> <texto...>` activa la skill y envía <texto...> al modelo.
            tokens = user_input.split(maxsplit=2)
            skill_name = tokens[1].strip() if len(tokens) > 1 else ""
            extra_instruction = tokens[2].strip() if len(tokens) > 2 else ""

            if not skill_name:
                console.print(f"[{RED}]Uso: use <nombre_skill> [instrucción]  (alias: usar)[/]")
                continue
            if activate_skill(skill_name):
                master_loaded = os.path.isfile(
                    os.path.join(TOOLS_MASTER_DIR, f"{skill_name}.md")
                )
                master_tag = (
                    f" · [bold {PURPLE}]tools_master/{skill_name}.md cargada[/]"
                    if master_loaded else ""
                )
                console.print(
                    f"[bold {GREEN}]✓ Skill '{skill_name}' activada.[/] "
                    f"Activas: {', '.join(ACTIVE_SKILLS)}{master_tag}"
                )
                save_session()
                if extra_instruction:
                    # Reemitimos la instrucción como entrada normal del usuario.
                    # Reseteamos cmd_lower/first_word para que ningún handler
                    # posterior la capture (p.ej. "use recon resume" no debe
                    # activar la skill 'recon' Y luego ejecutar 'resume').
                    user_input = extra_instruction
                    cmd_lower = ""
                    first_word = ""
                    # Cae al bloque del modelo abajo.
                else:
                    continue
            else:
                console.print(
                    f"[{RED}]No se encontró skills/{skill_name}/skill.md[/]"
                )
                continue

        if first_word in ("unuse", "quitar"):
            parts = user_input.split(maxsplit=1)
            skill_name = parts[1].strip() if len(parts) > 1 else ""
            if not skill_name:
                console.print(f"[{RED}]Uso: unuse <nombre_skill> (alias: quitar)[/]")
                continue
            if deactivate_skill(skill_name):
                remaining = ", ".join(ACTIVE_SKILLS) if ACTIVE_SKILLS else "(ninguna)"
                console.print(
                    f"[bold {CYAN}]Skill '{skill_name}' desactivada.[/] "
                    f"Activas: {remaining}"
                )
                save_session()
            else:
                console.print(
                    f"[{RED}]La skill '{skill_name}' no estaba activa.[/]"
                )
            continue

        if cmd_lower in ("sessions", "sesiones"):
            print_sessions_menu()
            continue

        if first_word in ("resume", "retomar"):
            parts = user_input.split(maxsplit=1)
            if len(parts) > 1:
                target_id = parts[1].strip()
            else:
                saved = list_saved_sessions(limit=1)
                if not saved:
                    console.print(f"[{RED}]No hay sesiones guardadas para retomar.[/]")
                    continue
                target_id = saved[0]["id"]
            if resume_session(target_id):
                skills_str = ", ".join(ACTIVE_SKILLS) if ACTIVE_SKILLS else "(ninguna)"
                target_str = (
                    f" · target: [bold {PURPLE}]{ACTIVE_TARGET}[/]"
                    if ACTIVE_TARGET else ""
                )
                console.print(
                    f"[bold {GREEN}]✓ Sesión '{target_id}' retomada[/] "
                    f"({len(history)} mensajes · skills: {skills_str}{target_str})."
                )
                # Mostrar el último intercambio prompt/respuesta para
                # recordar al operador dónde se quedó la sesión.
                last_user, last_assistant = get_last_exchange()
                if last_user:
                    # Recorto a un tamaño legible (cap por bloque)
                    USER_CAP = 1500
                    ASS_CAP = 3000
                    user_disp = last_user.strip()
                    if len(user_disp) > USER_CAP:
                        user_disp = user_disp[:USER_CAP] + f"\n\n[…+{len(last_user) - USER_CAP} chars…]"
                    body = [f"[bold {CYAN}]Tú dijiste:[/]\n{user_disp}"]
                    if last_assistant:
                        ass_disp = last_assistant.strip()
                        if len(ass_disp) > ASS_CAP:
                            ass_disp = ass_disp[:ASS_CAP] + f"\n\n[…+{len(last_assistant) - ASS_CAP} chars…]"
                        body.append("")
                        body.append(f"[bold {ORANGE}]Agente respondió:[/]")
                        body.append(ass_disp)
                    else:
                        body.append("")
                        body.append(
                            f"[dim](el agente no llegó a responder a este "
                            f"último prompt)[/]"
                        )
                    console.print()
                    console.print(Panel(
                        "\n".join(body),
                        title=f"[bold {CYAN}]» Último intercambio de la sesión «[/]",
                        border_style=CYAN, box=ROUNDED, padding=(1, 2),
                    ))
                else:
                    console.print(
                        f"[dim]› Sesión sin intercambios previos del "
                        f"operador (history sólo system messages).[/]"
                    )
            else:
                console.print(f"[{RED}]No se pudo cargar la sesión '{target_id}'.[/]")
            continue

        if cmd_lower in ("new", "nueva", "nuevo"):
            start_new_session()
            console.print(f"[bold {GREEN}]✓ Sesión nueva iniciada (id: {SESSION_ID}).[/]")
            continue

        if first_word in ("report", "informe"):
            if not ACTIVE_TARGET:
                console.print(
                    f"[{RED}]No hay target activo.[/] Carga uno con [bold]target <nombre>[/] "
                    f"antes de generar un informe."
                )
                continue

            parts_r = user_input.split(maxsplit=1)
            extra_instructions = parts_r[1].strip() if len(parts_r) > 1 else ""

            # Asegurar que la skill 'reporting' está activa
            if "reporting" not in ACTIVE_SKILLS:
                if activate_skill("reporting"):
                    console.print(f"[dim]→ Activando skill 'reporting'.[/]")
                    save_session()

            reporting_prompt = (
                f"Genera AHORA el informe técnico completo del target activo "
                f"'{ACTIVE_TARGET}'. Usa TODA la información que tienes en el "
                f"contexto del target (scope.md, infrastructure.md, identities.md, "
                f"attack-surface.md, wifi.md, notes.md, _timeline.md) más los "
                f"comandos ejecutados durante la sesión.\n\n"
                f"REGLAS DURAS PARA ESTE TURNO:\n"
                f"- NO emitas ningún bloque [[TARGET_UPDATE]]. NO emitas COMANDO.\n"
                f"- Devuelve SOLO el informe completo en Markdown, sin comentarios "
                f"meta ni preámbulos. La primera línea debe ser el título principal "
                f"con `# `.\n"
                f"- Sigue la estructura de la skill 'reporting': Resumen ejecutivo, "
                f"Alcance/Metodología, Resumen de hallazgos (tabla), Detalle de "
                f"cada hallazgo (Título · ID · Severidad+CVSS · CWE/OWASP · "
                f"Descripción · Activos · Reproducción · Evidencia · Impacto · "
                f"Mitigación · Referencias), Anexos.\n"
                f"- Para cada hallazgo, basa CVSS/severidad en lo que tienes "
                f"evidenciado. Si algo no está confirmado, márcalo como "
                f"\"Informativa\" o \"A confirmar\" en lugar de inventar severidad.\n"
                f"- Si faltan datos críticos (no hay hallazgos confirmados, alcance "
                f"vacío, etc.), genera igualmente el documento con secciones "
                f"\"Pendiente de completar\" — el operador rellenará después.\n"
            )
            if extra_instructions:
                reporting_prompt += (
                    f"\nInstrucciones adicionales del operador: {extra_instructions}"
                )

            console.print(
                f"[bold {CYAN}]→ Generando informe del target '{ACTIVE_TARGET}'…[/]"
            )

            answer = ask_model(reporting_prompt)

            # Volcar a reports/
            os.makedirs(os.path.join(WORKSPACE, "reports"), exist_ok=True)
            fname = (
                f"informe-{ACTIVE_TARGET}-"
                f"{datetime.now().strftime('%Y%m%d-%H%M')}.md"
            )
            report_path = os.path.join(WORKSPACE, "reports", fname)
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write((answer or "").strip() + "\n")
            except OSError as e:
                console.print(f"[{RED}]Error al escribir el informe: {e}[/]")
                continue

            # HOOK on_report — indexado, hash, etc. No bloquea aunque falle.
            run_hook("on_report", _build_hook_ctx(
                report_path=report_path,
                report_name=fname,
            ))

            size_kb = os.path.getsize(report_path) / 1024
            n_lines = (answer or "").count("\n") + 1

            console.print()
            console.print(Panel(
                f"[bold {GREEN}]✓ Informe generado[/]\n"
                f"[{WHITE}]{report_path}[/]\n\n"
                f"[dim]{size_kb:.1f} KB · {n_lines} líneas[/]\n\n"
                f"[dim]Convertir a PDF:[/]\n"
                f"  [bold]pandoc {os.path.relpath(report_path, WORKSPACE)} "
                f"-o {os.path.relpath(report_path, WORKSPACE)[:-3]}.pdf "
                f"--pdf-engine=xelatex[/]",
                title=f"[bold {ORANGE}]Informe técnico[/]",
                border_style=GREEN,
                box=ROUNDED,
                padding=(1, 2),
            ))
            continue

        try:
            # Auto-attach de la selección activa en VSCode/Cursor (si la
            # extensión maxiwatt-agent está corriendo y hay selección
            # fresca <120s). Equivale a haber escrito `@archivo:L43-L45`
            # a mano. Solo se aplica si el operador no lo mencionó ya.
            user_input, _auto_attached = vscode_auto_attach(user_input)
            if _auto_attached:
                console.print(
                    f"[dim]› auto-attached: selección actual del editor "
                    f"como contexto[/]"
                )

            # Resolver menciones @archivo (selector de contexto). Si el usuario
            # escribió @<nombre>, buscamos en el workspace y, si hay varias,
            # le preguntamos cuál usar. El contenido de los archivos elegidos
            # se inyecta como bloques de contexto delante de la petición.
            effective_input, _ = resolve_at_mentions(user_input)

            # ask_model imprime el answer en directo (streaming) o como Markdown
            # al final si STREAM_OUTPUT está desactivado. No volvemos a imprimirlo.
            answer = ask_model(effective_input)

            command = extract_command(answer)

            if command:
                # run_command muestra el panel con el comando propuesto, luego
                # ejecuta. En modo stream, salida en directo. En modo batch
                # (STREAM_OUTPUT=False), spinner durante la ejecución y al
                # terminar mostramos un panel con la salida completa.
                result = run_command(command)
                first_rc = LAST_COMMAND_RC

                # AUTOMÁTICO: append a _timeline.md (bitácora narrativa) y a
                # _runs.md (checklist estructurada para anti-duplicación).
                # No depende del modelo. Garantiza que nada se pierde.
                if ACTIVE_TARGET:
                    timeline_path = append_timeline_entry(command, result)
                    runs_path = append_runs_entry(command, first_rc)
                    notes = []
                    if timeline_path:
                        notes.append(
                            os.path.relpath(timeline_path, WORKSPACE)
                        )
                    if runs_path:
                        notes.append(
                            os.path.relpath(runs_path, WORKSPACE)
                        )
                    if notes:
                        console.print(
                            f"[dim]› anotado en {' · '.join(notes)}[/]"
                        )

                # AUTOPILOT de troubleshooting: si el comando falló y el modo
                # está activo, entrar al bucle de auto-fix antes de pasar al
                # análisis del modelo.
                if (TROUBLESHOOT_AUTOPILOT
                        and first_rc != 0 and first_rc != -1):
                    ts_outcome = troubleshoot_loop(command, result)
                    _print_troubleshoot_summary(ts_outcome)
                    # Reemplazamos el `result` que va al análisis con el
                    # output final tras el bucle (el modelo verá el estado
                    # post-fix, no el original).
                    if ts_outcome["resolved"]:
                        result = ts_outcome["final_output"]
                    else:
                        # En caso de no resuelto, encadenamos para que el
                        # modelo lo explique al usuario en el análisis.
                        result = (
                            f"[Comando original `{command}` falló y el autopilot "
                            f"no pudo resolverlo tras {len(ts_outcome['attempts'])} "
                            f"intentos.]\n\n{ts_outcome['final_output']}"
                        )

                if not STREAM_COMMAND_OUTPUT:
                    # Si no hubo streaming, el usuario no vio nada — mostramos
                    # el panel con la salida completa. Si hubo streaming,
                    # ya lo vio en directo y el panel sería redundante.
                    console.print()
                    console.print(Panel(
                        Text.from_ansi(result),
                        title=f"[bold {ORANGE}]Resultado[/bold {ORANGE}]",
                        border_style=ORANGE,
                        box=ROUNDED,
                    ))

                # COMANDO CANCELADO por el operador (rc=-1): no pedimos análisis
                # al modelo. Una cancelación es una decisión consciente del
                # operador — analizar "Comando cancelado por el usuario." sólo
                # produce bucles donde el modelo asume que el comando sigue
                # ejecutándose y propone variantes que el operador no quiere.
                if first_rc == -1:
                    cancel_note = (
                        f"[Comando cancelado por el operador — sin análisis "
                        f"automático. Cuando quieras retomar, escribe la "
                        f"siguiente acción o pide 'siguientes pasos'.]"
                    )
                    console.print(f"[dim]› {cancel_note}[/]")
                    # Persistimos en history el resultado para trazabilidad,
                    # pero NO disparamos analysis_prompt.
                    history.append({
                        "role": "user",
                        "content": f"Resultado del comando:\n{result}\n\n{cancel_note}"
                    })
                    save_session()
                    continue

                history.append({
                    "role": "user",
                    "content": f"Resultado del comando:\n{result}"
                })

                analysis_prompt = (
                    "Analiza la salida anterior en detalle: extrae y explica los datos "
                    "relevantes (IPs, puertos, servicios, versiones, usuarios, hashes, "
                    "archivos, errores, hallazgos). Termina con un bloque "
                    "**Siguientes pasos:** que liste 2-4 acciones concretas y "
                    "priorizadas (1 línea cada una). Si hay un siguiente paso obvio "
                    "y barato, propónlo además como bloque `COMANDO:` al final."
                )
                if ACTIVE_TARGET:
                    analysis_prompt += (
                        f"\n\nOBLIGATORIO — Persistencia del trabajo en target '{ACTIVE_TARGET}':\n"
                        f"Emite AL MENOS UN bloque [[TARGET_UPDATE: archivo.md]] al final de "
                        f"tu respuesta con los hallazgos de esta iteración. Mapeo recordatorio:\n"
                        f"  - hosts/puertos/servicios/endpoints/subdominios  → attack-surface.md\n"
                        f"  - DNS/ASN/hosting/tecnologías/certs              → infrastructure.md\n"
                        f"  - correos/usuarios/repos/leaks                   → identities.md\n"
                        f"  - SSIDs/BSSIDs/wifi                              → wifi.md\n"
                        f"  - decisiones, TODOs, hilos sueltos, atajos       → notes.md\n"
                        f"Si la salida fue vacía o no aportó nada accionable, emite al menos "
                        f"un bloque hacia notes.md con una entrada del tipo:\n"
                        f"  ## [YYYY-MM-DD HH:MM] <herramienta> · sin hallazgos\n"
                        f"  Detalle breve de por qué (timeout, host no responde, etc.).\n"
                        f"De este modo el informe final tendrá trazabilidad completa de la fase."
                    )

                ask_model(analysis_prompt)

        except KeyboardInterrupt:
            print()
            continue
        except Exception as e:
            console.print(Panel(
                f"[bold {RED}]Error:[/bold {RED}] {e}",
                border_style=RED,
                box=ROUNDED
            ))


if __name__ == "__main__":
    main()

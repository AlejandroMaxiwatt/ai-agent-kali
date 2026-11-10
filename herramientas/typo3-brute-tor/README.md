# typo3-brute-tor

Herramienta de prueba de credenciales contra el formulario de login de TYPO3.
Envía combinaciones de `users.txt` × `passwords.txt`, rota el circuito de Tor
cada N peticiones y registra las respuestas que no muestran el marcador de
error como candidatas para revisión manual.

## Advertencia de autorización

Esta herramienta genera tráfico de autenticación masivo contra un objetivo
real. **Úsala solo con autorización explícita y por escrito del propietario
del sistema**, dentro de un alcance acordado. El volumen de intentos y la
rotación de circuitos Tor pueden interpretarse como un ataque no autorizado
si se ejecutan fuera de un engagement.

## Requisitos

- Python 3 y `requests`.
- Tor escuchando en `127.0.0.1:9050` (SOCKS5) para el tráfico HTTP.
- `ControlPort 9051` accesible para rotar circuitos (`NEWNYM`). Si no está
  configurado, la rotación se omite y el script continúa.
- Listas en la raíz del repositorio:
  - `users.txt` — un usuario por línea.
  - `passwords.txt` — una contraseña por línea.

Ambas listas están en `.gitignore` y no deben versionarse.

## Uso

```bash
# Desde la raíz del repositorio
python3 herramientas/typo3-brute-tor/typo3_brute_tor.py
```

La configuración (target, endpoint, delays, rotación) está al principio del
script. Ajusta `TARGET`, `LOGIN_URL`, `MIN_DELAY`, `MAX_DELAY` y
`NEW_CIRCUIT_EVERY_N_REQUESTS` antes de ejecutarlo.

## Salida

- Progreso y errores por `stderr`.
- Candidatas (`usuario:contraseña` + código HTTP) por `stdout`.
- El script no guarda resultados en disco; redirige la salida si necesitas
  conservarlos.

## Nota de organización

El script resuelve `users.txt` y `passwords.txt` desde la raíz del repo
(`REPO_ROOT`), no desde su propio directorio. Así puede moverse dentro de
`herramientas/` sin romper las rutas.

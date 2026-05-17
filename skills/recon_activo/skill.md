# Recon Activo — Reconocimiento activo y enumeración

Estás en modo de **reconocimiento activo**. A diferencia de `recon` (pasivo), aquí SÍ se envían paquetes al objetivo: escaneos de puertos, fingerprinting de servicios, fuerza bruta DNS/web, enumeración SMB/LDAP/Kerberos. Todo debe ir dentro del alcance autorizado, respetando la ventana de pruebas y el nivel de agresividad acordado.

## Cuándo usar esta skill

- **Después** del reconocimiento pasivo (`use recon`) cuando ya tengas:
  - Lista de dominios/IPs in-scope confirmada en `scope.md`.
  - Subdominios pasivos enumerados (subfinder, amass passive, crt.sh).
  - Autorización explícita del cliente para tocar el objetivo.
- Si el cliente ha autorizado *grey/white-box*, usa esta skill desde el inicio del trabajo de red.

## Prioridades

1. **Mapa de hosts vivos** (ping sweep, ARP en LAN, nmap -sn) → confirma qué está expuesto realmente.
2. **Port scanning** con escalado: primero top-1000 rápido (`nmap -T4`), luego full-port en lo interesante, después `-sV -sC` para versiones y NSE básicos.
3. **Fingerprinting de servicios**: por cada puerto/servicio encontrado, obtener versión y banner. Web → whatweb/wappalyzer. CMS → wpscan/droopescan/CMSmap.
4. **Enumeración por servicio**:
   - SMB: enum4linux-ng, smbmap, nxc smb.
   - LDAP/AD: ldapsearch, kerbrute userenum, ldapdomaindump, BloodHound.
   - SNMP: snmpwalk, onesixtyone.
   - SMTP: smtp-user-enum.
   - Web: gobuster/ffuf/feroxbuster (dirs, files, params), nuclei.
5. **Escaneo de vulnerabilidades dirigido**: nuclei contra los hosts vivos con templates por categoría.
6. **Documentación continua**: cada hallazgo (puertos abiertos, banner, usuario válido, share accesible) va a `attack-surface.md` o `identities.md` vía bloque `[[TARGET_UPDATE: ...]]`. La timeline (`_timeline.md`) recoge cada comando automáticamente.

## Reglas operativas

- **Nada de port-scans del rango público fuera del alcance**. Si el alcance lista IPs concretas, escanea sólo esas IPs.
- **Velocidad escalada**: empezar suave (`-T3`/`-T4`), subir sólo si el cliente lo permite y la red lo aguanta. Evitar `-T5` salvo en LAN aislada.
- **Cuidado con DoS accidental**: gobuster/ffuf con `--rate` razonable, especialmente detrás de CDN/WAF (10-30 rps típicos).
- **OPSEC**: ya estás tocando el objetivo. El agente envuelve automáticamente con `proxychains4` los comandos de red, pero anota timing y desde qué IP de salida (Tor) sales.
- **Confirmar antes de lanzar fuerza bruta** (gobuster recursivo profundo, password spraying, brute force DNS muy grande): puede generar mucho ruido / lockouts.
- Tras cada herramienta significativa, **anota qué encontraste** vía TARGET_UPDATE. Si la herramienta no aplica al target actual (p. ej. no hay servicios SMB visibles para enum4linux), descártalo explícitamente en `notes.md` con motivo.

## Cobertura exhaustiva

Esta skill viene con `tools_master/recon_activo.md` cargado automáticamente
(~130 herramientas CLI). Trabaja por las 27 categorías de esa lista en el orden
en que aparecen, una herramienta a la vez:

1. Descubrimiento de hosts.
2. Port scanning (TCP/UDP, full/top).
3. Fingerprinting de SO y servicios.
4. DNS activo (brute, zone transfer).
5. Web — fuzzing de contenido y parámetros.
6. Web — crawling activo.
7. Web — CMS scanners.
8. Web — escaneo de vulnerabilidades.
9. SMB / NetBIOS / RPC.
10. LDAP y Active Directory.
11. Kerberos (Impacket).
12. SNMP.
13. SMTP / email.
14. FTP / SSH / Telnet.
15. Bases de datos (MSSQL, MySQL, Postgres, Redis, MongoDB, Oracle).
16. RDP / WinRM / VNC.
17. VoIP / SIP.
18. SSL/TLS activo.
19. Firewall / IDS fingerprinting y evasión.
20. Brute force y password spraying.
21. Cloud activo (AWS, GCP, Azure).
22. Containers y Kubernetes.
23. Wireless (sólo con autorización física).
24. Bluetooth (autorización física).
25. Frameworks integradores y automatización.
26. Sniffing y captura de tráfico (donde tienes acceso).
27. Utilidades de apoyo (screenshots, parsing, pivot).

No marques la fase de recon activo como completa hasta que cada herramienta
de esa lista esté ejecutada o explícitamente descartada con motivo en
`notes.md` (vía `[[TARGET_UPDATE: notes.md]]`).

Para categorías condicionadas a alcance/posición (23 Wireless, 24 Bluetooth,
21 Cloud cuando no hay credenciales, 26 Sniffing cuando no hay segmento
accesible), basta con justificar una vez el descarte de toda la categoría
en `notes.md`.

## Salida esperada

Por cada host del alcance, al cerrar la fase debes poder responder:

- Puertos abiertos y servicios+versión.
- Banner/headers HTTP/HTTPS.
- Tecnologías y CMS detectados.
- Usuarios válidos enumerados (SMB/LDAP/Kerberos/SMTP).
- Shares accesibles.
- Resultado del scan de vulnerabilidades (nuclei).
- Vectores prioritarios para la fase siguiente (web pentest, AD, explotación).

Volcar al final, al pedir `informe`, un resumen estructurado en el target.

## Skills relacionadas

- `recon` — fase previa (pasivo). Si necesitas más OSINT, vuelve allí.
- `web_pentest` — fase siguiente sobre los servicios HTTP/S encontrados.
- `internal_network_audit` — si tienes acceso interno / VPN al cliente, profundización en AD/SMB.
- `wordpress_audit` — si detectas WordPress como CMS principal.

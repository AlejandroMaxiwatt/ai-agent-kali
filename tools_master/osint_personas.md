# Herramientas de OSINT sobre Personas — CLI Kali Linux

Recon de empleados, ejecutivos y contactos de la organización target.
Exclusivamente fuentes públicas. Para usar dentro de un engagement
autorizado.

> **Aviso legal**: cumplir GDPR/CCPA. No combinar PII sin necesidad
> operativa. Documentar la finalidad de cada dato recolectado.

---

## 1. Email Discovery (a partir de dominio)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **theHarvester** | Preinstalado | `theHarvester -d empresa.com -b all -f harvest_empresa.html` |
| **emailfinder** | `pip install emailfinder --break-system-packages` | `emailfinder -d empresa.com` |
| **hunter.io (curl)** | Preinstalado | `curl "https://api.hunter.io/v2/domain-search?domain=empresa.com&api_key=KEY"` |
| **crosslinked** | `pip install crosslinked --break-system-packages` | `crosslinked -f '{first}.{last}@empresa.com' -t '<nombre empresa>' -j 3` |
| **phonebook.cz (web)** | curl | `curl "https://phonebook.cz/api/v2/email/empresa.com"` (API privada) |
| **skymem.info** | curl/manual | búsqueda web de emails por dominio |

---

## 2. Validación y Enrichment de Email

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **holehe** | `pip install holehe --break-system-packages` | `holehe carsten.pies@empresa.com` |
| **socialscan** | `pip install socialscan --break-system-packages` | `socialscan -e tanja@empresa.com -u tanjaf` |
| **emailrep (curl)** | Preinstalado | `curl "https://emailrep.io/tanja@empresa.com"` (API gratis con rate-limit) |
| **mosint** | `go install github.com/alpkeskin/mosint/v3/cmd/mosint@latest` | `mosint tanja@empresa.com` (multi-source) |
| **gitemails (git logs)** | curl + jq | `curl -s "https://api.github.com/repos/<org>/<repo>/commits?per_page=100" \| jq -r '.[].commit.author.email' \| sort -u` |
| **ghunt (Google OSINT)** | `pip install ghunt --break-system-packages` | `ghunt email tanja@gmail.com` (necesita cookies extraídas) |

---

## 3. Breaches / Credenciales Filtradas

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **h8mail** | `pip install h8mail --break-system-packages` | `h8mail -t tanja@empresa.com --config h8mail.ini` |
| **HIBP (curl)** | Preinstalado | `curl -s "https://haveibeenpwned.com/api/v3/breachedaccount/tanja@empresa.com" -H "hibp-api-key: KEY"` |
| **DeHashed (curl)** | Preinstalado | `curl -s "https://api.dehashed.com/search?query=email:tanja@empresa.com" -u "user@x.com:API_KEY"` |
| **IntelX (curl)** | Preinstalado | `curl -X POST "https://2.intelx.io/intelligent/search" -H "x-key: KEY" -d '{"term":"tanja@empresa.com"}'` |
| **LeakSearch** | `git clone https://github.com/JoelGMSec/LeakSearch` | `python3 LeakSearch.py -k tanja@empresa.com` |
| **pwndb** | `git clone https://github.com/davidtavarez/pwndb` | `python3 pwndb.py --target tanja@empresa.com` |
| **Hudson Rock (infostealer)** | curl | `curl -s "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-email?email=tanja@empresa.com"` |
| **breachdirectory (curl)** | Preinstalado | `curl -s "https://breachdirectory.org/api/?term=tanja@empresa.com"` (rate-limit) |

---

## 4. Username Enumeration en Plataformas

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **sherlock** | Preinstalado | `sherlock tanjaf maxiwatt_pies --print-found` |
| **maigret** | `pip install maigret --break-system-packages` | `maigret tanjaf --reports-path ./maigret/ --html` |
| **socialscan** | `pip install socialscan --break-system-packages` | `socialscan -u tanjaf maxiwatt` |
| **whatsmyname (json)** | curl | `curl -s "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"` (referencia local) |
| **userrecon** | `git clone https://github.com/thelinuxchoice/userrecon` | `bash userrecon.sh -u tanjaf` |
| **blackbird** | `git clone https://github.com/p1ngul1n0/blackbird` | `python3 blackbird.py -u tanjaf` |

---

## 5. LinkedIn / XING / Redes Profesionales

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **linkedin2username** | `git clone https://github.com/initstring/linkedin2username` | `python3 linkedin2username.py -c "GC Heat" -u attacker@x.com -p pass` (cookies) |
| **crosslinked** | `pip install crosslinked --break-system-packages` | `crosslinked -f '{first}.{last}@empresa.com' -t 'GC Heat' -j 3` |
| **inteltechniques (referencia)** | curl | bookmarks de búsquedas Google dork sobre LinkedIn público |
| **XING search (manual)** | navegador + Google dork | `site:xing.com "GC Heat"` para perfiles públicos |
| **theHarvester -b linkedin** | Preinstalado | `theHarvester -d empresa.com -b linkedin -l 500 -f linkedin.html` |

---

## 6. GitHub / GitLab / Repos Públicos

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **gitleaks** | `sudo apt install gitleaks` | `gitleaks detect --source=https://github.com/empresa --report-path=leaks.json` |
| **trufflehog** | `pip install trufflehog --break-system-packages` | `trufflehog github --org=empresa --json` |
| **gitdorker** | `git clone https://github.com/obheda12/GitDorker` | `python3 GitDorker.py -t GH_TOKEN -d dorks.txt -q empresa.com` |
| **gh search (API)** | `sudo apt install gh` | `gh search code "empresa.com" --owner=<user>` |
| **github-search (commits)** | curl | `curl -s "https://api.github.com/search/commits?q=author-email:tanja@empresa.com" -H "Accept: application/vnd.github.cloak-preview"` |
| **gitrob** | `go install github.com/michenriksen/gitrob@latest` | `gitrob empresa` |
| **shhgit** | `git clone https://github.com/eth0izzle/shhgit` | `./shhgit --silent --search-query empresa.com` |

---

## 7. Twitter/X · Mastodon · Telegram · Reddit

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **twint** (legacy, broken) | `pip install twint --break-system-packages` | `twint -u tanjaf --limit 200` (no funciona post-API-cambios) |
| **snscrape** | `pip install snscrape --break-system-packages` | `snscrape --max-results 100 twitter-user tanjaf` |
| **telepathy** | `pip install telepathy --break-system-packages` | `telepathy -t empresa_telegram_channel` |
| **tgstat (curl)** | Preinstalado | `curl "https://api.tgstat.com/channels/search?query=empresa&token=KEY"` |
| **lyzem (search)** | curl | `curl "https://lyzem.com/search?q=empresa.com"` |
| **reddit (PRAW alt)** | `pip install pushshift-py --break-system-packages` | `curl "https://api.pushshift.io/reddit/search/comment/?author=tanjaf"` |

---

## 8. Registros Corporativos y Financieros (Europa / Global)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **Handelsregister.de (DE)** | curl | `curl -s "https://www.handelsregister.de/rp_web/normalesuche.do?Suchtext=GC+Heat"` |
| **OpenCorporates** | curl | `curl -s "https://api.opencorporates.com/v0.4/companies/search?q=GC+Heat&api_token=KEY"` |
| **North Data (DE)** | curl | `curl -s "https://www.northdata.com/search?term=GC+Heat"` |
| **Societe.com (FR)** | curl | manual via search |
| **Companies House (UK)** | curl + API | `curl -s "https://api.company-information.service.gov.uk/search/companies?q=Maxiwatt" -u "API_KEY:"` |
| **SEC EDGAR (US)** | curl | `curl -s "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=Maxiwatt"` |
| **GLEIF (LEI)** | curl | `curl -s "https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=GC+Heat"` |

---

## 9. Frameworks Integradores OSINT

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **theHarvester** | Preinstalado | Ver §1 (multi-source: emails + nombres + hosts) |
| **spiderfoot** | `pip install spiderfoot --break-system-packages` | `sf -s "tanja@empresa.com" -t EMAILADDR -m sfp_haveibeenpwned -o results.json` |
| **recon-ng** | Preinstalado | `recon-cli -w empresa -C "marketplace install all; use recon/profiles-profiles/profiler; options set SOURCE tanjaf; run"` |
| **maltego-cli (transforms)** | Preinstalado (interfaz GUI; algunos transforms vía API) | API REST custom |
| **OSINT Industries (curl)** | API | `curl -X POST "https://api.osint.industries/v2/request?type=email&query=tanja@empresa.com" -H "api-key: KEY"` |

---

## 10. Reverse Image / Reconocimiento Facial

> **Reservado**: uso con autorización explícita en RoE. Implicación
> jurídica alta. Documenta finalidad.

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **Google Lens (manual)** | navegador | reverse image search |
| **Yandex Images (curl)** | Preinstalado | `curl -F image=@foto.jpg https://yandex.com/images/search?rpt=imageview` (manual via web) |
| **TinEye (API)** | curl | `curl -F image=@foto.jpg "https://api.tineye.com/rest/search/" -u "key:secret"` |
| **PimEyes (web)** | navegador | sólo manual, comercial |
| **FaceCheck.ID (web)** | navegador | sólo manual, comercial |

---

## 11. Geolocalización Pasiva

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **Wigle.net (curl)** | Preinstalado | `curl "https://api.wigle.net/api/v2/network/search?ssid=GC-Heat-Office" -u "TOKEN:"` |
| **Creepy** | `sudo apt install creepy` | (GUI; útil para social media geotag) |
| **Overpass Turbo (OSM)** | curl | `curl -d "[out:json];node['name'='GC Heat'];out;" "https://overpass-api.de/api/interpreter"` |
| **EXIF en fotos** | `sudo apt install libimage-exiftool-perl` | `exiftool -GPSLatitude -GPSLongitude *.jpg` |

---

## 12. Dark Web / Paste Sites

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **onionsearch** | `pip install onionsearch --break-system-packages` | `onionsearch -q "empresa.com" --len 100` |
| **torify + curl (Ahmia)** | `sudo apt install tor` | `torify curl -s "https://ahmia.fi/search/?q=empresa.com"` |
| **psbdmp (Pastebin dumps)** | curl | `curl -s "https://psbdmp.ws/api/search/tanja@empresa.com"` |
| **IntelX (curl)** | Idem §3 | Cubre pastes + dark web + breaches con una sola API |
| **Hudson Rock Cavalier** | Idem §3 | Cubre infostealer logs del dark web |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Preinstalado en Kali** | ~12 herramientas |
| **Instalable con pip/apt** | ~25 herramientas |
| **Git clone / Go install** | ~15 herramientas |
| **APIs externas (curl)** | ~20 servicios |
| **Total** | **~70 herramientas/servicios** |

---

## Alcance de esta lista

OSINT humano sobre fuentes públicas. NO incluye:
- Contacto activo con personas (eso es `social_engineering`).
- Recon de infraestructura (eso es `recon` / `recon_activo`).
- Acceso a redes sociales detrás de login del cliente.

Cumplir SIEMPRE GDPR/CCPA/LGPD. Documentar finalidad operativa de cada
dato recolectado para defensa legal del engagement.

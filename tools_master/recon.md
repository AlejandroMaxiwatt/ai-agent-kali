# Herramientas de Reconocimiento Pasivo/Semi-Pasivo Ejecutables desde Terminal Kali Linux

Exclusivamente herramientas que un modelo agéntico puede ejecutar desde CLI sin necesidad de navegador ni interfaz gráfica.

---

## 1. Frameworks de Reconocimiento Automatizado

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **recon-ng** | `sudo apt install recon-ng` (preinstalado) | `recon-cli -w gc-heat -C "marketplace install all; use recon/domains-hosts/hackertarget; options set SOURCE gc-heat.de; run"` |
| **theHarvester** | `sudo apt install theharvester` (preinstalado) | `theHarvester -d gc-heat.de -b all -f output` |
| **spiderfoot** | `pip install spiderfoot --break-system-packages` | `sf -s gc-heat.de -t DOMAIN_NAME -m all -o results.json` |
| **reconspider** | `sudo apt install reconspider` | `reconspider -h` |
| **datasploit** | `git clone https://github.com/DataSploit/datasploit` | `python3 datasploit.py -d gc-heat.de` |

---

## 2. Enumeración de Dominios y Subdominios

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **amass** | `sudo apt install amass` (preinstalado) | `amass enum -passive -d gc-heat.de -o amass_subs.txt` |
| **subfinder** | `sudo apt install subfinder` | `subfinder -d gc-heat.de -all -o subfinder.txt` |
| **assetfinder** | `go install github.com/tomnomnom/assetfinder@latest` | `assetfinder --subs-only gc-heat.de` |
| **findomain** | `sudo apt install findomain` | `findomain -t gc-heat.de -o` |
| **sublist3r** | `sudo apt install sublist3r` | `sublist3r -d gc-heat.de -o sublist3r.txt` |
| **knockpy** | `pip install knockpy --break-system-packages` | `knockpy gc-heat.de` |
| **puredns** | `go install github.com/d3mondev/puredns/v2@latest` | `puredns bruteforce wordlist.txt gc-heat.de` |
| **massdns** | `sudo apt install massdns` | `massdns -r resolvers.txt -t A -o S domains.txt` |
| **shuffledns** | `go install github.com/projectdiscovery/shuffledns/cmd/shuffledns@latest` | `shuffledns -d gc-heat.de -w wordlist.txt -r resolvers.txt` |

---

## 3. DNS Intelligence

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **dig** | Preinstalado | `dig any gc-heat.de`, `dig axfr gc-heat.de @ns1.example.com` |
| **host** | Preinstalado | `host -a gc-heat.de` |
| **nslookup** | Preinstalado | `nslookup -type=any gc-heat.de` |
| **dnsenum** | `sudo apt install dnsenum` (preinstalado) | `dnsenum gc-heat.de` |
| **dnsrecon** | `sudo apt install dnsrecon` (preinstalado) | `dnsrecon -d gc-heat.de -t std,brt,axfr` |
| **dnsx** | `go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest` | `cat subs.txt \| dnsx -silent -a -resp` |
| **fierce** | `sudo apt install fierce` (preinstalado) | `fierce --domain gc-heat.de` |
| **dnstwist** | `sudo apt install dnstwist` | `dnstwist gc-heat.de` |
| **dnsmap** | `sudo apt install dnsmap` | `dnsmap gc-heat.de` |

---

## 4. WHOIS e Infraestructura de Red

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **whois** | Preinstalado | `whois gc-heat.de`, `whois 185.243.132.173` |
| **curl (APIs)** | Preinstalado | `curl -s "https://api.bgpview.io/search?query_term=gc-heat"` |
| **traceroute** | Preinstalado | `traceroute gc-heat.de` |
| **mtr** | `sudo apt install mtr` | `mtr -n gc-heat.de` |

---

## 5. Fingerprinting Web y Tecnológico

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **whatweb** | `sudo apt install whatweb` (preinstalado) | `whatweb -a 3 https://gc-heat.de` |
| **httpx** | `go install github.com/projectdiscovery/httpx/cmd/httpx@latest` | `cat subs.txt \| httpx -title -status-code -tech-detect -server` |
| **wafw00f** | `sudo apt install wafw00f` (preinstalado) | `wafw00f https://gc-heat.de` |
| **webanalyze** | `go install github.com/rverton/webanalyze/cmd/webanalyze@latest` | `webanalyze -host https://gc-heat.de` |
| **curl** | Preinstalado | `curl -sI https://gc-heat.de` |

---

## 6. Motores de Búsqueda de Dispositivos (vía CLI/API)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **shodan** | `pip install shodan --break-system-packages` | `shodan host 185.243.132.173`, `shodan search "ssl.cert.subject.cn:gc-heat.de"` |
| **censys** | `pip install censys --break-system-packages` | `censys search "services.tls.certificates.leaf.names: gc-heat.de"` |
| **curl + APIs** | Preinstalado | `curl -s "https://internetdb.shodan.io/185.243.132.173"` |

---

## 7. Certificados SSL/TLS

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **sslscan** | `sudo apt install sslscan` (preinstalado) | `sslscan gc-heat.de` |
| **testssl.sh** | `sudo apt install testssl.sh` | `testssl.sh gc-heat.de` |
| **openssl** | Preinstalado | `openssl s_client -connect gc-heat.de:443 </dev/null 2>/dev/null \| openssl x509 -noout -text` |
| **sslyze** | `pip install sslyze --break-system-packages` | `sslyze gc-heat.de` |
| **curl (crt.sh)** | Preinstalado | `curl -s "https://crt.sh/?q=%25.gc-heat.de&output=json" \| jq -r '.[].name_value' \| sort -u` |

---

## 8. Email OSINT

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **theHarvester** | Preinstalado | `theHarvester -d gc-heat.de -b all` |
| **holehe** | `pip install holehe --break-system-packages` | `holehe carsten.pies@gc-heat.de` |
| **h8mail** | `pip install h8mail --break-system-packages` | `h8mail -t carsten.pies@gc-heat.de` |
| **infoga** | `git clone https://github.com/m4ll0k/Infoga` | `python3 infoga.py -d gc-heat.de -s all` |
| **emailfinder** | `pip install emailfinder --break-system-packages` | `emailfinder -d gc-heat.de` |
| **crosslinked** | `pip install crosslinked --break-system-packages` | `crosslinked -f '{first}.{last}@gc-heat.de' -t 'GC Heat' -j 3` |

---

## 9. Credenciales Filtradas y Breaches

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **h8mail** | `pip install h8mail --break-system-packages` | `h8mail -t @gc-heat.de --config h8mail_config.ini` |
| **pwndb** | `git clone https://github.com/davidtavarez/pwndb` | `python3 pwndb.py --target @gc-heat.de` |
| **LeakSearch** | `git clone https://github.com/JoelGMSec/LeakSearch` | `python3 LeakSearch.py -k gc-heat.de` |
| **curl (Hudson Rock)** | Preinstalado | `curl -s "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-domain?domain=gc-heat.de"` |
| **curl (HIBP)** | Preinstalado | `curl -s "https://haveibeenpwned.com/api/v3/breachedaccount/user@gc-heat.de" -H "hibp-api-key: KEY"` |

---

## 10. Metadata de Documentos

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **metagoofil** | `sudo apt install metagoofil` | `metagoofil -d gc-heat.de -t pdf,doc,xls,ppt -l 100 -n 50 -o ./meta/` |
| **exiftool** | `sudo apt install libimage-exiftool-perl` (preinstalado) | `exiftool -r ./docs/ \| grep -iE "author\|creator\|producer\|company"` |
| **mat2** | `sudo apt install mat2` | `mat2 -s document.pdf` |
| **pdfinfo** | `sudo apt install poppler-utils` | `pdfinfo documento.pdf` |
| **strings** | Preinstalado | `strings -n 8 documento.pdf \| grep -iE "author\|user\|password\|path"` |

---

## 11. Google Dorking Automatizado

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **googler** | `sudo apt install googler` | `googler -n 20 'site:gc-heat.de filetype:pdf'` |
| **pagodo** | `git clone https://github.com/opsdisk/pagodo` | `python3 pagodo.py -d gc-heat.de -g dorks.txt` |
| **dorkscout** | `go install github.com/R4yGM/dorkscout@latest` | `dorkscout -d gc-heat.de -e google` |
| **ghdb-scrape** | `git clone https://github.com/nccgroup/ghdb-scrape` | `python3 ghdb_scrape.py -d gc-heat.de` |

---

## 12. Username OSINT

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **sherlock** | `sudo apt install sherlock` (preinstalado) | `sherlock osteffens mgraumann cpies tweber ckelm` |
| **maigret** | `pip install maigret --break-system-packages` | `maigret osteffens mgraumann --reports-path ./maigret/` |
| **socialscan** | `pip install socialscan --break-system-packages` | `socialscan -e osteffens@gc-heat.de -u osteffens` |

---

## 13. Repositorios y Código Fuente

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **gitleaks** | `sudo apt install gitleaks` | `gitleaks detect --source=https://github.com/org --report-path=leaks.json` |
| **trufflehog** | `pip install trufflehog --break-system-packages` | `trufflehog github --org=gc-heat` |
| **gitdorker** | `git clone https://github.com/obheda12/GitDorker` | `python3 GitDorker.py -t TOKEN -d dorks.txt -q gc-heat.de` |
| **gitrob** | `go install github.com/michenriksen/gitrob@latest` | `gitrob gc-heat` |

---

## 14. Histórico Web y URLs

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **waybackurls** | `go install github.com/tomnomnom/waybackurls@latest` | `echo gc-heat.de \| waybackurls > wayback.txt` |
| **gau** | `go install github.com/lc/gau/v2/cmd/gau@latest` | `gau gc-heat.de --threads 5 --o gau.txt` |
| **katana** | `go install github.com/projectdiscovery/katana/cmd/katana@latest` | `katana -u https://gc-heat.de -d 3 -o katana.txt` |
| **hakrawler** | `go install github.com/hakluke/hakrawler@latest` | `echo https://gc-heat.de \| hakrawler` |
| **gospider** | `go install github.com/jaeles-project/gospider@latest` | `gospider -s https://gc-heat.de -d 2 -o gospider/` |
| **waymore** | `pip install waymore --break-system-packages` | `waymore -i gc-heat.de -mode U` |

---

## 15. Cloud Enumeration

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **cloud_enum** | `git clone https://github.com/initstring/cloud_enum` | `python3 cloud_enum.py -k gc-heat -k gcheat -l cloud.txt` |
| **s3scanner** | `pip install s3scanner --break-system-packages` | `s3scanner --bucket gc-heat` |
| **gcpbucketbrute** | `git clone https://github.com/RhinoSecurityLabs/GCPBucketBrute` | `python3 gcpbucketbrute.py -k gc-heat` |

---

## 16. Dark Web y Telegram

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **torify + curl** | `sudo apt install tor` | `torify curl -s "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q=gc-heat"` |
| **onionsearch** | `pip install onionsearch --break-system-packages` | `onionsearch -q gc-heat.de --len 100` |
| **telepathy** | `pip install telepathy --break-system-packages` | `telepathy -t gc-heat` |
| **curl (Ahmia)** | Preinstalado | `curl -s "https://ahmia.fi/search/?q=gc-heat"` |

---

## 17. Escaneo Pasivo de Red y Tráfico

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **p0f** | `sudo apt install p0f` (preinstalado) | `p0f -i eth0` |
| **netdiscover** | `sudo apt install netdiscover` (preinstalado) | `netdiscover -p -r 192.168.1.0/24` (modo pasivo) |
| **tcpdump** | Preinstalado | `tcpdump -i eth0 -w capture.pcap` |

---

## 18. Reputación e Inteligencia de Amenazas (vía API/CLI)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **curl (VirusTotal)** | Preinstalado | `curl -s "https://www.virustotal.com/api/v3/domains/gc-heat.de" -H "x-apikey: KEY"` |
| **curl (AbuseIPDB)** | Preinstalado | `curl -s "https://api.abuseipdb.com/api/v2/check?ipAddress=185.243.132.173" -H "Key: KEY"` |
| **curl (URLScan)** | Preinstalado | `curl -s "https://urlscan.io/api/v1/search/?q=domain:gc-heat.de" \| jq` |
| **curl (Shodan InternetDB)** | Preinstalado | `curl -s "https://internetdb.shodan.io/185.243.132.173"` |
| **curl (AlienVault OTX)** | Preinstalado | `curl -s "https://otx.alienvault.com/api/v1/indicators/domain/gc-heat.de/general"` |
| **curl (ThreatCrowd)** | Preinstalado | `curl -s "https://www.threatcrowd.org/searchApi/v2/domain/report/?domain=gc-heat.de"` |

---

## 19. Utilidades de Apoyo

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **jq** | `sudo apt install jq` (preinstalado) | `curl -s API_URL \| jq '.results[]'` |
| **wget** | Preinstalado | `wget -r -l2 -A pdf,doc https://gc-heat.de/` |
| **curl** | Preinstalado | Peticiones HTTP/API universales |
| **sed/awk/grep** | Preinstalado | Procesamiento de texto y filtrado |
| **anew** | `go install github.com/tomnomnom/anew@latest` | `cat new_subs.txt \| anew all_subs.txt` |
| **unfurl** | `go install github.com/tomnomnom/unfurl@latest` | `cat urls.txt \| unfurl domains` |
| **qsreplace** | `go install github.com/tomnomnom/qsreplace@latest` | `cat urls.txt \| qsreplace FUZZ` |
| **aquatone** | `go install github.com/michenriksen/aquatone@latest` | `cat subs.txt \| aquatone -out screenshots/` |
| **gowitness** | `go install github.com/sensepost/gowitness@latest` | `gowitness file -f subs.txt --screenshot-path ./screenshots/` |
| **notify** | `go install github.com/projectdiscovery/notify/cmd/notify@latest` | Pipeline de notificaciones para alertas en tiempo real |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Preinstalado en Kali** | ~23 herramientas |
| **Instalable con apt** | ~13 herramientas adicionales |
| **Instalable con pip** | ~18 herramientas adicionales |
| **Instalable con go install** | ~19 herramientas adicionales |
| **Git clone manual** | ~10 herramientas adicionales |
| **Total** | **~83 herramientas CLI** |

---

## Alcance de esta lista

Esta lista cubre **exclusivamente reconocimiento pasivo y semi-pasivo**: OSINT,
DNS, certificados, fingerprinting no intrusivo, histórico web y consultas
contra APIs públicas. Las herramientas activas (fuzzing de directorios/parámetros,
escaneo de vulnerabilidades con nuclei/nikto/wpscan, port scanning completo)
NO están aquí — pertenecen a las skills `recon_activo` y `web_pentest`. Si una
fase del trabajo requiere fuzzing o vulnscan, el operador debe activar
explícitamente la skill correspondiente.

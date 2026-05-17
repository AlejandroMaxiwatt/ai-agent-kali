# Herramientas de Análisis de Vulnerabilidades — CLI Kali Linux

Exclusivamente herramientas que un modelo agéntico puede ejecutar desde CLI.
Cubren detección, validación y enriquecimiento de vulnerabilidades sobre los
servicios/aplicaciones ya identificados en la fase de reconocimiento.

> **Aviso**: usar sólo sobre sistemas con autorización explícita por escrito.

---

## 1. CVE Lookup y Bases de Datos

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **searchsploit** | Preinstalado (`exploitdb` package) | `searchsploit apache 2.4.49`, `searchsploit -m 50383` (descarga PoC) |
| **searchsploit (JSON)** | Idem | `searchsploit --json "apache 2.4.49" \| jq` |
| **cve-bin-tool** | `pip install cve-bin-tool --break-system-packages` | `cve-bin-tool -o report.html /usr/bin/` |
| **vulners (nmap)** | Preinstalado con nmap | `nmap --script vulners -sV -p 22,80,443 target.com` |
| **vulscan (nmap)** | `git clone https://github.com/scipag/vulscan /usr/share/nmap/scripts/vulscan` | `nmap --script vulscan/vulscan.nse -sV target.com` |
| **curl (NVD)** | Preinstalado | `curl -s "https://services.nvd.nist.gov/rest/json/cves/2.0?cpeName=cpe:2.3:a:apache:http_server:2.4.49"` |
| **curl (CVEdetails)** | Preinstalado | `curl -s "https://www.cvedetails.com/json-feed.php?numrows=20&vendor_id=45"` |

---

## 2. Escaneo de Vulnerabilidades Genérico

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nuclei (CVEs críticas)** | Preinstalado | `nuclei -u https://target.com -t cves/ -severity critical,high -o nuclei_critical.txt` |
| **nuclei (multi-host)** | Idem | `cat hosts.txt \| httpx -silent \| nuclei -t cves/ -t exposures/ -t misconfiguration/ -severity medium,high,critical` |
| **nuclei (exposures)** | Idem | `nuclei -u https://target.com -t exposures/ -t exposed-panels/` |
| **nuclei (default-logins)** | Idem | `nuclei -u https://target.com -t default-logins/` |
| **nikto** | Preinstalado | `nikto -h https://target.com -Tuning x6 -o nikto.txt` |
| **wapiti** | Preinstalado | `wapiti -u https://target.com --scope domain -f html -o wapiti_report` |
| **skipfish** | Preinstalado | `skipfish -o skipfish_out https://target.com` |
| **openvas-cli / gvm-cli** | `sudo apt install gvm` | `gvm-cli socket --xml '<get_tasks/>'` (interactivo) |
| **arachni** | `git clone https://github.com/Arachni/arachni` | `arachni https://target.com --output-only-positives` |

---

## 3. CMS Vulnerability Scanners

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **wpscan** | Preinstalado | `wpscan --url https://target.com --enumerate vp,vt --api-token <KEY>` |
| **joomscan** | Preinstalado | `joomscan -u https://target.com -ec` |
| **droopescan** | `pip install droopescan --break-system-packages` | `droopescan scan drupal -u https://target.com` |
| **cmsmap** | `git clone https://github.com/Dionach/CMSmap` | `python3 cmsmap.py https://target.com -F` |
| **cmseek** | `git clone https://github.com/Tuhinshubhra/CMSeeK` | `python3 cmseek.py -u https://target.com` |

---

## 4. SSL/TLS Vulnerabilities

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **testssl.sh** | `sudo apt install testssl.sh` | `testssl.sh --severity LOW --jsonfile testssl.json target.com:443` |
| **sslscan** | Preinstalado | `sslscan --no-failed target.com:443` |
| **sslyze** | Preinstalado | `sslyze --regular target.com:443` |
| **nmap NSE ssl** | Preinstalado | `nmap -p443 --script "ssl-heartbleed,ssl-poodle,ssl-ccs-injection,ssl-dh-params" target.com` |
| **cipherscan** | `git clone https://github.com/mozilla/cipherscan` | `./cipherscan target.com:443` |
| **a2sv** | `pip install a2sv --break-system-packages` | `python3 a2sv.py -t target.com` |

---

## 5. Cabeceras HTTP y Configuración

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **curl -I** | Preinstalado | `curl -sI https://target.com` (analizar X-Frame-Options, CSP, HSTS, etc.) |
| **shcheck** | `pip install shcheck --break-system-packages` | `shcheck https://target.com` |
| **securityheaders (online via curl)** | Preinstalado | `curl -s "https://securityheaders.com/?q=target.com&followRedirects=on&hide=on"` |
| **nmap NSE http-headers** | Preinstalado | `nmap -p443 --script http-security-headers,http-csp-failure-report,http-cors target.com` |
| **nikto (cabeceras)** | Preinstalado | `nikto -h https://target.com -Tuning 1,4` (Interesting Files + Information Disclosure) |

---

## 6. Vulnerabilidades de Configuración Cloud / Misconfig

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nuclei (cloud)** | Idem | `nuclei -u https://target.com -tags cloud,aws,azure,gcp` |
| **cloud_enum** | `git clone https://github.com/initstring/cloud_enum` | `python3 cloud_enum.py -k target -l cloud.txt` |
| **s3scanner** | `pip install s3scanner --break-system-packages` | `s3scanner --bucket target` |
| **gcpbucketbrute** | `git clone https://github.com/RhinoSecurityLabs/GCPBucketBrute` | `python3 gcpbucketbrute.py -k target` |
| **ScoutSuite** | `pip install scoutsuite --break-system-packages` | `scout aws --profile <profile>` |
| **Prowler** | `pip install prowler --break-system-packages` | `prowler aws --output-modes csv,html` |
| **CloudFox** | `go install github.com/BishopFox/cloudfox@latest` | `cloudfox aws --profile <profile> all-checks` |

---

## 7. Secrets, .git / Backup Disclosure

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **gitleaks** | `sudo apt install gitleaks` | `gitleaks detect --source=https://github.com/org --report-path=leaks.json` |
| **trufflehog** | `pip install trufflehog --break-system-packages` | `trufflehog github --org=<org> --json` |
| **git-dumper** | `pip install git-dumper --break-system-packages` | `git-dumper https://target.com/.git ./git-dump/` |
| **dvcs-ripper** | `git clone https://github.com/kost/dvcs-ripper` | `perl rip-git.pl -v -u https://target.com/.git/` |
| **nuclei (exposed git)** | Idem | `nuclei -u https://target.com -t exposures/configs/git-config.yaml` |

---

## 8. Database Vulnerability Checks

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap NSE mysql** | Preinstalado | `nmap -p3306 --script "mysql-empty-password,mysql-info,mysql-vuln-cve2012-2122" target` |
| **nmap NSE mssql** | Preinstalado | `nmap -p1433 --script "ms-sql-empty-password,ms-sql-ntlm-info,ms-sql-info" target` |
| **nmap NSE mongodb** | Preinstalado | `nmap -p27017 --script "mongodb-info,mongodb-databases" target` (sin auth → leak) |
| **nmap NSE redis** | Preinstalado | `nmap -p6379 --script "redis-info" target` |
| **nmap NSE oracle** | Preinstalado | `nmap -p1521 --script "oracle-sid-brute,oracle-tns-version" target` |

---

## 9. SCADA / IoT / Firmware (si en alcance)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap NSE scada** | Preinstalado | `nmap -p502 --script modbus-discover target` (Modbus) |
| **nmap NSE iot** | Preinstalado | `nmap -p1883 --script mqtt-subscribe target` (MQTT) |
| **binwalk** | `sudo apt install binwalk` | `binwalk -e firmware.bin` |
| **firmwalker** | `git clone https://github.com/craigz28/firmwalker` | `./firmwalker.sh /tmp/extracted-firmware/` |

---

## 10. Validación Manual de Hallazgos

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **curl con headers/POST** | Preinstalado | `curl -i -X POST https://target.com/api/login -H "Content-Type: application/json" -d '{"u":"admin","p":"admin"}'` |
| **httpx (verify)** | Preinstalado | `echo https://target.com/.%2e/%2e%2e/etc/passwd \| httpx -mc 200 -mr "root:"` |
| **wget (descarga PoC)** | Preinstalado | `wget https://www.exploit-db.com/raw/50383 -O cve-2021-41773.txt` |
| **openssl (TLS validation)** | Preinstalado | `openssl s_client -connect target.com:443 -tls1 < /dev/null` (probar TLS1.0 weak) |

---

## 11. Análisis de Dependencias (SBOM / OSS)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **retire.js** | `npm install -g retire` | `retire --path /var/www/html/` |
| **safety** | `pip install safety --break-system-packages` | `safety check -r requirements.txt` |
| **bandit** | `pip install bandit --break-system-packages` | `bandit -r ./codebase/ -f json` |
| **snyk-cli** | `npm install -g snyk` | `snyk test --json` (requiere cuenta gratuita) |
| **trivy** | `sudo apt install trivy` | `trivy fs --severity HIGH,CRITICAL ./project/` |

---

## 12. Frameworks Integradores y Reporting

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **metasploit (db)** | Preinstalado | `msfconsole -q -x "db_import nmap.xml; analyze; vulns; hosts -c address,os_name; exit"` |
| **faraday-cli** | `pip install faraday-cli --break-system-packages` | `faraday-cli auth -u user -p pass -w workspace` |
| **dradis-cli** | API REST | `curl -s "$DRADIS_URL/pro/api/issues" -H "Authorization: Token token=$DRADIS_TOKEN"` |

---

## Resumen de Disponibilidad

| Estado | Cantidad aprox |
|---|---|
| **Preinstalado en Kali** | ~25 herramientas |
| **Instalable con apt/pip** | ~20 herramientas adicionales |
| **Go install / git clone** | ~15 herramientas adicionales |
| **Total** | **~60 herramientas CLI** |

---

## Alcance de esta lista

Esta lista cubre **detección y enriquecimiento** de vulnerabilidades sobre
servicios/apps ya inventariados. La explotación funcional (lanzar exploits
para conseguir RCE/foothold) pertenece a la skill `exploitation`. El testing
manual profundo de aplicaciones web (OWASP Top 10 con interacción) a
`web_pentest`. La revisión de fuentes y SAST pesado a `code_security_review`
(si está disponible).

# Herramientas de Reconocimiento Activo Ejecutables desde Terminal Kali Linux

> **Aviso:** todas estas herramientas envían paquetes/peticiones al objetivo.
> Usar exclusivamente sobre sistemas con autorización explícita por escrito,
> dentro de la ventana de pruebas y respetando el nivel de agresividad acordado.

Exclusivamente herramientas que un modelo agéntico puede ejecutar desde CLI sin necesidad de navegador ni interfaz gráfica.

---

## 1. Descubrimiento de Hosts (Host Discovery)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap (ping sweep)** | Preinstalado | `nmap -sn -PE -PP -PS21,22,80,443 10.10.10.0/24 -oA hosts_alive` |
| **fping** | `sudo apt install fping` (preinstalado) | `fping -a -g 10.10.10.0/24 2>/dev/null` |
| **arp-scan** | `sudo apt install arp-scan` (preinstalado) | `sudo arp-scan -l --interface eth0` (LAN únicamente) |
| **arping** | Preinstalado | `arping -c 3 10.10.10.10` |
| **netdiscover** | Preinstalado | `sudo netdiscover -i eth0 -r 10.10.10.0/24` |
| **masscan (ping)** | Preinstalado | `sudo masscan -p80,443 10.10.10.0/24 --rate=1000` |
| **hping3** | Preinstalado | `hping3 -1 -c 3 10.10.10.10` (ICMP), `hping3 -S -p 443 10.10.10.10` (TCP SYN) |

---

## 2. Port Scanning

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap** | Preinstalado | `nmap -sS -p- -T4 --min-rate=2000 -oA full_tcp 10.10.10.10` |
| **nmap (UDP)** | Preinstalado | `sudo nmap -sU --top-ports 200 -T4 10.10.10.10 -oA udp_top200` |
| **masscan** | Preinstalado | `sudo masscan -p1-65535 10.10.10.0/24 --rate=10000 -oG masscan.gnmap` |
| **rustscan** | `cargo install rustscan` o release deb | `rustscan -a 10.10.10.10 --ulimit 5000 -- -sV -sC -oA rs` |
| **naabu** | `go install github.com/projectdiscovery/naabu/v2/cmd/naabu@latest` | `naabu -host 10.10.10.10 -p - -rate 2000 -o naabu.txt` |
| **unicornscan** | `sudo apt install unicornscan` (preinstalado) | `sudo unicornscan -mT 10.10.10.10:a -r 500` |
| **zmap** | `sudo apt install zmap` | `sudo zmap -p 443 -o https_hosts.txt 10.10.10.0/24` (rangos amplios) |

---

## 3. Fingerprinting de SO y Servicios

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap -sV / -A** | Preinstalado | `nmap -sV -sC -O -A -p<ports> 10.10.10.10 -oA service_scan` |
| **nmap NSE (versionado)** | Preinstalado | `nmap --script=banner,version -sV -p<ports> 10.10.10.10` |
| **amap** | `sudo apt install amap` (preinstalado) | `amap -bqv 10.10.10.10 21 22 80 443` |
| **netcat / ncat** | Preinstalado | `nc -nv 10.10.10.10 80 <<< $'HEAD / HTTP/1.0\r\n\r\n'` |
| **whatweb (agresivo)** | Preinstalado | `whatweb -a 4 -v https://target.com` |
| **httpx (probing activo)** | Preinstalado | `cat hosts.txt \| httpx -title -tech-detect -status-code -web-server -tls-probe -o httpx.txt` |
| **wappalyzer-cli** | `npm install -g wappalyzer-cli` | `wappalyzer https://target.com` |

---

## 4. DNS Activo (Brute-Force, Zone Transfer)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **dnsrecon (brt)** | Preinstalado | `dnsrecon -d target.com -t std,brt,axfr -D /usr/share/wordlists/dnsmap.txt` |
| **dnsenum (brute)** | Preinstalado | `dnsenum --enum -f /usr/share/wordlists/dnsmap.txt target.com` |
| **fierce** | Preinstalado | `fierce --domain target.com --subdomain-file subs.txt` |
| **gobuster dns** | Preinstalado | `gobuster dns -d target.com -w /usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-110000.txt -t 50` |
| **dnsmap** | Preinstalado | `dnsmap target.com -w /usr/share/wordlists/dnsmap.txt -r dnsmap_out.txt` |
| **puredns** | `go install github.com/d3mondev/puredns/v2@latest` | `puredns bruteforce wordlist.txt target.com -r resolvers.txt` |
| **shuffledns** | `go install github.com/projectdiscovery/shuffledns/cmd/shuffledns@latest` | `shuffledns -d target.com -w wordlist.txt -r resolvers.txt -mode bruteforce` |
| **massdns** | Preinstalado | `massdns -r resolvers.txt -t A -o S domains.txt -w massdns_out.txt` |
| **dnsx (resolución)** | Preinstalado | `cat subs.txt \| dnsx -silent -a -resp -t 50` |
| **altdns / dnsgen** | `pip install py-altdns dnsgen --break-system-packages` | `altdns -i subs.txt -o permuted.txt -w words.txt` |

---

## 5. Web — Fuzzing de Contenido y Parámetros

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **ffuf** | Preinstalado | `ffuf -u https://target.com/FUZZ -w /usr/share/seclists/Discovery/Web-Content/raft-large-words.txt -mc 200,301,302,401,403 -ac -t 40` |
| **feroxbuster** | `sudo apt install feroxbuster` | `feroxbuster -u https://target.com -w wordlist.txt -x php,bak,txt -t 30 -o ferox.txt` |
| **gobuster dir** | Preinstalado | `gobuster dir -u https://target.com -w wordlist.txt -x php,html,txt,bak -t 40` |
| **gobuster vhost** | Preinstalado | `gobuster vhost -u https://target.com -w vhosts.txt --append-domain` |
| **dirsearch** | Preinstalado | `dirsearch -u https://target.com -e php,html,txt,bak,old -t 30 -x 404,400` |
| **dirb** | Preinstalado | `dirb https://target.com /usr/share/dirb/wordlists/common.txt -o dirb.txt` |
| **wfuzz** | Preinstalado | `wfuzz -c -w wordlist.txt --hc 404 https://target.com/FUZZ` |
| **arjun** | `pip install arjun --break-system-packages` | `arjun -u https://target.com/page -m GET,POST -oJ arjun.json` |
| **paramspider** | `pip install paramspider --break-system-packages` | `paramspider -d target.com` |
| **x8** | `cargo install x8` | `x8 -u https://target.com/api/v1/login -w params.txt` |
| **kiterunner** | `go install github.com/assetnote/kiterunner/cmd/kr@latest` | `kr scan https://target.com -w routes-large.kite -A=apiroutes-210228:20210228` |

---

## 6. Web — Crawling Activo

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **katana** | `go install github.com/projectdiscovery/katana/cmd/katana@latest` | `katana -u https://target.com -d 5 -jc -kf all -o katana.txt` |
| **hakrawler** | `go install github.com/hakluke/hakrawler@latest` | `echo https://target.com \| hakrawler -d 3 -subs` |
| **gospider** | `go install github.com/jaeles-project/gospider@latest` | `gospider -s https://target.com -d 3 -c 10 -t 20 -o gospider/` |
| **meg** | `go install github.com/tomnomnom/meg@latest` | `meg -d 1000 -v paths.txt hosts.txt out_dir/` |
| **photon** | `pip install photon --break-system-packages` | `photon -u https://target.com -l 3 -t 20 -o photon/` |

---

## 7. Web — CMS Scanners

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **wpscan** | Preinstalado | `wpscan --url https://target.com --enumerate vp,vt,u,m --api-token <TOKEN> -o wpscan.txt` |
| **joomscan** | Preinstalado | `joomscan -u https://target.com -ec` |
| **droopescan** | `pip install droopescan --break-system-packages` | `droopescan scan drupal -u https://target.com` |
| **cmsmap** | `git clone https://github.com/Dionach/CMSmap` | `python3 cmsmap.py https://target.com -F` |
| **cmseek** | `git clone https://github.com/Tuhinshubhra/CMSeeK` | `python3 cmseek.py -u https://target.com` |
| **wpforce** | `git clone https://github.com/n00py/WPForce` | `python3 wpforce.py -i users.txt -w passes.txt -u https://target.com` |
| **magescan** | `git clone https://github.com/steverobbins/magescan` | `magescan scan:all https://magento-target.com` |

---

## 8. Web — Escaneo de Vulnerabilidades

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nuclei** | Preinstalado | `nuclei -u https://target.com -t cves/ -t exposures/ -t misconfiguration/ -t vulnerabilities/ -severity medium,high,critical -o nuclei.txt` |
| **nuclei (lista)** | Preinstalado | `cat hosts.txt \| httpx -silent \| nuclei -t /root/.nuclei-templates/ -rl 50 -o nuclei.txt` |
| **nikto** | Preinstalado | `nikto -h https://target.com -Tuning x6 -o nikto.txt -Format txt` |
| **wapiti** | Preinstalado | `wapiti -u https://target.com --scope domain -f html -o wapiti_report` |
| **skipfish** | Preinstalado | `skipfish -o skipfish_out https://target.com` |
| **searchsploit** | Preinstalado | `searchsploit <producto> <versión>` |
| **nmap NSE (vuln)** | Preinstalado | `nmap --script "vuln and not dos" -sV -p <ports> 10.10.10.10 -oA nmap_vuln` |
| **nmap NSE (vulners)** | Preinstalado | `nmap --script vulners -sV -p <ports> 10.10.10.10` |

---

## 9. SMB / NetBIOS / RPC

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap NSE smb** | Preinstalado | `nmap --script "smb-os-discovery,smb-enum-shares,smb-enum-users,smb-vuln-*" -p139,445 10.10.10.10` |
| **enum4linux** | Preinstalado | `enum4linux -a 10.10.10.10` |
| **enum4linux-ng** | `pip install enum4linux-ng --break-system-packages` | `enum4linux-ng -A 10.10.10.10 -oA e4l_ng` |
| **smbmap** | Preinstalado | `smbmap -H 10.10.10.10 -u guest -p ''` , `smbmap -H 10.10.10.10 -u user -p pass -R` |
| **smbclient** | Preinstalado | `smbclient -L //10.10.10.10/ -N` , `smbclient //10.10.10.10/share -U user%pass` |
| **rpcclient** | Preinstalado | `rpcclient -U "" -N 10.10.10.10` (luego `enumdomusers`, `enumdomgroups`, `querydominfo`) |
| **nbtscan** | Preinstalado | `nbtscan -r 10.10.10.0/24` |
| **nmblookup** | Preinstalado | `nmblookup -A 10.10.10.10` |
| **netexec (nxc) smb** | Preinstalado | `netexec smb 10.10.10.0/24 -u '' -p '' --shares`, `netexec smb 10.10.10.10 -u user -p pass --users --groups --pass-pol` |
| **smbexec.py / wmiexec.py** | Preinstalado (impacket) | `impacket-smbexec user:pass@10.10.10.10` |
| **impacket-lookupsid** | Preinstalado | `impacket-lookupsid user:pass@10.10.10.10 20000` |

---

## 10. LDAP y Active Directory

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **ldapsearch (anon)** | Preinstalado | `ldapsearch -x -H ldap://10.10.10.10 -s base namingcontexts` |
| **ldapsearch (auth)** | Preinstalado | `ldapsearch -x -H ldap://10.10.10.10 -D 'user@corp.local' -w 'pass' -b 'DC=corp,DC=local' '(objectClass=user)'` |
| **ldapdomaindump** | Preinstalado | `ldapdomaindump -u 'corp\user' -p pass 10.10.10.10 -o ldd/` |
| **windapsearch** | `git clone https://github.com/ropnop/windapsearch` | `python3 windapsearch.py --dc-ip 10.10.10.10 -u user@corp.local -p pass -m users` |
| **bloodhound-python** | Preinstalado | `bloodhound-python -d corp.local -u user -p pass -c All -ns 10.10.10.10 --zip` |
| **netexec ldap** | Preinstalado | `netexec ldap 10.10.10.10 -u user -p pass --asreproast asrep.txt --kerberoasting kerb.txt` |
| **adidnsdump** | `pip install git+https://github.com/dirkjanm/adidnsdump --break-system-packages` | `adidnsdump -u corp\\user -p pass 10.10.10.10` |
| **certipy-ad (ADCS)** | `pip install certipy-ad --break-system-packages` | `certipy find -u user@corp.local -p pass -dc-ip 10.10.10.10 -vulnerable` |
| **bloodyAD** | `pip install bloodyAD --break-system-packages` | `bloodyAD -u user -p pass -d corp.local --host 10.10.10.10 get children` |
| **pywerview** | `pip install pywerview --break-system-packages` | `pywerview get-netuser -u user -p pass -d corp.local --dc-ip 10.10.10.10` |

---

## 11. Kerberos (Impacket)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **kerbrute (userenum)** | `go install github.com/ropnop/kerbrute@latest` | `kerbrute userenum -d corp.local --dc 10.10.10.10 users.txt` |
| **kerbrute (passwordspray)** | Idem | `kerbrute passwordspray -d corp.local --dc 10.10.10.10 users.txt 'Spring2026!'` |
| **impacket-GetNPUsers (ASREP)** | Preinstalado | `impacket-GetNPUsers corp.local/ -dc-ip 10.10.10.10 -usersfile users.txt -no-pass -format hashcat -outputfile asrep.hash` |
| **impacket-GetUserSPNs (Kerberoast)** | Preinstalado | `impacket-GetUserSPNs corp.local/user:pass -dc-ip 10.10.10.10 -request -outputfile kerb.hash` |
| **impacket-secretsdump** | Preinstalado | `impacket-secretsdump corp.local/user:pass@10.10.10.10` (semi-activo, requiere creds) |
| **impacket-rpcdump** | Preinstalado | `impacket-rpcdump @10.10.10.10` |
| **impacket-samrdump** | Preinstalado | `impacket-samrdump @10.10.10.10` |

---

## 12. SNMP

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **onesixtyone** | Preinstalado | `onesixtyone -c community.txt -i hosts.txt -o onesixtyone.txt` |
| **snmpwalk** | Preinstalado | `snmpwalk -v 2c -c public 10.10.10.10`, `snmpwalk -v 2c -c public 10.10.10.10 1.3.6.1.4.1.77.1.2.25` (usuarios Windows) |
| **snmp-check** | Preinstalado | `snmp-check 10.10.10.10 -c public` |
| **braa** | Preinstalado | `braa public@10.10.10.10:.1.3.6.*` |
| **nmap NSE snmp** | Preinstalado | `nmap -sU -p161 --script "snmp-*" 10.10.10.10` |

---

## 13. SMTP / Email Active

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **smtp-user-enum** | Preinstalado | `smtp-user-enum -M VRFY -U users.txt -t 10.10.10.10` |
| **swaks** | Preinstalado | `swaks --to admin@target.com --from test@evil.tld --server 10.10.10.10` |
| **nmap NSE smtp** | Preinstalado | `nmap -p25,465,587 --script "smtp-*" 10.10.10.10` |

---

## 14. FTP / SSH / Telnet

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap NSE ftp** | Preinstalado | `nmap -p21 --script "ftp-anon,ftp-bounce,ftp-syst,ftp-brute" 10.10.10.10` |
| **ftp client** | Preinstalado | `ftp 10.10.10.10` (banner + anon login) |
| **ncftp / lftp** | `sudo apt install lftp` | `lftp -u anonymous, ftp://10.10.10.10` |
| **ssh-audit** | `pip install ssh-audit --break-system-packages` o `apt` | `ssh-audit 10.10.10.10` |
| **nmap NSE ssh** | Preinstalado | `nmap -p22 --script "ssh-auth-methods,ssh-hostkey,ssh2-enum-algos" 10.10.10.10` |
| **ssh-keyscan** | Preinstalado | `ssh-keyscan -t rsa,ecdsa,ed25519 10.10.10.10` |
| **nmap NSE telnet** | Preinstalado | `nmap -p23 --script "telnet-encryption,telnet-ntlm-info,telnet-brute" 10.10.10.10` |

---

## 15. Bases de Datos (MSSQL, MySQL, Postgres, Redis, MongoDB, Oracle)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap NSE mssql** | Preinstalado | `nmap -p1433 --script "ms-sql-info,ms-sql-empty-password,ms-sql-ntlm-info" 10.10.10.10` |
| **impacket-mssqlclient** | Preinstalado | `impacket-mssqlclient corp.local/user:pass@10.10.10.10 -windows-auth` |
| **mssql-cli** | `pip install mssql-cli --break-system-packages` | `mssql-cli -S 10.10.10.10 -U sa -P pass` |
| **mysql client** | Preinstalado | `mysql -h 10.10.10.10 -u root -p` |
| **nmap NSE mysql** | Preinstalado | `nmap -p3306 --script "mysql-info,mysql-empty-password,mysql-enum,mysql-brute" 10.10.10.10` |
| **psql** | Preinstalado | `psql -h 10.10.10.10 -U postgres` |
| **nmap NSE postgres** | Preinstalado | `nmap -p5432 --script "pgsql-brute" 10.10.10.10` |
| **redis-cli** | Preinstalado | `redis-cli -h 10.10.10.10 INFO`, `redis-cli -h 10.10.10.10 CONFIG GET *` |
| **nmap NSE redis** | Preinstalado | `nmap -p6379 --script "redis-info,redis-brute" 10.10.10.10` |
| **mongosh** | `sudo apt install mongodb-mongosh` | `mongosh "mongodb://10.10.10.10:27017"` |
| **nmap NSE mongodb** | Preinstalado | `nmap -p27017 --script "mongodb-info,mongodb-databases" 10.10.10.10` |
| **nmap NSE oracle** | Preinstalado | `nmap -p1521 --script "oracle-sid-brute,oracle-tns-version" 10.10.10.10` |
| **odat (Oracle)** | `git clone https://github.com/quentinhardy/odat` | `./odat.py all -s 10.10.10.10 -p 1521` |

---

## 16. RDP / WinRM / VNC

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **nmap NSE rdp** | Preinstalado | `nmap -p3389 --script "rdp-enum-encryption,rdp-ntlm-info" 10.10.10.10` |
| **xfreerdp** | Preinstalado | `xfreerdp /v:10.10.10.10 /u:user /p:pass /cert:ignore` (banner / login) |
| **rdesktop** | Preinstalado | `rdesktop 10.10.10.10` |
| **netexec rdp** | Preinstalado | `netexec rdp 10.10.10.10 -u user -p pass` |
| **rdp-sec-check** | `git clone https://github.com/portcullislabs/rdp-sec-check` | `perl rdp-sec-check.pl 10.10.10.10` |
| **evil-winrm** | Preinstalado | `evil-winrm -i 10.10.10.10 -u user -p pass` |
| **netexec winrm** | Preinstalado | `netexec winrm 10.10.10.10 -u user -p pass` |
| **nmap NSE vnc** | Preinstalado | `nmap -p5900 --script "vnc-info,vnc-title,vnc-brute" 10.10.10.10` |

---

## 17. VoIP / SIP

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **svmap (sipvicious)** | Preinstalado | `svmap 10.10.10.0/24 -p5060-5062` |
| **svwar** | Preinstalado | `svwar -m INVITE -e100-999 10.10.10.10` |
| **nmap NSE sip** | Preinstalado | `nmap -sU -p5060 --script "sip-enum-users,sip-methods" 10.10.10.10` |

---

## 18. SSL/TLS Activo

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **sslscan** | Preinstalado | `sslscan --no-failed target.com:443` |
| **testssl.sh** | `sudo apt install testssl.sh` | `testssl.sh --severity LOW --jsonfile testssl.json target.com:443` |
| **sslyze** | Preinstalado | `sslyze --regular target.com:443` |
| **nmap NSE ssl/tls** | Preinstalado | `nmap -p443 --script "ssl-cert,ssl-enum-ciphers,ssl-heartbleed" target.com` |
| **openssl s_client** | Preinstalado | `openssl s_client -connect target.com:443 -showcerts </dev/null` |

---

## 19. Firewall / IDS Fingerprinting y Evasión

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **hping3** | Preinstalado | `hping3 -S -p 443 -c 5 --tcp-timestamp 10.10.10.10` |
| **nmap (evasión)** | Preinstalado | `nmap -f -D RND:10 --data-length 24 --source-port 53 -T2 10.10.10.10` |
| **firewalk** | `sudo apt install firewalk` | `firewalk -S1-65535 -i eth0 -n 10.10.10.10` |
| **fragroute / fragrouter** | `sudo apt install fragroute` | `fragroute -f fragroute.conf 10.10.10.10` |
| **wafw00f (activo)** | Preinstalado | `wafw00f -a https://target.com` |

---

## 20. Brute Force y Password Spraying

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **hydra** | Preinstalado | `hydra -L users.txt -P pass.txt ssh://10.10.10.10 -t 4 -o hydra_ssh.txt` |
| **medusa** | Preinstalado | `medusa -h 10.10.10.10 -U users.txt -P pass.txt -M ssh -t 4` |
| **patator** | Preinstalado | `patator ssh_login host=10.10.10.10 user=FILE0 password=FILE1 0=users.txt 1=pass.txt -x ignore:mesg='Auth fail'` |
| **netexec (spray SMB)** | Preinstalado | `netexec smb 10.10.10.0/24 -u users.txt -p 'Spring2026!' --continue-on-success` |
| **kerbrute spray** | Idem §11 | `kerbrute passwordspray -d corp.local users.txt 'Spring2026!'` |
| **crowbar** | `sudo apt install crowbar` | `crowbar -b rdp -s 10.10.10.10/32 -u user -C pass.txt` |

---

## 21. Cloud Activo (con credenciales válidas o sin ellas)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **awscli (enum)** | `sudo apt install awscli` | `aws sts get-caller-identity`, `aws s3 ls`, `aws iam list-users` |
| **pacu (AWS)** | `pip install pacu --break-system-packages` | `pacu` (interactivo), módulos `iam__enum_users_roles_policies_groups`, `s3__bucketfinder` |
| **ScoutSuite** | `pip install scoutsuite --break-system-packages` | `scout aws --profile <profile>` |
| **CloudFox** | `go install github.com/BishopFox/cloudfox@latest` | `cloudfox aws --profile <profile> all-checks` |
| **gcloud (enum)** | `sudo apt install google-cloud-cli` | `gcloud projects list`, `gcloud iam service-accounts list` |
| **az cli (enum)** | `curl -sL https://aka.ms/InstallAzureCLIDeb \| bash` | `az login`, `az ad user list`, `az resource list` |
| **ROADtools (Azure)** | `pip install roadrecon --break-system-packages` | `roadrecon auth -u user@tenant.onmicrosoft.com`, `roadrecon gather` |
| **AzureHound** | `go install github.com/bloodhoundad/azurehound@latest` | `azurehound -u user -p pass list --tenant <id>` |

---

## 22. Containers y Kubernetes

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **kube-hunter** | `pip install kube-hunter --break-system-packages` | `kube-hunter --remote 10.10.10.10` |
| **kube-bench** | `sudo apt install kube-bench` | `kube-bench run --targets master,node` |
| **peirates** | release binario en github | `peirates` (interactivo, requiere shell en pod) |
| **trivy** | `sudo apt install trivy` | `trivy image <registry>/<image>:<tag>`, `trivy k8s --report summary` |
| **docker (enum API)** | Preinstalado | `curl -s http://10.10.10.10:2375/version`, `docker -H tcp://10.10.10.10:2375 ps` |

---

## 23. Wireless (solo con autorización física y NIC en modo monitor)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **airodump-ng** | Preinstalado | `sudo airodump-ng wlan0mon` |
| **wash** | Preinstalado | `sudo wash -i wlan0mon` (puntos WPS) |
| **wifite** | Preinstalado | `sudo wifite` |
| **kismet** | Preinstalado | `sudo kismet -c wlan0mon` |
| **bettercap** | `sudo apt install bettercap` | `sudo bettercap -iface wlan0` |
| **iwlist** | Preinstalado | `sudo iwlist wlan0 scan` |

---

## 24. Bluetooth (autorización física)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **bluetoothctl** | Preinstalado | `bluetoothctl scan on` |
| **hcitool** | Preinstalado | `sudo hcitool scan`, `sudo hcitool inq` |
| **bluelog** | Preinstalado | `sudo bluelog -i hci0 -o bluelog.txt` |
| **btscanner** | Preinstalado | `sudo btscanner` |

---

## 25. Frameworks Integradores y Automatización

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **metasploit (msfconsole)** | Preinstalado | `msfconsole -q -x "use auxiliary/scanner/smb/smb_version; set RHOSTS 10.10.10.0/24; run; exit"` |
| **metasploit (db_nmap)** | Preinstalado | Importar nmap XML: `msfconsole -q -x "db_import nmap.xml; hosts; services; exit"` |
| **legion** | Preinstalado | `sudo legion` (GUI, pero útil tras escaneos) |
| **autorecon** | `pipx install git+https://github.com/Tib3rius/AutoRecon` | `autorecon 10.10.10.10` |
| **reconftw** | `git clone https://github.com/six2dez/reconftw` | `./reconftw.sh -d target.com -a` |
| **nuclei + chain** | Idem §8 | `subfinder -d target.com -silent \| httpx -silent \| nuclei -t /root/.nuclei-templates/ -severity high,critical` |

---

## 26. Sniffing y Captura de Tráfico (segmentos donde tienes acceso)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **tcpdump** | Preinstalado | `sudo tcpdump -i eth0 -w cap.pcap 'host 10.10.10.10'` |
| **tshark** | Preinstalado | `tshark -i eth0 -f "tcp port 80" -w http.pcap` |
| **wireshark (CLI dumpcap)** | Preinstalado | `dumpcap -i eth0 -w cap.pcap -b filesize:100000` |
| **bettercap (ARP)** | `sudo apt install bettercap` | `sudo bettercap -iface eth0 -eval "set arp.spoof.targets 10.10.10.10; arp.spoof on; net.sniff on"` (sólo en laboratorio autorizado) |
| **responder** | Preinstalado | `sudo responder -I eth0 -A` (análisis pasivo de broadcasts, sin envenenar) |

---

## 27. Utilidades de Apoyo

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **proxychains4** | Preinstalado | `proxychains4 nmap -sT -Pn 10.10.10.10` (pivot tras compromiso) |
| **aquatone** | `go install github.com/michenriksen/aquatone@latest` | `cat hosts.txt \| aquatone -ports xlarge -out aquatone/` |
| **gowitness** | `go install github.com/sensepost/gowitness@latest` | `gowitness scan single --url https://target.com`, `gowitness scan file -f hosts.txt` |
| **httpx (screenshot)** | Preinstalado | `httpx -l hosts.txt -ss -srd screenshots/` |
| **anew** | `go install github.com/tomnomnom/anew@latest` | `cat new.txt \| anew all.txt` |
| **unfurl** | `go install github.com/tomnomnom/unfurl@latest` | `cat urls.txt \| unfurl domains` |
| **qsreplace** | `go install github.com/tomnomnom/qsreplace@latest` | `cat urls.txt \| qsreplace FUZZ` |
| **jq** | Preinstalado | `cat nuclei.json \| jq '.[] \| select(.severity=="high")'` |
| **xsltproc (nmap → HTML)** | `sudo apt install xsltproc` | `xsltproc nmap.xml -o nmap.html` |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Preinstalado en Kali** | ~80 herramientas |
| **Instalable con apt** | ~15 herramientas adicionales |
| **Instalable con pip** | ~15 herramientas adicionales |
| **Instalable con go install** | ~12 herramientas adicionales |
| **Git clone manual** | ~8 herramientas adicionales |
| **Total** | **~130 herramientas CLI** |

---

## Alcance de esta lista

Esta lista cubre **reconocimiento activo y enumeración**: envío de paquetes,
peticiones, banners, bruteforce de directorios/DNS/credenciales, escaneo de
vulnerabilidades dirigido. Requiere **autorización explícita y por escrito**
del cliente sobre los rangos/dominios listados.

NO cubre:
- **Explotación / post-explotación** (uso de exploit, escalada, persistencia,
  lateral movement profundo) → skills `web_pentest`, `internal_network_audit`.
- **Recon pasivo / OSINT** (sin tocar el objetivo) → skill `recon`.
- **Auditoría WordPress dirigida** → skill `wordpress_audit`.

## Reglas operativas

- Empezar por escaneos suaves (`-T3`/`-T4`, rate bajo) y escalar sólo si el
  cliente lo permite.
- `-T5`, `--rate` muy alto y `masscan` con rate > 10000 sólo en LAN aislada o
  con autorización explícita: pueden tirar firewalls/IDS y servicios.
- Confirmar antes de lanzar fuerza bruta agresiva (lockouts AD, abuso de SMTP).
- Si una herramienta requiere credenciales (impacket, netexec con creds,
  ldapdomaindump), debe haber autorización explícita para usarlas.
- Pivot vía `proxychains4` cuando se trabaja desde un host comprometido o vía
  VPN del cliente.
- Cada hallazgo significativo (puerto, banner, share, usuario, vulnerabilidad)
  se anota mediante `[[TARGET_UPDATE: attack-surface.md]]` o
  `[[TARGET_UPDATE: identities.md]]`. Cada herramienta descartada por no
  aplicar al alcance se justifica en `notes.md`.

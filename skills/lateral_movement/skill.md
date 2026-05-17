# Lateral Movement — Pivoting · Pass-the-Hash · NTLM Relay · AD avanzado

Estás en modo de **movimiento lateral**: tienes foothold en uno o más
hosts y necesitas expandir el compromiso a otros sistemas del segmento
de red / dominio. Foco en Active Directory pero también pivoting puro
en redes Linux.

## Cuándo usar esta skill

- Tras `exploitation` + `post_exploitation`: tienes shell + credenciales
  locales o de dominio.
- Tras `internal_network_audit`: enumeración inicial AD hecha (BloodHound
  graph, users, computers).
- Para alcanzar segmentos no rutables directamente desde el atacante
  (DMZ→interna, VPN cliente→producción).

## Prioridades

### Pivoting de red (acceso a segmentos)
1. **SOCKS5 proxy** vía host comprometido: `chisel`, `ligolo-ng`, `ssh -D`,
   `meterpreter portfwd`. SOCKS5 + `proxychains4` permite usar cualquier
   tool del Kali contra la red interna.
2. **Port forwarding puntual**: `ssh -L` / `socat` para servicios
   específicos (RDP, web admin) que no quieres rutear todo el tráfico.
3. **DNS tunneling** si firewall agresivo bloquea TCP/UDP arbitrario:
   `iodine`, `dnscat2`, `chisel + DoH`.

### Lateral en dominio Windows (creds-based)
1. **Inventory pre-movimiento**: `netexec` (antes CME) contra el rango
   con las creds que tienes → mapeo de hosts donde son válidas.
2. **Pass-the-Hash (PtH)**: si tienes NTLM hash, `netexec smb -H <hash>`,
   `evil-winrm -H <hash>`, `psexec.py -hashes :<hash>`.
3. **Pass-the-Ticket (PtT)**: si tienes TGT/TGS Kerberos, `export
   KRB5CCNAME=ticket.ccache` y usar tools nativas (`klist`, `smbclient`
   con `-k`).
4. **Overpass-the-Hash**: NTLM hash → request TGT via Kerberos
   (`getTGT.py -hashes :<hash>`).
5. **Kerberoasting offline**: ya cubierto en `exploitation` § Kerberos.
   Aquí lo aplicas a CADA service account descubierto.
6. **DCSync** (si tienes user con replicación): `secretsdump.py
   -just-dc-user user corp/admin@dc`.

### NTLM Relay y coercion
1. **Coerce auth desde un host**: `PetitPotam.py`, `Coercer`,
   `printerbug.py` (SpoolService), `dfscoerce.py`. Engaña a un host
   target a autenticar contra nuestro listener.
2. **Listener relay**: `impacket-ntlmrelayx` configurado para
   relayar a LDAP/SMB/MSSQL del target. Con `--escalate-user` añade
   privs en AD si se relayia a LDAPS con WriteDACL.
3. **ADCS abuse (ESC1-ESC11)**: `certipy find -vulnerable` para detectar
   templates abusables; `certipy req` para solicitar cert como otro user.
4. **AS-REP Roasting**: ya cubierto, applies aquí también para users sin
   pre-auth.
5. **Resource-Based Constrained Delegation**: si controlas un computer
   account, configurar RBCD para impersonar admins.

### Lateral en redes Linux (SSH)
1. **SSH key reuse**: `find / -name "id_rsa*" -readable 2>/dev/null` →
   enumeración cross-host con `ssh-audit` + intentos con las keys.
2. **`.ssh/known_hosts` mining**: identifica hosts a los que el user
   comprometido se conecta habitualmente.
3. **Hashcat sobre `~/.ssh/id_rsa` con passphrase**: `ssh2john id_rsa >
   id_rsa.hash; john --wordlist=rockyou.txt id_rsa.hash`.
4. **Sudo NOPASSWD chain**: si `sudo -l` en host A muestra acceso a
   binary que conecta a B, abuso indirecto.

## Herramientas preferidas

- **Pivoting**: `chisel`, `ligolo-ng`, `ssh -D/-L/-R`, `socat`,
  `proxychains4`, `sshuttle`, `revsocks`.
- **Windows lateral (creds)**: `netexec` / `crackmapexec`,
  `evil-winrm`, `impacket-psexec/smbexec/wmiexec/atexec/dcomexec`,
  `rdesktop` / `xfreerdp` con `/restricted-admin` si aplica.
- **Kerberos**: `impacket-GetTGT/GetST/Ticketer/Rubeus.exe` (en target
  Windows), `certipy-ad`.
- **NTLM Relay**: `impacket-ntlmrelayx`, `Responder` (para captura
  inicial), `Inveigh` (.NET equivalente para target Windows).
- **Coercion**: `PetitPotam`, `Coercer`, `printerbug`, `dfscoerce`,
  `shadowcoerce`, `MS-EFSR`.
- **BloodHound graph queries**: ya cargado del initial recon, aquí
  consultas avanzadas (cypher): paths a Domain Admin, owns
  relationships, GPOs explotables.
- **ADCS**: `certipy-ad` (find + abuse + petitpotam chain).

## Reglas operativas DURAS

- **Cada hop = TARGET_UPDATE**: cada host nuevo comprometido se registra
  inmediatamente con cred usada, técnica, timestamp.
- **No password spray ciego**: usa `kerbrute passwordspray` con
  `--delay` (rate-limit interno). Sin spray hasta tener lista user
  enum validada — los lockouts arruinan engagements.
- **Listener relay sólo si activado intencional**: `responder` y
  `ntlmrelayx` deben configurarse explícitamente, NO en modo "siempre
  activo" — riesgo de capturar auths de hosts fuera de alcance.
- **No persistencia en cada hop**: persistencia solo se evalúa en hosts
  estratégicos (DCs, jump hosts), y sólo con RoE.
- **Limpiar tickets Kerberos**: tras usar PtT, `klist purge` antes de
  dejar el host.
- **OPSEC NTLM**: cada `psexec` tipo lanzamiento crea un service
  ephemeral con nombre semialeatorio — muy detectable por EDR. Usar
  `wmiexec`/`dcomexec` si quieres menos disco; `atexec` para
  ejecuciones puntuales.
- **DCSync requiere DA/RepAdmin**: el `secretsdump -just-dc` es ruidoso
  y trigger CRITICAL en EDRs modernos. Sólo cuando confirmes que es
  la última fase del engagement.

## Fuera de scope

- **Persistence en hosts** sin RoE explícito.
- **Destructive payloads** en lateral (no `del`, no rm, no
  modificación de configs).
- **Sin DoS** del DC (replicación masiva, locks).
- **Sin lateral fuera del segmento autorizado** (otras VLANs, cloud
  privado del cliente, partners): pregunta antes.

## Salida esperada

En `attack-surface.md` (vía TARGET_UPDATE):

```
## [2026-05-17 16:00] Hosts comprometidos (lateral)
| Host | IP | OS | Mech | Cred usada | Privs alcanzados |
|---|---|---|---|---|---|
| web01 | 10.10.10.20 | Linux | exploit Apache | (n/a) | root (PE-001) |
| fileserver01 | 10.10.10.40 | Windows | PtH from web01-creds | tanja:$NTLM | local admin |
| dc01 | 10.10.10.10 | WinSrv2019 | NTLM relay + ESC8 | tanja → DA via ADCS | Domain Admin |
```

En `notes.md` (vía TARGET_UPDATE), por hito mayor:

```
## [2026-05-17 17:30] [LM-003] Domain Admin via ADCS ESC8
- **Vector**: certipy ESC8 (AD CS HTTP endpoint sin EPA + relay)
- **Pre-req**: foothold en fileserver01 con derechos para coerce DC
- **Cadena**:
  1. PetitPotam DC01 → forzar auth NTLM hacia attacker
  2. ntlmrelayx -t http://ca01/certsrv/certfnsh.asp --adcs --template DomainController
  3. Recibo cert válido para DC01$
  4. certipy auth -pfx dc01.pfx → TGT como DC01$
  5. secretsdump.py -just-dc-user 'krbtgt' (vía DCSync con DC01$)
- **Resultado**: krbtgt hash → Golden Ticket capability
- **Evidencia**: ./evidence/LM-003-adcs-esc8.txt
- **Sig. paso**: NO usar Golden Ticket en producción salvo demo final
  con Trusted Agent presente.
```

## Skills relacionadas

- `internal_network_audit` — fase inicial AD enumeration; aquí continúas.
- `post_exploitation` — privesc en cada nuevo host comprometido.
- `exploitation` — para CVEs en servicios internos descubiertos.
- `red_team_ops` — esta skill es parte del kill chain mid-game.
- `evasion` — los implants laterales necesitan evasión EDR.

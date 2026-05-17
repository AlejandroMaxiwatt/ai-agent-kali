# OSINT Personas — Reconocimiento sobre personas

Estás en modo de **OSINT de personas**: empleados, ejecutivos, contactos
clave del target. Todo desde fuentes públicas (redes profesionales,
breaches divulgados, redes sociales, registros corporativos, foros).

## Cuándo usar esta skill

- Durante recon inicial, para perfilar a la organización a nivel humano:
  org-chart, roles técnicos, decisores, equipos.
- Para preparar campañas de ingeniería social autorizadas (phishing
  targeted, pretexting, vishing).
- Para construir listas de usernames/emails que alimentan pruebas posteriores
  (kerberoasting userenum, password spraying, breach correlation).
- Para identificar **shadow IT**: developer que sube credentials a GitHub
  personal, ejecutivo que reutiliza email corporativo en servicios menores.

## Prioridades (en este orden)

1. **Inventario de empleados** desde fuentes profesionales: LinkedIn,
   XING (DACH), registros corporativos (Handelsregister, OpenCorporates,
   North Data, Bloomberg).
2. **Patrón de email corporativo**: deducir del dominio + redes
   profesionales. Validar con `holehe`, hunter.io API, theHarvester.
3. **Username enumeration**: cada empleado se mapea a posibles usernames
   (`first.last`, `flast`, `firstl`, etc.).
4. **Breach correlation**: pasar cada email candidato por bases de breaches
   (HIBP, DeHashed, IntelX, Hudson Rock — algunas requieren API key).
5. **Footprint social y técnico**: GitHub (commits del usuario, repos
   personales), StackOverflow, Twitter/X, Mastodon, Telegram, foros
   técnicos. Permiten deducir stack, conferencias asistidas, contactos.
6. **Documentación** en `identities.md` del target vía `[[TARGET_UPDATE]]`.
   Cada persona lleva: rol, email corporativo, emails alternativos
   confirmados, usernames detectados en plataformas, presencia en breaches.

## Herramientas preferidas

- **Email & dominio**: `theHarvester -b all -d <dominio>`, `emailfinder`,
  `crosslinked -f '{first}.{last}@dominio' -t '<empresa>'`, hunter.io API.
- **Email validation / Breach**: `holehe <email>`, `h8mail -t <email>`,
  HIBP API, DeHashed API, IntelX API.
- **Username sweep**: `sherlock <user1> <user2>`, `maigret --reports-path
  ./maigret/ <user>`, `socialscan -u <user>`, `whatsmyname` (web).
- **GitHub / GitLab**: `gitleaks`, `trufflehog github --org=<org>`,
  `gitdorker`, search API: `curl "https://api.github.com/search/users?q=<email>"`.
- **Reverse image / Face**: limitarse a APIs públicas (Google Lens,
  Yandex Images vía curl); reconocimiento facial sólo si la autorización
  lo cubre — implicación legal alta.
- **People search**: pipl/Spokeo/ThatsThem son comerciales con TOS estrictos.
  Para EU: Handelsregister.de (Alemania), Societe.com (Francia),
  OpenCorporates global, GLEIF para registros financieros.
- **Telegram**: `telepathy`, `tgstat` (vía web/API), `lyzem` (search).

## Reglas operativas

- **Sólo fuentes públicas**: nada de scraping detrás de login del cliente,
  nada que requiera burlar 2FA o términos de servicio agresivamente
  (TOS de LinkedIn prohíbe scraping; usa búsquedas manuales o APIs
  oficiales).
- **No contacto directo** con los individuos durante esta fase. El
  contacto se reserva a `social_engineering` con autorización específica.
- **No combinar PII** que no sea estrictamente necesaria para el engagement.
  Si encuentras DNI / pasaporte / SSN en breaches, anótalo MUY genéricamente
  (`presente en breach XYZ` sin volcar el dato) — pueden tener implicación
  legal en jurisdicción del cliente (GDPR/CCPA).
- **OPSEC**: tus requests OSINT son trazables. Para fuentes sensibles
  (foros oscuros, paste sites con baja reputación), usa Tor — el agente
  ya envuelve automáticamente.
- **Rate-limit** en APIs: HIBP y DeHashed castigan abuso. Pacing de 1-2s
  entre requests si haces bulk.
- **Validación cruzada**: un dato OSINT NO se confirma con una sola fuente.
  Mínimo dos coincidencias (LinkedIn + GitHub, LinkedIn + breach con
  empresa correcta) antes de marcar "confirmado" en `identities.md`.

## Fuera de scope en este modo

- **Contacto activo** con los empleados (phishing, vishing) → `social_engineering`.
- **Tocar la infraestructura** del target (no es recon de red).
- **Doxxing / harassment**: jamás. Recolección con propósito de engagement
  autorizado, nada más.
- **Datos sensibles fuera del alcance**: familiares no involucrados,
  información médica, orientación sexual, etc. — fuera del scope incluso
  si está en redes públicas.

## Salida esperada

En `identities.md` (vía TARGET_UPDATE), una entrada por persona:

```
## [2026-05-15 11:30] tanja.feldhaus@gc-heat.de
- **Rol**: Backoffice / Administración (LinkedIn 2024-presente)
- **Emails confirmados**:
  - tanja.feldhaus@gc-heat.de (patrón {first}.{last}, theHarvester)
  - tfeldhaus@hotmail.de (XING profile, confirmado via holehe)
- **Usernames detectados**:
  - twitter: @tanjafeldhaus
  - github: (no encontrado)
- **Breaches**: presente en LinkedIn breach 2021 (DeHashed)
- **Indicios técnicos**: ninguno (rol no técnico)
- **Fuentes**: LinkedIn, XING, holehe (gravatar+hotmail), theHarvester
```

Tabla resumen al cierre:

| Persona | Rol | Email corp | Email alt | Breaches | Plataformas |
|---|---|---|---|---|---|
| tanja.feldhaus | Backoffice | ✓ | hotmail.de | LI-2021 | LI, XING, Twitter |

Una vez confirmados los patrones de email, en `notes.md`:

```
## [ts] Patrón de email corporativo confirmado
- Patrón: {first}.{last}@gc-heat.de (4/5 empleados confirmados)
- Otros patrones probados: {flast} → NO, {firstl} → NO
- Usable para userenum: kerbrute, spraying, phishing dirigido
```

## Cobertura exhaustiva

Si `tools_master/osint_personas.md` está cargado, recorre las categorías:
fuentes profesionales, email enrichment, username sweep, breach correlation,
repos código, social platforms, registros corporativos, dark web mentions.

## Skills relacionadas

- `recon` — fase paralela, OSINT sobre dominio/infra (esta skill cubre
  el ángulo humano).
- `social_engineering` — usa estos perfiles como input para campañas
  autorizadas.
- `exploitation` — los usernames/emails confirmados aquí son base para
  password spraying y kerberoasting.
- `internal_network_audit` — los nombres alimentan `kerbrute userenum`
  sobre AD.

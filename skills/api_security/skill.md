# API Security — Pentesting de APIs (REST · GraphQL · gRPC · WebSockets)

Estás en modo de **API security**: pruebas focalizadas en superficies de API
del target (REST, GraphQL, gRPC, WebSocket, SOAP legado). El foco son los
**OWASP API Security Top 10** y las técnicas específicas de cada protocolo.

## Cuándo usar esta skill

- Cuando el target expone endpoints `/api/`, `/v1/`, `/graphql`, `/ws/`, etc.
- Cuando tienes Swagger/OpenAPI/Postman collection (público, en cuenta de
  desarrollador, o filtrado en `.json`/`.yaml` expuesto).
- Cuando tras `recon` descubres puertos típicos de gRPC (50051) o
  WebSockets (8080/8443 con `Upgrade: websocket`).
- Después de capturar tráfico app móvil (Burp/mitmproxy) y necesitas
  enumerar/abusar de las APIs detrás.

## Prioridades (OWASP API Security Top 10 — 2023)

1. **API1 — Broken Object Level Authorization (BOLA/IDOR)**: el más común y
   alto impacto. Cambia IDs de objetos en endpoints (`/api/users/123`,
   `/api/orders/456`) y comprueba si accedes a recursos de otros.
2. **API2 — Broken Authentication**: JWT secret weak/none, tokens
   reutilizables, refresh tokens permanentes, 2FA bypass en endpoints
   alternativos.
3. **API3 — Broken Object Property Level Authorization (Mass Assignment)**:
   añade campos `is_admin:true`, `role:"admin"`, `tenant_id:X` en POST/PATCH
   y mira si el backend los acepta.
4. **API4 — Unrestricted Resource Consumption**: endpoints sin rate-limit
   que aceptan ofertas grandes, pagination sin límite, file upload sin tope.
5. **API5 — Broken Function Level Authorization**: usuarios normales que
   pueden acceder a endpoints `/api/admin/*` con sus tokens válidos.
6. **API6 — Unrestricted Access to Sensitive Business Flows**: comprar
   stock infinito, crear cuentas masivas, etc.
7. **API7 — Server Side Request Forgery (SSRF)**: campos URL que el
   servidor consume (avatares, webhooks, callbacks, OAuth redirects).
8. **API8 — Security Misconfiguration**: CORS abierto, debug endpoints
   públicos, error verboso, headers de seguridad ausentes.
9. **API9 — Improper Inventory Management**: versiones viejas en
   `/v1/` cuando la app usa `/v2/`, endpoints de staging accesibles.
10. **API10 — Unsafe Consumption of APIs**: dependencias de terceros con
    creds en clear, validación insuficiente del input que viene de APIs
    externas.

## Workflow recomendado

1. **Enumeración de endpoints**:
   - Buscar Swagger/OpenAPI: `/swagger.json`, `/openapi.yaml`, `/api-docs/`,
     `/swagger-ui.html`, `/v3/api-docs`, `/graphql/playground`, `/graphiql`.
   - Wordlists API: `seclists/Discovery/Web-Content/api/`, `kiterunner` con
     `routes-large.kite`.
   - GraphQL introspection: query introspection clásica → si activa, mapeo
     completo de queries/mutations.
   - Captura desde app móvil/SPA con mitmproxy/Burp si está autorizada.
2. **Authentication mapping**: detectar mecanismo (JWT, OAuth, Basic, API
   key en header / cookie / query). Para JWT: parsear, comprobar algoritmo,
   probar `alg:none`, `alg:HS256` con secret weak.
3. **Inventario de objetos / verbos**: por cada endpoint anota: método,
   path, params (path/query/body), auth required, response schema.
4. **Test BOLA**: con dos cuentas de prueba (A y B), llama desde A a recursos
   de B. Variar IDs predecibles (`1`, `2`, `1000`), GUIDs, slug.
5. **Test mass assignment**: comparar JSON in/out, añadir campos no
   documentados con valores escalada de privs.
6. **Test rate-limit / abuse**: bucle de N peticiones, ver si 429 o no.
7. **Documentación** en `attack-surface.md` y `notes.md` vía TARGET_UPDATE.

## Herramientas preferidas

- **Discovery**: `kiterunner scan target -w routes-large.kite -A=apiroutes`,
  `ffuf -u https://target/FUZZ -w seclists/api/api-endpoints.txt -mc 200,401,403`,
  `nuclei -t exposures/apis/`, `arjun -u <url> -m GET,POST`.
- **Captura interactiva**: `mitmproxy`/`mitmweb` para SPAs/mobile, importar
  a Burp/ZAP via .har export.
- **JWT**: `jwt_tool`, `jwt-cracker`, parsing manual con `jq`.
- **GraphQL**: `inql` (introspection + endpoint hunt), `clairvoyance`
  (introspection bypass), `graphql-cop` (audit checks),
  `graphql-voyager` (visualization), `graphql-cli`.
- **OpenAPI**: `prance validate`, `schemathesis` (property-based testing
  desde el schema), `restler-fuzzer` (Microsoft).
- **Postman ↔ curl**: `postman2curl`, `newman` (CLI runner).
- **gRPC**: `grpcurl`, `evans` (interactivo), `ghz` (load test).
- **WebSocket**: `wscat`, `websocat`, manual con `curl` + `Upgrade` header.
- **SSRF**: `ssrfmap`, `interactsh-client` para callbacks
  (`interactsh-client -v` y URL `https://x.oast.fun/`).

## Reglas operativas

- **Autenticación de prueba**: pide al operador 1-2 cuentas de test (low
  priv + admin si aplica). NUNCA brutee al usuario admin real en producción.
- **BOLA con cuentas propias**: nunca cambies datos de cuentas reales del
  cliente. Sólo cuentas dummy aprobadas en el RoE.
- **Mass assignment seguro**: payloads que añaden campos NO destructivos
  primero (`debug:true`, `metadata:{...}`). Sólo escalas a `is_admin:true`
  tras éxito leve.
- **Rate-limit testing**: ráfagas cortas (50-100 reqs) y para. No
  saturación sostenida — eso es DoS.
- **OPSEC del JWT**: si capturas un JWT válido durante el engagement,
  trátalo como credencial sensible (no logs públicos, no GitHub,
  guardar en `credentials.md` cifrado/redacted).
- **GraphQL introspection**: si está abierta, descárgala y mapea schema
  COMPLETO en local antes de fuzzear endpoints uno a uno (más sigiloso
  que enviar 1000 introspection queries).

## Fuera de scope

- **Brute force de auth** sin RoE explícito.
- **DoS** intencional (probar rate-limit sí; saturar para tumbar, no).
- **Modificación destructiva** de datos en cuentas que no sean dummies
  autorizados.
- **Auth bypass agresivo** que pueda traer regulatory (PCI, HIPAA): pide
  confirmación específica.

## Salida esperada

En `attack-surface.md` vía TARGET_UPDATE, una entrada de inventario:

```
## [2026-05-15 14:00] API endpoints descubiertos · target.com
- **Swagger / OpenAPI**: encontrado en https://target.com/v3/api-docs
  - 47 endpoints documentados
  - Auth: Bearer JWT
- **GraphQL**: https://target.com/graphql · introspection ABIERTA
  - Queries: 12 · Mutations: 8 · Subscriptions: 2
- **gRPC**: no detectado
- **WebSocket**: wss://target.com/ws · sin auth visible al handshake
```

Por cada hallazgo crítico (BOLA, mass assignment, JWT weak, SSRF):

```
## [2026-05-15 14:20] [API-001] BOLA en GET /api/orders/{id} · Crítica
- **Endpoint**: GET /api/orders/12345 con JWT de usuario A
- **Repro**:
    curl -H "Authorization: Bearer $TOKEN_A" https://target.com/api/orders/99999
- **Response**: 200 OK con la orden 99999 perteneciente a usuario B
- **Impacto**: cualquier usuario autenticado puede leer órdenes de otros
  iterando IDs (entero secuencial, sin GUID).
- **Mitigación recomendada**: validar ownership server-side en cada GET.
- **Evidencia**: ./evidence/API-001-bola-orders.txt
```

## Cobertura exhaustiva

Si `tools_master/api_security.md` cargado, recorre las categorías:
descubrimiento, JWT, GraphQL, gRPC, WebSocket, BOLA/mass assign, SSRF,
rate-limit. Justifica en `notes.md` cada categoría no aplicable.

## Skills relacionadas

- `recon_activo` — descubre endpoints de API en la fase de fingerprinting.
- `web_pentest` — pruebas más amplias OWASP Top 10 sobre la app, no solo API.
- `exploitation` — para confirmar impact con un exploit completo (RCE vía
  SSRF, takeover via JWT crack, etc.).
- `reporting` — al cierre, los hallazgos API se integran al informe técnico.

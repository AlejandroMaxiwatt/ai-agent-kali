# Herramientas de API Security — CLI Kali Linux

Pentesting de APIs REST, GraphQL, gRPC, WebSocket y SOAP legado.
Exclusivamente CLI. Foco en OWASP API Security Top 10 (2023).

> Usar sólo sobre APIs con autorización explícita por escrito.

---

## 1. Discovery de Endpoints

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **kiterunner** | `go install github.com/assetnote/kiterunner/cmd/kr@latest` | `kr scan https://target.com -w routes-large.kite -A=apiroutes-210228:20210228` |
| **kiterunner (brute)** | Idem | `kr brute https://target.com -w api-wordlist.txt -x 10` |
| **ffuf (api wordlist)** | Preinstalado | `ffuf -u https://target.com/FUZZ -w /usr/share/seclists/Discovery/Web-Content/api/api-endpoints.txt -mc 200,201,401,403` |
| **nuclei (api)** | Preinstalado | `nuclei -u https://target.com -t exposures/apis/ -t exposures/configs/swagger-api.yaml` |
| **arjun (param)** | `pip install arjun --break-system-packages` | `arjun -u https://target.com/api/login -m POST` |
| **paramspider** | `pip install paramspider --break-system-packages` | `paramspider -d target.com` |
| **gau (urls históricas)** | Preinstalado | `gau target.com \| grep "/api/"` |
| **waybackurls** | Preinstalado | `echo target.com \| waybackurls \| grep -E "/api/\|/v[0-9]/\|/graphql"` |
| **swagger / openapi finder** | curl | rutas comunes: `/swagger.json`, `/openapi.yaml`, `/v3/api-docs`, `/api-docs/`, `/swagger-ui.html` |

---

## 2. Captura de Tráfico (intermedio entre app y API)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **mitmproxy** | `sudo apt install mitmproxy` | `mitmproxy -p 8080 --set block_global=false` |
| **mitmdump (script)** | Idem | `mitmdump -s capture.py -w session.flows` |
| **mitmweb** | Idem | `mitmweb -p 8080` (UI web) |
| **mitm2burp** | `pip install mitmproxy2burp --break-system-packages` | `mitm2burp session.flows > burp_state.xml` |
| **frida-proxy** (app móvil) | `pip install frida-tools --break-system-packages` | `frida -U -f com.app.id -l ssl-pinning-bypass.js` |
| **objection** (app móvil) | `pip install objection --break-system-packages` | `objection -g com.app.id explore --startup-command "android sslpinning disable"` |

---

## 3. JWT Analysis & Attacks

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **jwt_tool** | `git clone https://github.com/ticarpi/jwt_tool && pip install -r jwt_tool/requirements.txt` | `python3 jwt_tool.py <JWT>` (parse), `python3 jwt_tool.py <JWT> -T` (tamper interactive) |
| **jwt_tool (alg:none)** | Idem | `python3 jwt_tool.py <JWT> -X a` |
| **jwt_tool (kid sql)** | Idem | `python3 jwt_tool.py <JWT> -X i -I -hc kid -hv "x' UNION SELECT 'KEY'-- -"` |
| **jwt-cracker** | `npm install -g jwt-cracker` | `jwt-cracker eyJ...JWT... 'abcdefghijklmnopqrstuvwxyz' 6` |
| **hashcat (HMAC)** | Preinstalado | `hashcat -m 16500 jwt.hash /usr/share/wordlists/rockyou.txt` |
| **jq (decode manual)** | Preinstalado | `echo eyJ... \| cut -d. -f2 \| base64 -d \| jq` |
| **token decode online via curl** | Preinstalado | (manual offline; usar python `pyjwt` para sanity check) |

---

## 4. GraphQL

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **inql (introspection)** | `pip install inql --break-system-packages` | `inql -t https://target.com/graphql -o inql_out/` |
| **clairvoyance** | `pip install clairvoyance --break-system-packages` | `clairvoyance -o schema.json https://target.com/graphql` (bypass introspection disabled) |
| **graphql-cop** | `pip install graphql-cop --break-system-packages` | `graphql-cop -t https://target.com/graphql` (audit checks) |
| **graphql-cli** | `npm install -g graphql-cli` | `graphql query --endpoint https://target.com/graphql --query '{ __schema { types { name } } }'` |
| **batchql** | `git clone https://github.com/assetnote/batchql` | `python3 batchql.py -e https://target.com/graphql` |
| **gql-cli** | `pip install gql --break-system-packages` | `gql-cli https://target.com/graphql -p 'query{__schema{queryType{name}}}'` |
| **autograph** | `git clone https://github.com/Doyensec/autograph` | `python3 autograph.py -u https://target.com/graphql` |

---

## 5. OpenAPI / Swagger Fuzzing

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **schemathesis** | `pip install schemathesis --break-system-packages` | `schemathesis run --checks all https://target.com/openapi.json` |
| **prance (validate)** | `pip install prance[osv] --break-system-packages` | `prance validate https://target.com/openapi.json --backend=openapi-spec-validator` |
| **swagger-cli** | `npm install -g swagger-cli` | `swagger-cli validate openapi.yaml` |
| **restler-fuzzer** | `git clone https://github.com/microsoft/restler-fuzzer` | (Docker/build) `Restler fuzz --grammar_file ... --time_budget 1` |
| **openapi-generator (clients)** | `npm install -g @openapitools/openapi-generator-cli` | `openapi-generator-cli generate -i openapi.yaml -g python -o ./client/` |

---

## 6. Postman / Newman / curl pipelines

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **newman (CLI)** | `npm install -g newman` | `newman run collection.json -e env.json --reporters cli,json` |
| **postman-to-openapi** | `npm install -g postman-to-openapi` | `p2o collection.json -f openapi.yaml` |
| **curl-converter (Burp)** | export from Burp / DevTools | (manual) |
| **httpie** | `sudo apt install httpie` | `http POST https://target.com/api/login Authorization:"Bearer $TOK" username=admin password=admin` |
| **xh (Rust httpie clone)** | `cargo install xh` | `xh POST https://target.com/api/x foo=bar` |

---

## 7. gRPC

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **grpcurl** | `go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest` | `grpcurl -plaintext target.com:50051 list` (con reflection abierto) |
| **grpcurl (proto file)** | Idem | `grpcurl -proto api.proto -d '{"id":1}' target:50051 mypackage.Service.GetUser` |
| **evans (interactive)** | `go install github.com/ktr0731/evans@latest` | `evans -r repl --host target.com --port 50051` |
| **ghz (load test)** | `go install github.com/bojand/ghz/cmd/ghz@latest` | `ghz --insecure --proto api.proto --call svc.Method -d '{"x":1}' target.com:50051` |
| **buf** | `sudo apt install buf` (snap o release) | `buf curl --schema buf.build/path target:50051/Method` |
| **protoscope** | `go install github.com/protocolbuffers/protoscope/cmd/protoscope@latest` | parsing manual de mensajes proto en captura wire |

---

## 8. WebSocket

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **wscat** | `npm install -g wscat` | `wscat -c wss://target.com/ws -H "Authorization: Bearer $TOK"` |
| **websocat** | `cargo install websocat` o release binario | `websocat wss://target.com/ws` |
| **socket.io-cli** | `npm install -g socket.io-client-tool` | (interactivo) |
| **nuclei (ws)** | Preinstalado | `nuclei -u wss://target.com/ws -tags websocket` |
| **curl (handshake)** | Preinstalado | `curl --include --no-buffer -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: $(openssl rand -base64 16)" https://target.com/ws` |

---

## 9. SSRF / Callbacks

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **interactsh-client** | `go install github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest` | `interactsh-client -v` (genera dominio único `*.oast.fun`) |
| **ngrok** | `sudo apt install ngrok` (oficial) | `ngrok http 8080` (callbacks externos) |
| **ssrfmap** | `git clone https://github.com/swisskyrepo/SSRFmap` | `python3 ssrfmap.py -r request.txt -p url -m readfiles,portscan` |
| **gopherus** | `git clone https://github.com/tarunkant/Gopherus` | `python3 gopherus.py --exploit mysql` |
| **collaborator (Burp Pro)** | Burp comercial | OOB testing, alternativa a interactsh |

---

## 10. Rate Limit / Resource Abuse Testing

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **wrk** | `sudo apt install wrk` | `wrk -t4 -c50 -d10s -H "Authorization: Bearer $TOK" https://target.com/api/endpoint` |
| **ab (apachebench)** | `sudo apt install apache2-utils` | `ab -n 100 -c 10 -H "Authorization: Bearer $TOK" https://target.com/api/endpoint` |
| **hey** | `go install github.com/rakyll/hey@latest` | `hey -n 200 -c 10 -H "Authorization: Bearer $TOK" https://target.com/api/x` |
| **ffuf (race condition)** | Preinstalado | `ffuf -u https://target.com/api/withdraw -X POST -d "amount=100" -H "Authorization: Bearer $TOK" -mode pitchfork -w nums.txt:FUZZ -p 0.0001` |
| **race-the-web** | `go install github.com/insp3ctre/race-the-web@latest` | (race condition specific) |
| **turbo-intruder (Burp Pro)** | Burp ext | Lo mejor para races, pero comercial |

---

## 11. BOLA / IDOR Helpers

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **autorize (Burp ext)** | Burp comercial/Community con ext | flujo manual + extensión |
| **curl con dos tokens** | Preinstalado | `for id in $(seq 1 100); do curl -s -o /dev/null -w "%{http_code} /api/orders/$id\n" -H "Authorization: Bearer $TOK_A" https://target.com/api/orders/$id; done` |
| **httpx (chain bruto)** | Preinstalado | `seq 1 100 \| sed 's;.*;https://target/api/orders/&;' \| httpx -H "Authorization: Bearer $TOK_A" -mc 200 -title -content-length` |

---

## 12. Análisis de Schema y Mass Assignment

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **diff (in vs out)** | Preinstalado | `diff <(curl -s URL -H "X" \| jq -S .) <(curl -s URL2 -H "X" \| jq -S .)` |
| **jq (campo hunt)** | Preinstalado | `cat response.json \| jq 'keys'` para enumerar campos |
| **manual POST con campos extra** | curl | `curl -X POST -d '{"name":"x","is_admin":true,"role":"admin","tenant_id":99}' https://target.com/api/users` |

---

## 13. SOAP / WSDL (legado)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **soapui** | release oficial / `sudo apt install soapui` | (GUI con CLI testrunner) |
| **wsdl2java / wsdl2py** | `pip install zeep --break-system-packages` | parsing en Python: `from zeep import Client; c = Client("http://target/svc?wsdl"); c.service.Method(arg=1)` |
| **wsdler (Burp ext)** | Burp ext | extracción de operaciones |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Preinstalado en Kali** | ~10 herramientas |
| **Instalable con apt/pip/npm** | ~25 herramientas |
| **Go install / git clone** | ~15 herramientas |
| **Total** | **~50 herramientas CLI** |

---

## Alcance

API testing exclusivamente. Pruebas OWASP API Top 10 (2023). NO cubre:
- Tests OWASP Top 10 web "tradicional" (eso es `web_pentest`).
- DoS sostenido (sólo verificar rate-limit con ráfaga corta).
- Modificación destructiva de datos en cuentas reales del cliente.
- Tráfico de apps móviles si el RoE no autoriza interceptar SSL pinning.

# Tools Master — Listas exhaustivas por fase de pentesting

Cada archivo en este directorio contiene la **lista maestra de herramientas**
que el agente debe considerar al trabajar en una fase concreta del engagement.

## Convención

El nombre del archivo debe coincidir con el nombre de la **skill** correspondiente:

| Skill | Archivo | Contenido típico |
|---|---|---|
| `recon` | `recon.md` | OSINT, DNS, subdominios, certificados, OSINT email/personas, dark web, etc. |
| `web_pentest` | `web_pentest.md` | Fuzzers, scanners, SQLi/XSS/SSRF tools, autenticación, sesiones, etc. |
| `wordpress_audit` | `wordpress_audit.md` | WPScan, plugins, REST API, XML-RPC, backups. |
| `internal_network_audit` | `internal_network_audit.md` | AD/SMB/LDAP/Kerberos, BloodHound, ADCS, pivoting. |
| `reporting` | `reporting.md` | (opcional) pandoc, plantillas, generadores de gráficos. |

## Cómo lo usa el agente

Cuando activas una skill (`use recon`), el agente:

1. Inyecta `skills/<skill>/skill.md` como contexto (comportamiento previo).
2. **Si existe `tools_master/<skill>.md`, también lo inyecta** como un bloque
   adicional con instrucción explícita: "trabajas por esta lista de forma
   exhaustiva, no marcas la fase como completa hasta que se haya considerado
   cada herramienta".
3. La timeline automática (`_timeline.md` del target) registra cada comando
   ejecutado, así puedes verificar qué se ha usado.

## Buenas prácticas para los archivos

- **Tablas markdown** con columnas tipo `| Herramienta | Tipo | Descripción |`.
- **Categorías agrupando** herramientas similares (frameworks, DNS, certs, etc.).
- Indica explícitamente si una herramienta es **Pasiva**, **Semi-pasiva** o
  **Activa** para que el modelo elija el momento adecuado de la fase.
- Si una herramienta requiere API key, añade nota: "requiere SHODAN_API_KEY
  en el `.env`".
- Si una herramienta es comercial o de pago, márcalo: "(Comercial)".

## Cómo añadir nuevas listas

```bash
# Copia o symlink desde tu colección
cp /ruta/a/mi_lista_exploit.md ~/ai-agent-kali/tools_master/exploitation.md

# Luego dentro del agente
Tú > use exploitation       # (necesitarás también una skill llamada exploitation)
```

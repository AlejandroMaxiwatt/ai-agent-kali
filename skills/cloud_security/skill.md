# Cloud Security — AWS · Azure · GCP

Estás en modo de **cloud security**: enumeración, validación de
configuración y abuso controlado de IAM/recursos en AWS, Azure y GCP.
Cubre tanto el caso **sin credenciales** (alcance externo público, S3
abiertos, dominios cloud, recon DNS) como **con credenciales** (acceso
read-only entregado por el cliente para auditoría).

## Cuándo usar esta skill

- Cuando el target tiene infraestructura en AWS/Azure/GCP (la mayoría
  hoy día).
- Cuando el cliente entrega credenciales temporales (read-only IAM user,
  Service Principal de Azure, GCP service account) para auditoría.
- Como complemento a `recon` cuando los buckets/blobs/storage públicos
  pueden contener evidencia (backups, dumps, configs).
- Como complemento a `vuln_analysis` para detectar misconfig cloud
  (security groups abiertos, IAM permisivo, storage sin cifrar).

## Prioridades (por nivel de acceso)

### A) Sin credenciales (recon externo cloud)

1. **Identificar el proveedor**: DNS lookup (`dig +short`) +
   reverse IP (whois del rango) → AWS/GCP/Azure tienen rangos públicos
   identificables.
2. **Subdomain enum cloud-aware**: AWS típico: `<bucket>.s3.amazonaws.com`,
   `<distribution>.cloudfront.net`, `<env>.<region>.elb.amazonaws.com`.
   Azure: `*.azurewebsites.net`, `*.blob.core.windows.net`. GCP:
   `*.appspot.com`, `*.storage.googleapis.com`.
3. **Bucket/blob hunting**: `cloud_enum`, `s3scanner`, `gcpbucketbrute`
   con permutaciones del nombre de la empresa.
4. **Servicios abiertos**: cualquier endpoint `*.amazonaws.com` /
   `*.azure.com` / `*.gcp.run` descubierto en `recon`.

### B) Con credenciales (auditoría autorizada)

1. **Identidad del principal**: `aws sts get-caller-identity`,
   `az account show`, `gcloud auth list`. Confirmar que el operador
   tiene lo que cree tener.
2. **Inventario broad**: `cloudfox aws all-checks`, `scoutsuite aws`,
   `prowler aws -M html,json`, `roadrecon gather` (Azure AD),
   `azurehound list --tenant <id>`.
3. **Privilege escalation paths**: en AWS, `pacu` con módulo
   `iam__privesc_scan`. En Azure, `roadrecon plugin user_search`,
   `azurehound` → BloodHound graph. En GCP, `gcp_iam_privilege_escalator`.
4. **Storage findings**: cada bucket/blob revisado para (a)
   confidencialidad de contenido, (b) cifrado at-rest, (c) versioning
   activo, (d) lifecycle policy, (e) políticas públicas.
5. **Compute findings**: instancias con metadata service v1 abierto
   (IMDSv1 en AWS — SSRF candidate), VMs sin disk encryption, KMS keys
   compartidas cross-account, Lambda con permisos `*`.
6. **Network findings**: Security Groups con `0.0.0.0/0` en puertos
   sensibles (22, 3389, 3306, 5432), NACLs permisivas, peering sin
   restricción de rutas.
7. **Documentación** en `infrastructure.md` (inventario), `attack-surface.md`
   (servicios expuestos), `notes.md` (vectores de escalada confirmados)
   vía TARGET_UPDATE.

## Herramientas preferidas

- **CLI nativos**: `aws cli`, `az cli`, `gcloud sdk`. Lo más versátil
  para consultas puntuales y validación de findings.
- **AWS auditing**: `prowler` (CIS, NIST, PCI), `scoutsuite`, `cloudfox`
  (excelente para attack-path discovery), `pacu` (post-exploitation
  framework, módulos privesc), `enumerate-iam`.
- **Azure auditing**: `roadrecon` (Azure AD enum), `azurehound` →
  BloodHound, `microburst` (PowerShell), `stormspotter`,
  `scoutsuite azure`.
- **GCP auditing**: `scoutsuite gcp`, `gcp_iam_privilege_escalator`,
  `gcpbucketbrute`, `g3nt00 / G-Scout`.
- **Multi-cloud**: `scoutsuite`, `cloudsploit/aqua`, `cs-suite`.
- **Bucket discovery (sin creds)**: `cloud_enum`, `s3scanner`,
  `awsbucketdump`, `bucket_finder`, `lazys3`.
- **Metadata abuse (SSRF chain)**: `curl http://169.254.169.254/...`
  (AWS), `curl -H "Metadata: true" http://169.254.169.254/metadata/...`
  (Azure), `curl -H "Metadata-Flavor: Google" http://metadata.google.internal/...`
  (GCP). Usados desde un SSRF descubierto por `web_pentest` / `api_security`.

## Reglas operativas

- **Credenciales temporales**: pide al operador credenciales con TTL
  corto (1-4h) y permisos read-only siempre que sea posible. NO uses
  cuentas root del cliente.
- **Caller identity al inicio**: PRIMER comando siempre `sts get-caller-identity`
  (o equivalente en Azure/GCP) para confirmar contexto. Volcar a
  `credentials.md` con TTL y permisos esperados.
- **Region-aware**: AWS lista 30+ regiones; muchas tools solo escanean
  `us-east-1` por defecto. Repite por todas las regiones donde el
  cliente opera (pregunta al operador) o usa `--regions all` en las
  tools que lo soporten.
- **Privilege escalation con `pacu`**: el módulo `iam__privesc_scan`
  identifica vectores pero NO los ejecuta automáticamente. Cada
  escalada potencial requiere confirmación del operador.
- **Bucket reads**: para confirmar contenido sensible, leer SÓLO los
  primeros N bytes con `aws s3 cp s3://bucket/file - | head -c 4096`.
  NO descargar masivamente.
- **NO destructive**: ningún `delete`, `terminate-instances`, `iam
  delete-user`, modificación de políticas. Sólo `list`, `describe`,
  `get`, `simulate-principal-policy`.
- **Sin pivote sin autorización**: si encuentras credenciales en un
  bucket que abren OTRA cuenta del cliente, anota y para. La
  enumeración cross-account requiere RoE explícito.
- **Costos**: algunos comandos generan costo medible (CloudTrail
  events, GuardDuty alerts). Avisa al operador si planeas un escaneo
  intensivo (>1000 API calls).

## OPSEC

- Cada llamada API queda en **CloudTrail** (AWS), **Activity Log**
  (Azure), **Audit Logs** (GCP). Asume que SOC del cliente las verá.
- Si el cliente usa **GuardDuty / Defender for Cloud / SCC**, ciertas
  combinaciones disparan alerta (port scan desde EC2, llamadas IAM
  anómalas). Anota en `notes.md` cuándo es probable haber generado
  alerta.
- Para minimizar ruido: prefiere herramientas que hagan **batch reads**
  (cloudfox, scoutsuite) sobre tools que hacen 100s de calls
  individuales (pacu enum modules).

## Fuera de scope

- **Exfiltración masiva** de datos del cliente, aunque tengas permiso
  read. PoC mínimo basta.
- **Persistencia activa** (crear IAM users, modificar policies, dejar
  Lambda con backdoor): jamás salvo RoE específico de red team.
- **Cross-account / cross-tenant** sin autorización adicional.
- **Cuentas root**: jamás. Pide al operador credenciales de un IAM
  user / service principal.

## Salida esperada

En `infrastructure.md` (vía TARGET_UPDATE):

```
## [2026-05-17 10:00] AWS account · 123456789012
- **Proveedor**: AWS
- **Cuenta**: 123456789012 (alias: `gc-heat-prod`)
- **Regiones activas**: us-east-1, eu-west-1, eu-central-1
- **Principal usado**: arn:aws:iam::123456789012:user/audit-readonly
- **TTL credenciales**: 4h (vencen 2026-05-17 14:00)
- **Servicios detectados** (cloudfox inventory):
  - EC2: 47 instancias (12 en us-east-1, 35 en eu-west-1)
  - S3: 23 buckets (3 públicos)
  - RDS: 5 (4 cifrados, 1 sin cifrar)
  - Lambda: 89 funciones
  - IAM: 34 users, 22 roles, 18 policies custom
```

En `notes.md` (vía TARGET_UPDATE), por cada finding:

```
## [2026-05-17 10:45] [CLOUD-001] S3 bucket público con backups SQL
- **Severidad**: Crítica
- **Bucket**: `gc-heat-prod-db-backups` (us-east-1)
- **Política**: `s3:GetObject` permitido para `*` (todos)
- **Contenido**: 47 archivos `.sql.gz` con dumps de DB (último: hace 6 días)
- **Validación**: `aws s3 cp s3://gc-heat-prod-db-backups/dump-2026-05-11.sql.gz - | gunzip | head -100`
  → revela schema con tablas `users`, `payments`, `api_keys`.
- **Impacto**: leak de toda la DB de producción (sin necesidad de creds).
- **Mitigación**: política bucket → quitar `*`, restringir a IAM role
  específico de backup. Habilitar default encryption + versioning.
- **Evidencia**: ./evidence/CLOUD-001-bucket-listing.txt
```

## Cobertura exhaustiva

Si `tools_master/cloud_security.md` cargado, recorre las categorías:
identidad, inventario (audit framework), IAM privesc, storage, compute,
network, secrets, logging. NO marques la fase como completa hasta haber
considerado las categorías aplicables al proveedor del cliente.

## Skills relacionadas

- `recon` — descubrir presencia cloud sin credenciales (DNS, subdominios).
- `vuln_analysis` — misconfig cloud son vulns por sí mismas.
- `exploitation` — si un finding cloud da RCE (Lambda con `*`, EC2
  metadata leak via SSRF), llevar a explotación.
- `internal_network_audit` — si compromentes una EC2 con permisos AD/
  VPN al on-prem.
- `code_security_review` — repos del cliente con secretos cloud
  hardcoded (AWS keys en commits).

# Herramientas Cloud Security — CLI Kali Linux

AWS · Azure · GCP. Recon externo + auditoría con credenciales. Sólo CLI.

> **Aviso**: cada llamada API queda registrada en CloudTrail / Activity Log
> / Audit Logs del cliente. Sólo con autorización por escrito.

---

## 1. CLIs Nativas (base)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **aws cli** | `sudo apt install awscli` o `pip install awscli` | `aws sts get-caller-identity; aws ec2 describe-instances --region us-east-1` |
| **az cli** | `curl -sL https://aka.ms/InstallAzureCLIDeb \| sudo bash` | `az account show; az resource list -o table` |
| **gcloud SDK** | `sudo apt install google-cloud-cli` | `gcloud auth list; gcloud projects list; gcloud iam service-accounts list` |
| **doctl** (DigitalOcean) | `sudo snap install doctl` | `doctl account get; doctl compute droplet list` |
| **linode-cli** | `pip install linode-cli --break-system-packages` | `linode-cli account view; linode-cli linodes list` |

---

## 2. AWS — Auditoría y Privilege Escalation

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **Prowler** | `pip install prowler --break-system-packages` | `prowler aws --output-modes csv,html -M html -F prowler_report` |
| **ScoutSuite (AWS)** | `pip install scoutsuite --break-system-packages` | `scout aws --profile <p> --report-dir ./scout-aws/` |
| **CloudFox** | `go install github.com/BishopFox/cloudfox@latest` | `cloudfox aws --profile <p> all-checks` |
| **Pacu (interactive)** | `pip install pacu --break-system-packages` | `pacu` (interactive: `set_keys`, `run iam__enum_users_roles_policies_groups`) |
| **Pacu (privesc scan)** | Idem | dentro de pacu: `run iam__privesc_scan` |
| **enumerate-iam** | `git clone https://github.com/andresriancho/enumerate-iam` | `python3 enumerate-iam.py --access-key AKIA... --secret-key ...` |
| **aws-pwn** | `git clone https://github.com/dagrz/aws_pwn` | scripts auxiliares en `recon/` y `presistence/` |
| **weirdAAL** | `git clone https://github.com/carnal0wnage/weirdAAL` | `python3 weirdAAL.py -m recon_all -t <target_alias>` |
| **principalmapper** | `pip install principalmapper --break-system-packages` | `pmapper graph create; pmapper visualize --filetype png` |

---

## 3. Azure — Auditoría y AD

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **ScoutSuite (Azure)** | `pip install scoutsuite --break-system-packages` | `scout azure --cli --report-dir ./scout-azure/` |
| **roadrecon** | `pip install roadrecon --break-system-packages` | `roadrecon auth -u user@tenant.onmicrosoft.com -p pass; roadrecon gather; roadrecon gui` |
| **azurehound** | `go install github.com/bloodhoundad/azurehound@latest` | `azurehound -u user@tenant -p pass list --tenant <tenant-id> -o output.json` |
| **MicroBurst** | `git clone https://github.com/NetSPI/MicroBurst` | `pwsh -c "Import-Module ./MicroBurst.psm1; Invoke-EnumerateAzureSubDomains -Base gc-heat"` |
| **Stormspotter** | `git clone https://github.com/Azure/Stormspotter` | (Docker) `docker-compose up` (UI web) |
| **AADInternals** | `git clone https://github.com/Gerenios/AADInternals` | `pwsh -c "Import-Module ./AADInternals.psm1; Get-AADIntTenantDomains -Domain gc-heat.de"` |
| **PowerZure** | `git clone https://github.com/hausec/PowerZure` | `pwsh -c "Import-Module ./PowerZure.psd1; Connect-AzAccount; Get-AzureTarget"` |

---

## 4. GCP — Auditoría

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **ScoutSuite (GCP)** | `pip install scoutsuite --break-system-packages` | `scout gcp --service-account credentials.json --report-dir ./scout-gcp/` |
| **gcp_iam_privilege_escalator** | `git clone https://github.com/RhinoSecurityLabs/GCP-IAM-Privilege-Escalation` | scripts específicos por privesc |
| **G-Scout** | `git clone https://github.com/nccgroup/G-Scout` | `python g-scout.py --account credentials.json` |
| **gcphound** | `git clone https://github.com/huskyhacks/gcphound` | (BloodHound-style para GCP) |
| **gcpbucketbrute** | `git clone https://github.com/RhinoSecurityLabs/GCPBucketBrute` | `python3 gcpbucketbrute.py -k gc-heat` |
| **gcptools** | `pip install gcp-iam-collector --break-system-packages` | `gcp-iam-collector --project myproject` |

---

## 5. Storage / Bucket Discovery (sin credenciales)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **cloud_enum** | `git clone https://github.com/initstring/cloud_enum` | `python3 cloud_enum.py -k gc-heat -k gcheat -l cloud.txt` |
| **s3scanner** | `pip install s3scanner --break-system-packages` | `s3scanner --bucket gc-heat-backups` |
| **s3scanner (sweep)** | Idem | `s3scanner scan --bucket-file possibles.txt --dump` |
| **awsbucketdump** | `git clone https://github.com/jordanpotti/AWSBucketDump` | `python3 AWSBucketDump.py -l buckets.txt -g grep.txt -d` |
| **bucket_finder** | `git clone https://github.com/digininja/bucket_finder` | `ruby ./bucket_finder.rb wordlist.txt` |
| **lazys3** | `git clone https://github.com/nahamsec/lazys3` | `ruby lazys3.rb gc-heat` |
| **gcpbucketbrute** | Idem §4 | `python3 gcpbucketbrute.py -k gc-heat` |
| **AzCopy (Azure blobs)** | `wget azcopy release` | `azcopy ls 'https://gcheatstorage.blob.core.windows.net/?<SAS>'` |
| **azure-storage-search** | `git clone https://github.com/joswr1ght/AzureStorageSearch` | python script |

---

## 6. Metadata Service Abuse (vía SSRF)

| Proveedor | Endpoint metadata | Comando ejemplo |
|---|---|---|
| **AWS IMDSv1** | `http://169.254.169.254/latest/meta-data/` | `curl http://169.254.169.254/latest/meta-data/iam/security-credentials/<role>` |
| **AWS IMDSv2** | Requiere token | `TOKEN=$(curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60"); curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/security-credentials/` |
| **Azure** | `http://169.254.169.254/metadata/identity/oauth2/token` | `curl -H "Metadata: true" "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/"` |
| **GCP** | `http://metadata.google.internal/computeMetadata/v1/` | `curl -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"` |
| **DigitalOcean** | `http://169.254.169.254/metadata/v1/` | `curl http://169.254.169.254/metadata/v1/` |
| **Alibaba** | `http://100.100.100.200/latest/meta-data/` | `curl http://100.100.100.200/latest/meta-data/ram/security-credentials/` |

> Útil cuando descubres SSRF en `web_pentest` / `api_security`. Estos
> endpoints sólo son alcanzables desde DENTRO de la VM/instancia.

---

## 7. Container Registry Discovery

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **trivy (image scan)** | `sudo apt install trivy` | `trivy image registry/image:tag` |
| **grype** | `curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh \| sh` | `grype docker:registry/image:tag` |
| **dive** | `wget release github` | `dive registry/image:tag` (capas + diff) |
| **skopeo** | `sudo apt install skopeo` | `skopeo inspect docker://registry/image:tag` |
| **docker-scout** | Docker plugin | `docker scout cves image:tag` |
| **ECR / ACR / GCR enum** | aws/az/gcloud CLI | `aws ecr describe-repositories; az acr repository list; gcloud container images list` |

---

## 8. Kubernetes (parcial — overlap con `container_k8s`)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **kubectl (auditoría)** | `sudo snap install kubectl --classic` | `kubectl auth can-i --list; kubectl get pods --all-namespaces` |
| **kube-hunter** | `pip install kube-hunter --break-system-packages` | `kube-hunter --remote <k8s-api>` o `kube-hunter --pod` (desde un pod) |
| **kube-bench** | `sudo apt install kube-bench` | `kube-bench run --targets master,node` |
| **peirates** | release github | `peirates` (post-exploitation desde dentro de pod) |
| **kubectl-trace** | krew plugin | `kubectl trace run <node> -e 'kfunc:vfs_open { printf("%s\\n", str(arg1->name)); }'` |

---

## 9. Secrets en Cloud Configuration

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **trufflehog (cloud)** | `pip install trufflehog --break-system-packages` | `trufflehog s3 --bucket gc-heat-backups` (escanea contenido S3) |
| **secretscanner** | `pip install secret-scanner --break-system-packages` | scan local de configs descargados |
| **gitleaks (cloud configs)** | Preinstalado/`sudo apt install gitleaks` | `gitleaks detect -s ./downloaded-configs/` |
| **detect-secrets** | `pip install detect-secrets --break-system-packages` | `detect-secrets scan ./configs/ > baseline.json` |
| **aws-secrets-manager-enum** | aws cli | `aws secretsmanager list-secrets --region us-east-1` |
| **azure key vault enum** | az cli | `az keyvault list; az keyvault secret list --vault-name <name>` |
| **gcp secret manager enum** | gcloud | `gcloud secrets list --project <p>; gcloud secrets versions access latest --secret=<n>` |

---

## 10. Compliance / Standards Reporting

| Herramienta | Compliance frameworks soportados | Comando de ejemplo |
|---|---|---|
| **Prowler** | CIS, NIST 800-53, NIST CSF, PCI-DSS, HIPAA, GDPR, ISO 27001 | `prowler aws -M html --compliance cis_2.0_aws --output-modes csv,html` |
| **ScoutSuite** | CIS-foundations (multi-cloud) | `scout aws --report-dir ./scout/` (incluye CIS por defecto) |
| **CloudSploit / Aqua** | CIS, AWS Well-Architected | `cloudsploit-scan --account aws` |
| **steampipe** | SQL queries cross-cloud | `steampipe query "select arn, public from aws_s3_bucket where public=true"` |

---

## 11. Logging / CloudTrail / Activity Log Analysis

| Herramienta | Para qué | Comando de ejemplo |
|---|---|---|
| **awslogs** | `pip install awslogs --break-system-packages` | `awslogs get /aws/lambda/<fn> ALL --start='1h ago' --watch` |
| **aws-cli logs** | Built-in | `aws logs filter-log-events --log-group-name <lg> --start-time $(date -d '1 hour ago' +%s)000` |
| **az monitor** | az cli | `az monitor activity-log list --start-time 2026-05-17T00:00:00Z` |
| **gcloud logging** | gcloud | `gcloud logging read 'resource.type=gce_instance' --limit 50` |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Instalables con apt/pip** | ~20 herramientas |
| **Go install** | ~5 herramientas |
| **Git clone** | ~15 herramientas |
| **CLI nativos cloud (5 proveedores)** | 5 herramientas |
| **Total** | **~45 herramientas CLI** |

---

## Alcance

Cloud security en AWS, Azure, GCP (principales). Cubre:
- **Sin credenciales**: bucket hunting, recon DNS cloud-aware.
- **Con credenciales read-only**: auditoría completa (IAM, storage,
  compute, network, secrets, logging).
- **Misconfig discovery**: SG abiertos, IAM permisivo, storage público,
  metadata abuse.

NO cubre (otras skills):
- **Container/K8s** profundo → `container_k8s`.
- **Exploitation de RCE** descubierto en Lambda/cloud function → `exploitation`.
- **SSRF inicial** que da acceso al metadata → `web_pentest` / `api_security`.
- **Secretos en código fuente** del repo del cliente → `secret_scanning`.

## Cuentas root / persistence

JAMÁS uses cuentas root del cliente. Si necesitas más permisos pide
credenciales adicionales con TTL claro. NO crees recursos, NO modifiques
policies, NO instales persistencia sin RoE específico de red team.

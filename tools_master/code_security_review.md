# Herramientas de Code Security Review (SAST + SCA + IaC) — CLI Kali Linux

Análisis estático de código fuente, dependencias y configuración IaC.
Exclusivamente CLI. Para repositorios donde el operador tiene autorización
de lectura.

---

## 1. Inventario y Métricas

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **tokei** | `cargo install tokei` o `sudo apt install tokei` | `tokei ./project/` |
| **cloc** | `sudo apt install cloc` | `cloc ./project/ --exclude-dir=node_modules,venv` |
| **scc** | `go install github.com/boyter/scc/v3@latest` | `scc ./project/` (más rápido) |
| **git-of-theseus** | `pip install git-of-theseus --break-system-packages` | `git-of-theseus-analyze .` (autor de cada línea, age) |
| **gitstats** | `sudo apt install gitstats` | `gitstats . ./stats-report/` |

---

## 2. Secret Scanning

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **gitleaks** | `sudo apt install gitleaks` | `gitleaks detect --source . --report-format json --report-path gitleaks.json` |
| **gitleaks (git history)** | Idem | `gitleaks detect --source . --log-opts="--all"` (todo el historial) |
| **trufflehog** | `pip install trufflehog --break-system-packages` | `trufflehog filesystem ./project/ --json > trufflehog.json` |
| **trufflehog github (org)** | Idem | `trufflehog github --org=gc-heat --token=$GH_TOKEN --json` |
| **detect-secrets** | `pip install detect-secrets --break-system-packages` | `detect-secrets scan ./project/ > .secrets.baseline; detect-secrets audit .secrets.baseline` |
| **whispers** | `pip install whispers --break-system-packages` | `whispers ./project/` |
| **secretscanner** | `git clone https://github.com/deepfence/SecretScanner` | (Docker) `docker run -v ./project:/tmp deepfenceio/secretscanner -container-path /tmp` |

---

## 3. SAST Multi-lenguaje

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **semgrep (auto)** | `pip install semgrep --break-system-packages` | `semgrep --config auto ./project/ --json --output semgrep.json` |
| **semgrep (sec audit)** | Idem | `semgrep --config p/security-audit --config p/owasp-top-ten ./project/` |
| **semgrep (CI mode)** | Idem | `semgrep ci --baseline-ref main` (sólo diff vs main) |
| **semgrep (registry custom)** | Idem | `semgrep --config p/python --config p/django --config p/javascript ./project/` |
| **opengrep** (fork comunidad de semgrep) | `pip install opengrep --break-system-packages` | `opengrep --config auto ./project/` |
| **codeql (cli)** | release github | `codeql database create db --language=python --source-root=./project; codeql database analyze db codeql/python-queries` |
| **horusec** | `curl -fsSL https://raw.githubusercontent.com/ZupIT/horusec/main/deployments/scripts/install.sh \| bash -s latest` | `horusec start -p ./project/ -o json -O horusec.json` |

---

## 4. SAST por Lenguaje

### Python
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **bandit** | `pip install bandit --break-system-packages` | `bandit -r ./project/ -f json -o bandit.json -ll` |
| **bandit (severity high)** | Idem | `bandit -r ./project/ -ll -ii` |
| **pylint security** | `pip install pylint --break-system-packages` | `pylint --disable=all --enable=W0611,W0703 ./project/` |
| **dlint** | `pip install dlint --break-system-packages` | `flake8 --select=DUO ./project/` |

### JavaScript / TypeScript
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **eslint + plugin-security** | `npm install -g eslint eslint-plugin-security` | `eslint --plugin security ./project/` |
| **njsscan** | `pip install njsscan --break-system-packages` | `njsscan ./project/ --json -o njsscan.json` |
| **nodejsscan** | `pip install nodejsscan --break-system-packages` | (web UI; CLI vía njsscan) |
| **retire.js** | `npm install -g retire` | `retire --path ./project/` |

### Go
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **gosec** | `go install github.com/securego/gosec/v2/cmd/gosec@latest` | `gosec -fmt=json -out=gosec.json ./...` |
| **govulncheck** | `go install golang.org/x/vuln/cmd/govulncheck@latest` | `govulncheck ./...` |
| **staticcheck** | `go install honnef.co/go/tools/cmd/staticcheck@latest` | `staticcheck ./...` |

### Java
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **spotbugs + FindSecBugs** | `sudo apt install spotbugs` + plugin | `spotbugs -textui -pluginList findsecbugs.jar -include includeSecurity.xml ./jars/` |
| **dependency-check** | `wget owasp-dependency-check release` | `dependency-check.sh --project myproj --scan ./project/` |

### Ruby
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **brakeman** | `gem install brakeman` | `brakeman ./project/ -o brakeman.json -f json` |
| **bundler-audit** | `gem install bundler-audit` | `bundle-audit check --update` |

### PHP
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **phpcs (Security)** | `composer global require pheromone/phpcs-security-audit` | `phpcs --standard=Security ./project/` |
| **progpilot** | `composer require designsecurity/progpilot` | `progpilot ./project/` |
| **psalm + security analysis** | `composer require vimeo/psalm` | `psalm --taint-analysis ./project/` |

### C / C++
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **cppcheck** | `sudo apt install cppcheck` | `cppcheck --enable=all --error-exitcode=1 ./project/` |
| **flawfinder** | `pip install flawfinder --break-system-packages` | `flawfinder ./project/` |
| **clang-tidy (security)** | `sudo apt install clang-tidy` | `clang-tidy ./src/*.c -checks='clang-analyzer-security*'` |

### .NET
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **security-code-scan** | `dotnet add package SecurityCodeScan.VS2019` (proyecto) | `dotnet build` (warnings vía Roslyn analyzer) |
| **dotnet-format / Roslyn** | `dotnet tool install -g dotnet-format` | `dotnet format analyzers` |

### Rust
| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **cargo audit** | `cargo install cargo-audit` | `cargo audit` |
| **cargo geiger** | `cargo install cargo-geiger` | `cargo geiger` (cuenta unsafe blocks) |
| **clippy** | `rustup component add clippy` | `cargo clippy -- -D warnings` |

---

## 5. SCA (Software Composition Analysis) — Dependencias vulnerables

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **trivy fs** | `sudo apt install trivy` | `trivy fs --scanners vuln,secret,misconfig ./project/` |
| **trivy (SBOM)** | Idem | `trivy fs --format cyclonedx --output sbom.json ./project/` |
| **safety (Python)** | `pip install safety --break-system-packages` | `safety check -r requirements.txt --json` |
| **pip-audit** | `pip install pip-audit --break-system-packages` | `pip-audit -r requirements.txt --format json` |
| **npm audit** | npm | `npm audit --json` |
| **yarn audit** | yarn | `yarn audit --json` |
| **snyk** | `npm install -g snyk` | `snyk test --json` (requiere cuenta gratis) |
| **govulncheck** | Idem §4 Go | `govulncheck ./...` |
| **bundler-audit** | Idem §4 Ruby | `bundle-audit check` |
| **composer audit** | composer | `composer audit --format=json` |
| **dependency-check (OWASP)** | Idem §4 Java | `dependency-check.sh --project p --scan ./project/` |
| **osv-scanner** | `go install github.com/google/osv-scanner/cmd/osv-scanner@latest` | `osv-scanner -r ./project/` |

---

## 6. IaC — Terraform / Ansible / Kubernetes / CloudFormation

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **checkov** | `pip install checkov --break-system-packages` | `checkov -d ./terraform/ -o cli -o json --output-file-path ./scans/` |
| **tfsec** | `curl -s https://raw.githubusercontent.com/aquasecurity/tfsec/master/scripts/install_linux.sh \| bash` | `tfsec ./terraform/` |
| **terrascan** | `curl -L https://github.com/tenable/terrascan/releases/latest/download/terrascan_Linux_x86_64.tar.gz \| tar -xz` | `terrascan scan -i terraform -d ./terraform/` |
| **kics** | `wget https://github.com/Checkmarx/kics/releases/latest/download/kics_<v>_linux_x64.tar.gz` | `kics scan -p ./iac/ -o ./scans/ --report-formats json,html` |
| **kube-linter** | `go install golang.stackrox.io/kube-linter/cmd/kube-linter@latest` | `kube-linter lint ./k8s-manifests/` |
| **kubeaudit** | `go install github.com/Shopify/kubeaudit/cmd/kubeaudit@latest` | `kubeaudit all -f ./k8s-manifests/deployment.yaml` |
| **kubesec** | release github | `kubesec scan ./k8s-manifests/deployment.yaml` |
| **datree** | `curl https://get.datree.io \| /bin/bash` | `datree test ./k8s/*.yaml` |
| **ansible-lint (security)** | `pip install ansible-lint --break-system-packages` | `ansible-lint ./playbooks/` |

---

## 7. Container Images (Dockerfile + image)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **hadolint** | `wget https://github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64 -O /usr/local/bin/hadolint; chmod +x /usr/local/bin/hadolint` | `hadolint ./Dockerfile` |
| **dockerfilelint** | `npm install -g dockerfilelint` | `dockerfilelint ./Dockerfile` |
| **trivy image** | Idem §5 | `trivy image --severity HIGH,CRITICAL registry/image:tag` |
| **grype** | `curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh \| sh` | `grype docker:registry/image:tag` |
| **dive** | release github | `dive registry/image:tag --ci` |
| **dockle** | `wget release github` | `dockle --exit-code 1 registry/image:tag` |
| **snyk container** | snyk | `snyk container test registry/image:tag` |

---

## 8. Diff Analysis (PR / commit review)

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **semgrep ci (baseline)** | Idem | `semgrep ci --baseline-ref main` |
| **gitleaks protect (staged)** | Idem | `gitleaks protect --staged --no-banner` |
| **trufflehog (git)** | Idem | `trufflehog git file://. --since-commit HEAD~10` |
| **diffoscope** | `sudo apt install diffoscope` | `diffoscope file1.bin file2.bin` (deep diff binaries) |

---

## 9. Diff / Audit del histórico Git

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **git log -S** | Built-in | `git log -S "password" --all --source` (pickaxe search) |
| **git log -p** | Built-in | `git log -p -- secrets.env` |
| **git-secrets** | `git clone https://github.com/awslabs/git-secrets; sudo make install` | `git secrets --scan-history` |
| **rusty-hog** | release github | `rusty-hog --regex_json regex.json --git_url <repo>` |

---

## 10. Reporting / Aggregación

| Herramienta | Instalación | Comando de ejemplo |
|---|---|---|
| **defectdojo** | Docker | `defectdojo importtools` (web UI; ingestion CLI) |
| **dependency-track** | Docker | API REST para SBOM upload |
| **owasp-glue** | docker | aggregator multi-SAST |
| **convert SARIF** | `pip install sarif-tools --break-system-packages` | `sarif --input semgrep.sarif --output sarif.csv` |

---

## Resumen de Disponibilidad

| Estado | Cantidad |
|---|---|
| **Preinstalado en Kali** | ~5 herramientas (gitleaks, cppcheck, cloc) |
| **Instalable con apt/pip** | ~25 herramientas |
| **npm / cargo / go install** | ~20 herramientas |
| **Release download** | ~10 herramientas |
| **Total** | **~60 herramientas CLI** |

---

## Alcance

Code review estático. Cubre:
- **Secrets** en código y git history.
- **SAST** multi-lenguaje y por-lenguaje.
- **SCA** de dependencias (todas las plataformas mayores).
- **IaC** Terraform/Ansible/K8s/CloudFormation.
- **Container images** y Dockerfiles.

NO cubre:
- **DAST** dinámico → `web_pentest` / `api_security` / `vuln_analysis`.
- **RE de binarios** sin código fuente → skill `binary_reverse` (si existe).
- **Modificación / commit** al repo del cliente. Sólo lectura.

## Sobre clonar repos privados

Pide al operador credenciales de read-only:
- GitHub: PAT con scope `repo` (read only).
- GitLab: deploy token / personal token read.
- Bitbucket: app password.

Cancela el token al cierre del engagement. Nunca persistas el repo
clonado en disco más allá de la duración del engagement.

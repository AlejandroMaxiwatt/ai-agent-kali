"""Workers permanentes del enjambre.

- ReconWorker: ejecuta tareas de reconocimiento, extrae activos/hallazgos y
  encola seguimientos (reglas + planner LLM opcional).
- GuardianWorker: valida hallazgos con evidencia y alcance; puede confirmar,
  rechazar o pedir más evidencia. El validador LLM es opcional.
"""

from __future__ import annotations

import re
import threading

from .policy import extract_hosts

# ---------------------------------------------------------------------------
# Parsers deterministas
# ---------------------------------------------------------------------------
_NMAP_OPEN_RE = re.compile(
    r"^\s*(\d{1,5})/(tcp|udp)\s+open\s+(\S+)\s*(.*)$", re.I | re.M
)
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.I)
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.I)
_NUCLEI_RE = re.compile(
    r"\[(?P<sev>critical|high|medium|low|info)\]\s+"
    r"(?P<title>.+?)(?:\s+\[(?P<id>[^\]]+)\])?\s*$",
    re.I | re.M,
)
_PROOF_RE = re.compile(
    r"CVE-\d{4}-\d{4,}|\[critical\]|\[high\]|\[vulnerable\]|"
    r"\bvulnerable\b|\bexploit(?:ed|able)?\b|\bshell\b|uid=\d+|"
    r"FLAG\{|sql syntax|error in your sql|command injection|"
    r"authentication bypass|access granted|root:",
    re.I,
)
_VERSION_CLAIM_RE = re.compile(r"\bversi[oó]n|version\b|\bbanner\b", re.I)
_HTTP_PORTS = {80, 8080, 8000, 8888, 443, 8443, 9443}


def _result_fields(res):
    """Normaliza el retorno del runner a (rc, output)."""
    if res is None:
        return 1, ""
    if isinstance(res, dict):
        return int(res.get("rc", 1) or 0), str(res.get("output", ""))
    if isinstance(res, tuple):
        if len(res) >= 2:
            return int(res[1] or 0), str(res[0])
        return 0, str(res[0])
    rc = getattr(res, "rc", 0)
    output = getattr(res, "output", "")
    return int(rc or 0), str(output or "")


def parse_assets(task, output: str) -> list[dict]:
    """Extrae activos de la salida de una tarea de recon."""
    hosts = sorted(extract_hosts(task.command or ""))
    default_host = hosts[0] if hosts else None
    assets = []
    seen = set()

    for m in _NMAP_OPEN_RE.finditer(output or ""):
        port = int(m.group(1))
        proto = m.group(2).lower()
        service = m.group(3)
        version = m.group(4).strip()
        host = default_host or ""
        key = (host, port, proto)
        if key in seen:
            continue
        seen.add(key)
        assets.append({
            "target": task.target, "host": host, "port": port,
            "service": service, "version": version,
            "source": f"nmap:{proto}", "confidence": 0.8,
        })

    for url in _URL_RE.findall(output or ""):
        host = re.sub(r"^https?://", "", url).split("/", 1)[0]
        host = host.split(":", 1)[0]
        port = None
        m = re.search(r"^https?://[^/]+:(\d+)", url)
        if m:
            port = int(m.group(1))
        else:
            port = 443 if url.lower().startswith("https://") else 80
        key = (host, port, "http")
        if key in seen:
            continue
        seen.add(key)
        assets.append({
            "target": task.target, "host": host, "port": port,
            "service": "http", "version": "",
            "source": "url", "confidence": 0.6,
        })

    return assets[:100]


def parse_findings(task, output: str) -> list[dict]:
    """Extrae hallazgos candidatos de salidas tipo nuclei/CVE."""
    findings = []
    for m in _NUCLEI_RE.finditer(output or ""):
        findings.append({
            "target": task.target,
            "title": m.group("title").strip()[:240],
            "severity": m.group("sev").lower(),
            "claim": m.group("title").strip()[:1000],
            "evidence": m.group(0).strip()[:4000],
            "confidence": 0.55,
            "created_by": "recon",
        })
    # CVE sueltos con severidad explícita en la línea.
    for line in (output or "").splitlines():
        if not _CVE_RE.search(line):
            continue
        low = line.lower()
        sev = ("critical" if "critical" in low else
               "high" if "high" in low else
               "medium" if "medium" in low else "low")
        if any(k in low for k in ("critical", "high", "medium", "low",
                                  "vulnerab", "cve-")):
            title = line.strip()[:240]
            if not any(f["title"] == title for f in findings):
                findings.append({
                    "target": task.target, "title": title,
                    "severity": sev, "claim": line.strip()[:1000],
                    "evidence": line.strip()[:4000],
                    "confidence": 0.45, "created_by": "recon",
                })
    return findings[:50]


def suggest_followups(_task, _output: str, assets: list[dict],
                      limit: int = 3) -> list[str]:
    """Reglas simples de pivote a partir de los activos descubiertos."""
    cmds = []
    seen_hosts = set()
    for a in assets:
        host = a.get("host") or ""
        port = a.get("port")
        if not host or host in seen_hosts:
            continue
        if port in _HTTP_PORTS:
            scheme = "https" if port in (443, 8443, 9443) else "http"
            url = f"{scheme}://{host}" + ("" if port in (80, 443) else f":{port}")
            cmds.append(f"whatweb {url}")
            seen_hosts.add(host)
        elif port == 445:
            cmds.append(f"enum4linux -a {host}")
            seen_hosts.add(host)
        if len(cmds) >= limit:
            break
    return cmds[:limit]


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------
class _WorkerBase(threading.Thread):
    def __init__(self, name, store, stop_event, poll_interval=1.0):
        super().__init__(name=name, daemon=True)
        self.store = store
        self.stop_event = stop_event
        self.poll_interval = float(poll_interval)

    def _sleep(self):
        self.stop_event.wait(self.poll_interval)


class ReconWorker(_WorkerBase):
    """Subagente permanente de reconocimiento e inteligencia."""

    role = "recon"

    def __init__(self, store, policy, runner, stop_event,
                 target=None, llm_planner=None, poll_interval=1.0):
        super().__init__("swarm-recon", store, stop_event, poll_interval)
        self.policy = policy
        self.runner = runner
        self.target = target
        self.llm_planner = llm_planner

    def run(self):
        self.store.register_agent(self.name, self.role)
        while not self.stop_event.is_set():
            task = self.store.claim_task(self.role, agent=self.name)
            if task is None:
                self._sleep()
                continue
            try:
                self._process(task)
            except Exception as e:
                self.store.finish_task(task.id, "failed", f"excepción: {e}")
                self.store.add_event(
                    "task_exception", self.name, task.id, {"error": str(e)}
                )

    def _process(self, task):
        self.store.add_event("task_started", self.name, task.id,
                             {"command": task.command})
        decision = self.policy.authorize_task(
            task.command or "", task.target, self.role,
            exclude_task_id=task.id,
        )
        if decision.blocked or not decision.allowed:
            self.store.finish_task(task.id, "blocked", decision.reason)
            self.store.add_event(
                "task_blocked", self.name, task.id,
                {"reason": decision.reason, "level": int(decision.level)},
            )
            return

        rc, output = _result_fields(self.runner(task.command, task))
        status = "done" if rc == 0 else "failed"
        self.store.finish_task(task.id, status, output, rc)
        self.store.add_event(
            "task_finished", self.name, task.id,
            {"rc": rc, "status": status, "bytes": len(output)},
        )

        assets = parse_assets(task, output)
        for a in assets:
            self.store.add_asset(**a)
        if assets:
            self.store.add_event(
                "assets_found", self.name, task.id,
                {"count": len(assets), "sample": assets[:5]},
            )

        for f in parse_findings(task, output):
            if self._finding_exists(f):
                continue
            fid = self.store.add_finding(**f)
            self.store.add_event(
                "finding_created", self.name, task.id,
                {"finding_id": fid, "title": f["title"]},
            )
            self.store.enqueue_task(
                "validation", kind="validate", target=f.get("target"),
                finding_id=fid, priority=3,
            )

        followups = suggest_followups(task, output, assets)
        if self.llm_planner and assets:
            try:
                extra = self.llm_planner(task, output, assets) or []
                for cmd in extra:
                    if isinstance(cmd, str) and cmd.strip():
                        followups.append(cmd.strip())
            except Exception as e:
                self.store.add_event(
                    "planner_error", self.name, task.id, {"error": str(e)}
                )
        self._enqueue_followups(task, followups)

    def _finding_exists(self, f) -> bool:
        for existing in self.store.list_findings(
                target=f.get("target"), limit=200):
            if existing.title.strip().lower() == f["title"].strip().lower():
                return True
        return False

    def _enqueue_followups(self, parent, commands):
        seen = set()
        for cmd in commands:
            cmd = (cmd or "").strip()
            if not cmd or cmd in seen:
                continue
            seen.add(cmd)
            decision = self.policy.authorize_task(cmd, parent.target, "recon")
            if decision.blocked or not decision.allowed:
                self.store.add_event(
                    "followup_rejected", self.name, parent.id,
                    {"command": cmd[:300], "reason": decision.reason},
                )
                continue
            fp = decision.fingerprint
            if fp and self.store.find_duplicate(fp, window_s=3600):
                continue
            self.store.enqueue_task(
                "recon", kind="command", target=parent.target,
                command=cmd, priority=min(9, parent.priority + 1),
                payload={"parent": parent.id, "origin": "recon"},
                fingerprint=fp,
            )
            self.store.add_event(
                "followup_enqueued", self.name, parent.id,
                {"command": cmd[:300]},
            )


class GuardianWorker(_WorkerBase):
    """Subagente permanente de validación y guardia."""

    role = "validation"

    def __init__(self, store, policy, stop_event, llm_validator=None,
                 poll_interval=1.0):
        super().__init__("swarm-guardian", store, stop_event, poll_interval)
        self.policy = policy
        self.llm_validator = llm_validator

    def run(self):
        self.store.register_agent(self.name, self.role)
        while not self.stop_event.is_set():
            task = self.store.claim_task(self.role, agent=self.name)
            if task is None:
                self._sleep()
                continue
            try:
                self._process(task)
            except Exception as e:
                self.store.finish_task(task.id, "failed", f"excepción: {e}")
                self.store.add_event(
                    "validation_exception", self.name, task.id,
                    {"error": str(e)},
                )

    def _process(self, task):
        finding = self.store.get_finding(task.finding_id) if task.finding_id else None
        if finding is None:
            self.store.finish_task(task.id, "failed", "finding inexistente")
            return

        self.store.add_event(
            "validation_started", self.name, task.id,
            {"finding_id": finding.id, "title": finding.title},
        )
        decision, reason, confidence = self._validate(finding, task)

        # Segunda opinión LLM solo si el determinista no es concluyente.
        if self.llm_validator and decision == "needs_more_evidence":
            try:
                evidence_texts = self._evidence_texts(finding)
                extra = self.llm_validator(
                    finding, evidence_texts, self.policy.scope.describe(),
                )
                if isinstance(extra, dict) and extra.get("decision"):
                    decision = extra["decision"]
                    reason = extra.get("reason", reason)
                    confidence = float(extra.get("confidence", confidence) or confidence)
            except Exception as e:
                self.store.add_event(
                    "llm_validator_error", self.name, task.id,
                    {"error": str(e)},
                )

        status = {
            "confirmed": "confirmed",
            "rejected": "rejected",
            "needs_more_evidence": "needs_more_evidence",
        }.get(decision, "needs_more_evidence")
        self.store.update_finding_status(finding.id, status, validated_by=self.name)
        self.store.add_decision(
            finding_id=finding.id, task_id=task.id, agent=self.name,
            decision=decision, reason=reason,
            policy={"confidence": confidence, "scope": self.policy.scope.describe()},
        )
        self.store.finish_task(task.id, "done", decision)
        self.store.add_event(
            "validation_decision", self.name, task.id,
            {"finding_id": finding.id, "decision": decision,
             "confidence": confidence, "reason": reason[:300]},
        )

    def _evidence_texts(self, finding) -> list[str]:
        texts = []
        if finding.evidence:
            texts.append(finding.evidence[:4000])
        for ev in self.store.evidence_for_finding(finding.id):
            if not ev.path:
                continue
            try:
                with open(ev.path, "r", encoding="utf-8", errors="replace") as f:
                    texts.append(f.read(4000))
            except OSError:
                texts.append(f"[evidencia no legible: {ev.path}]")
        return texts

    def _validate(self, finding, _task):
        if finding.target and not self.policy.scope.is_empty():
            if not self.policy.scope.contains(finding.target):
                return "rejected", "target fuera de alcance", 0.99

        evidence = self.store.evidence_for_finding(finding.id)
        texts = []
        invalid = []
        for ev in evidence:
            if ev.path:
                try:
                    with open(ev.path, "r", encoding="utf-8",
                              errors="replace") as f:
                        content = f.read(4000)
                except OSError:
                    invalid.append(ev.path)
                    continue
                if ev.sha256:
                    actual = self.store.file_sha256(ev.path)
                    if actual and actual != ev.sha256:
                        invalid.append(ev.path + " (hash no coincide)")
                        continue
                texts.append(content)
            elif ev.excerpt:
                texts.append(ev.excerpt)
        if invalid:
            return ("needs_more_evidence",
                    "evidencia inválida o alterada: " + ", ".join(invalid[:3]),
                    0.4)

        proof_text = "\n".join([finding.claim, finding.evidence] + texts)
        if not proof_text.strip():
            return "needs_more_evidence", "sin evidencia", 0.2

        if _VERSION_CLAIM_RE.search(proof_text) and not _PROOF_RE.search(proof_text):
            return ("needs_more_evidence",
                    "sólo hay coincidencia de versión/banner; falta prueba "
                    "de explotación o comportamiento vulnerable", 0.45)

        if _PROOF_RE.search(proof_text):
            return "confirmed", "marcador de prueba presente en la evidencia", 0.8

        return ("needs_more_evidence",
                "no hay marcador de explotación ni prueba suficiente", 0.35)

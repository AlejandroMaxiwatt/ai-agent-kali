"""Motor de políticas determinista.

Se ejecuta FUERA de los modelos: decide si un comando está autorizado según
alcance, nivel de autonomía, riesgo, duplicados y límites de frecuencia.

Niveles:
  1 AUTO           → lectura/pasivo
  2 PREAPPROVED    → recon activo controlado
  3 HUMAN_APPROVAL → explotación / cambios con impacto
  4 BLOCKED        → destructivo o fuera de alcance
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass, field

from .models import AutonomyLevel, PolicyDecision

# ---------------------------------------------------------------------------
# Clasificación de herramientas
# ---------------------------------------------------------------------------
LEVEL1_TOOLS = {
    "ls", "cat", "head", "tail", "less", "more", "wc", "file", "stat",
    "tree", "grep", "egrep", "fgrep", "ag", "rg", "find", "locate",
    "which", "type", "command", "ps", "pgrep", "pidof", "lsof",
    "id", "whoami", "groups", "uname", "hostname", "uptime",
    "df", "du", "free", "lsblk", "lscpu", "lspci", "lsusb",
    "echo", "printf", "true", "false", "test", "sleep", "pwd", "date",
    "env", "printenv", "history", "basename", "dirname", "readlink",
    "realpath", "mktemp",
    "dig", "nslookup", "whois", "host", "drill", "searchsploit",
    "git", "jq", "yq", "xmllint", "cut", "awk", "sed", "sort",
    "uniq", "tr", "xargs", "tee",
}

# Herramientas locales de manipulación de archivos: no son destructivas por
# sí mismas, pero pueden sobrescribir. Nivel 2 (preaprobado).
LEVEL2_LOCAL_TOOLS = {"mkdir", "touch", "cp", "mv", "ln", "install"}

LEVEL2_TOOLS = {
    "nmap", "masscan", "rustscan", "unicornscan", "naabu",
    "subfinder", "assetfinder", "amass", "findomain", "sublist3r",
    "dnsx", "dnsrecon", "dnsenum", "fierce", "puredns",
    "httpx", "httprobe", "whatweb", "wappalyzer", "wafw00f",
    "katana", "gau", "waybackurls", "hakrawler",
    "gobuster", "feroxbuster", "ffuf", "dirb", "dirbuster",
    "dirsearch", "wfuzz", "nuclei", "nikto", "wapiti", "skipfish",
    "enum4linux", "enum4linux-ng", "smbmap", "smbclient", "rpcclient",
    "ldapsearch", "snmpwalk", "snmpcheck", "onesixtyone", "showmount",
    "sslscan", "sslyze", "testssl", "curl", "wget", "ping", "ping6",
    "tracepath", "traceroute", "mtr", "joomscan", "droopescan",
}

LEVEL3_TOOLS = {
    "sqlmap", "metasploit", "msfconsole", "msfvenom",
    "hydra", "medusa", "patator", "ncrack", "john", "hashcat",
    "crackmapexec", "netexec", "cme", "responder", "mitm6",
    "ettercap", "bettercap", "evil-winrm", "smbexec",
    "wpscan", "aircrack-ng", "airodump-ng", "aireplay-ng",
}

LEVEL4_TOOLS = {
    "rm", "dd", "mkfs", "shred", "fdisk", "parted", "wipefs",
    "useradd", "userdel", "usermod", "passwd", "chpasswd",
    "iptables", "ip6tables", "nft", "ufw", "firewalld",
    "systemctl", "service", "apt", "apt-get", "dpkg", "pacman",
    "yum", "dnf", "snap", "flatpak", "pip", "pip3", "npm", "yarn",
    "gem", "cargo", "mount", "umount", "swapoff", "swapon",
    "kill", "killall", "pkill", "reboot", "shutdown", "poweroff",
    "halt",
}

DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-[rRf]+",
    r"\bsudo\s+rm\b",
    r">\s*/(etc|usr|bin|sbin|boot|var|root)/",
    r">>\s*/(etc|usr|bin|sbin|boot|var|root)/",
    r"\bchmod\s+(-R\s+)?777\b",
    r"\bchown\s+-R\b",
    r"\beval\s+",
    r"\b(curl|wget)\b[^|]*\|\s*(sh|bash|zsh)",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",
    r"\bdd\s+if=.*\s+of=/dev/",
    r"\b/dev/(sd[a-z]|nvme|mmcblk)",
]

_EXPLOIT_FLAGS = (
    "--os-shell", "--dump", "--passwords", "--file-read", "--file-write",
    "--os-pwn", "--os-cmd", "-e ", "--exploit", "--script", "-x ",
)

_PROXY_WRAPPERS = {"proxychains", "proxychains4", "torify", "torsocks"}

# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_CIDR_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b")
_URL_HOST_RE = re.compile(r"https?://([^/\s'\"`]+)", re.I)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
)
_FILE_EXT_RE = re.compile(
    r"\.(?:txt|md|json|ya?ml|xml|csv|log|py|sh|rb|pl|js|html?|conf|ini|cfg|"
    r"nmap|gnmap|php|asp|aspx|jsp|bak|old|zip|gz|tar|pem|key|db|sqlite)$",
    re.I,
)
_EXCLUDE_WORDS = ("exclu", "fuera de alcance", "fuera del alcance",
                  "no autorizado", "no está autorizado", "out of scope")


@dataclass
class Scope:
    """Alcance autorizado: dominios, IPs, redes y exclusiones."""
    target: str | None = None
    domains: set = field(default_factory=set)
    ips: set = field(default_factory=set)
    networks: list = field(default_factory=list)
    exclusions: set = field(default_factory=set)
    raw: str = ""

    @classmethod
    def from_text(cls, text: str, target: str | None = None) -> "Scope":
        raw = text or ""
        scope = cls(target=target, raw=raw)
        # Exclusiones: líneas que hablan de fuera de alcance.
        excluded_text = []
        included_text = []
        for line in raw.splitlines():
            low = line.lower()
            if any(w in low for w in _EXCLUDE_WORDS):
                excluded_text.append(line)
            else:
                included_text.append(line)
        inc = "\n".join(included_text)
        exc = "\n".join(excluded_text)

        for net in _CIDR_RE.findall(inc):
            try:
                scope.networks.append(ipaddress.ip_network(net, strict=False))
            except ValueError:
                pass
        for ip in _IP_RE.findall(inc):
            try:
                ipaddress.ip_address(ip)
                scope.ips.add(ip)
            except ValueError:
                pass
        for dom in _DOMAIN_RE.findall(inc):
            dom = dom.lower().strip(".")
            if not _FILE_EXT_RE.search(dom) and "@" not in dom:
                scope.domains.add(dom)
        for item in _IP_RE.findall(exc) + _DOMAIN_RE.findall(exc):
            scope.exclusions.add(item.lower())
        if target:
            scope.exclusions.discard(target.lower())
            scope.domains.add(target.lower())
        return scope

    def is_empty(self) -> bool:
        return not (self.domains or self.ips or self.networks)

    @staticmethod
    def _clean(host: str) -> str:
        h = (host or "").strip().lower()
        h = re.sub(r"^https?://", "", h)
        h = h.split("/", 1)[0]
        # IPv4:port → ip ; dominio:port → dominio
        if h.count(":") == 1:
            h = h.split(":", 1)[0]
        return h.strip("[]")

    def contains(self, host: str) -> bool:
        h = self._clean(host)
        if not h:
            return False
        if any(h == e or h.endswith("." + e) for e in self.exclusions):
            return False
        try:
            ip = ipaddress.ip_address(h)
            if h in self.ips:
                return True
            return any(ip in net for net in self.networks)
        except ValueError:
            pass
        for dom in self.domains:
            if h == dom or h.endswith("." + dom):
                return True
        return False

    def describe(self) -> str:
        parts = []
        if self.domains:
            parts.append("dominios=" + ",".join(sorted(self.domains)))
        if self.ips:
            parts.append("ips=" + ",".join(sorted(self.ips)))
        if self.networks:
            parts.append("redes=" + ",".join(str(n) for n in self.networks))
        if self.exclusions:
            parts.append("excl=" + ",".join(sorted(self.exclusions)))
        return " · ".join(parts) or "(vacío)"


# ---------------------------------------------------------------------------
# Extracción de hosts / clasificación
# ---------------------------------------------------------------------------
def extract_hosts(command: str) -> set[str]:
    """Extrae hosts plausibles de un comando (IPs, dominios, URLs)."""
    cmd = command or ""
    hosts = set()
    for h in _URL_HOST_RE.findall(cmd):
        hosts.add(Scope._clean(h))
    for ip in _IP_RE.findall(cmd):
        hosts.add(ip)
    for token in re.split(r"[\s'\"`]+", cmd):
        token = token.strip(",;()[]")
        if not token or "/" in token or "=" in token:
            continue
        if _FILE_EXT_RE.search(token):
            continue
        if _DOMAIN_RE.fullmatch(token):
            hosts.add(token.lower())
    return {h for h in hosts if h}


def _strip_proxy_wrapper(command: str) -> str:
    """Si el comando está envuelto en proxychains/torify, devuelve el interior."""
    m = re.search(
        r"\b(?:proxychains4?|torify|torsocks)\b[^\n]*?\b(?:bash|sh)\s+-c\s+(.+)",
        command or "", re.I,
    )
    if m:
        inner = m.group(1).strip()
        if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "'\"":
            inner = inner[1:-1]
        return inner
    return command or ""


def _split_subcommands(command: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?:&&|\|\||;|\|)", command or "")
            if p.strip()]


def _first_tool(sub: str) -> str:
    tokens = sub.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "sudo" or ("=" in tok.split("/")[-1] and not tok.startswith("-")):
            i += 1
            continue
        return tok.split("/")[-1].lower()
    return ""


def classify_risk(command: str) -> tuple[int, str]:
    """Devuelve (nivel, motivo) para un comando o cadena de comandos."""
    cmd = command or ""
    if not cmd.strip():
        return AutonomyLevel.AUTO, "comando vacío"

    for pat in DESTRUCTIVE_PATTERNS:
        if re.search(pat, cmd):
            return AutonomyLevel.BLOCKED, f"patrón destructivo: {pat}"

    inner = _strip_proxy_wrapper(cmd)
    max_level = AutonomyLevel.AUTO
    reasons = []
    for sub in _split_subcommands(inner):
        # Desenvolver `bash -c "<cmd>"` / `sh -c "<cmd>"` para clasificar
        # el comando real, no el intérprete.
        m = re.match(r"^(?:bash|sh|zsh)\s+-c\s+(.+)$", sub, re.I)
        if m:
            sub = m.group(1).strip()
            if len(sub) >= 2 and sub[0] == sub[-1] and sub[0] in "'\"":
                sub = sub[1:-1]
        tool = _first_tool(sub)
        if not tool:
            continue
        if tool in LEVEL4_TOOLS:
            return AutonomyLevel.BLOCKED, f"herramienta destructiva: {tool}"
        if tool in LEVEL3_TOOLS or tool.startswith("impacket-"):
            lvl = AutonomyLevel.HUMAN_APPROVAL
            reason = f"explotación/credenciales: {tool}"
        elif tool in LEVEL2_TOOLS or tool in LEVEL2_LOCAL_TOOLS:
            lvl = AutonomyLevel.PREAPPROVED
            reason = f"recon/operación local: {tool}"
        elif tool in LEVEL1_TOOLS:
            lvl = AutonomyLevel.AUTO
            reason = f"lectura/pasivo: {tool}"
        else:
            lvl = AutonomyLevel.HUMAN_APPROVAL
            reason = f"herramienta desconocida: {tool}"
        if any(flag in sub for flag in _EXPLOIT_FLAGS):
            lvl = max(lvl, AutonomyLevel.HUMAN_APPROVAL)
            reason += " (flag de explotación)"
        if lvl > max_level:
            max_level = lvl
            reasons.append(reason)

    return max_level, "; ".join(reasons) or "sin herramienta reconocida"


def command_fingerprint(command: str, target: str | None = None) -> str:
    """Huella estable de tool + target + flags para deduplicación."""
    cmd = " ".join((command or "").split())
    cmd = re.sub(r"\s*2>>?\s*/dev/null", "", cmd)
    cmd = re.sub(r"\s*&>>?\s*/dev/null", "", cmd)
    cmd = re.sub(r"\s*>\s*/dev/null\s+2>&1", "", cmd)
    cmd = re.sub(r"-o[NXGAS]?\s+\S+", "", cmd)
    inner = _strip_proxy_wrapper(cmd)
    tools = []
    flags = []
    for sub in _split_subcommands(inner):
        tool = _first_tool(sub)
        if tool:
            tools.append(tool)
        flags.extend(t for t in sub.split() if t.startswith("-"))
    hosts = sorted(extract_hosts(inner))
    if target:
        hosts = sorted(set(hosts) | {target.lower()})
    payload = "|".join([
        ",".join(sorted(set(tools))),
        ",".join(hosts),
        " ".join(sorted(set(flags))),
    ])
    return hashlib.sha1(payload.encode("utf-8", "replace")).hexdigest()


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------
class PolicyEngine:
    """Decide autorización, aprobación o bloqueo de un comando."""

    def __init__(self, store, scope: Scope | None = None,
                 autonomy_level: int = AutonomyLevel.PREAPPROVED,
                 per_minute: int = 30, per_hour: int = 300):
        self.store = store
        self.scope = scope or Scope()
        self.autonomy_level = int(autonomy_level)
        self.per_minute = int(per_minute)
        self.per_hour = int(per_hour)

    def authorize(self, command: str, agent_role: str = "main",
                  target: str | None = None,
                  exclude_task_id: int | None = None) -> PolicyDecision:
        cmd = (command or "").strip()
        if not cmd:
            return PolicyDecision(True, False, False, 1, "comando vacío")

        block = self.store.active_block(target)
        if block:
            return PolicyDecision(
                False, False, True, AutonomyLevel.BLOCKED,
                f"target bloqueado: {block.get('reason', '')}",
                target=target,
            )

        hosts = extract_hosts(cmd)
        if hosts:
            if self.scope.is_empty():
                return PolicyDecision(
                    False, False, True, AutonomyLevel.BLOCKED,
                    "no hay scope configurado; comandos con host bloqueados",
                    target=target,
                )
            out = [h for h in hosts if not self.scope.contains(h)]
            if out:
                return PolicyDecision(
                    False, False, True, AutonomyLevel.BLOCKED,
                    "fuera de alcance: " + ", ".join(sorted(out)),
                    target=target,
                )

        level, reason = classify_risk(cmd)
        fp = command_fingerprint(cmd, target)

        # Los subagentes de fondo nunca piden aprobación humana: si el
        # comando supera su nivel, se bloquea.
        if agent_role in ("recon", "validation", "subagent"):
            if level > AutonomyLevel.PREAPPROVED:
                return PolicyDecision(
                    False, False, True, AutonomyLevel.BLOCKED,
                    f"rol '{agent_role}' no puede ejecutar nivel {int(level)}: {reason}",
                    fingerprint=fp, target=target,
                )
            level = min(level, AutonomyLevel.PREAPPROVED)

        if level >= AutonomyLevel.BLOCKED:
            return PolicyDecision(
                False, False, True, level, reason,
                fingerprint=fp, target=target,
            )

        # Nivel 3 (explotación / cambios con impacto) SIEMPRE requiere
        # aprobación humana para el agente principal; los roles de fondo
        # no pueden pedirla y ya se bloquearon arriba.
        if level >= AutonomyLevel.HUMAN_APPROVAL:
            if agent_role != "main":
                return PolicyDecision(
                    False, False, True, AutonomyLevel.BLOCKED,
                    f"rol '{agent_role}' no puede ejecutar nivel 3: {reason}",
                    fingerprint=fp, target=target,
                )
            return PolicyDecision(
                False, True, False, level,
                f"nivel 3 · aprobación humana obligatoria: {reason}",
                fingerprint=fp, target=target,
            )

        # Límites de frecuencia y duplicados. No aplicamos rate-limit a
        # comandos locales de nivel 1 (ls, cat, grep…) para no bloquear al
        # operador; sí a herramientas de red o de nivel >= 2.
        tool = _first_tool(_strip_proxy_wrapper(cmd)) or "unknown"
        networkish = (
            tool in LEVEL2_TOOLS or tool in LEVEL3_TOOLS
            or tool in LEVEL4_TOOLS or tool.startswith("impacket-")
            or tool in {"dig", "nslookup", "whois", "host", "drill",
                        "ping", "tracepath", "traceroute", "mtr"}
        )
        if networkish and self.per_minute and self.store.count_recent_tasks(
                target, tool, 60) >= self.per_minute:
            return PolicyDecision(
                False, True, False, AutonomyLevel.HUMAN_APPROVAL,
                f"rate limit: {self.per_minute}/min para {tool}",
                fingerprint=fp, target=target,
            )
        if networkish and self.per_hour and self.store.count_recent_tasks(
                target, tool, 3600) >= self.per_hour:
            return PolicyDecision(
                False, True, False, AutonomyLevel.HUMAN_APPROVAL,
                f"rate limit: {self.per_hour}/h para {tool}",
                fingerprint=fp, target=target,
            )

        if level >= AutonomyLevel.PREAPPROVED:
            duplicate = self.store.find_duplicate(
                fp, window_s=3600, exclude_task_id=exclude_task_id,
            )
            if duplicate:
                return PolicyDecision(
                    False, True, False, AutonomyLevel.HUMAN_APPROVAL,
                    f"duplicado de tarea #{duplicate.id} ({duplicate.status})",
                    fingerprint=fp, duplicate_of=duplicate.id, target=target,
                )

        if level > self.autonomy_level:
            return PolicyDecision(
                False, True, False, level,
                f"nivel {int(level)} > autonomía {self.autonomy_level}: {reason}",
                fingerprint=fp, target=target,
            )

        return PolicyDecision(
            True, False, False, level, reason,
            fingerprint=fp, target=target,
        )

    # Alias semántico para workers.
    def authorize_task(self, command: str, target: str | None,
                       role: str,
                       exclude_task_id: int | None = None) -> PolicyDecision:
        return self.authorize(
            command, agent_role=role, target=target,
            exclude_task_id=exclude_task_id,
        )

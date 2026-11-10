"""Resultado estructurado de la ejecución de un comando."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class CommandResult:
    """Resultado de ejecutar un comando.

    Sustituye al patrón antiguo ``run_command(...); rc = LAST_COMMAND_RC``,
    que era una carrera entre subagentes concurrentes: cada ejecución
    devuelve ahora su propio objeto y nadie lee estado global compartido.
    """
    command: str = ""
    rc: int = 0
    output: str = ""
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    cancelled: bool = False
    meta: dict | None = None
    artifacts: list = dataclasses.field(default_factory=list)
    error_class: str | None = None
    # Modo de proxy efectivo tras la ejecución (puede cambiar si el agente
    # emitió `agent:proxy off`). None = no aplica / no cambió.
    proxy_mode: str | None = None

    @property
    def ok(self) -> bool:
        return self.rc == 0

    def __str__(self) -> str:
        return self.output

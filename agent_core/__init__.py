"""Núcleo desacoplado del agente.

Módulos puros y testables que no dependen de Rich, del cliente LLM ni del
estado global del REPL. `agent.py` los importa y les pasa el workspace.

- results:  CommandResult (resultado estructurado de un comando)
- goalspec: GoalSpec + verificador objetivo de criterios de éxito
"""

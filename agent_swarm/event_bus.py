"""Bus de eventos opcional para el enjambre.

- `InProcessEventBus`: cola en memoria (default, sin dependencias).
- `RedisStreamsEventBus`: Redis Streams para varios procesos/máquinas.

El `Store` publica cada evento en el bus si tiene uno asignado. La cola de
tareas sigue viviendo en el Store (SQLite/PostgreSQL); Redis se usa para
notificar y observar el flujo en tiempo real.
"""

from __future__ import annotations

import json
import queue
import time


class EventBus:
    def publish(self, event_type: str, payload: dict | None = None,
                agent: str = "", task_id=None):
        raise NotImplementedError

    def read(self, last_id="$", count: int = 100,
             block_ms: int = 1000) -> list[dict]:
        raise NotImplementedError

    def close(self):
        pass


class InProcessEventBus(EventBus):
    """Cola en memoria; útil para tests y para el propio proceso."""

    def __init__(self, maxsize: int = 10000):
        self._q = queue.Queue(maxsize=maxsize)

    def publish(self, event_type, payload=None, agent="", task_id=None):
        item = {
            "id": str(time.time_ns()),
            "type": event_type,
            "agent": agent,
            "task_id": task_id,
            "payload": payload or {},
            "ts": time.time(),
        }
        try:
            self._q.put_nowait(item)
        except queue.Full:
            pass
        return item["id"]

    def read(self, last_id="$", count=100, block_ms=1000):
        out = []
        deadline = time.time() + max(0, block_ms) / 1000.0
        while len(out) < count and time.time() < deadline:
            try:
                out.append(self._q.get(timeout=0.1))
            except queue.Empty:
                if out:
                    break
        return out

    def close(self):
        pass


class RedisStreamsEventBus(EventBus):
    """Bus Redis Streams. Requiere el paquete `redis`."""

    def __init__(self, url: str = "redis://127.0.0.1:6379/0",
                 stream: str = "maxiwatt:swarm"):
        import redis  # import perezoso: solo si se usa
        self.url = url
        self.stream = stream
        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._redis.ping()

    def publish(self, event_type, payload=None, agent="", task_id=None):
        return self._redis.xadd(self.stream, {
            "type": event_type,
            "agent": agent or "",
            "task_id": "" if task_id is None else str(task_id),
            "payload": json.dumps(payload or {}, ensure_ascii=False),
        })

    def read(self, last_id="$", count=100, block_ms=1000):
        resp = self._redis.xread(
            {self.stream: last_id}, count=count, block=block_ms,
        )
        out = []
        for _stream, entries in resp or []:
            for entry_id, fields in entries:
                try:
                    payload = json.loads(fields.get("payload") or "{}")
                except Exception:
                    payload = {}
                task_id = fields.get("task_id")
                out.append({
                    "id": entry_id,
                    "type": fields.get("type", ""),
                    "agent": fields.get("agent", ""),
                    "task_id": int(task_id) if task_id else None,
                    "payload": payload,
                    "ts": entry_id.split("-")[0],
                })
        return out

    def close(self):
        try:
            self._redis.close()
        except Exception:
            pass


def make_event_bus(backend: str = "none", url: str | None = None):
    """Crea un bus según configuración. `none` devuelve None."""
    backend = (backend or "none").strip().lower()
    if backend in ("none", "off", ""):
        return None
    if backend in ("memory", "inprocess"):
        return InProcessEventBus()
    if backend in ("redis", "redis-streams", "streams"):
        return RedisStreamsEventBus(url or "redis://127.0.0.1:6379/0")
    raise ValueError(f"bus de eventos desconocido: {backend!r}")

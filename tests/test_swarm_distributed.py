"""Tests de los backends distribuidos: PostgreSQL y Redis Streams.

Se saltan automáticamente si no están instalados los binarios o los
paquetes Python. Levantan servidores temporales en directorios temporales
(sin tocar servicios del sistema).
"""

import glob
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

import importlib.util

HAS_PSYCOPG = importlib.util.find_spec("psycopg2") is not None
HAS_REDIS = importlib.util.find_spec("redis") is not None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _pg_bindir():
    for path in sorted(glob.glob("/usr/lib/postgresql/*/bin")):
        if (os.path.isfile(os.path.join(path, "initdb"))
                and os.path.isfile(os.path.join(path, "pg_ctl"))):
            return path
    return None


PG_BIN = _pg_bindir()


@unittest.skipUnless(HAS_PSYCOPG, "psycopg2 no instalado")
@unittest.skipUnless(PG_BIN, "binarios de PostgreSQL no disponibles")
class TestPostgresStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from agent_swarm.postgres_store import PostgresStore
        cls._Store = PostgresStore
        cls.base = tempfile.mkdtemp(prefix="pg-swarm-test-")
        cls.data = os.path.join(cls.base, "data")
        cls.sock = os.path.join(cls.base, "sock")
        cls.log = os.path.join(cls.base, "pg.log")
        os.makedirs(cls.sock, exist_ok=True)
        cls.port = str(_free_port())
        try:
            subprocess.run(
                [f"{PG_BIN}/initdb", "-D", cls.data, "-A", "trust",
                 "-U", "postgres", "-E", "UTF8", "--locale=C"],
                check=True, capture_output=True,
            )
            subprocess.run(
                [f"{PG_BIN}/pg_ctl", "-D", cls.data, "-l", cls.log,
                 "-o", f"-p {cls.port} -k {cls.sock}", "-w", "start"],
                check=True, capture_output=True,
            )
        except Exception as e:
            shutil.rmtree(cls.base, ignore_errors=True)
            raise unittest.SkipTest(f"no se pudo levantar PostgreSQL: {e}")
        cls.dsn = (f"dbname=postgres user=postgres "
                   f"host={cls.sock} port={cls.port}")

    @classmethod
    def tearDownClass(cls):
        subprocess.run(
            [f"{PG_BIN}/pg_ctl", "-D", cls.data, "-m", "immediate", "stop"],
            capture_output=True,
        )
        shutil.rmtree(cls.base, ignore_errors=True)

    def setUp(self):
        self.store = self._Store(self.dsn)

    def tearDown(self):
        self.store.close()

    def test_lifecycle(self):
        tid = self.store.enqueue_task(
            "recon", target="t", command="nmap 10.0.0.1",
            fingerprint="fp-pg",
        )
        task = self.store.claim_task("recon", agent="w1")
        self.assertIsNotNone(task)
        self.assertEqual(task.id, tid)
        self.assertEqual(task.status, "running")
        self.store.finish_task(tid, "done", "ok", 0)
        self.assertEqual(self.store.get_task(tid).status, "done")
        self.assertIn("recon", self.store.task_stats())

    def test_findings_evidence_decisions(self):
        fid = self.store.add_finding("t", "SQLi", severity="high",
                                     claim="id=1")
        self.store.add_evidence(fid, None, path="/tmp/e.txt",
                                sha256="abc", excerpt="payload")
        self.store.add_decision(fid, None, "guardian", "confirmed", "ok")
        self.store.update_finding_status(fid, "confirmed", "guardian")
        self.assertEqual(self.store.get_finding(fid).status, "confirmed")
        self.assertEqual(len(self.store.evidence_for_finding(fid)), 1)
        self.assertEqual(len(self.store.decisions_for_finding(fid)), 1)

    def test_cancel_and_blocks(self):
        tid = self.store.enqueue_task("recon", target="t", command="x")
        self.assertTrue(self.store.cancel_task(tid, "test"))
        self.assertEqual(self.store.get_task(tid).status, "cancelled")
        self.store.finish_task(tid, "done", "no debe sobrescribir", 0)
        self.assertEqual(self.store.get_task(tid).status, "cancelled")
        self.store.add_block("t", "riesgo")
        self.assertIsNotNone(self.store.active_block("t"))
        self.store.clear_blocks("t")
        self.assertIsNone(self.store.active_block("t"))


@unittest.skipUnless(HAS_REDIS, "paquete redis no instalado")
@unittest.skipUnless(shutil.which("redis-server"), "redis-server no disponible")
class TestRedisStreamsEventBus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from agent_swarm.event_bus import RedisStreamsEventBus
        cls._Bus = RedisStreamsEventBus
        cls.base = tempfile.mkdtemp(prefix="redis-swarm-test-")
        cls.port = str(_free_port())
        try:
            subprocess.run(
                ["redis-server", "--port", cls.port, "--save", "",
                 "--appendonly", "no", "--daemonize", "yes",
                 "--dir", cls.base,
                 "--pidfile", os.path.join(cls.base, "r.pid")],
                check=True, capture_output=True,
            )
            time.sleep(0.4)
        except Exception as e:
            shutil.rmtree(cls.base, ignore_errors=True)
            raise unittest.SkipTest(f"no se pudo levantar Redis: {e}")
        cls.url = f"redis://127.0.0.1:{cls.port}/0"

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["redis-cli", "-p", cls.port, "shutdown", "nosave"],
                       capture_output=True)
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_publish_read(self):
        bus = self._Bus(self.url)
        try:
            bus.publish("task_started", {"command": "nmap"},
                        agent="recon", task_id=7)
            events = bus.read(last_id="0-0", count=10, block_ms=500)
            self.assertTrue(events)
            self.assertEqual(events[0]["type"], "task_started")
            self.assertEqual(events[0]["task_id"], 7)
            self.assertEqual(events[0]["payload"]["command"], "nmap")
        finally:
            bus.close()


if __name__ == "__main__":
    unittest.main()

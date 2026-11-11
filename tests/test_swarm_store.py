"""Tests de la memoria compartida del enjambre (SQLite)."""

import os
import tempfile
import unittest

from agent_swarm.store import Store


class TestSwarmStore(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.path)
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self.path + suffix)
            except OSError:
                pass

    def test_task_lifecycle(self):
        tid = self.store.enqueue_task(
            "recon", target="t", command="nmap 10.0.0.1", priority=2,
            fingerprint="fp1",
        )
        task = self.store.claim_task("recon", agent="w1")
        self.assertIsNotNone(task)
        self.assertEqual(task.id, tid)
        self.assertEqual(task.status, "running")
        self.store.finish_task(tid, "done", "ok", 0)
        done = self.store.get_task(tid)
        self.assertEqual(done.status, "done")
        self.assertEqual(done.rc, 0)
        stats = self.store.task_stats()
        self.assertEqual(stats["recon"]["done"], 1)

    def test_cancel_task_does_not_get_overwritten(self):
        tid = self.store.enqueue_task("recon", target="t", command="x")
        self.assertTrue(self.store.cancel_task(tid, "operador"))
        self.assertEqual(self.store.get_task(tid).status, "cancelled")
        # Un finish posterior del worker no debe resucitar la tarea.
        self.store.finish_task(tid, "done", "ok", 0)
        self.assertEqual(self.store.get_task(tid).status, "cancelled")
        self.assertFalse(self.store.cancel_task(tid))

    def test_duplicate_lookup(self):
        fp = "same-fingerprint"
        self.store.enqueue_task("recon", target="t", command="x",
                                fingerprint=fp)
        dup = self.store.find_duplicate(fp)
        self.assertIsNotNone(dup)
        self.assertIsNone(self.store.find_duplicate("other"))

    def test_findings_evidence_decisions(self):
        fid = self.store.add_finding(
            target="t", title="SQLi", severity="high",
            claim="id=1 vulnerable", evidence="proof",
        )
        self.store.add_evidence(fid, None, path="/tmp/e.txt",
                                sha256="abc", excerpt="payload")
        self.store.add_decision(fid, None, "guardian", "confirmed", "ok")
        self.store.update_finding_status(fid, "confirmed", "guardian")
        f = self.store.get_finding(fid)
        self.assertEqual(f.status, "confirmed")
        self.assertEqual(len(self.store.evidence_for_finding(fid)), 1)
        self.assertEqual(len(self.store.decisions_for_finding(fid)), 1)

    def test_assets_and_blocks(self):
        self.store.add_asset("t", "10.0.0.1", 80, "http", "nginx",
                             "nmap", 0.8)
        self.assertEqual(len(self.store.list_assets("t")), 1)
        self.store.add_block("t", "riesgo")
        self.assertIsNotNone(self.store.active_block("t"))
        self.store.clear_blocks("t")
        self.assertIsNone(self.store.active_block("t"))

    def test_events_and_stats(self):
        self.store.add_event("test", "w", 1, {"a": 1})
        events = self.store.list_events(10)
        self.assertEqual(events[0]["type"], "test")
        self.assertEqual(events[0]["payload"], {"a": 1})
        self.assertIn("findings", self.store.stats())


if __name__ == "__main__":
    unittest.main()

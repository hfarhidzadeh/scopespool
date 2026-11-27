import contextlib
import copy
import hashlib
import importlib.util
import inspect
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "private_retention_socket.py"
spec = importlib.util.spec_from_file_location("private_retention_socket", SCRIPT)
socket_bench = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = socket_bench
spec.loader.exec_module(socket_bench)

ARM_CHECKS = {
    "all_calls_completed": True,
    "observer_unchanged_by_reads": True,
    "observer_probes_nonempty": True,
    "observer_lists_empty": True,
    "personal_ids_and_counts_match": True,
    "private_rows_only_for_searching_readers": True,
}


def pair(memories=256, readers=2, number=1):
    names = [f"reader{i}" for i in range(readers)]
    return {
        "memories": memories, "readers": readers, "pair": number,
        "exact_match": {name: True for name in ("warmup", "serial", "concurrent", "observer",
                                                "prune_preview", "applied_prune")},
        "arms": {
            "silent": {"checks": dict(ARM_CHECKS), "retained_by_reader": [0] * readers,
                       "private_members": []},
            "private": {"checks": dict(ARM_CHECKS), "retained_by_reader": [3] * readers,
                        "private_members": names},
        },
    }


def verdict(pairs):
    return socket_bench.acceptance_gate(pairs)


class GateTests(unittest.TestCase):
    def test_every_criterion_holding_passes(self):
        gate = verdict([pair(), pair(number=2), pair(4096, 8)])
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["verdict"], "pass")

    def test_a_failed_request_fails_criterion_a(self):
        broken = pair()
        broken["arms"]["private"]["checks"]["all_calls_completed"] = False
        gate = verdict([pair(), broken])
        self.assertEqual(gate["criteria"]["a_no_failed_requests"]["held"], 1)
        self.assertEqual(gate["first_failure"]["criteria"], ["a_no_failed_requests"])

    def test_a_mismatch_or_changed_observer_fails_criterion_b(self):
        mismatch = pair()
        mismatch["exact_match"]["prune_preview"] = False
        changed = pair(number=2)
        changed["arms"]["silent"]["checks"]["observer_unchanged_by_reads"] = False
        gate = verdict([mismatch, changed])
        self.assertEqual(gate["criteria"]["b_results_match"]["held"], 0)

    def test_an_empty_reader_list_or_a_silent_entry_fails_criterion_c(self):
        empty = pair()
        empty["arms"]["private"]["retained_by_reader"] = [3, 0]
        unavailable = pair(number=2)
        unavailable["arms"]["private"]["retained_by_reader"] = [3, None]
        silent_entry = pair(number=3)
        silent_entry["arms"]["silent"]["retained_by_reader"] = [1, 0]
        short = pair(number=4)
        short["arms"]["private"]["retained_by_reader"] = [3]
        gate = verdict([empty, unavailable, silent_entry, short])
        self.assertEqual(gate["criteria"]["c_retained_for_every_reader"]["held"], 0)
        self.assertTrue(all(gate["criteria"][name]["held"] == 4
                            for name in gate["criteria"] if name != "c_retained_for_every_reader"))

    def test_any_cross_member_trace_fails_criterion_d(self):
        foreign_row = pair()
        foreign_row["arms"]["private"]["checks"]["private_rows_only_for_searching_readers"] = False
        peer_list = pair(number=2)
        peer_list["arms"]["silent"]["checks"]["observer_lists_empty"] = False
        silent_rows = pair(number=3)
        silent_rows["arms"]["silent"]["private_members"] = ["reader0"]
        gate = verdict([foreign_row, peer_list, silent_rows])
        self.assertEqual(gate["criteria"]["d_no_cross_member_attribution"]["held"], 0)
        self.assertIn("d failed", gate["verdict"])

    def test_no_pairs_is_not_a_pass(self):
        self.assertEqual(verdict([])["verdict"], "fail (no pairs ran)")

    def test_the_gate_reads_but_does_not_change_the_pairs(self):
        pairs = [pair(), pair(number=2)]
        before = copy.deepcopy(pairs)
        verdict(pairs)
        self.assertEqual(pairs, before)

    def test_a_fault_counts_as_detected_only_if_d_fails_in_every_pair(self):
        caught, missed = pair(), pair(number=2)
        caught["arms"]["private"]["checks"]["private_rows_only_for_searching_readers"] = False
        self.assertTrue(socket_bench.validate_fault("wrong-member", verdict([caught]))["detected"])
        self.assertFalse(socket_bench.validate_fault("wrong-member", verdict([caught, missed]))["detected"])
        self.assertIsNone(socket_bench.validate_fault(None, verdict([caught])))


class ConfigTests(unittest.TestCase):
    def test_the_default_run_matches_the_scale_benchmark_sizes(self):
        args = socket_bench.parse_args([])
        self.assertEqual(args.sizes, ((256, 2), (1024, 4), (4096, 8)))
        self.assertEqual(args.repetitions, 4)
        self.assertIsNone(args.fault)
        config = socket_bench.build_config(args.sizes, args.repetitions)
        self.assertEqual(
            {key: config[key] for key in ("warmup", "serial", "concurrent_per_reader",
                                          "previews_per_phase", "personal_rounds", "search_limit")},
            {"warmup": 4, "serial": 24, "concurrent_per_reader": 12, "previews_per_phase": 2,
             "personal_rounds": 6, "search_limit": 5})

    def test_partial_and_smoke_runs(self):
        self.assertEqual(socket_bench.parse_args(["--smoke"]).sizes, ((256, 2),))
        self.assertEqual(socket_bench.parse_args(["--size", "4096", "--repetitions", "1"]).sizes,
                         ((4096, 8),))
        with contextlib.redirect_stderr(io.StringIO()):
            for bad in (["--smoke", "--size", "256"], ["--repetitions", "0"], ["--fault", "other"]):
                with self.assertRaises(SystemExit):
                    socket_bench.parse_args(bad)

    def test_the_gate_and_fault_are_written_in_the_docstring(self):
        doc = socket_bench.__doc__
        self.assertIn("fixed on 2026-11-26 before any recorded run", doc)
        for marker in ("(a)", "(b)", "(c)", "(d)", "--fault wrong-member"):
            self.assertIn(marker, doc)

    def test_every_gated_source_is_hashed(self):
        hashes = socket_bench.source_hashes()
        for name in ("store.py", "server.py", "cli.py", "auth.py"):
            self.assertIn("src/dynmemory/" + name, hashes)
        self.assertIn("experiments/private_retention_socket.py", hashes)


class PersistentClientTests(unittest.TestCase):
    # SHA-256 of the gate text and gate code as fixed on 2026-11-26; adding the
    # --persistent-client measurement aid must not change any of them.
    GATE_DOCSTRING_SHA = "da304c42e1a2e31a47bcdb5dc6b7c3bcc13bc6007011e10c9a7998e1841dad14"
    GATE_CODE_SHA = {
        "gate_criteria": "171e434570d730dc9015d08de62cc3e7be89858799b8d21ec324e0728527eb3a",
        "acceptance_gate": "333e5b77d35e9e1e84024b1d5f3d1ba9b4b40d8d52299206ceed9aca5bdc32b4",
        "validate_fault": "f0c01c394ef2c32d85e073a5a432880970acd5d1ae4ef86f01b065bf5ccde313",
    }

    def test_the_default_run_and_its_gate_are_unchanged(self):
        doc = socket_bench.__doc__
        gate = doc[doc.index("Acceptance gate, fixed on 2026-11-26"):doc.index("Smoke check:")]
        self.assertEqual(hashlib.sha256(gate.encode()).hexdigest(), self.GATE_DOCSTRING_SHA)
        for name, digest in self.GATE_CODE_SHA.items():
            source = inspect.getsource(getattr(socket_bench, name))
            self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), digest, name)
        args = socket_bench.parse_args([])
        self.assertFalse(args.persistent_client)
        self.assertEqual(socket_bench.build_config(args.sizes, args.repetitions), {
            "smoke": False,
            "sizes": [{"memories": 256, "readers": 2}, {"memories": 1024, "readers": 4},
                      {"memories": 4096, "readers": 8}],
            "repetitions": 4, "warmup": 4, "serial": 24, "concurrent_per_reader": 12,
            "previews_per_phase": 2, "personal_rounds": 6, "search_limit": 5,
            "client_timeout_s": 30.0,
        })
        self.assertTrue(socket_bench.parse_args(["--smoke", "--persistent-client"]).persistent_client)

    def arm(self, persistent, directory, template, secret_file, authority):
        with tempfile.TemporaryDirectory(dir=directory) as arm_dir:
            return socket_bench.arm(Path(arm_dir), template, 2, True, 0, secret_file, authority,
                                    persistent=persistent)

    def test_persistent_mode_returns_identical_results_over_one_connection_per_member(self):
        directory = Path(tempfile.mkdtemp(prefix="ss", dir="/tmp"))  # short socket paths
        self.addCleanup(shutil.rmtree, directory, True)
        secret = socket_bench.TokenAuthority.generate_secret()
        secret_file = directory / "key"
        secret_file.write_text(secret.hex())
        authority = socket_bench.TokenAuthority(secret)
        template = directory / "fixture.db"
        socket_bench.seed_database(template, 256, 2)
        opened = []
        original = socket_bench.ScopeSpoolClient.call

        def counting(client, *args, **kwargs):
            opened.append(client.token)  # one connection per call by design
            return original(client, *args, **kwargs)

        with mock.patch.object(socket_bench.ScopeSpoolClient, "call", counting):
            default, default_shared = self.arm(False, directory, template, secret_file, authority)
        persistent, persistent_shared = self.arm(True, directory, template, secret_file, authority)
        self.assertEqual(persistent_shared, default_shared)
        for name in ("retained_by_reader", "eligible_by_reader", "shared_archived",
                     "private_members", "checks"):
            self.assertEqual(persistent[name], default[name], name)
        self.assertTrue(all(default["checks"].values()))
        self.assertNotIn("connections_by_member", default)
        # Control: the default arm really opened one connection per call; the
        # persistent arm opened exactly one per member for the same calls.
        calls = sum(phase["attempts"] for name, phase in default["phases"].items()
                    if name != "prune_preview")
        self.assertEqual(len(opened), calls)
        self.assertEqual(persistent["connections_by_member"],
                         {"reader0": 1, "reader1": 1, "peer": 1, "outsider": 1})
        self.assertGreater(calls, 10 * len(persistent["connections_by_member"]))

    def test_a_dropped_connection_fails_the_call_and_the_next_call_reconnects(self):
        client = socket_bench.PersistentClient("/nonexistent/s.sock", "t", timeout=1)
        with self.assertRaises(OSError):
            client.search("x")
        self.assertIsNone(client._connection)
        self.assertEqual(client.connections_opened, 0)


class EndToEndTests(unittest.TestCase):
    def run_smoke(self, *extra):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "socket"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = socket_bench.main(["--smoke", "--output", str(output), *extra])
            return code, json.loads(output.with_suffix(".json").read_text())

    def test_the_real_server_passes_the_gate(self):
        code, report = self.run_smoke()
        self.assertEqual(code, 0)
        self.assertEqual(report["acceptance_gate"]["verdict"], "pass")

    def test_the_server_stops_even_if_started_with_sigint_ignored(self):
        # A non-interactive shell starts `cmd &` with SIGINT ignored, and the
        # child inherits that; the full suite run in the background then hung
        # in every server shutdown until the boot code restored the handler.
        import signal
        directory = Path(tempfile.mkdtemp(prefix="ss", dir="/tmp"))  # short socket path
        self.addCleanup(shutil.rmtree, directory, True)
        secret_file = directory / "key"
        secret_file.write_text(socket_bench.TokenAuthority.generate_secret().hex())
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            with socket_bench.running_server(directory / "s.db", directory / "s.sock", secret_file):
                pass
        finally:
            signal.signal(signal.SIGINT, previous)
        self.assertFalse((directory / "s.sock").exists())

    def test_a_server_that_records_for_another_member_is_caught(self):
        code, report = self.run_smoke("--fault", "wrong-member")
        self.assertEqual(code, 0)
        self.assertTrue(report["validation"]["detected"])
        criteria = report["pairs"][0]["gate_criteria"]
        self.assertFalse(criteria["d_no_cross_member_attribution"])
        self.assertTrue(criteria["a_no_failed_requests"] and criteria["b_results_match"])
        self.assertEqual(report["pairs"][0]["arms"]["private"]["private_members"], ["peer"])


if __name__ == "__main__":
    unittest.main()

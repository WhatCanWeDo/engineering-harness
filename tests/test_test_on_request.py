"""Public, black-box checks for the test-on-request CLI contract.

These tests were authored from the interface specification, independently of
its implementation. They do not claim evaluator isolation or private coverage.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/test-on-request/scripts/testing.py"


class TestOnRequestCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.spec = self.base / "requirements.md"
        self.spec_text = "# Public contract\nReturn the sum. Unicode: сумма.\n"
        self.spec.write_text(self.spec_text, encoding="utf-8")
        self.run = self.base / "run"
        self.environment = self.base / "environment.json"
        self.environment.write_text('{"python":"3","platform":"portable"}', encoding="utf-8")
        self.source = self.root / "src" / "model.py"
        self.source.parent.mkdir()
        self.source.write_text("CANDIDATE_ONLY_SENTINEL = 17\n", encoding="utf-8")

    def cli(self, *args, code=0):
        # All fixtures are outside a Git repository. External executables are
        # deliberately unavailable: preparing artifacts must be self-contained.
        env = os.environ.copy()
        env["PATH"] = ""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            cwd=self.base, env=env, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        if code == 0:
            self.assertEqual(result.stderr, "", result.stderr)
            payload = json.loads(result.stdout)
        else:
            self.assertEqual(result.stdout, "", result.stdout)
            payload = json.loads(result.stderr)
        self.assertIsInstance(payload, dict)
        return payload

    def initialize(self, run=None, *extra):
        run = run or self.run
        self.cli("init", "--task-id", "public-task", "--spec", self.spec,
                 "--run", run, *extra)
        return json.loads((run / "plan.json").read_text(encoding="utf-8"))

    def freeze(self, run=None, files=None, environment=None):
        run = run or self.run
        files = files or ["src/model.py"]
        previous = set((run / "candidates").glob("*"))
        self.cli("freeze", "--run", run, "--root", self.root, "--files", *files,
                 "--environment", environment or self.environment)
        candidates = set((run / "candidates").glob("*"))
        created = candidates - previous
        self.assertLessEqual(len(created), 1)
        candidate = next(iter(created or candidates))
        self.assertRegex(candidate.name, r"^[a-f0-9]{64}$")
        self.assertTrue((candidate / "manifest.json").is_file())
        self.assertTrue((candidate / "tree").is_dir())
        self.cli("verify", "--candidate", candidate)
        return candidate

    def brief(self, role="public", *extra, run=None):
        return self.cli("brief", "--run", run or self.run, "--role", role,
                        "--output-scope", self.base / "public-tests", *extra)

    def test_init_copies_spec_and_records_defaults(self):
        plan = self.initialize()
        self.assertEqual((self.run / "spec.md").read_bytes(), self.spec.read_bytes())
        self.assertEqual(plan["version"], 1)
        self.assertEqual(plan["task_id"], "public-task")
        self.assertEqual(plan["spec_sha256"], hashlib.sha256(self.spec.read_bytes()).hexdigest())
        self.assertEqual(plan["phase"], "before")
        self.assertEqual(plan["selected_suites"], ["public"])
        self.assertIs(plan["private_available"], False)
        self.assertIsInstance(plan["budgets"], dict)
        self.assertTrue(plan["budgets"])
        self.spec.write_text("Later external change", encoding="utf-8")
        self.assertEqual((self.run / "spec.md").read_text(encoding="utf-8"), self.spec_text)

    def test_init_records_explicit_suites_and_phase(self):
        plan = self.initialize(None, "--phase", "after", "--suite", "public",
                               "--suite", "private", "--suite", "adversarial")
        self.assertEqual(plan["phase"], "after")
        self.assertEqual(set(plan["selected_suites"]), {"public", "private", "adversarial"})
        self.assertIs(plan["private_available"], False)

    def test_init_never_overwrites_existing_directory(self):
        for populated in (False, True):
            with self.subTest(populated=populated):
                run = self.base / ("existing-full" if populated else "existing-empty")
                run.mkdir()
                if populated:
                    (run / "plan.json").write_text("KEEP", encoding="utf-8")
                before = {p.name: p.read_bytes() for p in run.iterdir()}
                self.cli("init", "--task-id", "replacement", "--spec", self.spec,
                         "--run", run, code=2)
                self.assertEqual({p.name: p.read_bytes() for p in run.iterdir()}, before)

    def test_argument_errors_are_json(self):
        for arguments in ((), ("unknown-command",), ("init",),
                          ("init", "--task-id", "x", "--spec", self.spec,
                           "--run", self.run, "--phase", "unknown")):
            with self.subTest(arguments=arguments):
                self.cli(*arguments, code=2)

    def test_freeze_copies_only_explicit_files_without_git_or_execution(self):
        self.initialize()
        marker = self.base / "must-not-exist"
        executable_text = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        self.source.write_text(executable_text, encoding="utf-8")
        (self.root / "developer-history.txt").write_text("PRIVATE_HISTORY_SENTINEL", encoding="utf-8")
        (self.root / "unselected-link").symlink_to(self.base / "absent")
        candidate = self.freeze()
        self.assertEqual((candidate / "tree/src/model.py").read_text(encoding="utf-8"), executable_text)
        paths = {str(p.relative_to(candidate / "tree"))
                 for p in (candidate / "tree").rglob("*") if p.is_file()}
        self.assertEqual(paths, {"src/model.py"})
        self.assertFalse(marker.exists())
        self.assertNotIn("PRIVATE_HISTORY_SENTINEL", (candidate / "manifest.json").read_text())
        self.source.write_text("changed working copy\n", encoding="utf-8")
        self.cli("verify", "--candidate", candidate)
        self.assertEqual((candidate / "tree/src/model.py").read_text(encoding="utf-8"), executable_text)

    def test_candidate_identity_is_stable_across_runs_and_file_order(self):
        self.initialize()
        (self.root / "second.txt").write_text("second\n", encoding="utf-8")
        first = self.freeze(files=["src/model.py", "second.txt"])
        other_run = self.base / "second-run"
        self.initialize(other_run)
        second = self.freeze(run=other_run, files=["second.txt", "src/model.py"])
        self.assertEqual(first.name, second.name)

    def test_candidate_identity_changes_with_content_path_and_environment(self):
        self.initialize()
        original = self.freeze()
        self.source.write_text("changed content", encoding="utf-8")
        changed = self.freeze()
        self.assertNotEqual(original.name, changed.name)
        (self.root / "renamed.py").write_bytes(self.source.read_bytes())
        renamed = self.freeze(files=["renamed.py"])
        self.assertNotEqual(changed.name, renamed.name)
        self.environment.write_text('{"python":"4","platform":"portable"}', encoding="utf-8")
        new_environment = self.freeze(files=["renamed.py"])
        self.assertNotEqual(renamed.name, new_environment.name)

    def test_freeze_rejects_unsafe_paths_and_duplicates(self):
        self.initialize()
        (self.base / "outside.py").write_text("OUTSIDE", encoding="utf-8")
        cases = [["../outside.py"], [str(self.source)],
                 ["src/model.py", "src/model.py"], ["missing.py"]]
        for paths in cases:
            with self.subTest(paths=paths):
                self.cli("freeze", "--run", self.run, "--root", self.root,
                         "--environment", self.environment, "--files", *paths, code=2)

    def test_freeze_rejects_file_and_directory_symlinks(self):
        self.initialize()
        (self.root / "linked.py").symlink_to(self.source)
        (self.root / "linked-dir").symlink_to(self.source.parent, target_is_directory=True)
        for path in ("linked.py", "linked-dir/model.py"):
            with self.subTest(path=path):
                self.cli("freeze", "--run", self.run, "--root", self.root,
                         "--files", path, "--environment", self.environment, code=2)

    def test_freeze_requires_environment_json_object(self):
        self.initialize()
        self.cli("freeze", "--run", self.run, "--root", self.root,
                 "--files", "src/model.py", code=2)
        for content in ("[]", "null", '"string"', "42", "not JSON"):
            with self.subTest(content=content):
                self.environment.write_text(content, encoding="utf-8")
                self.cli("freeze", "--run", self.run, "--root", self.root,
                         "--files", "src/model.py", "--environment", self.environment, code=2)

    def test_verify_rejects_modified_removed_and_added_files(self):
        for mutation in ("modify", "remove", "add"):
            with self.subTest(mutation=mutation):
                run = self.base / mutation
                self.initialize(run)
                candidate = self.freeze(run=run)
                target = candidate / "tree/src/model.py"
                if mutation == "modify":
                    target.write_text("tampered", encoding="utf-8")
                elif mutation == "remove":
                    target.unlink()
                else:
                    (candidate / "tree/extra.txt").write_text("extra", encoding="utf-8")
                self.cli("verify", "--candidate", candidate, code=2)

    def test_verify_rejects_symlink_replacing_frozen_file(self):
        self.initialize()
        candidate = self.freeze()
        frozen = candidate / "tree/src/model.py"
        frozen.unlink()
        frozen.symlink_to(self.source)
        self.cli("verify", "--candidate", candidate, code=2)

    def test_verify_rejects_candidate_directory_rename(self):
        self.initialize()
        candidate = self.freeze()
        renamed = candidate.with_name("0" * 64 if candidate.name != "0" * 64 else "1" * 64)
        candidate.rename(renamed)
        self.cli("verify", "--candidate", renamed, code=2)

    def test_public_brief_contains_spec_and_scope_without_candidate(self):
        self.initialize()
        candidate = self.freeze()
        response = self.brief("public")
        self.assertEqual(response["status"], "ready")
        prompt = response["prompt"]
        self.assertIn(self.spec_text, prompt)
        self.assertIn(str(self.base / "public-tests"), prompt)
        self.assertNotIn("CANDIDATE_ONLY_SENTINEL", prompt)
        self.assertNotIn(str(candidate), prompt)
        self.assertNotIn(candidate.name, prompt)
        self.cli("brief", "--run", self.run, "--role", "public",
                 "--output-scope", self.base / "public-tests",
                 "--candidate", candidate, code=2)

    def test_public_brief_is_available_before_candidate_exists(self):
        self.initialize()
        response = self.brief()
        self.assertEqual(response["status"], "ready")
        self.assertIn(self.spec_text, response["prompt"])

    def test_private_brief_reports_unavailable(self):
        self.initialize(None, "--suite", "private")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "brief", "--run", str(self.run),
             "--role", "private", "--output-scope", str(self.base / "private-output")],
            cwd=self.base, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(response["reason"], "private_backend_unavailable")
        self.assertFalse(response.get("prompt"))
        self.assertFalse((self.base / "private-output").exists())

    def test_adversarial_brief_requires_valid_candidate_and_excludes_history(self):
        self.initialize(None, "--suite", "adversarial")
        self.cli("brief", "--run", self.run, "--role", "adversarial",
                 "--output-scope", self.base / "adversarial-tests", code=2)
        (self.root / "developer-history.txt").write_text("PRIVATE_HISTORY_SENTINEL", encoding="utf-8")
        candidate = self.freeze()
        response = self.brief("adversarial", "--candidate", candidate)
        self.assertEqual(response["status"], "ready")
        self.assertIn(self.spec_text, response["prompt"])
        self.assertIn(str(self.base / "public-tests"), response["prompt"])
        self.assertNotIn("PRIVATE_HISTORY_SENTINEL", json.dumps(response))
        (candidate / "tree/src/model.py").write_text("tampered", encoding="utf-8")
        self.cli("brief", "--run", self.run, "--role", "adversarial",
                 "--output-scope", self.base / "adversarial-tests",
                 "--candidate", candidate, code=2)

    def test_brief_rejects_unselected_role(self):
        self.initialize()
        self.cli("brief", "--run", self.run, "--role", "adversarial",
                 "--output-scope", self.base / "adversarial-tests", code=2)

    def test_adversarial_brief_rejects_candidate_for_different_spec(self):
        self.initialize(None, "--suite", "adversarial")
        candidate = self.freeze()
        self.spec.write_text("A different public contract", encoding="utf-8")
        other_run = self.base / "different-spec-run"
        self.initialize(other_run, "--suite", "adversarial")
        self.cli("brief", "--run", other_run, "--role", "adversarial",
                 "--output-scope", self.base / "adversarial-tests",
                 "--candidate", candidate, code=2)

    def test_init_rejects_nonpositive_budgets(self):
        for option in ("--budget-seconds", "--budget-cases", "--budget-findings", "--private-queries"):
            for value in ("0", "-1"):
                with self.subTest(option=option, value=value):
                    run = self.base / (option.removeprefix("--") + value)
                    self.cli("init", "--task-id", "x", "--spec", self.spec,
                             "--run", run, option, value, code=2)

    def test_after_phase_brief_discloses_post_hoc_provenance(self):
        self.initialize(None, "--phase", "after")
        response = self.brief()
        self.assertEqual(response["provenance"], "post_hoc")
        self.assertRegex(response["prompt"].lower(), r"post[-_ ]hoc")


if __name__ == "__main__":
    unittest.main()

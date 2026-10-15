"""
The credit runner's guard and ledger, offline. Run: python3 -m unittest tools.test_credit_runner
"""

import tempfile
import unittest
from pathlib import Path

from tools import credit_runner as cr


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.wd = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def allow(self, tool, **inp):
        self.assertIsNone(cr.guard_decision(tool, inp, self.wd), (tool, inp))

    def deny(self, tool, **inp):
        self.assertIsNotNone(cr.guard_decision(tool, inp, self.wd), (tool, inp))

    def test_writes_stay_in_the_copy(self):
        self.allow("Edit", file_path=str(self.wd / "strategy.py"))
        self.allow("Write", file_path="IMPROVEMENTS.md")
        self.deny("Write", file_path="/etc/hosts")
        self.deny("Edit", file_path=str(self.wd / ".." / "elsewhere.py"))
        self.deny("Write", file_path=str(self.wd / ".env"))
        self.deny("Write", file_path=str(self.wd / "config.yaml"))

    def test_reads_stay_in_the_copy_and_off_secrets(self):
        self.allow("Read", file_path=str(self.wd / "README.md"))
        self.allow("Grep", pattern="TODO")
        self.deny("Read", file_path=str(Path.home() / ".anthropic_key"))
        self.deny("Grep", pattern="sk-ant", path=str(Path.home()))
        self.deny("Read", file_path=str(self.wd / ".pypowerwall.fleetapi"))
        self.deny("Read", file_path=str(self.wd / "tesla-fleet-private.pem"))

    def test_shell_allows_tests_and_local_git(self):
        for cmd in ["python3 -m unittest test_strategy -v", "python3 -m pytest -q", ".venv/bin/python -m unittest discover",
                    "git status", "git diff --stat", "git add -A && git commit -m \"Fix the env var docs; set a default\"",
                    "cd tests && python3 -m pytest", "ls -la", "python3 -m py_compile strategy.py"]:
            self.allow("Bash", command=cmd)

    def test_shell_blocks_the_rest(self):
        for cmd in ["git push origin HEAD", "curl https://api.octopus.energy", "python3 feed.py --once",
                    "python3 controller.py", "printenv", "env", "echo $ANTHROPIC_API_KEY", "cat ~/.anthropic_key",
                    "python3 -m pytest -k \"$(cat ~/.anthropic_key)\"", "pip install requests", "rm -rf build",
                    "python3 -c 'import os'", "sudo ls", "git fetch", "echo hi > ~/x", "launchctl list"]:
            self.deny("Bash", command=cmd)

    def test_unknown_tools_are_refused(self):
        self.deny("SomeNewTool")
        self.allow("WebSearch", query="pypowerwall fleet api reserve")


class LedgerTests(unittest.TestCase):
    def test_remaining_never_negative(self):
        self.assertEqual(cr.remaining({"cap": 10.0, "spent": 12.5}), 0.0)
        self.assertAlmostEqual(cr.remaining({"cap": 74.0, "spent": 20.25}), 53.75)

    def test_shares_leave_room_for_the_fact_checker(self):
        self.assertLess(sum(cr.SHARES.values()), 74.0)


if __name__ == "__main__":
    unittest.main()

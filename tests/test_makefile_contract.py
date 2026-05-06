"""Regression tests for operator-facing Makefile contracts."""
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"


class MakefileContractTests(unittest.TestCase):
    def test_kanban_create_exposes_workspace_selection(self):
        makefile = MAKEFILE.read_text()

        self.assertIn("WORKSPACE ?= scratch", makefile)
        self.assertIn("--workspace \"$(WORKSPACE)\"", makefile)
        self.assertIn("WORKSPACE=dir:/workspace", makefile)


if __name__ == "__main__":
    unittest.main()

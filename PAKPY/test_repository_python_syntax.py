"""Compile every Python source file so startup syntax regressions fail in tests."""
from pathlib import Path
import tokenize
import unittest


class RepositoryPythonSyntaxTests(unittest.TestCase):
    def test_all_python_sources_compile(self):
        root = Path(__file__).resolve().parent
        failures = []
        for path in sorted(root.glob("*.py")):
            try:
                with tokenize.open(path) as handle:
                    source = handle.read()
                compile(source, str(path), "exec")
            except SyntaxError as exc:
                failures.append(
                    f"{path.name}:{exc.lineno}:{exc.offset}: {exc.msg}"
                )
        self.assertFalse(failures, "\n".join(failures))


if __name__ == "__main__":
    unittest.main()

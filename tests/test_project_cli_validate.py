import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock


CLI_PATH = Path(__file__).resolve().parents[1] / "tools" / "project_cli.py"
SPEC = importlib.util.spec_from_file_location("project_cli_validate", CLI_PATH)
project_cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(project_cli)


class TestProjectCliValidate(unittest.TestCase):
    def test_vscode_jsonc_comments_and_comment_markers_in_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Project", encoding="utf-8")
            vscode = root / ".vscode"
            vscode.mkdir()
            (vscode / "settings.json").write_text(
                '// VS Code settings\n'
                '{\n'
                '  "url": "https://example.test/path", /* inline comment */\n'
                '  "text": "literal // and /* markers */"\n'
                '}\n',
                encoding="utf-8",
            )
            with mock.patch.object(project_cli, "KIT", root):
                with contextlib.redirect_stdout(io.StringIO()):
                    project_cli.validate(root)

    def test_unterminated_vscode_jsonc_comment_fails_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Project", encoding="utf-8")
            vscode = root / ".vscode"
            vscode.mkdir()
            (vscode / "settings.json").write_text(
                '{"setting": true /* unterminated',
                encoding="utf-8",
            )
            with mock.patch.object(project_cli, "KIT", root):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, r"settings\.json"):
                        project_cli.validate(root)

    def test_regular_json_remains_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Project", encoding="utf-8")
            (root / "config.json").write_text(
                '{"setting": true // not valid JSON here\n}',
                encoding="utf-8",
            )
            with mock.patch.object(project_cli, "KIT", root):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, r"config\.json"):
                        project_cli.validate(root)


if __name__ == "__main__":
    unittest.main()

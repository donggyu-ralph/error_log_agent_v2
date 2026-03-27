"""Unit tests for ReAct agent tools."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.tools.file_system import read_source_code, search_related_files, list_project_files, get_git_history
from src.tools.k8s_ops import read_k8s_logs, get_pod_status


class TestReadSourceCode:
    @patch("src.tools.file_system._get_project_root", return_value="/tmp/test_project")
    def test_read_existing_file(self, mock_root, tmp_path):
        # Create test file
        project = tmp_path / "test_project"
        project.mkdir()
        (project / "src").mkdir()
        test_file = project / "src" / "main.py"
        test_file.write_text("line1\nline2\nline3\n")

        with patch("src.tools.file_system._get_project_root", return_value=str(project)):
            result = read_source_code.invoke({"file_path": "src/main.py"})
            assert "line1" in result
            assert "line2" in result

    @patch("src.tools.file_system._get_project_root", return_value="/tmp/nonexistent")
    def test_read_missing_file(self, mock_root):
        result = read_source_code.invoke({"file_path": "missing.py"})
        assert "not found" in result.lower()

    @patch("src.tools.file_system._get_project_root", return_value="/tmp/test")
    def test_read_with_line_range(self, mock_root, tmp_path):
        project = tmp_path / "test"
        project.mkdir()
        test_file = project / "code.py"
        test_file.write_text("\n".join(f"line{i}" for i in range(1, 21)))

        with patch("src.tools.file_system._get_project_root", return_value=str(project)):
            result = read_source_code.invoke({"file_path": "code.py", "start_line": 5, "end_line": 10})
            assert "line5" in result
            assert "line10" in result
            assert "line11" not in result

    @patch("src.tools.file_system._get_project_root", return_value="/tmp/test")
    def test_normalize_app_prefix(self, mock_root, tmp_path):
        project = tmp_path / "test"
        project.mkdir()
        (project / "src").mkdir()
        (project / "src" / "app.py").write_text("hello")

        with patch("src.tools.file_system._get_project_root", return_value=str(project)):
            result = read_source_code.invoke({"file_path": "/app/src/app.py"})
            assert "hello" in result


class TestSearchRelatedFiles:
    @patch("src.tools.file_system._get_project_root")
    def test_search_keyword(self, mock_root, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "src").mkdir()
        (project / "src" / "a.py").write_text("def process_data():\n    pass\n")
        (project / "src" / "b.py").write_text("import os\n")

        mock_root.return_value = str(project)
        with patch("src.config.settings.get_settings") as mock_settings:
            mock_settings.return_value.target_projects = [MagicMock(exclude_paths=[])]
            result = search_related_files.invoke({"keyword": "process_data"})
            assert "a.py" in result
            assert "b.py" not in result

    @patch("src.tools.file_system._get_project_root", return_value="/tmp/nonexistent")
    def test_search_no_project(self, mock_root):
        result = search_related_files.invoke({"keyword": "test"})
        assert "not found" in result.lower()


class TestListProjectFiles:
    @patch("src.tools.file_system._get_project_root")
    def test_list_files(self, mock_root, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "src").mkdir()
        (project / "src" / "a.py").write_text("x")
        (project / "src" / "b.py").write_text("y")

        mock_root.return_value = str(project)
        result = list_project_files.invoke({"directory": "src"})
        assert "a.py" in result
        assert "b.py" in result

    @patch("src.tools.file_system._get_project_root", return_value="/tmp/test")
    def test_list_missing_dir(self, mock_root):
        result = list_project_files.invoke({"directory": "nonexistent"})
        assert "not found" in result.lower()


class TestGetGitHistory:
    @patch("subprocess.run")
    @patch("src.tools.file_system._get_project_root", return_value="/tmp/repo")
    def test_git_history(self, mock_root, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123 initial commit\ndef456 fix bug\n")
        result = get_git_history.invoke({"count": 5})
        assert "initial commit" in result
        assert "fix bug" in result

    @patch("subprocess.run")
    @patch("src.tools.file_system._get_project_root", return_value="/tmp/repo")
    def test_git_error(self, mock_root, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="not a git repo")
        result = get_git_history.invoke({"count": 5})
        assert "error" in result.lower()


class TestK8sTools:
    @patch("subprocess.run")
    def test_read_k8s_logs(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ERROR - something failed\n")
        result = read_k8s_logs.invoke({})
        assert "ERROR" in result

    @patch("subprocess.run")
    def test_read_k8s_logs_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        result = read_k8s_logs.invoke({})
        assert "error" in result.lower()

    @patch("subprocess.run")
    def test_get_pod_status(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="NAME  READY  STATUS\npod1  1/1    Running\n")
        result = get_pod_status.invoke({})
        assert "Running" in result

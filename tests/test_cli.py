"""Tests for the CLI module — config merging and client detection."""

import json
from pathlib import Path
from unittest.mock import patch

from notebooklm_mcp_2026.cli import (
    ClaudeCodeConfig,
    CursorConfig,
    merge_mcp_config,
)


class TestMergeConfig:
    """Test the JSON config merging logic."""

    def test_create_new_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "mcp.json"
        ok, msg = merge_mcp_config(
            config_path, "mcpServers", "test-server", {"command": "test"}
        )
        assert ok
        assert "Added" in msg

        data = json.loads(config_path.read_text())
        assert data["mcpServers"]["test-server"] == {"command": "test"}

    def test_preserve_existing_servers(self, tmp_path: Path) -> None:
        config_path = tmp_path / "mcp.json"
        existing = {
            "mcpServers": {
                "other-server": {"command": "other", "args": ["--flag"]}
            }
        }
        config_path.write_text(json.dumps(existing))

        ok, _ = merge_mcp_config(
            config_path, "mcpServers", "test-server", {"command": "test"}
        )
        assert ok

        data = json.loads(config_path.read_text())
        assert "other-server" in data["mcpServers"]
        assert data["mcpServers"]["other-server"]["command"] == "other"
        assert "test-server" in data["mcpServers"]

    def test_preserve_other_settings(self, tmp_path: Path) -> None:
        config_path = tmp_path / "settings.json"
        existing = {"permissions": {"allow": []}, "model": "opus"}
        config_path.write_text(json.dumps(existing))

        ok, _ = merge_mcp_config(
            config_path, "mcpServers", "test-server", {"command": "test"}
        )
        assert ok

        data = json.loads(config_path.read_text())
        assert data["permissions"] == {"allow": []}
        assert data["model"] == "opus"
        assert "mcpServers" in data

    def test_update_existing_entry(self, tmp_path: Path) -> None:
        config_path = tmp_path / "mcp.json"
        existing = {"mcpServers": {"test-server": {"command": "old"}}}
        config_path.write_text(json.dumps(existing))

        ok, msg = merge_mcp_config(
            config_path, "mcpServers", "test-server", {"command": "new"}
        )
        assert ok
        assert "Updated" in msg

        data = json.loads(config_path.read_text())
        assert data["mcpServers"]["test-server"]["command"] == "new"

    def test_corrupt_json_backup(self, tmp_path: Path) -> None:
        config_path = tmp_path / "mcp.json"
        config_path.write_text("not valid json{{{")

        ok, msg = merge_mcp_config(
            config_path, "mcpServers", "test-server", {"command": "test"}
        )
        assert not ok
        assert "Corrupt" in msg
        assert (tmp_path / "mcp.json.backup").exists()

    def test_vscode_servers_key(self, tmp_path: Path) -> None:
        config_path = tmp_path / "mcp.json"
        existing = {"servers": {"github": {"url": "https://example.com"}}}
        config_path.write_text(json.dumps(existing))

        ok, _ = merge_mcp_config(
            config_path, "servers", "test-server", {"command": "test"}
        )
        assert ok

        data = json.loads(config_path.read_text())
        assert "github" in data["servers"]
        assert "test-server" in data["servers"]

    def test_empty_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "mcp.json"
        config_path.write_text("")

        ok, msg = merge_mcp_config(
            config_path, "mcpServers", "test-server", {"command": "test"}
        )
        assert ok
        assert "Added" in msg

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        config_path = tmp_path / "nested" / "dir" / "mcp.json"
        ok, _ = merge_mcp_config(
            config_path, "mcpServers", "test-server", {"command": "test"}
        )
        assert ok
        assert config_path.exists()

    def test_trailing_newline(self, tmp_path: Path) -> None:
        config_path = tmp_path / "mcp.json"
        merge_mcp_config(config_path, "mcpServers", "test-server", {"command": "test"})
        raw = config_path.read_text()
        assert raw.endswith("\n")
        assert not raw.endswith("\n\n")


class TestClientDetection:
    def test_claude_code_detected_when_dir_exists(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        cfg = ClaudeCodeConfig()
        with patch.object(Path, "home", return_value=tmp_path):
            assert cfg.detect()

    def test_claude_code_not_detected_when_missing(self, tmp_path: Path) -> None:
        cfg = ClaudeCodeConfig()
        with patch.object(Path, "home", return_value=tmp_path):
            assert not cfg.detect()

    def test_cursor_detected_when_dir_exists(self, tmp_path: Path) -> None:
        (tmp_path / ".cursor").mkdir()
        cfg = CursorConfig()
        with patch.object(Path, "home", return_value=tmp_path):
            assert cfg.detect()

    def test_cursor_not_detected_when_missing(self, tmp_path: Path) -> None:
        cfg = CursorConfig()
        with patch.object(Path, "home", return_value=tmp_path):
            assert not cfg.detect()

    def test_claude_code_config_path(self) -> None:
        cfg = ClaudeCodeConfig()
        path = cfg.config_path()
        assert path is not None
        assert path.name == ".claude.json"

    def test_cursor_config_path(self) -> None:
        cfg = CursorConfig()
        path = cfg.config_path()
        assert path is not None
        assert path.name == "mcp.json"
        assert ".cursor" in str(path)

"""Tests for shrip.ignore module."""

from __future__ import annotations

from pathlib import Path

from shrip.ignore import collect_ignore_patterns, parse_ignore_file


class TestParseIgnoreFile:
    def test_basic_patterns(self, tmp_path: Path):
        f = tmp_path / ".shripignore"
        f.write_text("*.log\nnode_modules/\n.env\n")

        patterns = parse_ignore_file(f)
        assert patterns == ["*.log", "node_modules/", ".env"]

    def test_comments_stripped(self, tmp_path: Path):
        f = tmp_path / ".shripignore"
        f.write_text("# This is a comment\n*.log\n# Another comment\n.env\n")

        patterns = parse_ignore_file(f)
        assert patterns == ["*.log", ".env"]

    def test_empty_lines_ignored(self, tmp_path: Path):
        f = tmp_path / ".shripignore"
        f.write_text("*.log\n\n\n.env\n\n")

        patterns = parse_ignore_file(f)
        assert patterns == ["*.log", ".env"]

    def test_trailing_whitespace_stripped(self, tmp_path: Path):
        f = tmp_path / ".shripignore"
        f.write_text("*.log   \n.env  \n")

        patterns = parse_ignore_file(f)
        assert patterns == ["*.log", ".env"]

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / ".shripignore"
        f.write_text("")

        patterns = parse_ignore_file(f)
        assert patterns == []

    def test_comments_only(self, tmp_path: Path):
        f = tmp_path / ".shripignore"
        f.write_text("# just comments\n# nothing else\n")

        patterns = parse_ignore_file(f)
        assert patterns == []

    def test_nonexistent_file(self, tmp_path: Path):
        f = tmp_path / ".shripignore"

        patterns = parse_ignore_file(f)
        assert patterns == []

    def test_negation_preserved(self, tmp_path: Path):
        f = tmp_path / ".shripignore"
        f.write_text("*.log\n!important.log\n")

        patterns = parse_ignore_file(f)
        assert patterns == ["*.log", "!important.log"]


class TestCollectIgnorePatterns:
    def test_from_directory(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".shripignore").write_text("*.log\n")

        patterns = collect_ignore_patterns([d])
        assert "*.log" in patterns

    def test_no_ignore_file(self, tmp_path: Path, monkeypatch: object):
        d = tmp_path / "proj"
        d.mkdir()
        # Use tmp_path as CWD so no real .gitignore is found
        monkeypatch.chdir(tmp_path)

        patterns = collect_ignore_patterns([d])
        assert patterns == []

    def test_no_ignore_flag(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".shripignore").write_text("*.log\n")

        patterns = collect_ignore_patterns([d], no_ignore=True)
        assert patterns == []

    def test_deduplicates_files(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".shripignore").write_text("*.log\n")

        # Pass same directory twice
        patterns = collect_ignore_patterns([d, d])
        assert patterns.count("*.log") == 1

    def test_file_input_checks_parent(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        f = d / "data.txt"
        f.write_text("data")
        (d / ".shripignore").write_text("*.log\n")

        patterns = collect_ignore_patterns([f])
        assert "*.log" in patterns

    def test_gitignore_patterns_loaded(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".gitignore").write_text("node_modules/\n__pycache__/\n")

        patterns = collect_ignore_patterns([d])
        assert "node_modules/" in patterns
        assert "__pycache__/" in patterns

    def test_shripignore_and_gitignore_merged(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".shripignore").write_text("*.log\n")
        (d / ".gitignore").write_text("node_modules/\n")

        patterns = collect_ignore_patterns([d])
        assert "*.log" in patterns
        assert "node_modules/" in patterns

    def test_duplicate_patterns_across_files_deduplicated(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".shripignore").write_text("*.log\n.env\n")
        (d / ".gitignore").write_text("*.log\nnode_modules/\n")

        patterns = collect_ignore_patterns([d])
        assert patterns.count("*.log") == 1
        assert ".env" in patterns
        assert "node_modules/" in patterns

    def test_shripignore_loaded_before_gitignore(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".shripignore").write_text("from_shrip\n")
        (d / ".gitignore").write_text("from_git\n")

        patterns = collect_ignore_patterns([d])
        assert patterns.index("from_shrip") < patterns.index("from_git")

    def test_no_ignore_flag_skips_gitignore(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".gitignore").write_text("node_modules/\n")

        patterns = collect_ignore_patterns([d], no_ignore=True)
        assert patterns == []

    def test_only_gitignore_no_shripignore(self, tmp_path: Path):
        d = tmp_path / "proj"
        d.mkdir()
        (d / ".gitignore").write_text("*.pyc\n")

        patterns = collect_ignore_patterns([d])
        assert "*.pyc" in patterns

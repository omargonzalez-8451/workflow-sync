"""Tests for renderer utilities and version comparison logic."""

from pathlib import Path

import pytest

from workflow_sync.renderer import (
    find_template_file,
    needs_update,
    parse_deployed_meta,
    parse_template_meta,
    render_template,
)
from workflow_sync.base_schemas import Repo

_SAMPLE = """\
# title: Sample Workflow
# version: 2.1.0
# description: A sample workflow for testing

name: Sample
on:
  push:
    branches: [main]
"""


class TestParseTemplateMeta:
    def test_parses_all_keys(self, tmp_path):
        f = tmp_path / "workflow.yml.j2"
        f.write_text(_SAMPLE)
        meta = parse_template_meta(f)
        assert meta["title"] == "Sample Workflow"
        assert meta["version"] == "2.1.0"
        assert meta["description"] == "A sample workflow for testing"

    def test_stops_at_non_comment(self, tmp_path):
        f = tmp_path / "workflow.yml.j2"
        f.write_text("# version: 1.0.0\nname: CI\n# ignored: yes\n")
        meta = parse_template_meta(f)
        assert "ignored" not in meta

    def test_empty_file(self, tmp_path):
        f = tmp_path / "workflow.yml.j2"
        f.write_text("")
        assert parse_template_meta(f) == {}


class TestParseDeployedMeta:
    def test_parses_keys(self):
        meta = parse_deployed_meta(_SAMPLE)
        assert meta["version"] == "2.1.0"

    def test_no_meta(self):
        assert parse_deployed_meta("name: CI\n") == {}


class TestNeedsUpdate:
    def test_no_deployed_file(self):
        assert needs_update("1.0.0", None) is True

    def test_older_deployed_version(self):
        content = "# version: 0.9.0\nname: CI\n"
        assert needs_update("1.0.0", content) is True

    def test_same_version(self):
        content = "# version: 1.0.0\nname: CI\n"
        assert needs_update("1.0.0", content) is False

    def test_newer_deployed_version(self):
        content = "# version: 2.0.0\nname: CI\n"
        assert needs_update("1.0.0", content) is False

    def test_no_version_in_deployed(self):
        assert needs_update("1.0.0", "name: CI\n") is True

    def test_non_semver_same_string(self):
        content = "# version: abc\nname: CI\n"
        assert needs_update("abc", content) is False

    def test_non_semver_different_string(self):
        content = "# version: abc\nname: CI\n"
        assert needs_update("xyz", content) is True


class TestFindTemplateFile:
    def test_prefers_j2(self, tmp_path):
        (tmp_path / "workflow.yml").write_text("a: 1")
        (tmp_path / "workflow.yml.j2").write_text("b: 2")
        result = find_template_file(tmp_path)
        assert result is not None
        assert result.suffix == ".j2"

    def test_falls_back_to_yml(self, tmp_path):
        (tmp_path / "workflow.yml").write_text("a: 1")
        result = find_template_file(tmp_path)
        assert result is not None
        assert result.name == "workflow.yml"

    def test_empty_dir_returns_none(self, tmp_path):
        assert find_template_file(tmp_path) is None


class TestRenderTemplate:
    def test_renders_variable(self, tmp_path):
        f = tmp_path / "workflow.yml.j2"
        f.write_text("# title: Test\nname: {{ repo.name }}\n")
        repo = Repo(
            url="https://github.com/org/my-repo",
            language="python",
            workflows=[],
        )
        rendered = render_template(f, {"repo": repo})
        assert "my-repo" in rendered

    def test_static_template(self, tmp_path):
        f = tmp_path / "workflow.yml.j2"
        f.write_text("name: CI\n")
        rendered = render_template(f, {})
        assert rendered == "name: CI\n"

    def test_github_actions_expressions_are_preserved(self, tmp_path):
        f = tmp_path / "workflow.yml.j2"
        f.write_text(
            "env:\n"
            "  SHA: ${{ github.sha }}\n"
            "  TOKEN: ${{ secrets.MY_TOKEN }}\n"
            "  REPO: {{ repo.name }}\n"
        )
        repo = Repo(
            url="https://github.com/org/my-repo", language="python", workflows=[]
        )
        rendered = render_template(f, {"repo": repo})
        assert "${{ github.sha }}" in rendered
        assert "${{ secrets.MY_TOKEN }}" in rendered
        assert "my-repo" in rendered

    def test_partial_include(self, tmp_path):
        """Templates can {% include %} partials resolved via extra_search_paths."""
        partials_dir = tmp_path / "_partials"
        partials_dir.mkdir()
        (partials_dir / "_greeting.j2").write_text(
            "      - name: Hello {{ repo.name }}\n"
        )

        f = tmp_path / "workflow.yml.j2"
        f.write_text("steps:\n{% include '_partials/_greeting.j2' %}\n")

        repo = Repo(
            url="https://github.com/org/my-repo", language="python", workflows=[]
        )
        rendered = render_template(f, {"repo": repo}, extra_search_paths=[tmp_path])
        assert "Hello my-repo" in rendered

    def test_nojira_prefix_skipped_in_partial(self, tmp_path):
        """The NOJIRA guard string is rendered into the partial output."""
        partials_dir = tmp_path / "_partials"
        partials_dir.mkdir()
        # Minimal stand-in for _jira-common that only contains the NOJIRA check
        (partials_dir / "_jira-common.yml.j2").write_text(
            "          if echo \"$BRANCH\" | grep -qiE '^NOJIRA'; then\n"
            '            echo "found=false" >> $GITHUB_OUTPUT\n'
            "            exit 0\n"
            "          fi\n"
        )
        f = tmp_path / "workflow.yml.j2"
        f.write_text("{% include '_partials/_jira-common.yml.j2' %}\n")
        rendered = render_template(f, {}, extra_search_paths=[tmp_path])
        assert "NOJIRA" in rendered
        assert "found=false" in rendered

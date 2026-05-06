"""Tests for sync helpers."""

import pytest

from workflow_sync.sync import _is_version_bump_only

_HEADER_V1 = """\
# id: my-workflow
# title: My Workflow
# version: 1.0.0
# description: Does things
"""

_HEADER_V2 = """\
# id: my-workflow
# title: My Workflow
# version: 2.0.0
# description: Does things
"""

_BODY = """\
name: My Workflow

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  my-job:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""


class TestIsVersionBumpOnly:
    def test_version_bump_only(self):
        old = _HEADER_V1 + _BODY
        new = _HEADER_V2 + _BODY
        assert _is_version_bump_only(old, new) is True

    def test_workflow_body_changed(self):
        old = _HEADER_V1 + _BODY
        new = _HEADER_V2 + _BODY.replace("ubuntu-latest", "self-hosted")
        assert _is_version_bump_only(old, new) is False

    def test_new_step_added(self):
        old = _HEADER_V1 + _BODY
        new = _HEADER_V2 + _BODY + "      - run: echo hello\n"
        assert _is_version_bump_only(old, new) is False

    def test_identical_content(self):
        # Same version, same body — should count as bump-only (no body diff)
        assert _is_version_bump_only(_HEADER_V1 + _BODY, _HEADER_V1 + _BODY) is True

    def test_first_deploy_no_old_content(self):
        # Callers pass deployed_content=None guard before calling this helper,
        # but if somehow called with empty string it should not crash
        assert _is_version_bump_only("", _HEADER_V2 + _BODY) is False

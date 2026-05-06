"""Shared enumerations for workflow-sync."""

from enum import StrEnum


class Language(StrEnum):
    """Primary programming language of a repository."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    JAVA = "java"
    RUST = "rust"
    RUBY = "ruby"
    CSHARP = "csharp"
    CPP = "cpp"
    SHELL = "shell"

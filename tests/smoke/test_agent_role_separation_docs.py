from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_agent_role_contract_is_loaded_before_repository_details() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    role_heading = "## Agent Role Separation"
    assert role_heading in agents
    assert agents.index(role_heading) < agents.index(
        "## Project Structure & Module Organization"
    )
    for role in (
        "Spec / Architecture Owner",
        "Domain / API Implementer",
        "UI / Design Specialist",
        "Independent Reviewer",
        "Supervisor / Integrator",
    ):
        assert role in agents
    assert "delegation never broadens the original authority" in agents


def test_claude_imports_canonical_rules_without_project_overview_copy() -> None:
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "@AGENTS.md" in claude.splitlines()
    assert "## Claude Code-specific guidance" in claude
    assert "## Project Overview" not in claude
    assert "## Current Architecture" not in claude
    assert "UI / Design Specialist" in claude
    assert "stop at a clean handoff" in claude


def test_external_reviewer_uses_the_same_role_contract() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    runbook = (
        ROOT / "docs" / "opencode_external_reviewer_runbook.md"
    ).read_text(encoding="utf-8")
    workflow = (
        ROOT / "docs" / "AI_Feature_Development_Workflow.md"
    ).read_text(encoding="utf-8")

    assert "docs/opencode_external_reviewer_runbook.md" in agents
    assert "Independent Reviewer role from `AGENTS.md`" in runbook
    assert "An OpenCode full-diff audit counts against the review budget" in runbook
    assert "Название инструмента не выдаёт полномочия" in workflow

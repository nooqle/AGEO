# Skill Package Inventory

Skill packages are natural-language guidance files that can be attached to a
registered skill family. They are not executors and do not replace skill
contracts.

Current package mappings live in `app/services/skill_package_service.py`.

## Active Packages

- `analysis-report`
  - Mapped to `analysis_report_skill`.
- `post-analysis`
  - Mapped to `post_analysis_skill`.

## Removed Legacy Package

- `confidence-signal`
  - Removed because the old citation-confidence public skill has been retired.
  - The current live capability is `site_confidence_assessment_skill` / "官网 AI 友好度".
  - That live capability should get its own `site-confidence-assessment` package
    before prompt-style guidance is added.

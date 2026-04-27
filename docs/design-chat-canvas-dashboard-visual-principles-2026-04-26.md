# Chat / Canvas / Dashboard Visual Design Principles

Date: 2026-04-26

This document is the 2026-04 visual refresh implementation checklist for Chat, Canvas, Dashboard, Settings, public landing, auth, Control-plane, dialogs, charts, and shared UI components.

The global visual standard lives in `docs/design-global-visual-principles-2026-04-26.md`. If this document and the global standard ever conflict, the global standard wins.

## Context

Specta is a brand intelligence workspace for brand, growth, and marketing teams. Users come here to compare answers, inspect evidence, review reports, and decide what to optimize next. The interface should feel like a professional research and operations surface, not a generic AI chat product.

This document records the visual direction used in the 2026-04 Chat / Canvas / Dashboard refresh and should be treated as the baseline for future UI changes.

## Core Direction

The product is light-first, evidence-led, calm, and report-oriented.

The UI should communicate:

- Evidence before magic
- Reports and sources before spectacle
- Workbench clarity before marketing decoration
- Precise actions before playful AI personality
- Shared tokens before one-off styling

Avoid making AI itself the visual protagonist. The visible protagonist is the user's brand evidence: reports, citations, scenarios, sources, risks, and next actions.

## Visual Identity

Specta should be recognizable through restraint, not through decorative effects.

The platform signature color is **Specta Evidence Teal**:

- Core: `#1F7A6B`
- Hover: `#17685B`
- Soft surface: `#DCECE7`
- Soft border: `rgba(31, 122, 107, 0.24)`

Use Specta Evidence Teal for:

- Brand recognition moments: logo-adjacent marks, platform-owned labels, selected brand context.
- Primary actions: create, apply, confirm, enter analysis, refresh/run when it is the main command.
- Active navigation and selected states.
- Evidence confirmation: validated, high-confidence, or "Specta output" markers.

Do not use the signature color as general decoration. The more the paper-neutral surface carries the page, the more recognizable the teal becomes when it appears.

Secondary color roles:

- Blue-gray is for sources, platforms, and references.
- Amber is for warning, opportunity, or pending work.
- Red is for risk and negative evidence.
- Neutral ink is for text, metrics, separators, and dense report structure.

## Anti-AI Visual Rules

Do not use these as primary interface language:

- Purple-to-blue gradients
- Neon cyan / purple / violet accents
- Glowing cards, glowing borders, and decorative bloom
- Glassmorphism as a general surface treatment
- Sparkle, robot, brain, magic, or "AI wonder" iconography
- Over-rounded pill/card surfaces everywhere
- Gradient text for metrics or headings
- Decorative orbs, bokeh blobs, or blurred radial background circles
- Generic "AI SaaS" dark mode with neon accents
- Card piles where a report-like layout or simple separator would work better

Permitted exceptions:

- Platform brand color can appear only when it is required for platform recognition, and it should be muted if it competes with evidence hierarchy.
- Small loading or status animation is acceptable when it communicates system state.
- A modal is acceptable for blocking tasks such as brand creation, but it must use restrained radius, border, and shadow.

## Palette

Use tinted paper neutrals as the main surface and reserve color for action, status, and evidence categories.

Primary tokens:

- `--brand-primary`: Specta Evidence Teal, the platform signature and main action color
- `--brand-hover`: action hover
- `--brand-active`: action active
- `--brand-contrast`: text on action surfaces
- `--bg-primary`, `--bg-secondary`, `--bg-tertiary`, `--bg-elevated`: workspace surfaces
- `--bg-report`, `--bg-report-muted`: Canvas / report surfaces
- `--surface-command`: Chat command and user-message surface

Evidence tokens:

- `--evidence-primary`: main evidence/action accent
- `--evidence-secondary`: secondary analytical category
- `--evidence-source`: sources, platforms, references
- `--evidence-risk`: risk and negative evidence
- `--evidence-opportunity`: warning, opportunity, or next action

Status tokens:

- `--success`, `--warning`, `--error`, `--info`
- `--status-success-bg`, `--status-warning-bg`, `--status-error-bg`, `--status-info-bg`

Rules:

- Use tokens instead of hard-coded `indigo`, `violet`, `purple`, `cyan`, `sky`, or old AI gradient hex values.
- Do not introduce a second competing brand color. If a surface needs identity, use Specta Evidence Teal through `--brand-*` tokens.
- If a chart needs fixed SVG colors, mirror the evidence palette in `frontend/src/styles/chart-theme.ts`.
- Do not introduce a new color unless it maps to a user-understandable category.

## Typography

Use the system Chinese UI stack:

`"PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif`

Rules:

- Keep dashboard/report headings measured; reserve hero-scale type for actual public landing heroes.
- Avoid negative letter spacing inside compact panels, tabs, cards, dialogs, and buttons.
- Metrics should be clear and readable, not decorative.
- Do not use monospace as a lazy "technical" aesthetic. Use it only for code-like values, IDs, or logs.

## Shape, Elevation, And Surfaces

Default component radius should be restrained:

- Buttons and inputs: `rounded-lg` or `rounded-xl`
- Compact cards and options: `rounded-xl`
- Larger report sections: 12-18px radius when a frame is necessary
- Avoid `rounded-3xl` except for rare, intentionally large marketing surfaces

Elevation:

- Prefer borders and separators over heavy shadow.
- Use `shadow-sm` for floating controls and dialogs.
- Avoid `shadow-xl`, `shadow-2xl`, glow shadows, and decorative blur.

Surfaces:

- Dashboard: calm operational workspace.
- Canvas: report-grade brief with readable structure and restrained category color.
- Chat: command surface. Messages should feel precise, not mascot-like.
- Settings: utilitarian control surface with clear form hierarchy.

## Chat Principles

Chat should be an execution and command surface.

Rules:

- User messages use `--surface-command`, not bright filled AI chat bubbles.
- Agent avatar should be a simple brand mark or monogram, not robot / brain / sparkle.
- Thinking states should say what is happening in work terms, not "magic" terms.
- Confirmation blocks should prioritize the decision, impact, and available actions.
- Output cards should look like report artifacts, not AI-generated badges.

## Canvas Principles

Canvas is the evidence workspace.

Rules:

- Reports should read like concise research briefs.
- Use separators and section rhythm instead of nested cards.
- Use evidence colors for source/risk/opportunity categories only.
- Avoid decorative glow around newly created artifacts; use border emphasis or state dots.
- Artifact navigation should use report/source/data icons, not robot icons.

## Dashboard Principles

Dashboard is the overview layer for brand operations.

Rules:

- Prioritize scanability: fewer decorative panels, clearer status hierarchy.
- Brand cards should be compact, operational, and token-based.
- Charts use the evidence palette, not the old AI palette.
- Empty states should explain the next useful action without marketing tone.
- Metric panels should not use gradient hero-number styling.

## Settings Principles

Settings is a utility surface.

Rules:

- Avoid large decorative headers.
- Keep status cards compact with clear labels.
- Use standard form controls and restrained selected states.
- Use a single primary action per section where possible.

## Modal And Dialog Rules

Dialogs should feel like focused work surfaces.

Rules:

- Use `rounded-xl`, subtle borders, and restrained shadows.
- Avoid glow selection states.
- Selection states use border emphasis and a small check indicator.
- Dialog copy should be direct: object, action, consequence.

## Implementation Checklist

Before shipping any UI change in Chat, Canvas, Dashboard, Settings, or shared components:

1. Scan for old AI palette terms: `indigo`, `violet`, `purple`, `cyan`, `sky`, `#6366F1`, `#8B5CF6`, `#A855F7`, `#06B6D4`, `#EC4899`.
2. Scan for AI spectacle icons: `Sparkle`, `Sparkling`, `Brain`, `Robot`, `RiRobot`, `RiBrain`.
3. Scan for decorative effects: `glow`, `blur-3xl`, `backdrop-blur`, `shadow-2xl`, `shadow-indigo`.
4. Replace hard-coded colors with tokens or the chart evidence palette.
5. Check dialogs, empty states, loading states, and selected states.
6. Verify no newly introduced Chinese text was saved as question-mark corruption.
7. Run frontend type-check and lint for the changed scope.

Recommended scan command on Windows:

```powershell
Get-ChildItem -Path frontend\src -Recurse -Include *.tsx,*.ts,*.css |
  Select-String -Pattern "indigo|violet|purple|fuchsia|cyan|sky|#6366F1|#8B5CF6|#A855F7|#06B6D4|#EC4899|Sparkles|Sparkle|Brain|Robot|RiRobot|RiBrain|shadow-indigo|glow-border|rgba\(99,102,241"
```

## Current Audit Notes

The 2026-04 refresh scanned and updated:

- Chat message surfaces, input area, output cards, confirmations, task/progress indicators, and loading state.
- Canvas header, panel, artifact navigation, report scaffold, chart/report/content sections, source/risk badges, and workflow footer states.
- Dashboard top bar, hero/empty state, brand avatar/card, brand selection/detail/create dialogs, metric/chart palette, overview boards, monitoring panels, graph, shared UI button/card/toast components.
- Settings header, section cards, form controls, pill options, status panels, and account/monitoring control sections.
- Public landing and marketing showcase color usage where old AI palette values were still visible.

Known intentional leftovers:

- Some legacy class/function names may still refer to older abstractions if renaming would create churn without visual impact.
- Existing report/chart components may still use gradients for subtle surface depth, but not purple-blue AI gradients or decorative glow.

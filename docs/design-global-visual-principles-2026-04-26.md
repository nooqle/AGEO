# Specta Global Visual Design Principles

Date: 2026-04-26

This is the global visual standard for Specta frontend work. It applies to public landing pages, auth, Chat, Canvas, Dashboard, Settings, Control-plane, dialogs, charts, empty states, and shared UI components.

## Product Identity

Specta is a brand intelligence workspace for evidence-heavy work: comparing AI answers, inspecting citations, reviewing reports, and deciding what to optimize next.

The interface should feel:

- Professional
- Evidence-led
- Calm
- Operational
- Report-oriented

The interface should not feel like a generic AI chat product, AI toy, or neon SaaS landing page.

## Signature Color

The platform signature color is **Specta Evidence Teal**.

Canonical values:

- Core: `#1F7A6B`
- Hover: `#17685B`
- Soft surface: `#DCECE7`
- Soft border: `rgba(31, 122, 107, 0.24)`

Use it through these tokens:

- `--brand-primary`
- `--brand-hover`
- `--brand-contrast`
- `--brand-bg`
- `--brand-bg-hover`
- `--brand-border`
- `--brand-text`
- `--evidence-primary`

Use Specta Evidence Teal for:

- Brand recognition moments
- Primary actions
- Active navigation
- Selected states
- Current object context
- High-confidence evidence confirmation
- "Specta output" or platform-owned analytical marks

Do not use the signature color as general decoration. Most screens should be carried by paper-neutral surfaces, so the teal becomes recognizable by restraint.

## Color Roles

Use color only when it maps to a user-understandable role.

- Teal: Specta identity, primary action, evidence confirmation
- Blue-gray: sources, platforms, references, informational state
- Amber: warning, opportunity, pending work, next action
- Red: risk, negative evidence, destructive/error state
- Neutral ink: body text, metrics, separators, dense report structure
- Paper neutrals: app background, panels, cards, report surfaces

Do not introduce a second competing brand color.

## Anti-AI Rules

Do not use these as primary interface language:

- Purple-to-blue gradients
- Indigo, violet, cyan, sky, fuchsia, neon palettes
- Glowing cards, glowing borders, decorative bloom
- Glassmorphism as a general surface treatment
- Sparkle, robot, brain, magic, or AI wonder iconography
- Over-rounded pill/card surfaces everywhere
- Gradient text for metrics or headings
- Decorative orbs, bokeh blobs, or blurred radial background circles
- Generic dark AI SaaS aesthetic with neon accents
- Card piles where a report-like section or separator would work better

## Surface And Shape

Default UI should be light-first and report-oriented.

Use:

- Tinted paper backgrounds
- Subtle borders
- Restrained shadow
- Clear section rhythm
- Smaller, denser controls for operational workflows

Avoid:

- Heavy drop shadows
- Decorative blur
- Nested cards inside cards
- Oversized marketing panels in product workspaces
- `rounded-3xl` as a default

Preferred radius:

- Buttons and inputs: `rounded-lg` or `rounded-xl`
- Compact cards/options: `rounded-xl`
- Larger report sections: 12-18px when a frame is needed
- Dialogs: `rounded-xl`

## Typography

Use the system Chinese UI stack:

`"PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif`

Rules:

- No negative letter spacing in compact panels, cards, dialogs, buttons, tabs, or dense dashboards.
- Hero-scale type is only for public landing heroes.
- Metrics should be readable and calm, not decorative.
- Monospace is only for IDs, logs, codes, or code-like values.

## Component Rules

Buttons:

- Primary actions use `--brand-primary`.
- Secondary actions use paper-neutral surfaces and borders.
- Destructive actions use risk/error tokens only.

Forms:

- Inputs use paper-neutral surfaces, subtle borders, and brand focus state.
- Selected options use `--brand-bg` / `--brand-border`, not glow.

Dialogs:

- Use restrained borders, `rounded-xl`, and light shadow.
- Do not use glow, glass, or large decorative headers.

Charts:

- Use the evidence palette from `frontend/src/styles/chart-theme.ts`.
- Fixed chart colors must mirror design tokens.

Footer:

- ICP and legal copy must live in normal footer document flow.
- Do not implement ICP as fixed, sticky, floating, or viewport watermark text.

## Page Responsibilities

Public landing:

- Can use strong hierarchy, but primary CTAs should use Specta Evidence Teal.
- Avoid generic AI SaaS gradient hero composition.

Auth:

- Must be light-first, focused, and operational.
- No dark neon onboarding style.

Chat:

- Treat Chat as a command surface.
- User messages should feel precise and operational.
- Agent/system states should communicate work progress, not magic.

Canvas:

- Treat Canvas as evidence workspace and concise research brief.
- Prefer sections, separators, and report rhythm over nested cards.

Dashboard:

- Treat Dashboard as brand operations overview.
- Prioritize scanability and evidence hierarchy.

Control-plane:

- Treat Control-plane as internal operations tooling.
- Keep it denser, quieter, and token-based.

## Agent Enforcement Card

Before implementing UI work:

1. Read `.impeccable.md`.
2. Read this file.
3. Check whether the target area has a more specific design doc.
4. Identify which existing tokens/components should be reused.

Before finishing UI work:

1. Scan for old AI palette and effects:

   ```powershell
   Get-ChildItem -Path frontend\src -Recurse -Include *.tsx,*.ts,*.css |
     Select-String -Pattern "indigo|violet|purple|fuchsia|cyan|sky|#4f46e5|#6366F1|#8B5CF6|#A855F7|#06B6D4|#EC4899|Sparkles|Sparkle|Brain|Robot|RiRobot|RiBrain|shadow-indigo|glow|blur-3xl"
   ```

2. Scan edited files for `???`.
3. Run `python scripts/validate_change.py` for non-trivial UI changes.
4. Use browser screenshot or Playwright verification for visible layout changes.

## Relationship To Other Docs

This file is the global standard.

`.impeccable.md` is the compact design context that agents should read first.

`docs/design-chat-canvas-dashboard-visual-principles-2026-04-26.md` records the 2026-04 refresh implementation checklist and area-specific rules for Chat, Canvas, Dashboard, Settings, public landing, auth, and Control-plane.

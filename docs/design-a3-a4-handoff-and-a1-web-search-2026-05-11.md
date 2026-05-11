# A3 to A4 Handoff and A1 Web Search Fix

## Context

Two runtime issues were confirmed on `origin/main` at `99d18fd`:

1. After A3 question generation, the user-visible choice could fall into generic follow-up recommendations instead of the next pipeline step.
2. A1 brand profile links were generated from model knowledge without a reliable web-search path because the GLM5 wrapper filtered out `type=web_search` tools.

## Desired Behavior

- After A3 generates or imports questions, the next `ask_user` checkpoint must ask for A4 answer collection mode.
- The A3 checkpoint options must be:
  - `fast`: quick collection
  - `full`: full browser collection
  - `regenerate`: regenerate questions
- Selecting `fast` or `full` must set `next_required_action` to `answer_fetch` with the chosen `fetch_mode`.
- A1 must pass GLM5 server-side `web_search` tools through to the GLM5 API request.
- Function tools must keep the existing streaming `tool_stream=true` behavior.

## Non-goals

- Do not add a second special-case report-entry flow.
- Do not change A4 platform fetching behavior.
- Do not introduce Bocha into A1 in this fix.
- Do not validate website reachability in this fix; the immediate requirement is enabling GLM5 web search.

## Verification

- Unit-test A3 confirmation payload shape and state update.
- Unit-test GLM5 request preparation keeps `web_search` tools and enables `tool_stream` only when function tools are present.
- Run the shared validation entry point after targeted tests.

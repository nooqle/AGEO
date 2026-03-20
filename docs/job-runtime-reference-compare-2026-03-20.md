# Unified Job Runtime External Reference Compare

## Purpose

Validate whether the current runtime design is aligned with established open-source workflow/runtime systems before we continue expanding it.

## References

- LangGraph durable execution:
  - https://docs.langchain.com/oss/python/langgraph/durable-execution
- Prefect states:
  - https://docs.prefect.io/v3/concepts/states
- Prefect workers:
  - https://docs.prefect.io/v3/concepts/workers
- Temporal durable execution overview:
  - https://assets.temporal.io/durable-execution.pdf
- Git repositories:
  - https://github.com/langchain-ai/langgraph
  - https://github.com/PrefectHQ/prefect
  - https://github.com/temporalio/temporal

## What Those Systems Consistently Do

1. Durable state and ephemeral execution are separated.
   - LangGraph persists workflow state/checkpoints and resumes from interrupts.
   - Prefect persists run states while workers poll and execute.
   - Temporal persists workflow history while workers execute tasks.

2. Execution is lease/poll based rather than "the request handler owns the task forever".
   - Prefect workers poll work pools/work queues.
   - Temporal workers poll task queues.

3. Cancellation is cooperative, not just a UI flag.
   - Workers/executors observe durable state and stop.
   - Heartbeats/checkpoints are part of liveness and cancellation semantics.

4. Human interruption / resume is modeled explicitly.
   - LangGraph treats interrupts/resume as first-class durable behavior.

## Mapping To Our Current Design

- `AnalysisTask`
  - Business-facing task record.
- `TaskRun`
  - Durable execution attempt, closer to Prefect flow/task run or a Temporal task attempt.
- `JobSubmissionService`
  - Unified submission boundary.
- `JobDispatcher`
  - Queue/claim/lease owner semantics.
- `LocalRuntimeRegistry`
  - Local executor binding + cooperative cancel loop.
- `RuntimeCoordinator`
  - Ephemeral coordination boundary reserved for local vs Redis-backed implementations.
- `waiting_input` / `resume_after_input`
  - Our LangGraph-style interrupt/resume bridge.

## Why The Current Direction Is Sound

1. We no longer bind runtime identity to the incoming transport.
   - This matches durable systems better than the earlier "WebSocket request arrives and directly owns execution" model.

2. We introduced an explicit execution-attempt layer.
   - `TaskRun` is the correct structural move; mature systems do not overload a single business task row with queue, claim, retry, and resume semantics.

3. We split durable truth from ephemeral coordination.
   - Postgres keeps task/run truth.
   - Coordinator handles session-local execution presence and future shared locks.
   - This is consistent with how mature systems separate persistence from worker/runtime presence.

4. We modeled human-in-loop as runtime state, not just frontend state.
   - `waiting_input` / `resume_after_input` is the right pattern.

## Where We Are Still Behind Mature Systems

1. Not all entrypoints are fully unified yet.
   - `messages.py` is now routed into the same runtime handler, but remains a compatibility entrypoint rather than a first-class dedicated runtime service.

2. A4 child execution is not yet a first-class attempt model.
   - The active A4 flow is covered by the parent TaskRun.
   - Historical Celery fetch code is not part of the current orchestration path.

3. Shared coordination is now partially implemented.
   - Redis-backed shared locks/markers exist.
   - Cross-worker `cancel` broadcast is implemented.
   - Task-status pubsub is implemented.
   - Session event fanout is implemented for session-scoped events published through the session event publisher.
   - Remaining gap: not every transport-specific edge case is distributed, especially direct websocket-only responses.

4. Production hardening is still lighter than Prefect/Temporal.
   - Fewer concurrency race tests.
   - Fewer deployment safeguards around single-worker assumptions.

## Practical Conclusion

The current runtime direction is not ad-hoc. Structurally it is aligned with the same core patterns used by LangGraph, Prefect, and Temporal:

- durable run state
- executor claim/lease
- cooperative cancellation
- explicit interrupt/resume
- separation of durable truth and ephemeral coordination

What remains is not a fundamental redesign. The remaining work is mainly coverage and hardening:

- unify remaining entrypoints
- harden cross-process coordination edge cases
- decide whether A4 child execution should become first-class runtime attempts

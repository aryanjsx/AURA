"""AURA execution runtime (router, registry, engine, worker IPC, planner).

These modules implement the single authorised execution path:

    User / LLM / API -> Router -> CommandRegistry -> Dispatcher -> Worker

All enforcement primitives they rely on (sandbox, policy, safety gate,
audit chain, permissions, rate limiter, plugin manifest) live in
:mod:`aura.security`.  All infrastructure primitives they build on
(event bus, logger, schema, intent, config, error types) live in
:mod:`aura.core`.
"""

"""AURA security / enforcement primitives.

Everything here is pure policy: it validates, restricts, or audits.
None of these modules own the execution path - they are consulted by
:mod:`aura.runtime` (registry + worker client) before and after each
dispatch.

Owning surfaces:

* :mod:`aura.security.sandbox`         - filesystem base-dir enforcement
* :mod:`aura.security.policy`          - shell argv allowlist / denylist
* :mod:`aura.security.permissions`     - PermissionLevel validator
* :mod:`aura.security.safety_gate`     - non-blocking confirmation
* :mod:`aura.security.rate_limiter`    - per-source sliding-window limiter
* :mod:`aura.security.audit_log`       - tamper-evident hash-chain log
* :mod:`aura.security.audit_events`    - dynamic audit-event registry
* :mod:`aura.security.plugin_manifest` - authoritative plugin policy +
                                         cross-process SHA-256 binding
"""

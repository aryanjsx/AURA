---
name: Module Proposal
about: Propose a new AURA skill or module
title: "[module] "
labels: enhancement
assignees: ''
---

## Module Name

What should this module be called?

## Purpose

What does this module do? What problem does it solve for developers?

## Proposed Location

Where should this live in the codebase? (e.g., `aura-core/`, `aura-devtools/`, new directory)

## Key Functions / API

Describe the main functions or interface this module would expose.

```python
# Example API sketch
def example_function(param: str) -> str:
    """Brief description."""
    ...
```

## Dependencies

What external libraries (if any) would this module need? Remember: AURA must stay fully offline.

## Offline Compatibility

Confirm this module works without internet access:

- [ ] Yes — fully offline
- [ ] Partially — needs internet for initial setup only
- [ ] No — requires ongoing internet access

## Additional Context

References, similar tools, design considerations.

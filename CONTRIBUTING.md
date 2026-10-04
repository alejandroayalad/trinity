# Contributing to Trinity

Write code that a human can understand, review, and debug.
These rules apply to human-written and AI-generated code.

## Code comments

### Style

Use simple technical English, guided by ASD-STE100 principles:

- Write short sentences. Express one idea per sentence.
- Use active voice. Use the imperative for instructions: "Return None when...".
- Use simple words. Use the same term for the same thing.
- Explain technical terms when their meaning is not clear from the context.

### When to comment

Add a comment when the code cannot explain an important detail:

- Why the code does something unusual or non-obvious.
- A business rule, limit, or edge case that the reader cannot see in the code.
- A workaround and the reason it exists.

Do not comment:

- What the code does when the names already explain it.
- Every function, variable, or line.
- Changes such as "Now we use X instead of Y". Git history records changes.

Use the docstring rules below for public APIs and slice entry points.

### Rules

- Keep comments minimal. One line is the default. Use more only when needed.
- Do not put ticket numbers or ticket references in comments. Put them in commit messages.
- Do not add author names, author tags, dates, or history blocks.
- Give public API members a one-line summary docstring. Add parameter documentation only when the meaning is not obvious.
- Document important failure behavior when it is not clear from the code or signature.
- Describe current behavior. Do not describe planned behavior as implemented.
- When you change code, update or delete comments that no longer match it.

### Examples

Good: explains a non-obvious reason.

```python
# Parse the source string directly. A float can lose decimal precision.
value = Decimal(raw_value)
```

Bad: records change history instead of explaining the current rule.

```python
# TICKET-123: We now use Decimal instead of float because the previous
# implementation caused precision problems during validation.
value = Decimal(raw_value)
```

Bad: repeats the code.

```python
# Increment the counter.
counter += 1
```

## Slice overview

A slice is a small, independently testable part of the implementation.

At a slice's main entry point, add a short docstring when its role is not
clear from the code. Expand the existing summary instead of adding a
second explanation.

Explain its purpose, input, result, and important failure behavior.
Include only details that the reader cannot see from the signature.
Do not repeat this overview in every helper function.

Keep the main flow readable through clear names and explicit steps.
Do not use comments to compensate for unclear code.

Example of an entry-point docstring:

```python
"""Build an unpublished candidate from extracted records for one date window.

Validate the saved files before upload.
Keep available evidence if preparation fails.
"""
```

## Before submitting

Review the diff and confirm that:

- The main flow is clear without reading every helper function.
- Comments explain reasons or rules, not obvious syntax.
- Comments and docstrings match the implementation.
- Relevant tests cover the changed behavior. State which tests ran and which did not.

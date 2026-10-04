# Contributing to Trinity

Write code that a human can understand, review, and debug.
These rules apply to human-written and AI-generated code.

Write for a backend developer who is learning Python and this project.
The reader should be able to follow a slice from its source files without
needing the chat history. Prefer enough explanation to teach the flow over
the smallest possible number of comments.

## Code comments

### Style

Use ASD-STE100 as the writing guide for all comments and docstrings.
This includes slice overviews, helper explanations, and test comments.
These project rules use its principles; they do not claim formal compliance.

- Write short sentences. Express one idea per sentence.
- Use active voice. Name the code or caller that performs the action. Use the imperative for instructions: "Return None when...".
- Use simple, direct words. Use the same term for the same thing. Avoid idioms and vague references such as "handle this".
- Explain an unfamiliar technical term at its first relevant use. Preserve exact code identifiers, API names, units, and error codes.
- State conditions and results explicitly. For example: "If capacity is negative, raise NormalizationError."

Short sentences do not mean fewer explanations. Use several short sentences
when a rule needs a reason, an example, and a failure result. Apply this
style to every explanation required below.

### When to comment

Add comments throughout the meaningful steps of a slice. Explain:

- The purpose of each logical block and how it moves data toward the result.
- Business rules, limits, and edge cases, including why a value is rejected or preserved.
- Python or library behavior that a developer new to the stack may not know.
- Ownership and side effects: what is copied, changed, retained, read, or written.
- Workarounds and the reason they exist.

Avoid comments that only repeat an assignment, loop, or function name.
A clear name does not replace an explanation of the rule behind the code.
Do not add a comment to every line or record change history such as
"Now we use X instead of Y". Git history records changes.

Use docstrings to explain a function's role. Use nearby block comments to
explain the steps inside it. Do not copy the same explanation into both.

### Rules

- Apply the ASD-STE100 guidance above. Do not restrict explanations to one line. Use a short paragraph when the reason, example, or consequence needs it.
- Put a comment before each meaningful transformation, validation group, or external operation whose purpose needs explanation. Explain the goal and rule, not each statement.
- Explain unfamiliar syntax where it matters, such as a regular expression, decimal context, dataclass option, or read-only mapping. State its effect in this code, not a general language tutorial.
- Give public API members a summary docstring. For functions, explain input meaning, result, and important failures. Add detail beyond the summary when needed; type annotations alone do not explain behavior.
- Give private helpers a short docstring when their role or rule is not clear to the intended reader. Explain what they accept, preserve, or reject instead of only rephrasing their name.
- Include a small example for difficult rules. For a numeric limit, show an accepted value and a rejected value, with the reason. Use synthetic values, never secrets or private payloads.
- In tests, explain why unusual inputs, mocks, or precision settings are needed and which failure they expose. Do not narrate every assertion.
- Do not put ticket numbers or ticket references in comments. Put them in commit messages.
- Do not add author names, author tags, dates, or history blocks.
- Describe current behavior. Do not describe planned behavior as implemented.
- When you change code, update or delete comments that no longer match it.

### Examples

Good: explains a non-obvious reason.

```python
# Parse the source string directly. A float can lose decimal precision.
value = Decimal(raw_value)
```

Good: explains a limit with an accepted and a rejected value.

```python
# The storage type allows six decimal places without rounding.
# "863.4000000" fits because the extra fractional zeros add no value.
# "863.4000001" fails because removing its seventh digit changes the value.
if len(fractional.rstrip("0")) > 6:
    raise NormalizationError("decimal_scale", field_name)
```

Good: explains a Python option and its practical limit.

```python
# frozen=True prevents replacing the fields after construction.
# It does not prevent changes to entries inside the values dictionary.
@dataclass(frozen=True)
class NormalizedRow:
    """Hold parsed analytical values and observation codes for one row."""

    values: dict[str, ParsedValue]
    diagnostic_codes: tuple[str, ...]
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

At a slice's main entry point, include an overview docstring. Expand the
existing summary instead of adding a second explanation elsewhere.

Explain its purpose, where the input comes from, the main processing steps,
and what the caller receives. State important failure behavior and who
retains the input or evidence after failure. Make the boundary clear:
which work this entry point completes and which checks it does not perform.
Do not repeat the full overview in every helper function.

Keep the main flow readable through clear names and explicit steps.
Add local comments so the reader can follow those steps without repeatedly
jumping into helpers. Clear code and explanatory comments work together.

Example of an entry-point docstring:

```python
"""Parse one sanitized EIA row into analytical values and observation codes.

The connector supplies the sanitized row. Parse its date and identifiers.
Check the units. Convert measurement text to exact Decimal values.
Return only analytical columns, with codes for missing optional values.

Raise NormalizationError if a required value is invalid or cannot fit
the storage type without rounding. Leave the input unchanged so the caller
can retain it as evidence on success or failure.

This function does not write Parquet files or decide publication readiness.
"""
```

## Before submitting

Review the diff and confirm that:

- A developer learning Python can trace input, processing, result, and failure from the entry point and nearby comments.
- Meaningful blocks and unfamiliar constructs have enough explanation; a summary docstring alone is not sufficient for a complex flow.
- Difficult rules have concrete examples, and comments explain reasons or consequences instead of only repeating statements.
- Comments and docstrings match the implementation and follow the ASD-STE100 guidance above. Check for short sentences, active voice, consistent terms, and exact identifiers.
- Relevant tests cover the changed behavior. State which tests ran and which did not.

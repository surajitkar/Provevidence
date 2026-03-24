# Copilot Instructions

## Before writing any code for a task

Run this command from the repo root:

```bash
python scripts/get_variant.py --task "<ticket-ref-or-description>"
```

Examples:
```bash
python scripts/get_variant.py --task "PROJ-142"
python scripts/get_variant.py --task "LIN-55"
python scripts/get_variant.py --task "add discount code to checkout"
```

Read the instructions it prints and follow them when writing the code.
The instructions tell you the exact PR format, diff size limit, and
test requirements for this task.

## When opening the pull request

Include the tag printed by `get_variant.py` at the end of your PR body.
It looks like:

```
[autoresearch:task=PROJ-142:variant=compact_diff_v1]
```

This tag is required for experiment tracking. Without it the PR cannot
be attributed to the correct variant and the experiment data is lost.

## Before raising any PR |  IMPORTANT 

Follow every rule it prints. Include the tag in the PR body.
This is mandatory for all tasks in this repo.

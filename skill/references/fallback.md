# Fallback: Manual Variant Assignment

Use this when `scripts/get_variant.py` is not available.

## Assign a variant manually

```python
import hashlib
task     = "PROJ-142"   # your task ref or description slug
variants = ["baseline", "compact_diff_v1"]   # from experiment.yaml
idx      = int(hashlib.md5(task.lower().encode()).hexdigest(), 16) % len(variants)
print(variants[idx])
```

## Build the tag manually

```
[autoresearch:task=PROJ-142:variant=baseline]
```

## Read the instructions manually

Open the correct file from `.repo-autoresearch/variants/`:

- `baseline`        → `variants/baseline.md`
- `compact_diff_v1` → `variants/compact-diff.md`

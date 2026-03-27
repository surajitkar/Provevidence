"""
experiment_metrics.py — evaluation config normalization, guardrails, and safe formula eval.
Used by autoresearch.evaluate_experiment().
"""

from __future__ import annotations

import ast
import re
from typing import Any

# Built-in metrics recorded by autoresearch.py (no formula / external required in YAML).
DEFAULT_METRICS: dict[str, dict[str, Any]] = {
    "review_round_trips": {"direction": "lower_is_better"},
    "first_pass_ci_success": {"direction": "higher_is_better"},
    "time_to_merge_hours": {"direction": "lower_is_better"},
}

GUARD_RE = re.compile(
    r"^\s*(\w+)\s*(>=|<=|>|<)\s*baseline\s*([+-])\s*([\d.]+)\s*$",
    re.IGNORECASE,
)


def uses_new_evaluation(experiment: dict) -> bool:
    ev = experiment.get("evaluation")
    return isinstance(ev, dict) and bool(ev.get("metric"))


def normalize_experiment(experiment: dict | None) -> dict:
    """Attach merged metrics for new-style YAML; mark legacy otherwise."""
    if not experiment:
        return {}
    exp = dict(experiment)
    if uses_new_evaluation(exp):
        metrics = dict(exp.get("metrics") or {})
        for k, v in DEFAULT_METRICS.items():
            if k not in metrics:
                metrics[k] = dict(v)
        exp["metrics"] = metrics
        exp["_evaluation_style"] = "v2"
        return exp
    exp["_evaluation_style"] = "legacy"
    return exp


def promotion_threshold_pct(experiment: dict) -> float:
    exp = normalize_experiment(experiment)
    if exp.get("_evaluation_style") == "v2":
        return float((exp.get("evaluation") or {}).get("min_improvement_pct", 15))
    return float(experiment.get("promotion_threshold_pct", 15))


def primary_metric_label(experiment: dict) -> str:
    exp = normalize_experiment(experiment)
    if exp.get("_evaluation_style") == "v2":
        return str((exp.get("evaluation") or {}).get("metric", "metric"))
    return str(experiment.get("primary_metric", "review_round_trips"))


def evaluation_min_prs(experiment: dict) -> int:
    """Prefer evaluation.min_prs; else evaluation_window.value; default 20."""
    exp = normalize_experiment(experiment)
    ev = exp.get("evaluation") or {}
    if exp.get("_evaluation_style") == "v2" and ev.get("min_prs") is not None:
        return int(ev["min_prs"])
    w = experiment.get("evaluation_window") or {}
    return int(w.get("value", 20))


def report_metric_section(decision: dict, experiment: dict) -> list[str]:
    """Extra markdown lines listing all configured metrics (v2 only)."""
    exp = normalize_experiment(experiment)
    if exp.get("_evaluation_style") != "v2":
        return []
    metrics = exp.get("metrics") or {}
    primary = (exp.get("evaluation") or {}).get("metric")
    lines = ["**All metrics (avg):**"]
    for name in metrics:
        bs = decision["baseline_stats"].get(f"avg_{name}")
        cs = decision["challenger_stats"].get(f"avg_{name}")
        if bs is None and cs is None:
            continue
        tag = " *(primary)*" if name == primary else ""
        b_s = f"{bs:.4f}" if bs is not None else "—"
        c_s = f"{cs:.4f}" if cs is not None else "—"
        lines.append(f"- `{name}`{tag}: baseline {b_s} → challenger {c_s}")
    return lines if len(lines) > 1 else []


def improvement_pct(
    base_avg: float,
    chal_avg: float,
    direction: str,
) -> float:
    """Improvement toward "better" as a percentage, positive = challenger improved."""
    if base_avg == 0:
        return 0.0
    if direction == "lower_is_better":
        return (base_avg - chal_avg) / base_avg * 100
    if direction == "higher_is_better":
        return (chal_avg - base_avg) / base_avg * 100
    return 0.0


def parse_guardrail_expr(line: str) -> tuple[str, str, float] | None:
    """
    Parse 'field >= baseline - 0.03' or 'field <= baseline + 10'.
    Returns (field, op, delta) where rhs = baseline_avg + delta.
    """
    m = GUARD_RE.match(line.strip())
    if not m:
        return None
    field, op, sign, num = m.group(1), m.group(2), m.group(3), float(m.group(4))
    delta = num if sign == "+" else -num
    return field, op, delta


def guardrail_passes(
    chal_avg: float,
    base_avg: float,
    op: str,
    delta: float,
) -> bool:
    rhs = base_avg + delta
    if op == ">=":
        return chal_avg >= rhs
    if op == "<=":
        return chal_avg <= rhs
    if op == ">":
        return chal_avg > rhs
    if op == "<":
        return chal_avg < rhs
    return False


def _eval_formula_node(node: ast.AST, run: dict[str, Any]) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("invalid constant in formula")
    if isinstance(node, ast.Num):  # py<3.8 compat
        return float(node.n)
    if isinstance(node, ast.Name):
        v = run.get(node.id)
        if v is None:
            return 0.0
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        return float(v)
    if isinstance(node, ast.BinOp):
        left = _eval_formula_node(node.left, run)
        right = _eval_formula_node(node.right, run)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right if right != 0 else 0.0
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_formula_node(node.operand, run)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            fn = node.func.id
            args = [_eval_formula_node(a, run) for a in node.args]
            if fn == "max":
                return max(args) if args else 0.0
            if fn == "min":
                return min(args) if args else 0.0
            if fn == "abs":
                return abs(args[0]) if args else 0.0
    raise ValueError(f"unsupported formula node: {type(node).__name__}")


def safe_eval_formula(formula: str, run: dict[str, Any]) -> float | None:
    """Evaluate a metric formula against one PR run (safe subset, no exec)."""
    try:
        tree = ast.parse(formula.strip(), mode="eval")
        return _eval_formula_node(tree.body, run)
    except Exception:
        return None


def metric_value_for_run(
    metric_name: str,
    metric_def: dict[str, Any],
    run: dict[str, Any],
) -> float | None:
    if metric_def.get("source") == "external":
        v = run.get(metric_name)
        if v is None:
            return None
        return float(v) if not isinstance(v, bool) else (1.0 if v else 0.0)
    if metric_def.get("formula"):
        return safe_eval_formula(metric_def["formula"], run)
    v = run.get(metric_name)
    if v is None:
        return None
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    return float(v)


def average_metric_for_runs(
    runs: list[dict],
    metric_name: str,
    metric_def: dict[str, Any],
    metrics: dict[str, dict],
) -> tuple[float, int]:
    """Sum of values / count of runs with a value."""
    vals = []
    for r in runs:
        v = metric_value_for_run(metric_name, metric_def, r)
        if v is not None:
            vals.append(v)
    if not vals:
        return 0.0, 0
    return sum(vals) / len(vals), len(vals)


def stats_bundle(
    runs: list[dict],
    metrics: dict[str, dict],
) -> dict[str, Any]:
    """Per-variant stats: avg per metric + ci_pass_rate."""
    out: dict[str, Any] = {"count": len(runs)}
    ci = [r.get("first_pass_ci_success", False) for r in runs]
    out["ci_pass_rate"] = sum(bool(x) for x in ci) / len(ci) if ci else 0.0
    for name, mdef in metrics.items():
        if mdef.get("source") == "external" and name not in str(mdef.get("formula", "")):
            pass
        avg, n = average_metric_for_runs(runs, name, mdef, metrics)
        out[f"avg_{name}"] = avg
        out[f"n_{name}"] = n
    return out


def legacy_evaluate_experiment(state: dict, experiment: dict):
    """Original behavior when new-style evaluation: block is absent."""
    variants = experiment.get("variants", [])
    if len(variants) < 2:
        return None
    min_prs = experiment.get("evaluation_window", {}).get("value", 20)
    primary = experiment.get("primary_metric", "review_round_trips")
    threshold = experiment.get("promotion_threshold_pct", 15)

    by_variant: dict[str, list] = {}
    for run in state.get("pr_runs", {}).values():
        by_variant.setdefault(run.get("variant_id"), []).append(run)

    baseline_id = variants[0]["id"]
    baseline_runs = by_variant.get(baseline_id, [])
    if len(baseline_runs) < min_prs:
        print(f"  Not enough data: baseline has {len(baseline_runs)}/{min_prs} PRs")
        return None

    def stats(runs):
        metric = [r.get(primary, 0) for r in runs if r.get(primary) is not None]
        ci = [r.get("first_pass_ci_success", False) for r in runs]
        return {
            "count": len(runs),
            "avg_metric": sum(metric) / len(metric) if metric else 0,
            "ci_pass_rate": sum(bool(x) for x in ci) / len(ci) if ci else 0,
        }

    base = stats(baseline_runs)
    decisions = []
    for v in variants[1:]:
        vid = v["id"]
        runs = by_variant.get(vid, [])
        if not runs:
            continue
        chal = stats(runs)
        improv = (
            (base["avg_metric"] - chal["avg_metric"]) / base["avg_metric"] * 100
            if base["avg_metric"] > 0
            else 0
        )
        ci_drop = base["ci_pass_rate"] - chal["ci_pass_rate"]
        guardrail_ok = ci_drop <= 0.03
        decisions.append(
            {
                "variant_id": vid,
                "baseline_id": baseline_id,
                "improvement_pct": round(improv, 1),
                "promote": improv >= threshold and guardrail_ok,
                "guardrail_ok": guardrail_ok,
                "guardrail_notes": (
                    [f"CI pass rate dropped {ci_drop:.1%} (limit: 3%)"]
                    if not guardrail_ok
                    else []
                ),
                "baseline_stats": base,
                "challenger_stats": chal,
                "primary_metric": primary,
            }
        )
    return decisions or None


def evaluate_experiment_v2(state: dict, experiment: dict):
    """New-style evaluation with metrics: + evaluation: blocks."""
    exp = normalize_experiment(experiment)
    metrics = exp.get("metrics") or {}
    ev = exp.get("evaluation") or {}
    min_prs = evaluation_min_prs(experiment)
    primary = ev.get("metric")
    threshold = float(ev.get("min_improvement_pct", 15))
    guardrails = ev.get("guardrails") or []

    if not primary or primary not in metrics:
        print("  evaluation.metric must be a key in metrics:")
        return None

    variants = exp.get("variants", [])
    if len(variants) < 2:
        return None

    by_variant: dict[str, list] = {}
    for run in state.get("pr_runs", {}).values():
        by_variant.setdefault(run.get("variant_id"), []).append(run)

    baseline_id = variants[0]["id"]
    baseline_runs = by_variant.get(baseline_id, [])
    if len(baseline_runs) < min_prs:
        print(f"  Not enough data: baseline has {len(baseline_runs)}/{min_prs} PRs")
        return None

    def stats_for(runs):
        return stats_bundle(runs, metrics)

    base = stats_for(baseline_runs)
    base["avg_metric"] = base.get(f"avg_{primary}", 0.0)
    decisions = []
    direction = metrics[primary].get("direction", "lower_is_better")

    for v in variants[1:]:
        vid = v["id"]
        runs = by_variant.get(vid, [])
        if not runs:
            continue
        chal = stats_for(runs)
        chal["avg_metric"] = chal.get(f"avg_{primary}", 0.0)
        base_avg = base["avg_metric"]
        chal_avg = chal["avg_metric"]
        improv = improvement_pct(base_avg, chal_avg, direction)

        notes = []
        ok_all = True
        for line in guardrails:
            parsed = parse_guardrail_expr(line)
            if not parsed:
                notes.append(f"unparseable guardrail: {line}")
                ok_all = False
                continue
            g_field, op, delta = parsed
            if g_field not in metrics:
                notes.append(f"unknown metric in guardrail: {g_field}")
                ok_all = False
                continue
            b_n = int(base.get(f"n_{g_field}", 0))
            c_n = int(chal.get(f"n_{g_field}", 0))
            if b_n == 0 or c_n == 0:
                notes.append(
                    f"{g_field}: insufficient samples for guardrail "
                    f"(baseline n={b_n}, challenger n={c_n})"
                )
                ok_all = False
                continue
            bga = base.get(f"avg_{g_field}", 0.0)
            cha = chal.get(f"avg_{g_field}", 0.0)
            if not guardrail_passes(cha, bga, op, delta):
                ok_all = False
                notes.append(
                    f"{g_field}: challenger {cha:.4f} vs baseline {bga:.4f} "
                    f"(need {op} baseline {delta:+.4f})"
                )

        promote = improv >= threshold and ok_all
        decisions.append(
            {
                "variant_id": vid,
                "baseline_id": baseline_id,
                "improvement_pct": round(improv, 1),
                "promote": promote,
                "guardrail_ok": ok_all,
                "guardrail_notes": notes,
                "baseline_stats": base,
                "challenger_stats": chal,
                "primary_metric": primary,
            }
        )
    return decisions or None


def evaluate_experiment(state: dict, experiment: dict):
    """Dispatch to new or legacy evaluation."""
    if uses_new_evaluation(experiment):
        return evaluate_experiment_v2(state, experiment)
    return legacy_evaluate_experiment(state, experiment)

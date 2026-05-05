#!/usr/bin/env python3
"""Static readiness audit for Python OR-Tools projects.

This is intentionally heuristic. It flags files that deserve engineering review;
it does not prove correctness.
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
from dataclasses import dataclass

ORTOOLS_PATTERNS = [
    "ortools",
    "cp_model",
    "CpSolver",
    "RoutingModel",
    "pywraplp",
    "math_opt",
]

LIMIT_PATTERNS = [
    "max_time_in_seconds",
    "SetTimeLimit",
    "set_time_limit",
    "time_limit",
    "solution_limit",
]

QUALITY_PATTERNS = [
    "relative_gap_limit",
    "absolute_gap_limit",
    "mip_gap",
    "limits/gap",
    "best_objective_bound",
]

STATUS_PATTERNS = [
    "OPTIMAL",
    "FEASIBLE",
    "INFEASIBLE",
    "MODEL_INVALID",
    "UNKNOWN",
    "StatusName",
    "status_name",
]

@dataclass
class FileAudit:
    path: pathlib.Path
    has_ortools: bool
    has_solve: bool
    has_limit: bool
    has_quality: bool
    has_status_handling: bool
    solve_functions: list[str]
    build_functions: list[str]
    nested_loop_count: int
    line_count: int


def iter_py_files(root: pathlib.Path):
    if root.is_file() and root.suffix == ".py":
        yield root
    elif root.is_dir():
        skip = {".git", ".venv", "venv", "node_modules", "__pycache__"}
        for path in root.rglob("*.py"):
            if not any(part in skip for part in path.parts):
                yield path


def contains_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


def audit_file(path: pathlib.Path) -> FileAudit:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])

    solve_functions: list[str] = []
    build_functions: list[str] = []
    nested_loop_count = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name.lower()
            body = ast.get_source_segment(text, node) or ""
            if "solve" in name or re.search(r"\.solve\(|\.Solve\(|solve\(", body):
                solve_functions.append(node.name)
            if any(token in name for token in ("build", "model", "create")):
                build_functions.append(node.name)
        if isinstance(node, ast.For):
            if any(isinstance(child, ast.For) for child in ast.walk(node) if child is not node):
                nested_loop_count += 1

    return FileAudit(
        path=path,
        has_ortools=contains_any(text, ORTOOLS_PATTERNS),
        has_solve=bool(re.search(r"\.solve\(|\.Solve\(|solve\(", text)),
        has_limit=contains_any(text, LIMIT_PATTERNS),
        has_quality=contains_any(text, QUALITY_PATTERNS),
        has_status_handling=contains_any(text, STATUS_PATTERNS),
        solve_functions=solve_functions,
        build_functions=build_functions,
        nested_loop_count=nested_loop_count,
        line_count=text.count("\n") + 1,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Python OR-Tools code for production-readiness heuristics.")
    parser.add_argument("path", type=pathlib.Path, help="Python file or repository root")
    args = parser.parse_args()

    audits = [audit_file(p) for p in iter_py_files(args.path)]
    ort_files = [a for a in audits if a.has_ortools]

    print(f"OR-Tools static audit: {args.path}")
    print(f"Python files scanned: {len(audits)}")
    print(f"OR-Tools files found: {len(ort_files)}")

    if not ort_files:
        print("No OR-Tools usage detected.")
        return 0

    print("\nFindings:")
    for a in ort_files:
        rel = a.path.relative_to(args.path) if args.path.is_dir() else a.path
        flags: list[str] = []
        if a.has_solve and not a.has_limit:
            flags.append("MISSING_SOLVE_LIMIT")
        if a.has_solve and not a.has_status_handling:
            flags.append("WEAK_STATUS_HANDLING")
        if a.has_solve and not a.has_quality:
            flags.append("NO_GAP_OR_BOUND_POLICY")
        if a.has_solve and a.build_functions and any(fn in a.build_functions for fn in a.solve_functions):
            flags.append("BUILD_SOLVE_MAY_BE_COUPLED")
        if a.nested_loop_count >= 3:
            flags.append(f"MANY_NESTED_LOOPS={a.nested_loop_count}")
        if not flags:
            flags.append("OK_REVIEW_MANUALLY")
        print(f"- {rel}: {', '.join(flags)}")
        if a.solve_functions:
            print(f"  solve-like functions: {', '.join(a.solve_functions[:8])}")
        if a.build_functions:
            print(f"  build/model-like functions: {', '.join(a.build_functions[:8])}")

    print("\nRecommended next checks:")
    print("1. Confirm every solve path has a hard time limit and explicit status branch.")
    print("2. Confirm FEASIBLE incumbents are accepted/rejected by a documented gap policy.")
    print("3. Confirm model generation is isolated from API/database side effects.")
    print("4. Add tiny feasible and infeasible fixtures if missing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

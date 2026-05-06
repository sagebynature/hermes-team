---
name: ortools-optimization-lifecycle
description: Use when designing, implementing, reviewing, debugging, or productionizing Google OR-Tools optimization models. Covers solver selection across CP-SAT, Routing, GLOP/PDLP, SCIP/MPSolver, and MathOpt; mathematical formulation before code; production solve limits and solution-quality controls; scalable model generation; infeasibility debugging; and OR-Tools repository/code audits such as soon-optimizer.
---

# OR-Tools Optimization Lifecycle

## Core workflow

1. **Classify the problem before coding.** Identify variables, domains, objective, hard constraints, soft constraints, data scale, and required optimality. Use `references/engine-selection.md` for solver choice.
2. **Write the math contract.** Produce a short formulation with sets, parameters, decision variables, objective, constraints, units, and acceptance tolerances. Use `references/formulation-workflow.md`.
3. **Separate model build from solve.** Build deterministic model-generation code that emits a model/proto plus metadata; run solve code with explicit limits, logging, and status handling. Use `references/production-patterns.md`.
4. **Optimize model generation.** Prefer indexed collections, sparse data structures, precomputed eligibility sets, and generator expressions over nested scans that create unnecessary variables or constraints.
5. **Verify result semantics.** Treat `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `MODEL_INVALID`, and `UNKNOWN` differently. Never assume timeout means failure if a feasible incumbent exists.
6. **Debug infeasibility systematically.** Start with data validation and minimal reproductions, then isolate constraint families and use assumptions/IIS when the selected solver supports it. Use `references/infeasibility-debugging.md`.
7. **Review production readiness.** Run targeted tests plus `scripts/ortools_static_audit.py <repo-or-file>` to flag missing limits, weak status handling, and coupled build/solve logic.

## Solver quick chooser

- **Scheduling, rostering, assignment with many Booleans, reified logic, no-overlap, cumulative resources (e.g. Job-Shop):** CP-SAT.
- **Vehicle routes, TSP/VRP, capacity/time windows, pickups-deliveries, optional dropped visits:** Routing library.
- **Continuous linear programs:** GLOP first; PDLP for very large/approximate LPs; MathOpt when solver interchange matters.
- **Mixed-integer linear models with general integer quantities and LP-like structure (e.g. Bin Packing, Knapsack):** SCIP/MPSolver or MathOpt; compare with CP-SAT when variables are mostly Boolean.
- **Network flow / assignment primitives:** use OR-Tools specialized graph/assignment APIs before hand-building a general MIP.

## Rapid Implementation Reference

### CP-SAT Basic Pattern (Integer Logic)
```python
from ortools.sat.python import cp_model

model = cp_model.CpModel()
# Variables: NewIntVar(lower, upper, name)
x = model.NewIntVar(0, 10, 'x')
y = model.NewIntVar(0, 10, 'y')

model.Add(x + y <= 8)
model.Maximize(x + 2 * y)

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60.0 # Production requirement
status = solver.Solve(model)

if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
    print(f'x = {solver.Value(x)}, y = {solver.Value(y)}')
```

### Critical Implementation Rules

- **Scale your Floats**: CP-SAT is strictly integer. Convert `1.25` to `125` and adjust coefficients accordingly.
- **Conditional Constraints**: Do NOT use Python `if` statements inside the model. Use `OnlyEnforceIf` with Boolean variables.
  - `b = model.NewBoolVar('b')`
  - `model.Add(x > 5).OnlyEnforceIf(b)`
- **Index Variables**: To use a variable as an index in an array, use `model.AddElement`.
- **Symmetry Breaking**: Force an ordering (e.g., `model.Add(x_A <= x_B)`) for identical items to prevent the solver from exploring redundant permutations.

## Production defaults to enforce

- Always set wall-clock limits (`max_time_in_seconds`, `set_time_limit`, or routing `time_limit`) and record the configured value in solve metadata.
- Set quality gates appropriate to the solver: CP-SAT `relative_gap_limit`/`absolute_gap_limit`, MIP relative MIP gap parameters, or routing search strategy/time budget plus incumbent acceptance.
- Return the best feasible solution with objective, bound, gap, status, runtime, parameters, model statistics, and validation checks.
- Keep hard constraints hard; model business preferences as explicit soft penalties with named terms and weights.
- Serialize or snapshot inputs and model metadata so production failures can be reproduced offline.

## Reference project workflow: soon-optimizer

When asked to work on `soon-optimizer` or a similar repo:

1. Clone or inspect the local repo. If GitHub returns 404/private, report access blocker and still produce a readiness checklist.
2. Locate OR-Tools usage: `grep -R \"ortools\\|cp_model\\|RoutingModel\\|pywraplp\\|math_opt\"`.
3. Run `python3 skills/ortools-optimization-lifecycle/scripts/ortools_static_audit.py <repo>`.
4. Map current code to the lifecycle: formulation docs, model builder, solver runner, status handling, limits, logging, infeasibility tooling, and tests.
5. Recommend the smallest behavior-preserving changes first: explicit limits, feasible incumbent handling, status-aware API response, data validation, and one regression fixture.

## Evidence and citations

Use official OR-Tools docs when making solver or API claims. Start with:

- Google OR-Tools overview: https://developers.google.com/optimization
- CP-SAT and solver limits: https://developers.google.com/optimization/cp/cp_solver and https://developers.google.com/optimization/cp/cp_tasks
- Routing and routing options: https://developers.google.com/optimization/routing and https://developers.google.com/optimization/routing/routing_options
- LP/MIP/MathOpt: https://developers.google.com/optimization/lp/lp_example, https://developers.google.com/optimization/lp/lp_advanced, https://developers.google.com/optimization/mip, https://developers.google.com/optimization/math_opt

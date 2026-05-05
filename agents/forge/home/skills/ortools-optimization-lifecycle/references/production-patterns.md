# Production OR-Tools patterns

## Architecture boundary

Use a four-part boundary:

1. **Data preparation**: validate schema, normalize units/timezones, precompute eligibility, reject impossible requests early.
2. **Model generation**: deterministic pure function from canonical data to model/proto plus variable registry.
3. **Solve execution**: configurable worker that sets limits, logs parameters, runs the solver, and captures response metadata.
4. **Solution extraction/validation**: convert solver values to domain output and independently verify hard constraints.

Never let API handlers construct variables directly. Never let extraction code add constraints.

## Execution control examples

CP-SAT Python:

```python
from ortools.sat.python import cp_model

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = config.time_limit_seconds
solver.parameters.relative_gap_limit = config.relative_gap_limit  # e.g. 0.01
solver.parameters.num_search_workers = config.workers
# Optional when supported by installed OR-Tools version:
# solver.parameters.max_memory_in_mb = config.max_memory_mb
status = solver.solve(model)

if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    return incumbent_solution(status, solver.objective_value, solver.best_objective_bound)
if status == cp_model.INFEASIBLE:
    raise InfeasibleModel(...)
if status == cp_model.MODEL_INVALID:
    raise InvalidModel(...)
raise NoSolutionFound(status=solver.status_name(status))
```

MPSolver / SCIP / GLOP:

```python
solver.SetTimeLimit(config.time_limit_ms)
# For MIP gap, use solver-specific parameters or MathOpt parameters when available.
# Example for SCIP-style parameter strings; verify syntax against installed solver:
solver.SetSolverSpecificParametersAsString(f"limits/gap = {config.relative_gap_limit}")
status = solver.Solve()
```

Routing:

```python
search_parameters = pywrapcp.DefaultRoutingSearchParameters()
search_parameters.time_limit.seconds = config.time_limit_seconds
search_parameters.solution_limit = config.solution_limit
search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
assignment = routing.SolveWithParameters(search_parameters)
```

## Feasible sub-optimal policy

Define up front:

- Accept `OPTIMAL`: proven optimum.
- Accept `FEASIBLE`: incumbent found but not proven optimal; require `objective_value`, `best_objective_bound`, relative/absolute gap if available, and business validation pass.
- Reject/queue retry `UNKNOWN` unless a solution callback or API exposes a valid incumbent. Make this explicit per solver.
- In routing, expect good-but-not-proven-optimal solutions on large VRPs; use search time, strategy, and validation rather than demanding exact proof.

## Scalable model generation

- Precompute `eligible_pairs = [(i, j) ...]`; create variables only for eligible pairs.
- Build constraints from indexes (`by_item`, `by_resource`, `by_time`) rather than scanning every variable repeatedly.
- Avoid callback functions that do expensive database or network work; routing transit callbacks should index precomputed matrices.
- Use generator expressions for linear sums, but materialize lists only when reused.
- Keep variable names stable but not huge. Avoid embedding large JSON/user text in names.
- Log counts: variables, constraints, objective terms, solve workers, time limit, gap limit, input cardinalities.

## Testing and observability

- Unit-test data validators and objective term builders separately.
- Snapshot tiny model outputs or solution summaries, not full opaque solver internals.
- Include one infeasible fixture and verify the diagnostic path.
- Include a scale smoke test that asserts model generation time and counts stay within expected bounds.
- Emit structured solve metadata: status, status_name, objective, bound, gap, wall_time, deterministic_time if available, conflicts/branches for CP-SAT, parameters, input hash, model version.

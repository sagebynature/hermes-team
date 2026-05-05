# Infeasibility debugging methodology

## First response checklist

1. **Distinguish invalid from infeasible.** `MODEL_INVALID` means API/model construction error; `INFEASIBLE` means constraints have no common solution; `UNKNOWN` may be a limit/time issue.
2. **Validate raw data.** Check missing capacities, negative durations, timezone errors, duplicate IDs, impossible availabilities, and unit mismatches.
3. **Run a known-feasible baseline.** Remove soft constraints and optional preferences; keep only core assignment/capacity feasibility.
4. **Minimize the instance.** Binary-search rows/time periods/resources until the smallest failing dataset remains.
5. **Toggle constraint families.** Add constraints in named groups and identify the first family combination that fails.
6. **Add slacks for diagnosis only.** Convert suspected hard constraints to soft constraints with high penalties; solve and inspect which slacks are nonzero.
7. **Use assumptions/IIS when available.** CP-SAT supports assumption literals for unsat-core style debugging; MathOpt documents IIS support for Gurobi only.

## CP-SAT assumption pattern

Use this only in diagnostic builds, not production solves:

```python
from ortools.sat.python import cp_model

model = cp_model.CpModel()
assumptions = {}

def guarded(name: str, add_constraint):
    guard = model.new_bool_var(f"assume::{name}")
    ct = add_constraint()
    ct.only_enforce_if(guard)
    model.add_assumption(guard)
    assumptions[guard.index] = name

# guarded("capacity_resource_A_day_1", lambda: model.add(load_a_d1 <= cap_a_d1))

solver = cp_model.CpSolver()
status = solver.solve(model)
if status == cp_model.INFEASIBLE:
    core = solver.sufficient_assumptions_for_infeasibility()
    print([assumptions.get(i, i) for i in core])
```

Verify method names against the installed OR-Tools version; APIs may be camelCase in older language bindings.

## Slack diagnosis pattern

For a suspect constraint `lhs <= rhs`, add nonnegative slack:

```python
slack = model.new_int_var(0, max_slack, "slack::capacity_A")
model.add(lhs <= rhs + slack)
penalties.append(weight * slack)
```

Then minimize the normal objective plus diagnostic penalties. A nonzero slack points to violated business rules or bad data.

## What to report

- Minimal failing input ID/hash.
- Solver, version, parameters, status, runtime.
- Constraint families enabled.
- Suspected conflicting constraints with business names.
- Whether infeasibility is due to data, formulation, or true business impossibility.
- Recommended product decision if business constraints conflict.

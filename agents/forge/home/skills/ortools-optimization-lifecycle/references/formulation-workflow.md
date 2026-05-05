# Mathematical formulation workflow

Produce this artifact before implementation. Keep it versioned with model code.

## Formulation template

```markdown
# Optimization formulation: <problem name>

## Business goal
One sentence: what operational decision this model makes and how success is measured.

## Sets / indices
- I: <items>, size |I| = n
- J: <resources>, size |J| = m
- T: <time periods>, granularity and timezone

## Parameters / data
- c[i,j]: cost or benefit, units, allowed range, default/missing handling
- a[i,j]: eligibility/compatibility indicator
- cap[j]: capacity, units

## Decision variables
- x[i,j] ∈ {0,1}: 1 iff item i is assigned to resource j
- y[...] ∈ Z or R: define domain, units, and bounds

## Objective
Minimize/Maximize:
  primary term + soft penalty terms
List every term, weight, units, and rationale.

## Hard constraints
1. Assignment: ∑_j x[i,j] = 1 for all i ∈ I
2. Capacity: ∑_i demand[i] x[i,j] ≤ cap[j] for all j ∈ J
3. Eligibility: x[i,j] = 0 where a[i,j] = 0

## Soft constraints
- Preference violation p[...] with penalty weight w; explain why not hard.

## Solver choice
Chosen engine, fallback engine, and why alternatives were rejected.

## Runtime / quality contract
- Time limit:
- Gap tolerance / incumbent policy:
- Required status handling:
- Validation checks on returned solution:

## Test fixtures
- Tiny feasible case with hand-checked optimum.
- Infeasible case proving diagnostics work.
- Large smoke case proving model generation is bounded.
```

## Formulation rules

- Name every business rule as either hard, soft, or data validation. Do not hide business policy in anonymous coefficients.
- Use tight variable bounds. Avoid unconstrained/infinite domains unless mathematically required.
- Keep units explicit. Scale CP-SAT integer data once at the boundary, not throughout constraints.
- Prefer sparse variables over dense `I × J × T` grids when eligibility is sparse.
- Write objective terms separately in code so objective attribution can be logged.
- Create tiny fixtures where the optimum can be checked manually before scaling.

## Implementation mapping

Map math to code with stable names:

- `build_data()` validates and normalizes raw inputs.
- `build_model(data)` creates variables/constraints/objective only.
- `solve_model(model, config)` applies parameters and calls the solver.
- `extract_solution(model, solver, data)` converts solver values into domain objects.
- `validate_solution(solution, data)` checks hard constraints independently of OR-Tools.

# OR-Tools engine selection guide

Use this guide before writing model code.

## Decision tree

1. **Is the domain naturally a route/path over locations?**
   - Use the Routing library for TSP/VRP, capacities, time windows, pickups/deliveries, dimensions, resource constraints, and optional dropped visits.
   - Avoid encoding VRP as a generic MIP unless the routing API cannot express core constraints.

2. **Are most decisions Boolean/integer with logical constraints?**
   - Use CP-SAT for scheduling, assignment, rostering, sequencing, no-overlap/cumulative resources, implications, allowed assignments, and objective penalties over discrete choices.
   - CP-SAT requires integer coefficients/domains; scale non-integer data deliberately and record units.

3. **Is it continuous and linear?**
   - Use GLOP first for standard LPs.
   - Try dual simplex if primal simplex is slow.
   - Use PDLP when the LP is huge and approximate solutions are acceptable.
   - Use MathOpt when you need solver-independent modeling, remote solving, or advanced solve metadata.

4. **Is it an LP plus integer quantities?**
   - Use SCIP/MPSolver or MathOpt for standard MIPs with arbitrary integer variables.
   - Compare with CP-SAT when variables are mostly Boolean or constraints are combinatorial/logical.

5. **Is it a pure assignment/flow/packing primitive?**
   - Prefer specialized OR-Tools APIs (linear sum assignment, min-cost flow, max flow, knapsack/bin packing examples) before generic models.

## Selection checklist

Capture these in the design note:

- Decision variables: continuous, integer, Boolean, interval, route index.
- Constraint shape: linear, logical, scheduling, routing dimension, graph flow.
- Scale: number of variables, constraints, vehicles/nodes, time periods, candidate assignments.
- Optimality requirement: proof required, feasible enough, bounded gap, or heuristic route quality.
- Runtime budget: interactive, batch, overnight, remote worker.
- Licensing constraints: open-source only vs commercial solver allowed.
- Numerical risk: coefficient ranges, units, tolerances, scaling.

## Official-doc anchors

- OR-Tools covers vehicle routing, flows, integer/linear programming, and constraint programming, with solvers including GLOP, SCIP, GLPK, CP-SAT, and commercial backends.
- Google describes CP as feasibility-focused over constraints/variables and calls CP-SAT the primary CP solver; it also notes linear objective/linear constraints should consider MPSolver, while routing is typically best in the routing library.
- Google’s MIP guide says there is no ironclad MIP-vs-CP-SAT rule; MIP solvers fit LP-like models with integer variables, while CP-SAT often fits mostly Boolean models.
- Google’s advanced LP guide recommends trying GLOP first, commercial solvers if licensed, then PDLP for very large/approximate LPs.
- MathOpt separates modeling from solving and supports multiple solvers including GLOP, PDLP, CP-SAT, SCIP, GLPK, Gurobi, Xpress, and HiGHS.

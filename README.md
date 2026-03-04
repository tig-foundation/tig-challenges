# tig-challenges

Suite of optimization and algorithmic challenges featured in **The Innovation Game (TIG)**, collated for evaluating and comparing **AI-driven algorithm discovery** methods.

This repo provides a unified CLI and data formats so you can generate instances, run solvers, and evaluate solutions across multiple challenge domains. It is designed to integrate with frameworks like [SkyDiscover](https://github.com/skydiscover-ai/skydiscover), [CodeEvolve](https://github.com/inter-co/science-codeevolve), and [OpenEvolve](https://github.com/codelion/openevolve): the code under evolution is `src/<challenge>/algorithm.rs`, which you can replace or evolve (e.g. via LLM-generated code) while using this repo for instance generation and evaluation.

---

## Challenges

- **[knapsack](src/knapsack/README.md)** — Select items to maximize value under a weight constraint, with pairwise interaction values (quadratic knapsack / team formation).
- **[job_scheduling](src/job_scheduling/README.md)** — Schedule operations on eligible machines to minimize makespan (Flexible Job Shop).
- **[satisfiability](src/satisfiability/README.md)** — Determine whether a Boolean formula (e.g. 3-SAT) has a satisfying truth assignment.
- **[vehicle_routing](src/vehicle_routing/README.md)** — Route a fleet of vehicles from a depot to serve customers with time windows and capacity constraints (VRPTW).

---

## CLI Usage

```bash
./tig-challenges <challenge> <mode> [args...]
```

- **`<challenge>`** — One of: `knapsack`, `job_scheduling`, `satisfiability`, `vehicle_routing`.
- **`<mode>`** — One of: `generate`, `solve`, `evaluate`.

### Mode: `generate`

Generate problem instances for a given track.

```bash
./tig-challenges <challenge> generate <track> [options]
```

| Argument / Option | Description |
|-------------------|-------------|
| `<track>`         | Track name (e.g. `small`, `medium`, `large`). Defines instance size/difficulty. |
| `--seed <seed>`   | *(Optional)* Random seed for reproducibility. |
| `--n <number>`    | *(Optional)* Number of instances to generate. Default: 1. |
| `--out <dir>`     | *(Optional)* Output folder. Default: `<challenge>/<track>`. |

**Example:** *(coming soon)*

```bash
./tig-challenges knapsack generate small --seed 42 --n 10 --out knapsack/small
```

### Mode: `solve`

Run the built-in or configured solver on a single instance.

```bash
./tig-challenges <challenge> solve <instance>
```

| Argument   | Description |
|------------|-------------|
| `<instance>` | Path to a single instance file (e.g. JSON). |

Output: solution written to stdout or a default path. *(Exact behavior: coming soon.)*

**Example:** *(coming soon)*

```bash
./tig-challenges vehicle_routing solve instances/c101.json
```

### Mode: `evaluate`

Score a solution file against an instance.

```bash
./tig-challenges <challenge> evaluate <instance> <solution>
```

| Argument    | Description |
|-------------|-------------|
| `<instance>`  | Path to the instance file. |
| `<solution>`  | Path to the solution file. |

Output: metrics (e.g. objective value, feasibility) to stdout. *(Exact format: coming soon.)*

**Example:** *(coming soon)*

```bash
./tig-challenges vehicle_routing evaluate instances/c101.json solutions/c101_sol.json
```

---

## Integration with AI Discovery Frameworks

The intended integration point for AI-driven algorithm discovery is **`src/<challenge>/algorithm.rs`**.

- Each challenge exposes a `solve_challenge`-style API in its `algorithm` module.
- Discovery frameworks (e.g. SkyDiscover, CodeEvolve, EvoX, AdaEvolve) can treat this file as the **evolvable program**: they generate or mutate `algorithm.rs`, build the project, and use the CLI in **solve** or **evaluate** mode to get objective scores.
- The rest of the repo (instance parsing, validation, scoring) stays fixed so that evolution is focused on the solver logic only.

*(Concrete wiring for each framework: coming soon.)*

---

## Building and Running

*(Coming soon: exact build/run instructions.)*

```bash
cargo build --release
./target/release/tig-challenges <challenge> <mode> ...
```

---

## References

- **SkyDiscover:** [SkyDiscover](https://github.com/skydiscover-ai/skydiscover) — *A Flexible Framework for AI-Driven Scientific and Algorithmic Discovery*
- **CodeEvolve:** [inter-co/science-codeevolve](https://github.com/inter-co/science-codeevolve) — *Open-source evolutionary coding agent for algorithm discovery and optimization*
- **OpenEvolve:** [codelion/openevolve](https://github.com/codelion/openevolve)

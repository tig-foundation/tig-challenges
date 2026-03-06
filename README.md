# tig-challenges

Suite of algorithmic challenges featured in **The Innovation Game (TIG)**, collated for evaluating and comparing **AI-driven algorithm discovery** methods.

This repo provides a unified CLI and data formats so you can generate instances, run solvers, and evaluate solutions across multiple challenge domains. It is designed to integrate with frameworks like [SkyDiscover](https://github.com/skydiscover-ai/skydiscover), [CodeEvolve](https://github.com/inter-co/science-codeevolve), and [OpenEvolve](https://github.com/codelion/openevolve): **algorithm discovery frameworks should only edit `src/<challenge>/algorithm.rs`**; that file is the evolvable program. The rest of the repo (instance parsing, validation, scoring) stays fixed.

---

## Challenges

- **[knapsack](src/knapsack/README.md)** — Select items to maximize value under a weight constraint, with pairwise interaction values (quadratic knapsack / team formation). [Challenge Design](https://docs.tig.foundation/static/knapsack.pdf).
- **[job_scheduling](src/job_scheduling/README.md)** — Schedule operations on eligible machines to minimize makespan (Flexible Job Shop). [Challenge Design](https://docs.tig.foundation/static/jssp.pdf).
- **[satisfiability](src/satisfiability/README.md)** — Determine whether a Boolean formula (e.g. 3-SAT) has a satisfying truth assignment.
- **[vehicle_routing](src/vehicle_routing/README.md)** — Route a fleet of vehicles from a depot to serve customers with time windows and capacity constraints (VRPTW). [Challenge Design](https://docs.tig.foundation/static/vrptw.pdf).

---

## CLI Usage

The CLI uses **mode-first** subcommands:

```bash
./tig-challenges <mode> <challenge> [args...]
```

**`<mode>`** — One of: `generate`, `solve`, `evaluate`.  
**`<challenge>`** — One of: `satisfiability`, `knapsack`, `vehicle_routing`, `job_scheduling`.

### Mode: `generate`

Generate problem instances for a given track.

```bash
./tig-challenges generate <challenge> <track> [options]
```

| Argument / Option | Description |
|-------------------|-------------|
| `<challenge>`     | Challenge name (see above). |
| `<track>`         | Track specification: key=value,key=value format (challenge-specific). See [Recommended tracks](#recommended-tracks) below. |
| `--seed <seed>`   | *(Optional)* Random seed string (hashed for instance generation). Default: `0`. |
| `-n, --n <N>`     | *(Optional)* Number of instances to generate. Default: `1`. |
| `-o, --out <dir>` | *(Optional)* Output directory. Default: `<challenge>/<track>`. |

Instances are written as `<out>/0.txt`, `<out>/1.txt`, etc. (one `.txt` per instance in the challenge’s text format).

### Mode: `solve`

Run the solver on a single instance and write the solution to a file. Each time the algorithm calls `save_solution`, the solution is written immediately to the given path so that if the process is interrupted, the latest solution is still saved.

```bash
./tig-challenges solve <challenge> <instance_file> <solution_file> [options]
```

| Argument / Option | Description |
|-------------------|-------------|
| `<challenge>`       | Challenge name. |
| `<instance_file>`   | Path to a single instance file (`.txt`). Must exist. |
| `<solution_file>`   | Path where the solution will be written (`.txt`). |
| `--hyperparameters [JSON]` | *(Optional)* JSON object string for solver hyperparameters (e.g. `'{"timeout": 60}'`). |

### Mode: `evaluate`

Score a solution file against an instance. **Requires building with the `evaluate` feature** (see [Building](#building)).

```bash
./tig-challenges evaluate <challenge> <instance_file> <solution_file>
```

| Argument | Description |
|----------|-------------|
| `<challenge>`       | Challenge name. |
| `<instance_file>`   | Path to the instance file. Must exist. |
| `<solution_file>`  | Path to the solution file. Must exist. |

Output: quality score printed to stdout.

**Note:** The `evaluate` subcommand is intentionally gated by a Cargo feature so that evaluation logic and baselines are not visible to algorithm discovery; only `algorithm.rs` is meant to be evolved.

---

## Recommended tracks

Use these track strings with `generate` (track format is `key=value,key=value`; pass as a single argument, optionally quoted).

**satisfiability**
- `"n_vars=10000,ratio=4267"`
- `"n_vars=100000,ratio=4150"`
- `"n_vars=100000,ratio=4200"`
- `"n_vars=5000,ratio=4267"`
- `"n_vars=7500,ratio=4267"`

**vehicle_routing**
- `"n_nodes=600"`
- `"n_nodes=700"`
- `"n_nodes=800"`
- `"n_nodes=900"`
- `"n_nodes=1000"`

**knapsack**
- `"n_items=1000,budget=10"`
- `"n_items=1000,budget=25"`
- `"n_items=1000,budget=5"`
- `"n_items=5000,budget=10"`
- `"n_items=5000,budget=25"`

**job_scheduling**
- `"n=50,s=fjsp_high"`
- `"n=50,s=fjsp_medium"`
- `"n=50,s=flow_shop"`
- `"n=50,s=hybrid_flow_shop"`
- `"n=50,s=job_shop"`

---

## Integration with AI discovery frameworks

- The only file that should be modified or evolved by discovery frameworks is **`src/<challenge>/algorithm.rs`**. It exposes a `solve_challenge`-style API; frameworks generate or mutate this file, build the project, and invoke the CLI in **solve** (and optionally **evaluate**) mode to obtain scores.
- Instance parsing, verification, and quality scoring are implemented elsewhere and stay fixed so that evolution is focused on the solver logic only.
- To run **evaluate** (and thus expose evaluation to your workflow), build with `--features evaluate`. Without that feature, the binary does not include evaluation; this is intentional so that algorithm evolution does not see the evaluation implementation.

---

## Building

```bash
cargo build --release
./target/release/tig-challenges <mode> <challenge> ...
```

To enable the **evaluate** subcommand (score solutions against instances):

```bash
cargo build --release --features evaluate
```

Without `--features evaluate`, the **evaluate** subcommand is not available (the binary will report that the feature is required).

---

## References

- **SkyDiscover:** [SkyDiscover](https://github.com/skydiscover-ai/skydiscover) — *A Flexible Framework for AI-Driven Scientific and Algorithmic Discovery*
- **CodeEvolve:** [inter-co/science-codeevolve](https://github.com/inter-co/science-codeevolve) — *Open-source evolutionary coding agent for algorithm discovery and optimization*
- **OpenEvolve:** [codelion/openevolve](https://github.com/codelion/openevolve)

# tig-challenges

Suite of algorithmic challenges featured in **The Innovation Game (TIG)**, collated for evaluating and comparing **AI-driven algorithm discovery** methods.

This repo provides a unified CLI and data formats so you can generate instances, run solvers, and evaluate solutions across multiple challenge domains. It is designed to integrate with frameworks like [SkyDiscover](https://github.com/skydiscover-ai/skydiscover), [CodeEvolve](https://github.com/inter-co/science-codeevolve), and [OpenEvolve](https://github.com/codelion/openevolve): **algorithm discovery frameworks should only edit `src/<challenge>/algorithm.rs`**; that file is the evolvable program. The rest of the repo (instance parsing, validation, scoring) stays fixed.

---

## Quick start

### 1. Generate or obtain datasets

Generate datasets for a specific challenge using the Python CLI. Splits (e.g. `train`, `val`, `test`) and tracks are defined in **`datasets_config.json`**:

```bash
python3 tig.py generate_datasets <challenge>
```

Example: `python3 tig.py generate_datasets satisfiability` generates instances for all tracks and splits configured for satisfiability. Output is written under `datasets/<challenge>/<split>/<track>/`.

**Pre-computed instances:** *(Coming soon — [download pre-computed instances](#) for all challenges and splits.)*

### 2. Evolve the solver

Use an **AI-driven algorithm discovery framework** (e.g. SkyDiscover, CodeEvolve, OpenEvolve) to evolve **`src/<challenge>/algorithm.rs`**. That file is the only one you modify; the framework builds the project and runs the solver/evaluator to get scores.

### 3. Test on instances and get metrics

Run your solver on a dataset directory to collect **solution quality**, **time taken**, and **memory used**:

```bash
python3 tig.py test_algorithm <challenge> <dataset_dir> [--workers N] [--timeout SEC] [--hyperparameters JSON] [--debug]
```

Example: `python3 tig.py test_algorithm knapsack datasets/knapsack/test/n_items=1000,budget=10` runs the current solver on all `.txt` instances in that directory and prints aggregate metrics.

**Invocation:** You can either run the script or import it as a module:

```bash
python3 tig.py generate_datasets vehicle_routing
python3 tig.py test_algorithm vehicle_routing datasets/vehicle_routing/val/n_nodes=800
```

```python
import tig
tig.generate_datasets("job_scheduling")
tig.test_algorithm("job_scheduling", "datasets/job_scheduling/test/n=50,s=flow_shop", num_workers=4)
```

---

## Challenges

- **[knapsack](src/knapsack/README.md)** — Select items to maximize value under a weight constraint, with pairwise interaction values (quadratic knapsack / team formation). [Challenge Design](https://docs.tig.foundation/static/knapsack.pdf).
- **[job_scheduling](src/job_scheduling/README.md)** — Schedule operations on eligible machines to minimize makespan (Flexible Job Shop). [Challenge Design](https://docs.tig.foundation/static/jssp.pdf).
- **[satisfiability](src/satisfiability/README.md)** — Determine whether a Boolean formula (e.g. 3-SAT) has a satisfying truth assignment.
- **[vehicle_routing](src/vehicle_routing/README.md)** — Route a fleet of vehicles from a depot to serve customers with time windows and capacity constraints (VRPTW). [Challenge Design](https://docs.tig.foundation/static/vrptw.pdf).

---

## CLI Usage

The Rust crate exposes **three binaries**. You can call them directly or use the Python CLI (`tig.py`) which builds and invokes them as needed.

| Binary | Purpose |
|--------|---------|
| `tig_generator` | Generate instance files for a challenge/track. |
| `tig_solver` | Solve an instance and write the solution to a file. |
| `tig_evaluator` | Score a solution against an instance (quality printed to stdout). |

### Generator: `tig_generator`

Generate problem instances for a given track.

**Build:**
```bash
cargo build -r --bin tig_generator --features generator
```

**Run:**
```bash
./target/release/tig_generator <challenge> <track> [options]
```

| Argument / Option | Description |
|-------------------|-------------|
| `<challenge>`     | Challenge name: `satisfiability`, `knapsack`, `vehicle_routing`, `job_scheduling`. |
| `<track>`         | Track specification: `key=value,key=value` (challenge-specific). See [Recommended tracks](#recommended-tracks) below. |
| `--seed <seed>`   | *(Optional)* Random seed string (hashed for instance generation). Default: `0`. |
| `-n, --n <N>`     | *(Optional)* Number of instances to generate. Default: `1`. |
| `-o, --out <dir>` | *(Optional)* Output directory. Default: `<challenge>/<track>`. |

Instances are written as `<out>/0.txt`, `<out>/1.txt`, etc.

### Solver: `tig_solver`

Run the solver on a single instance and write the solution to a file. Each time the algorithm calls `save_solution`, the solution is written immediately so that if the process is interrupted, the latest solution is still saved.

**Integration with AI discovery:** Discovery frameworks (SkyDiscover, CodeEvolve, OpenEvolve, etc.) should **only edit `src/<challenge>/algorithm.rs`**. That file exposes a `solve_challenge`-style API; frameworks generate or mutate it, build the project, and invoke `tig_solver` to obtain solutions. Instance parsing, verification, and scoring stay fixed. The solver is built with the `hide_evaluate` feature so evaluation logic is not visible to the evolved code.

**Build** (must enable at least one challenge):
```bash
cargo build -r --bin tig_solver --no-default-features --features "solver,<challenge>"
```
Example: `--features "solver,knapsack"` or `--features "solver,satisfiability,knapsack,vehicle_routing,job_scheduling"` for all.

**Run:**
```bash
./target/release/tig_solver <challenge> <instance_file> <solution_file> [options]
```

| Argument / Option | Description |
|-------------------|-------------|
| `<challenge>`       | Challenge name. |
| `<instance_file>`   | Path to a single instance file (`.txt`). Must exist. |
| `<solution_file>`   | Path where the solution will be written (`.txt`). |
| `--hyperparameters [JSON]` | *(Optional)* JSON object string for solver hyperparameters (e.g. `'{"timeout": 60}'`). |

### Evaluator: `tig_evaluator`

Score a solution file against an instance. Used by pipelines (e.g. `tig.py test_algorithm`) to compute quality after running the solver. Built with full challenge features and no `hide_evaluate`, so evaluation logic is available; the solver binary is built separately with `hide_evaluate` so algorithm discovery does not see it.

**Build:**
```bash
cargo build -r --bin tig_evaluator --features evaluator
```

**Run:**
```bash
./target/release/tig_evaluator <challenge> <instance_file> <solution_file>
```

Output: quality score printed to stdout.

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

## References

- **SkyDiscover:** [SkyDiscover](https://github.com/skydiscover-ai/skydiscover) — *A Flexible Framework for AI-Driven Scientific and Algorithmic Discovery*
- **CodeEvolve:** [inter-co/science-codeevolve](https://github.com/inter-co/science-codeevolve) — *Open-source evolutionary coding agent for algorithm discovery and optimization*
- **OpenEvolve:** [codelion/openevolve](https://github.com/codelion/openevolve)

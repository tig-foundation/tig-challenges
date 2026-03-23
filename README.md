# tig-challenges

Suite of algorithmic challenges featured in **The Innovation Game (TIG)**, collated for evaluating and comparing **AI-driven algorithm discovery** methods.

This repo provides a unified CLI and data formats so you can generate instances, run solvers, and evaluate solutions across multiple challenge domains. It is designed to integrate with frameworks like [SkyDiscover](https://github.com/skydiscover-ai/skydiscover), [CodeEvolve](https://github.com/inter-co/science-codeevolve), and [OpenEvolve](https://github.com/codelion/openevolve): **algorithm discovery frameworks should only edit files inside `src/<challenge>/algorithm/`**; that folder contains the evolvable program. The rest of the repo (instance parsing, validation, scoring) stays fixed.

---

## Quick start

### 0. Prerequisites

- Python 3.8+
- Rust/Cargo (required because `tig.py` builds Rust binaries)

Check your environment:

```bash
python3 --version
cargo --version
```

### 1. Generate datasets

Use one of the provided configs and generate instances:

```bash
python3 tig.py generate_dataset job_scheduling datasets/job_scheduling/train.json
```

Use `datasets/<challenge>/test.json` the same way to generate the test split (different `seed` and output paths in the file). This writes instance files under `datasets/job_scheduling/<seed>/...` by default.  
To choose a custom output directory, pass `--out <dir>`.

### 2. Evolve or edit the algorithm

Run your algorithm discovery workflow against files in `src/<challenge>/algorithm/` (typically `src/<challenge>/algorithm/mod.rs`).  
Keep all other code unchanged; only the algorithm files should evolve.

### 3. Run algorithm on a dataset

Run the current algorithm on all instances in a dataset directory:

```bash
python3 tig.py run_algorithm job_scheduling datasets/job_scheduling/test/TIG/flow_shop/50_30_30 --workers 4 --timeout 120
```

Notes:
- Solutions are saved as `<instance>.solution`.
- Add `--baseline` to run the built-in baseline solver.
- Add `--csv runs.csv` to export runtime and memory stats.
- Optional **`--interval <seconds>`**: while the solver runs, periodically copy the latest solution to `<instance>.solution.<n×interval>` (wall-clock).
- Optional **`--snapshot-times T1,T2,...`**: copy the latest solution at those elapsed wall-clock seconds to `<instance>.solution.<T>` for each `T`. If set, this overrides `--interval`.


Outputs go under `runs/baseline_testTIG_t1800_i300/<challenge>/` (mirroring `datasets/<challenge>/test/TIG/...`), plus `manifest.json` and per-challenge `runs.csv`. Override `TIMEOUT`, `INTERVAL`, `WORKERS`, or `RUN_ROOT` via environment variables (see comments in the script).


### 4. Evaluate solutions

Score generated solutions:

```bash
python3 tig.py evaluate_solutions job_scheduling datasets/job_scheduling/test/TIG/flow_shop/50_30_30 --csv eval.csv
```

Optional:
- Use `--solutions <dir>` if solutions are stored outside the dataset directory.
- Use `--snapshots` to evaluate intermediate snapshot files (`.solution.*`).


---

## Challenges

- **[knapsack](src/knapsack/README.md)** — Select items to maximize value under a weight constraint, with pairwise interaction values (quadratic knapsack / team formation). [Challenge Design](https://docs.tig.foundation/static/knapsack.pdf).
- **[job_scheduling](src/job_scheduling/README.md)** — Schedule operations on eligible machines to minimize makespan (Flexible Job Shop). [Challenge Design](https://docs.tig.foundation/static/jssp.pdf).
- **[vehicle_routing](src/vehicle_routing/README.md)** — Route a fleet of vehicles from a depot to serve customers with time windows and capacity constraints (VRPTW). [Challenge Design](https://docs.tig.foundation/static/vrptw.pdf).

### SOTA results

*(Placeholder — leaderboard / state-of-the-art results and baselines will be linked here.)*

---

## Python API

**Invocation:** You can either run the script or import it as a module:

```bash
python3 tig.py --help
python3 tig.py <sub-command> ...
```

The Python CLI exposes three sub-commands:

### `generate_dataset`

Generate challenge instances from a JSON config file.

```bash
python3 tig.py generate_dataset <challenge> <config> [--out <output_dir>]
```

Arguments/options:
- `challenge`: one of `knapsack`, `vehicle_routing`, `job_scheduling`.
- `config`: path to a JSON file containing:
  - `seed` (string), and
  - per-track entries: `track_id -> { "track": { … }, "n_instances": <int> }` (challenge-specific `track` fields; see each challenge’s `Track` type).
- `--out`: optional output root directory. Default is `datasets/<challenge>`.

Example:
```bash
python3 tig.py generate_dataset job_scheduling datasets/job_scheduling/train.json
```

### `run_algorithm`

Build `tig_solver`, run it over all `*.txt` instances under a dataset directory, and write `<instance>.solution` files.

```bash
python3 tig.py run_algorithm <challenge> <dataset_dir> [options]
```

Arguments/options:
- `challenge`: one of `knapsack`, `vehicle_routing`, `job_scheduling`.
- `dataset_dir`: directory searched recursively for `.txt` files.
- `--workers <int>`: number of worker threads (default: `1`).
- `--hyperparameters <json_or_string>`: for example, `--hyperparameters '{"exploration_level":5}'
- `--timeout <seconds>`: per-instance timeout in seconds (default: `60`).
- `--interval <seconds>`: snapshot interval in seconds; periodically copies latest solution to `.solution.<t>`.
- `--out <output_dir>`: write solutions under a separate directory preserving relative paths (default: alongside dataset files).
- `--baseline`: runs baseline algorithm
- `--csv <file>`: write stats as csv format with columns `instance_file,time_taken,memory`.

Example:
```bash
python3 tig.py run_algorithm vehicle_routing datasets/vehicle_routing/test/TIG/800 --workers 4 --timeout 120 --csv runs.csv
```

### `evaluate_solutions`

Build `tig_evaluator`, evaluate saved solutions for each instance, and return quality outputs.

```bash
python3 tig.py evaluate_solutions <challenge> <dataset_dir> [options]
```

Arguments/options:
- `challenge`: one of `knapsack`, `vehicle_routing`, `job_scheduling`.
- `dataset_dir`: directory searched recursively for `.txt` instance files.
- `--solutions <dir>`: solution root directory (default: `dataset_dir`). Solutions are searched as `<solutions_dir>/<instance_file>.solution`.
- `--snapshots`: evaluate snapshot files matching `<instance>.solution*` instead of only `<instance>.solution`.
- `--workers <int>`: number of worker threads (default: `1`).
- `--csv <file>`: write evaluation CSV with columns `solution_file,output`.

Example:
```bash
python3 tig.py evaluate_solutions vehicle_routing datasets/vehicle_routing/test/TIG/800 --solutions outputs --snapshots --csv eval.csv
```

### `import tig`

As a Python module, the same entry points are available:
```python
import tig

tig.generate_dataset(
    "job_scheduling",
    "datasets/job_scheduling/train.json",
    out_dir=None,
)

tig.run_algorithm(
    "job_scheduling",
    "datasets/job_scheduling/test/TIG/flow_shop/50_30_30",
    num_workers=4,
    timeout=120,
)

tig.evaluate_solutions(
    "job_scheduling",
    "datasets/job_scheduling/test/TIG/flow_shop/50_30_30",
    solutions_dir=None,
    snapshots=False,
    num_workers=4,
)
```

---

## References

- **SkyDiscover:** [SkyDiscover](https://github.com/skydiscover-ai/skydiscover) — *A Flexible Framework for AI-Driven Scientific and Algorithmic Discovery*
- **CodeEvolve:** [inter-co/science-codeevolve](https://github.com/inter-co/science-codeevolve) — *Open-source evolutionary coding agent for algorithm discovery and optimization*
- **OpenEvolve:** [codelion/openevolve](https://github.com/codelion/openevolve)

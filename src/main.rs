use anyhow::Result;
use clap::{arg, value_parser, Command};
use serde_json::{Map, Value};
use std::fs;
use std::path::{Path, PathBuf};
use tig_challenges::*;

fn cli() -> Command {
    Command::new("tig-challenges")
        .about("TIG challenge instance generation, solving, and evaluation")
        .subcommand_required(true)
        .subcommand(
            Command::new("generate")
                .about("Generate one or more instance files for a challenge/track")
                .arg(
                    arg!(<CHALLENGE> "Challenge name: satisfiability, knapsack, vehicle_routing, job_scheduling")
                        .value_parser(value_parser!(String)),
                )
                .arg(
                    arg!(<TRACK> "Track specification (key=value,key=value format, challenge-specific)")
                        .value_parser(value_parser!(String)),
                )
                .arg(
                    arg!(--seed [SEED] "Random seed string (hashed for instance generation)")
                        .default_value("0")
                        .value_parser(value_parser!(String)),
                )
                .arg(
                    arg!(-n --n <N> "Number of instances to generate")
                        .default_value("1")
                        .value_parser(value_parser!(String)),
                )
                .arg(
                    arg!(-o --out [OUT] "Output directory for instance files")
                        .value_parser(value_parser!(PathBuf)),
                ),
        )
        .subcommand(
            Command::new("solve")
                .about("Solve an instance and write the solution to a file")
                .arg(
                    arg!(<CHALLENGE> "Challenge name: satisfiability, knapsack, vehicle_routing, job_scheduling")
                        .value_parser(value_parser!(String)),
                )
                .arg(
                    arg!(<INSTANCE_FILE> "Path to the instance file")
                        .value_parser(value_parser!(PathBuf)),
                )
                .arg(
                    arg!(<SOLUTION_FILE> "Path to write the solution file")
                        .value_parser(value_parser!(PathBuf)),
                )
                .arg(
                    arg!(--hyperparameters [HYPERPARAMETERS] "JSON string for solver hyperparameters")
                        .value_parser(value_parser!(String)),
                ),
        )
        .subcommand(
            Command::new("evaluate")
                .about("Evaluate a solution against an instance and print the quality score")
                .arg(
                    arg!(<CHALLENGE> "Challenge name: satisfiability, knapsack, vehicle_routing, job_scheduling")
                        .value_parser(value_parser!(String)),
                )
                .arg(
                    arg!(<INSTANCE_FILE> "Path to the instance file")
                        .value_parser(value_parser!(PathBuf)),
                )
                .arg(
                    arg!(<SOLUTION_FILE> "Path to the solution file")
                        .value_parser(value_parser!(PathBuf)),
                ),
        )
}

fn run_generate(
    challenge: &str,
    track: &str,
    seed: &str,
    n: usize,
    out: Option<&PathBuf>,
) -> Result<()> {
    let seed = blake3::hash(seed.as_bytes());
    let out_dir: PathBuf = out
        .cloned()
        .unwrap_or_else(|| PathBuf::from(format!("{}/{}", challenge, track)));
    fs::create_dir_all(&out_dir)?;

    macro_rules! dispatch_generate {
        ($c:ident) => {{
            let track = if track.starts_with('"') && track.ends_with('"') {
                track.to_string()
            } else {
                format!(r#""{}""#, track)
            };
            let track = serde_json::from_str::<$c::Track>(&track).map_err(|e| {
                anyhow::anyhow!(
                    "Failed to parse track '{}' as {}::Track: {}",
                    track,
                    stringify!($c),
                    e
                )
            })?;
            for i in 0..n {
                let instance = $c::Challenge::generate_instance(seed.as_bytes(), &track)?;
                let path = Path::new(&out_dir).join(format!("{}.txt", i));
                fs::write(path, instance.to_txt())?;
            }
        }};
    }

    match challenge {
        "satisfiability" => dispatch_generate!(satisfiability),
        "knapsack" => dispatch_generate!(knapsack),
        "vehicle_routing" => dispatch_generate!(vehicle_routing),
        "job_scheduling" => dispatch_generate!(job_scheduling),
        _ => anyhow::bail!("Unknown challenge: {}", challenge),
    }
    Ok(())
}

fn run_solve(
    challenge: &str,
    instance_file: &Path,
    solution_file: &Path,
    hyperparameters: &Option<Map<String, Value>>,
) -> Result<()> {
    anyhow::ensure!(
        instance_file.exists(),
        "Instance file does not exist: {}",
        instance_file.display()
    );
    let content = fs::read_to_string(instance_file)?;

    macro_rules! dispatch_solve {
        ($c:ident) => {{
            let instance = $c::Challenge::from_txt(&content)?;
            let save_solution_fn = |solution: &$c::Solution| -> Result<()> {
                fs::write(&solution_file, solution.to_txt())?;
                Ok(())
            };
            $c::solve_challenge(&instance, &save_solution_fn, hyperparameters)?;
        }};
    }
    match challenge {
        "satisfiability" => dispatch_solve!(satisfiability),
        "knapsack" => dispatch_solve!(knapsack),
        "vehicle_routing" => dispatch_solve!(vehicle_routing),
        "job_scheduling" => dispatch_solve!(job_scheduling),
        _ => anyhow::bail!("Unknown challenge: {}", challenge),
    }
    Ok(())
}

#[cfg(feature = "evaluate")]
fn run_evaluate(challenge: &str, instance_file: &Path, solution_file: &Path) -> Result<()> {
    anyhow::ensure!(
        instance_file.exists(),
        "Instance file does not exist: {}",
        instance_file.display()
    );
    anyhow::ensure!(
        solution_file.exists(),
        "Solution file does not exist: {}",
        solution_file.display()
    );
    let instance_content = fs::read_to_string(instance_file)?;
    let solution_content = fs::read_to_string(solution_file)?;

    macro_rules! dispatch_evaluate {
        ($c:ident) => {{
            let instance = $c::Challenge::from_txt(&instance_content)?;
            let solution = $c::Solution::from_txt(&solution_content)?;
            instance.evaluate_solution(&solution)?
        }};
    }

    let quality = match challenge {
        "satisfiability" => dispatch_evaluate!(satisfiability),
        "knapsack" => dispatch_evaluate!(knapsack),
        "vehicle_routing" => dispatch_evaluate!(vehicle_routing),
        "job_scheduling" => dispatch_evaluate!(job_scheduling),
        _ => anyhow::bail!("Unknown challenge: {}", challenge),
    };
    println!("{}", quality);
    Ok(())
}

fn main() -> Result<()> {
    let matches = cli().get_matches();
    match matches.subcommand() {
        Some(("generate", sub)) => {
            let challenge = sub.get_one::<String>("CHALLENGE").unwrap();
            let track = sub.get_one::<String>("TRACK").unwrap();
            let seed = sub.get_one::<String>("seed").unwrap();
            let n: usize = sub.get_one::<String>("n").unwrap().parse()?;
            let out = sub.get_one::<PathBuf>("out");
            run_generate(challenge, track, seed, n, out)
        }
        Some(("solve", sub)) => {
            let challenge = sub.get_one::<String>("CHALLENGE").unwrap();
            let instance_file = sub.get_one::<PathBuf>("INSTANCE_FILE").unwrap();
            let solution_file = sub.get_one::<PathBuf>("SOLUTION_FILE").unwrap();
            let hyperparameters = sub
                .get_one::<String>("hyperparameters")
                .map(|s| serde_json::from_str(s))
                .transpose()
                .map_err(|e| anyhow::anyhow!("Invalid --hyperparameters JSON: {}", e))?;
            run_solve(challenge, instance_file, solution_file, &hyperparameters)
        }
        #[cfg(not(feature = "evaluate"))]
        Some(("evaluate", _)) => {
            anyhow::bail!("Must compile with feature `evaluate` to evaluate solutions");
        }
        #[cfg(feature = "evaluate")]
        Some(("evaluate", sub)) => {
            let challenge = sub.get_one::<String>("CHALLENGE").unwrap();
            let instance_file = sub.get_one::<PathBuf>("INSTANCE_FILE").unwrap();
            let solution_file = sub.get_one::<PathBuf>("SOLUTION_FILE").unwrap();
            run_evaluate(challenge, instance_file, solution_file)
        }
        _ => unreachable!(),
    }
}

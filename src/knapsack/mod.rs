mod algorithm;
mod baselines;
mod challenge;
mod solution;

use crate::QUALITY_PRECISION;
pub use algorithm::*;
use anyhow::{anyhow, Result};
pub use challenge::*;
use rand::{rngs::SmallRng, Rng, SeedableRng};
pub use solution::*;
use std::{cell::RefCell, collections::HashSet, f64::consts::PI};

/// Generate a sample from lognormal distribution using Box-Muller transform
fn sample_lognormal(rng: &mut SmallRng, mean: f64, std_dev: f64) -> f64 {
    let u1: f64 = rng.gen();
    let u2: f64 = rng.gen();
    let z = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
    (mean + std_dev * z).exp()
}

impl_kv_string_serde! {
    Track {
        n_items: usize,
        budget: u32,
        density: u32,
        dispersion: String,
        track_type: String,
    }
}

impl_base64_serde! {
    Solution {
        items: Vec<usize>,
    }
}

impl Solution {
    pub fn new() -> Self {
        Self { items: Vec::new() }
    }
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Challenge {
    pub seed: [u8; 32],
    pub num_items: usize,
    pub weights: Vec<u32>,
    pub values: Vec<u32>,
    pub interaction_values: Vec<Vec<i32>>,
    pub max_weight: u32,
}

impl Challenge {
    pub fn generate_instance(seed: &[u8; 32], track: &Track) -> Result<Self> {
        
        match track.track_type.as_str() {
            "standard_qkp" => Self::generate_standard_qkp(seed, track),
            "team_formation" => Self::generate_team_formation(seed, track),
            "dispersion_qkp" => Self::generate_dispersion_qkp(seed, track),
            "hidden_clique" => Self::generate_hidden_clique_ci(seed, track),
            _ => Err(anyhow!("Invalid track type: {}", track.track_type)),
        }
    }

    /// Standard-QKP generator (Large-QKP style)
    /// - Weights: random in [1, 50]
    /// - Values: [1, 100] with density probability, else 0
    /// - Interaction matrix: symmetric, [1, 100] with density, else 0
    fn generate_standard_qkp(seed: &[u8; 32], track: &Track) -> Result<Self> {
        let mut rng = SmallRng::from_seed(seed.clone());
        let density = track.density as f64 / 100.0;

        // Generate weights w_i in the range [1, 50]
        let weights: Vec<u32> = (0..track.n_items).map(|_| rng.gen_range(1..=50)).collect();

        // Generate values v_i in the range [1, 100] with density probability, 0 otherwise
        let values: Vec<u32> = (0..track.n_items)
            .map(|_| {
                if rng.gen_bool(density) {
                    rng.gen_range(1..=100)
                } else {
                    0
                }
            })
            .collect();

        // Generate interaction values V_ij with the following properties:
        // - V_ij == V_ji (symmetric matrix)
        // - V_ii == 0 (diagonal is zero)
        // - Values are in range [1, 100] with density probability, 0 otherwise
        let mut interaction_values: Vec<Vec<i32>> = vec![vec![0; track.n_items]; track.n_items];

        for i in 0..track.n_items {
            for j in (i + 1)..track.n_items {
                let value = if rng.gen_bool(density) {
                    rng.gen_range(1..=100)
                } else {
                    0
                };
                interaction_values[i][j] = value;
                interaction_values[j][i] = value;
            }
        }

        let max_weight = (track.budget as f64 / 100.0 * weights.iter().sum::<u32>() as f64) as u32;

        Ok(Challenge {
            seed: seed.clone(),
            num_items: track.n_items.clone(),
            weights,
            values,
            interaction_values,
            max_weight,
        })
    }

    /// Team-Formation-QKP generator
    /// - Projects assigned to participants via lognormal distribution
    /// - Interaction values based on Jaccard similarity
    /// - Weights: random in [1, 10]
    /// - Values: 0 (no linear terms)
    fn generate_team_formation(seed: &[u8; 32], track: &Track) -> Result<Self> {
        let mut rng = SmallRng::from_seed(seed.clone());
        let n_participants = track.n_items;
        let n_projects = 30000;
        let log_normal_mean = 4.0;
        let log_normal_std = 1.0;
        let max_weight_val = 10;

        // Step 1: Generate subsets of projects using lognormal cardinalities
        let mut subsets: Vec<Vec<usize>> = Vec::new();
        let mut counter: usize = 0;
        while counter < n_projects {
            let cardinality = 1 + sample_lognormal(&mut rng, log_normal_mean, log_normal_std) as usize;
            let end = (counter + cardinality).min(n_projects);
            subsets.push((counter..end).collect());
            counter = end;
        }
        let n_subsets = subsets.len();

        // Step 2: Determine number of projects per participant
        let n_projects_per_participant: Vec<usize> = (0..n_participants)
            .map(|_| 1 + sample_lognormal(&mut rng, log_normal_mean, log_normal_std) as usize)
            .collect();

        // Step 3: Assign projects to each participant
        let mut projects_dict: Vec<HashSet<usize>> = Vec::with_capacity(n_participants);
        for i in 0..n_participants {
            let subset_id = rng.gen_range(0..n_subsets);
            let subset = &subsets[subset_id];
            let cardinality_of_subset = subset.len();
            
            let selected_projects: HashSet<usize> = if n_projects_per_participant[i] < cardinality_of_subset {
                // Sample without replacement from subset
                let mut selected: Vec<usize> = subset.clone();
                for j in 0..n_projects_per_participant[i] {
                    let idx = rng.gen_range(j..selected.len());
                    selected.swap(j, idx);
                }
                selected.into_iter().take(n_projects_per_participant[i]).collect()
            } else {
                // Take all from subset and sample more from remaining projects
                let mut selected: HashSet<usize> = subset.iter().cloned().collect();
                let n_projects_to_choose = n_projects_per_participant[i] - cardinality_of_subset;
                
                // Sample additional projects not in the subset
                let mut remaining: Vec<usize> = (0..n_projects)
                    .filter(|p| !selected.contains(p))
                    .collect();
                
                for j in 0..n_projects_to_choose.min(remaining.len()) {
                    let idx = rng.gen_range(j..remaining.len());
                    remaining.swap(j, idx);
                    selected.insert(remaining[j]);
                }
                selected
            };
            projects_dict.push(selected_projects);
        }

        // Step 4: Compute Jaccard similarity for interaction values
        // Scale by 1000 to convert float to integer
        let mut interaction_values: Vec<Vec<i32>> = vec![vec![0; n_participants]; n_participants];
        for i in 0..n_participants {
            for j in (i + 1)..n_participants {
                let set_i = &projects_dict[i];
                let set_j = &projects_dict[j];
                let intersection_size = set_i.intersection(set_j).count();
                let union_size = set_i.len() + set_j.len() - intersection_size;
                
                if union_size > 0 && intersection_size > 0 {
                    let jaccard = (intersection_size as f64 / union_size as f64 * 1000.0) as i32;
                    interaction_values[i][j] = jaccard;
                    interaction_values[j][i] = jaccard;
                }
            }
        }

        // Generate weights in [1, 10]
        let weights: Vec<u32> = (0..n_participants)
            .map(|_| rng.gen_range(1..=max_weight_val))
            .collect();

        // No linear values in team-formation
        let values: Vec<u32> = vec![0; n_participants];

        let max_weight = (track.budget as f64 / 100.0 * weights.iter().sum::<u32>() as f64) as u32;

        Ok(Challenge {
            seed: seed.clone(),
            num_items: n_participants,
            weights,
            values,
            interaction_values,
            max_weight,
        })
    }

    /// Dispersion-QKP generator with 4 sub-types
    /// Sub-type selected via (seed/6) mod 4: geo, wgeo, expo, ran
    /// Sparsification uses track.density
    fn generate_dispersion_qkp(seed: &[u8; 32], track: &Track) -> Result<Self> {
        let mut rng = SmallRng::from_seed(seed.clone());
        let density = track.density as f64 / 100.0;
        let n_nodes = track.n_items;

        // Generate utility matrix based on sub-type
        let utility_matrix: Vec<Vec<f64>> = match track.dispersion.as_str() {
            "geo" => Self::generate_geo_utility(&mut rng, n_nodes),
            "wgeo" => Self::generate_wgeo_utility(&mut rng, n_nodes),
            "expo" => Self::generate_expo_utility(&mut rng, n_nodes),
            "ran" => Self::generate_ran_utility(&mut rng, n_nodes),
        };

        // Apply sparsification and convert to interaction values
        // Scale by 100 to convert float to integer
        // TODO: consider why it's scaled by 1000
        let mut interaction_values: Vec<Vec<i32>> = vec![vec![0; n_nodes]; n_nodes];
        for i in 0..n_nodes {
            for j in (i + 1)..n_nodes {
                if rng.gen_bool(density) && utility_matrix[i][j] > 0.0 {
                    let value = (utility_matrix[i][j]).round() as i32;
                    interaction_values[i][j] = value;
                    interaction_values[j][i] = value;
                }
            }
        }

        // Generate weights in [1, 100]
        let weights: Vec<u32> = (0..n_nodes).map(|_| rng.gen_range(1..=100)).collect();

        // No linear values in dispersion-qkp
        let values: Vec<u32> = vec![0; n_nodes];

        let max_weight = (track.budget as f64 / 100.0 * weights.iter().sum::<u32>() as f64) as u32;

        Ok(Challenge {
            seed: seed.clone(),
            num_items: track.n_items.clone(),
            weights,
            values,
            interaction_values,
            max_weight,
        })
    }

    /// Geometrical: Euclidean distance from random 2D points in [0, 100]
    fn generate_geo_utility(rng: &mut SmallRng, n_nodes: usize) -> Vec<Vec<f64>> {
        let locations: Vec<(f64, f64)> = (0..n_nodes)
            .map(|_| (rng.gen::<f64>() * 100.0, rng.gen::<f64>() * 100.0))
            .collect();

        let mut distances = vec![vec![0.0; n_nodes]; n_nodes];
        for i in 0..n_nodes {
            for j in (i + 1)..n_nodes {
                let dx = locations[i].0 - locations[j].0;
                let dy = locations[i].1 - locations[j].1;
                let dist = (dx * dx + dy * dy).sqrt();
                distances[i][j] = dist;
                distances[j][i] = dist;
            }
        }
        distances
    }

    /// Weighted Geometrical: Weighted Euclidean with node weights in [5, 10]
    fn generate_wgeo_utility(rng: &mut SmallRng, n_nodes: usize) -> Vec<Vec<f64>> {
        let locations: Vec<(f64, f64)> = (0..n_nodes)
            .map(|_| (rng.gen::<f64>() * 100.0, rng.gen::<f64>() * 100.0))
            .collect();

        let node_weights: Vec<f64> = (0..n_nodes)
            .map(|_| rng.gen::<f64>() * 5.0 + 5.0)
            .collect();

        let mut distances = vec![vec![0.0; n_nodes]; n_nodes];
        for i in 0..n_nodes {
            for j in (i + 1)..n_nodes {
                let dx = locations[i].0 - locations[j].0;
                let dy = locations[i].1 - locations[j].1;
                let dist = (dx * dx + dy * dy).sqrt();
                let weighted_dist = node_weights[i] * node_weights[j] * dist;
                distances[i][j] = weighted_dist;
                distances[j][i] = weighted_dist;
            }
        }
        distances
    }

    /// Exponential: Exponential distribution (mean=50), symmetric
    fn generate_expo_utility(rng: &mut SmallRng, n_nodes: usize) -> Vec<Vec<f64>> {
        let mean = 50.0;
        let mut distances = vec![vec![0.0; n_nodes]; n_nodes];
        for i in 0..n_nodes {
            for j in (i + 1)..n_nodes {
                // Exponential distribution: -mean * ln(U) where U is uniform(0,1)
                let u: f64 = rng.gen();
                let value = -mean * u.ln();
                distances[i][j] = value;
                distances[j][i] = value;
            }
        }
        distances
    }

    /// Random: Random integers in [1, 100], symmetric
    fn generate_ran_utility(rng: &mut SmallRng, n_nodes: usize) -> Vec<Vec<f64>> {
        let mut distances = vec![vec![0.0; n_nodes]; n_nodes];
        for i in 0..n_nodes {
            for j in (i + 1)..n_nodes {
                let value = rng.gen_range(1..=100) as f64;
                distances[i][j] = value;
                distances[j][i] = value;
            }
        }
        distances
    }


    pub fn evaluate_total_value(&self, solution: &Solution) -> Result<u32> {
        let selected_items: HashSet<usize> = solution.items.iter().cloned().collect();
        if selected_items.len() != solution.items.len() {
            return Err(anyhow!("Duplicate items selected."));
        }

        let total_weight = selected_items
            .iter()
            .map(|&item| {
                if item >= self.weights.len() {
                    return Err(anyhow!("Item ({}) is out of bounds", item));
                }
                Ok(self.weights[item])
            })
            .collect::<Result<Vec<_>, _>>()?
            .iter()
            .sum::<u32>();

        if total_weight > self.max_weight {
            return Err(anyhow!(
                "Total weight ({}) exceeded max weight ({})",
                total_weight,
                self.max_weight
            ));
        }
        let mut indices: Vec<usize> = selected_items.into_iter().collect();
        indices.sort();

        let mut total_value = 0i32;

        // Sum the individual values
        for &i in &indices {
            total_value += self.values[i] as i32;
        }

        // Sum the interactive values for pairs in indices
        for i in 0..indices.len() {
            for j in (i + 1)..indices.len() {
                let idx_i = indices[i];
                let idx_j = indices[j];
                total_value += self.interaction_values[idx_i][idx_j];
            }
        }

        Ok(match total_value {
            v if v < 0 => 0u32,
            v => v as u32,
        })
    }

    conditional_pub!(
        fn compute_greedy_baseline(&self) -> Result<Solution> {
            let solution = RefCell::new(Solution::new());
            let save_solution_fn = |s: &Solution| -> Result<()> {
                *solution.borrow_mut() = s.clone();
                Ok(())
            };
            baselines::tabu_search::solve_challenge(self, &save_solution_fn, &None)?;
            Ok(solution.into_inner())
        }
    );

    conditional_pub!(
        fn compute_sota_baseline(&self) -> Result<Solution> {
            Err(anyhow!("Not implemented yet"))
        }
    );

    conditional_pub!(
        fn evaluate_solution(&self, solution: &Solution) -> Result<i32> {
            let total_value = self.evaluate_total_value(solution)?;
            let greedy_solution = self.compute_greedy_baseline()?;
            let greedy_total_value = self.evaluate_total_value(&greedy_solution)?;
            // TODO: implement SOTA baseline
            let sota_total_value = greedy_total_value;
            let quality = (total_value as f64 - sota_total_value as f64) / sota_total_value as f64
            
            let quality = quality.clamp(-10.0, 10.0) * QUALITY_PRECISION as f64;
            let quality = quality.round() as i32;
            Ok(quality)
        }
    );
}

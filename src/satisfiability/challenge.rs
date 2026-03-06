//! SAT challenge (instance); serde (de)serialization uses DIMACS CNF format.
//!
//! DIMACS CNF: `p cnf <vars> <clauses>`, then clause lines (literals + 0). Comment lines `c ...` are ignored.

use anyhow::Result;
use serde::de::{self, Visitor};
use serde::{Deserialize, Serialize};
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub struct Challenge {
    pub seed: [u8; 32],
    pub num_variables: usize,
    pub clauses: Vec<Vec<i32>>,
}

impl Challenge {
    /// Serialize this instance to txt (DIMACS CNF format). Seed is not serialized.
    pub fn to_txt(&self) -> String {
        let mut out = format!("p cnf {} {}\n", self.num_variables, self.clauses.len());
        for clause in &self.clauses {
            let lits: Vec<String> = clause.iter().map(|n| n.to_string()).collect();
            out.push_str(&format!("{} 0\n", lits.join(" ")));
        }
        out
    }

    /// Deserialize an instance from txt (DIMACS CNF format). Seed is set to zeros.
    pub fn from_txt(s: &str) -> Result<Self> {
        let mut num_variables = 0usize;
        let mut num_clauses = 0usize;
        let mut clauses: Vec<Vec<i32>> = Vec::new();
        let mut current_clause: Vec<i32> = Vec::new();

        for line in s.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('c') {
                continue;
            }
            if line.starts_with('p') {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() >= 4 && parts[0] == "p" && parts[1].to_lowercase() == "cnf" {
                    num_variables = parts[2]
                        .parse()
                        .map_err(|_| anyhow::anyhow!("Invalid num_variables in p line"))?;
                    num_clauses = parts[3]
                        .parse()
                        .map_err(|_| anyhow::anyhow!("Invalid num_clauses in p line"))?;
                } else {
                    return Err(anyhow::anyhow!("Invalid problem line: {:?}", line));
                }
                continue;
            }

            for token in line.split_whitespace() {
                let n: i32 = token
                    .parse()
                    .map_err(|_| anyhow::anyhow!("Invalid literal: {:?}", token))?;
                if n == 0 {
                    if !current_clause.is_empty() {
                        clauses.push(std::mem::take(&mut current_clause));
                    }
                } else {
                    current_clause.push(n);
                }
            }
        }
        if !current_clause.is_empty() {
            clauses.push(current_clause);
        }

        if num_variables == 0 && num_clauses == 0 && !clauses.is_empty() {
            return Err(anyhow::anyhow!("Missing p cnf header"));
        }
        if num_clauses != 0 && clauses.len() != num_clauses {
            return Err(anyhow::anyhow!(
                "Clause count mismatch: header says {}, found {}",
                num_clauses,
                clauses.len()
            ));
        }

        Ok(Challenge {
            seed: [0u8; 32],
            num_variables,
            clauses,
        })
    }
}

impl Serialize for Challenge {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_txt())
    }
}

impl<'de> Deserialize<'de> for Challenge {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        struct ChallengeVisitor;
        impl<'de> Visitor<'de> for ChallengeVisitor {
            type Value = Challenge;
            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("DIMACS CNF string (p cnf ..., clause lines)")
            }
            fn visit_str<E>(self, v: &str) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                Challenge::from_txt(v).map_err(de::Error::custom)
            }
        }
        deserializer.deserialize_str(ChallengeVisitor)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_txt() {
        let c = Challenge {
            seed: [0u8; 32],
            num_variables: 4,
            clauses: vec![vec![1, 2, -3], vec![-1, 3, 4], vec![2, -3, 4]],
        };
        let txt = serde_json::to_string(&c).unwrap();
        let back: Challenge = serde_json::from_str(&txt).unwrap();
        assert_eq!(back, c);
    }
}

//! SAT solution; serde (de)serialization uses DIMACS solution format.
//!
//! DIMACS solution: `s SATISFIABLE` then `v <lit1> <lit2> ... 0` (positive = true, negative = false, 1-based).

use anyhow::Result;
use serde::de::{self, Visitor};
use serde::{Deserialize, Serialize};
use std::fmt;

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Solution {
    pub assignment: Vec<bool>,
}

impl Solution {
    pub fn new() -> Self {
        Self::default()
    }

    /// Serialize this solution to txt (DIMACS solution format).
    pub fn to_txt(&self) -> String {
        let lits: Vec<String> = self
            .assignment
            .iter()
            .enumerate()
            .map(|(i, &b)| {
                let var = (i + 1) as i32;
                if b {
                    var
                } else {
                    -var
                }
            })
            .map(|n| n.to_string())
            .collect();
        format!("v {} 0\n", lits.join(" "))
    }

    /// Deserialize a solution from txt (DIMACS solution format).
    pub fn from_txt(s: &str) -> Result<Self> {
        let mut assignment: Vec<Option<bool>> = Vec::new();
        for line in s.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('c') || line.starts_with('s') {
                continue;
            }
            if !line.starts_with('v') {
                continue;
            }
            let rest = line[1..].trim();
            for token in rest.split_whitespace() {
                let n: i32 = token
                    .parse()
                    .map_err(|_| anyhow::anyhow!("Invalid literal: {:?}", token))?;
                if n == 0 {
                    break;
                }
                let idx = (n.abs() as usize)
                    .checked_sub(1)
                    .ok_or_else(|| anyhow::anyhow!("Variable index 0 not allowed"))?;
                let value = n > 0;
                if idx >= assignment.len() {
                    assignment.resize(idx + 1, None);
                }
                assignment[idx] = Some(value);
            }
        }
        let assignment: Vec<bool> = assignment.into_iter().map(|o| o.unwrap_or(false)).collect();
        Ok(Solution { assignment })
    }
}

impl Serialize for Solution {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_txt())
    }
}

impl<'de> Deserialize<'de> for Solution {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        struct SolutionVisitor;
        impl<'de> Visitor<'de> for SolutionVisitor {
            type Value = Solution;
            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("DIMACS solution string (s SATISFIABLE, v ... 0)")
            }
            fn visit_str<E>(self, v: &str) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                Solution::from_txt(v).map_err(de::Error::custom)
            }
        }
        deserializer.deserialize_str(SolutionVisitor)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_txt() {
        let sol = Solution {
            assignment: vec![true, false, true, false],
        };
        let txt = serde_json::to_string(&sol).unwrap();
        let back: Solution = serde_json::from_str(&txt).unwrap();
        assert_eq!(back, sol);
    }
}

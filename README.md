# Computational package for article 120

This package reproduces the synthetic demonstration used in the manuscript.
It is not a field-calibrated data set. The purpose is to make the proposed
state-conditioned temporal reliability workflow auditable.

Public repository: https://github.com/gabrielmontufar/article-120-slope-state-envelope

## Reproduce

```bash
python code/slope_state_envelope.py
```

The random seed is fixed at `120`, with `30,000` Monte Carlo samples.

## Outputs

- `data/deterministic_scenario_summary.csv`
- `data/deterministic_time_series.csv`
- `data/monte_carlo_summary.csv`
- `data/failure_probability_time_series.csv`
- `data/state_conditioned_threshold_envelope.csv`
- `data/sensitivity_summary.csv`
- `data/monte_carlo_convergence.csv`
- `figures/Fig1_conceptual_workflow.png` to `figures/Fig6_state_risk_contrast.png`
- `figures/Fig7_monte_carlo_convergence.png`

## Scope

The model couples a reduced infiltration state variable, suction loss,
positive pore pressure, crack water loading, root cohesion, deterministic
factor of safety, and Monte Carlo reliability. Parameters are transparent
and intended for reproducible comparison rather than site-specific design.

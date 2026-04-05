# Variant B Report

- run_id: `winsim-demo-001`
- thread_id: `variantb-demo`
- incident_id: `winsim-demo-001`
- verdict: `ACCEPT`
- retry_count: `1`
- fatal_status: `<none>`

## Sandbox Metrics

| scenario_id | status | time(h) | cost($) | risk |
|---|---:|---:|---:|---:|
| `winsim-demo-001-S1` | `SUCCESS` | 120.0 | 50000.0 | 0.2 |
| `winsim-demo-001-S2` | `SUCCESS` | 120.0 | 50000.0 | 0.2 |
| `winsim-demo-001-S3` | `SUCCESS` | 120.0 | 50000.0 | 0.2 |

## Pareto Frontier (minimize time, cost, risk)

- frontier_ids: ['winsim-demo-001-S1', 'winsim-demo-001-S2', 'winsim-demo-001-S3']


## Trade-off Analysis

## Sandbox Metrics Analysis

All scenarios (`winsim-demo-001-S1`, `S2`, `S3`) achieved **SUCCESS** with identical metrics: **120.0h** time, **$50,000** cost, **0.2** risk. No failures or variations observed.

## Pareto Frontier
Ground truth: `['winsim-demo-001-S1', 'winsim-demo-001-S2', 'winsim-demo-001-S3']`. All frontier points are equivalent (non-dominated, identical trade-offs).

## Recommendation
**winsim-demo-001-S1**: Optimal due to balanced, identical time/cost/risk across frontier (120h / $50k / 0.2); no trade-offs favor alternatives.

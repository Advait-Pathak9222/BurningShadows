# Reproducible evaluation

All values below were generated from `data/test.jsonl` by `make report`.
Monetary loss and catch rates are labelled simulation assumptions, not production findings.

- Allocator loss averted at full budget: INR 3779200.00
- Allocator assurance ROI at full budget: 3936.67
- Allocator intervention precision: 0.467

## Conformal calibration

- `support-assistant`: threshold 0.55, upper escape-risk bound 0.073 at alpha 0.20
- `internal-kb`: threshold 0.65, upper escape-risk bound 0.179 at alpha 0.20
- `finops-agent`: threshold 0.80, upper escape-risk bound 0.142 at alpha 0.20

## Held-out calibration

- `support-assistant`: ECE 0.143 on 100 rows
- `internal-kb`: ECE 0.181 on 100 rows
- `finops-agent`: ECE 0.133 on 100 rows

## Metrics by policy and budget

| policy     |   interactions |   assurance_spend_inr |   loss_averted_inr |   assurance_roi |   escaped_harm_rate |   intervention_precision |   abstention_rate |   p99_text_latency_ms |   p99_effect_latency_ms |   budget_variance |   audit_coverage |   cost_per_1k_inr |   cost_per_1k_usd |   budget_fraction |
|:-----------|---------------:|----------------------:|-------------------:|----------------:|--------------------:|-------------------------:|------------------:|----------------------:|------------------------:|------------------:|-----------------:|------------------:|------------------:|------------------:|
| check_none |            300 |                     0 |         0          |            0    |            0.266055 |                 0        |         0.273333  |                     4 |                       0 |         -1        |                1 |              0    |            0      |              0.1  |
| fixed_rate |            300 |                   368 |         2.6335e+06 |         7156.25 |            0        |                 0.991304 |         0.0866667 |                    12 |                     900 |          2.83333  |                1 |           1226.67 |           13.9394 |              0.1  |
| allocator  |            300 |                   368 |         2.6335e+06 |         7156.25 |            0        |                 0.991304 |         0.0866667 |                    12 |                     900 |          2.83333  |                1 |           1226.67 |           13.9394 |              0.1  |
| check_none |            300 |                     0 |         0          |            0    |            0.266055 |                 0        |         0.273333  |                     4 |                       0 |         -1        |                1 |              0    |            0      |              0.25 |
| fixed_rate |            300 |                   368 |         2.6335e+06 |         7156.25 |            0        |                 0.991304 |         0.0866667 |                    12 |                     900 |          0.533333 |                1 |           1226.67 |           13.9394 |              0.25 |
| allocator  |            300 |                   368 |         2.6335e+06 |         7156.25 |            0        |                 0.991304 |         0.0866667 |                    12 |                     900 |          0.533333 |                1 |           1226.67 |           13.9394 |              0.25 |
| check_none |            300 |                     0 |         0          |            0    |            0.266055 |                 0        |         0.273333  |                     4 |                       0 |         -1        |                1 |              0    |            0      |              0.4  |
| fixed_rate |            300 |                   384 |         2.7755e+06 |         7227.86 |            0        |                 0.991667 |         0.07      |                    12 |                     900 |          0        |                1 |           1280    |           14.5455 |              0.4  |
| allocator  |            300 |                   384 |         2.8135e+06 |         7326.82 |            0        |                 0.983333 |         0.0733333 |                    12 |                     900 |          0        |                1 |           1280    |           14.5455 |              0.4  |
| check_none |            300 |                     0 |         0          |            0    |            0.266055 |                 0        |         0.273333  |                     4 |                       0 |         -1        |                1 |              0    |            0      |              0.6  |
| fixed_rate |            300 |                   576 |         3.7792e+06 |         6561.11 |            0        |                 0.777778 |         0         |                    12 |                     900 |          0        |                1 |           1920    |           21.8182 |              0.6  |
| allocator  |            300 |                   576 |         3.6525e+06 |         6341.15 |            0        |                 0.722222 |         0.0333333 |                    12 |                     900 |          0        |                1 |           1920    |           21.8182 |              0.6  |
| check_none |            300 |                     0 |         0          |            0    |            0.266055 |                 0        |         0.273333  |                     4 |                       0 |         -1        |                1 |              0    |            0      |              0.8  |
| fixed_rate |            300 |                   768 |         3.7792e+06 |         4920.83 |            0        |                 0.583333 |         0         |                    12 |                     900 |          0        |                1 |           2560    |           29.0909 |              0.8  |
| allocator  |            300 |                   768 |         3.7792e+06 |         4920.83 |            0        |                 0.583333 |         0         |                    12 |                     900 |          0        |                1 |           2560    |           29.0909 |              0.8  |
| check_none |            300 |                     0 |         0          |            0    |            0.266055 |                 0        |         0.273333  |                     4 |                       0 |         -1        |                1 |              0    |            0      |              1    |
| fixed_rate |            300 |                   960 |         3.7792e+06 |         3936.67 |            0        |                 0.466667 |         0         |                    12 |                     900 |          0        |                1 |           3200    |           36.3636 |              1    |
| allocator  |            300 |                   960 |         3.7792e+06 |         3936.67 |            0        |                 0.466667 |         0         |                    12 |                     900 |          0        |                1 |           3200    |           36.3636 |              1    |
| check_all  |            300 |                   960 |         3.7792e+06 |         3936.67 |            0        |                 0.466667 |         0         |                    12 |                     900 |          0        |                1 |           3200    |           36.3636 |              1    |

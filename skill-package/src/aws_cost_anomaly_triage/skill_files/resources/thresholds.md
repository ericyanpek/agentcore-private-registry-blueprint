# Internal cost anomaly thresholds

Internal-only — do not share outside FinOps and Platform teams.

| Scope | Active triage threshold | Page-the-team threshold |
|---|---|---|
| Production account, any service | $200 / day or 20% MoM | $1000 / day or 50% MoM |
| Non-prod account, any service | $500 / day or 50% MoM | $2000 / day or 100% MoM |
| Single workload (by tag `app`) | $100 / day or 30% MoM | $500 / day or 75% MoM |
| New service activation | Any > $0 unscheduled | Any > $50 / day |

These are illustrative numbers for the demo. In a real environment
they would be calibrated against actual baseline spend.

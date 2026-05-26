---
name: aws-cost-anomaly-triage
description: Use when the user reports an unexpected AWS cost spike, an alert from AWS Cost Anomaly Detection, or asks "why did my AWS bill go up". Walks through a structured triage SOP using Cost Explorer, CUR, and service-specific signals before recommending remediation.
---

# AWS Cost Anomaly Triage

This skill encodes the internal SOP our FinOps team uses when an AWS
cost anomaly is raised. Apply it whenever you see a cost spike alert,
an unfamiliar line item on the bill, or a customer-reported overage.

## When to invoke
- An anomaly is reported by AWS Cost Anomaly Detection (email, Slack, EventBridge)
- Month-over-month spend on any service rises by more than the threshold in `resources/thresholds.md`
- A customer or team asks "why is my AWS bill higher than expected"

## Triage workflow

Follow these steps **in order**. Do not skip ahead even if the cause
seems obvious — early steps surface confounding factors that shape
later recommendations.

### Step 1 — Bound the anomaly
1. Identify the **time window** (start, end, ongoing?). Use Cost Explorer
   `GetCostAndUsage` grouped by `SERVICE` over the past 30 days at daily
   granularity.
2. Identify the **scope**: account, region, service, usage type, linked
   account, or tag dimension. Always confirm the anomaly persists when
   you remove plausible confounders (RI/SP amortization, credits,
   refunds — see `resources/confounders.md`).
3. Quantify: absolute $ delta and % delta. If <$50 or <5%, downgrade to
   monitoring rather than active triage.

### Step 2 — Classify
Match against the patterns in `resources/anomaly-patterns.md`. The
common ones in order of frequency:
- Compute scale-up (EC2/Fargate/Lambda)
- Data transfer (especially cross-AZ and NAT GW egress)
- Storage growth (S3 standard creep, EBS snapshots)
- New service activation (Bedrock, OpenSearch, Aurora upgrade)
- Tagging gap surfacing previously hidden cost
- Credit / discount expiration

### Step 3 — Drill down
Use service-specific dashboards listed in
`resources/per-service-drilldown.md`. Always check:
- CloudTrail for unusual `Run*` / `Create*` API spikes around the
  anomaly start time
- Cost and Usage Report (CUR) at hourly granularity if Cost Explorer
  daily isn't enough
- Resource tags to attribute to a team or workload

### Step 4 — Decide remediation
Map the classified cause to one of the responses in
`resources/remediation-playbook.md`. Never propose:
- Disabling a security service (GuardDuty, Macie, Detective) without
  the security team's written sign-off
- Deleting CloudTrail logs or VPC Flow Logs to save storage
- Removing tags to "simplify"

### Step 5 — Document
Write up findings using the template in `resources/postmortem-template.md`.
File it in the FinOps tracker even if cause was benign — the patterns
compound across incidents.

## Resources
- [Confounders to rule out](resources/confounders.md)
- [Anomaly patterns library](resources/anomaly-patterns.md)
- [Per-service drilldown links](resources/per-service-drilldown.md)
- [Remediation playbook](resources/remediation-playbook.md)
- [Postmortem template](resources/postmortem-template.md)
- [Internal thresholds](resources/thresholds.md)

## What this skill is NOT
- Not a substitute for Cost Optimization Hub or Trusted Advisor
  recommendations — those are starting points, not conclusions.
- Not for capacity planning or pricing-model selection (RI/SP). Use the
  `aws-savings-plan-modeling` skill for those.

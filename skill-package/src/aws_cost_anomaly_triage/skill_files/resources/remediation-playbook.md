# Remediation playbook

Map the classified pattern (A–F) to a remediation. Always pair a
remediation with a guardrail so the same anomaly cannot recur silently.

## Pattern A — Compute scale-up
- **Remediation**: rightsizing recommendation from Compute Optimizer,
  or instance termination if work is already done
- **Guardrail**: Service Control Policy denying `RunInstances` for
  instance types > 8xlarge in non-prod accounts; budget alert at the
  team OU

## Pattern B — Data transfer surge
- **Remediation**: introduce VPC endpoint (S3, DynamoDB, Bedrock) to
  remove NAT GW path; or move workload into same AZ as data
- **Guardrail**: Network Access Analyzer scheduled scan for
  cross-AZ paths; CloudWatch alarm on NAT GW bytes

## Pattern C — Storage creep
- **Remediation**: enable S3 Lifecycle to Intelligent-Tiering or
  Glacier IR; reduce snapshot retention
- **Guardrail**: AWS Config rule
  `s3-bucket-default-lock-enabled` or
  `s3-lifecycle-policy-check`

## Pattern D — New service activation
- **Remediation**: deactivate if unauthorized; if authorized, set up
  budget and tag the resource
- **Guardrail**: SCP `Deny` on `Create*` for the service in accounts
  that should not host it

## Pattern E — Tagging gap closure
- **Remediation**: usually no remediation needed — this is correct
  cost being attributed to its real owner
- **Guardrail**: Tag Policy enforcement at the OU level

## Pattern F — Discount expiration
- **Remediation**: renew RI / SP for steady-state usage; consider
  Compute SP for flexibility
- **Guardrail**: Cost Explorer "Reservation Expiration" report
  scheduled monthly to inbox

## Hard NOs
Never recommend any of the following as cost remediation:
- Disabling GuardDuty, Macie, Detective, Security Hub, Inspector
- Deleting CloudTrail logs (1-year retention is regulatory minimum)
- Deleting VPC Flow Logs while in incident-response window
- Removing resource tags
- Reducing RDS backup retention below 7 days
- Disabling Multi-AZ on production databases

If a stakeholder asks for any of the above to save cost, escalate to
the FinOps Steering Committee — do not implement.

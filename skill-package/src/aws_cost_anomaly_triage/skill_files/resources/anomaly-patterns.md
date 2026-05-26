# Anomaly pattern library

Ordered by historical frequency in our environment. Match the
observed signals to the closest pattern, then jump to its drilldown
section in `per-service-drilldown.md`.

## Pattern A — Compute scale-up
- Signals: EC2/Fargate/Lambda usage hours up, new instance IDs in
  CloudTrail, autoscaling activity in CloudWatch
- Common causes: load test left running, autoscaling min capacity
  raised, new service deployed without rightsizing
- First check: CloudTrail `RunInstances` / `CreateService` /
  `CreateFunction` events

## Pattern B — Data transfer surge
- Signals: `DataTransfer-Out-Bytes` or `NatGateway-Bytes` line items up
- Common causes: cross-AZ chatter from a new microservice, S3 download
  from outside region, missing VPC endpoint
- First check: VPC Flow Logs aggregated by `dstaddr` for the affected
  AZ/region

## Pattern C — Storage creep
- Signals: S3 `TimedStorage-ByteHrs` or EBS `VolumeUsage` up
- Common causes: lifecycle policy missing, snapshot retention ramping,
  backup-AMI accumulation
- First check: S3 Storage Lens dashboard, `aws ec2 describe-snapshots`

## Pattern D — New service activation
- Signals: brand-new service line item appears
- Common causes: someone enabled Bedrock / OpenSearch / Aurora /
  GuardDuty without approval; trial period ended
- First check: CloudTrail across all regions for the service's
  `Create*` events

## Pattern E — Tagging gap closure
- Signals: tagged-cost goes up by amount equal to drop in
  untagged-cost
- Common causes: tagging policy enforcement, automation backfill
- First check: Cost Explorer grouped by tag `team` (or your equivalent)
  with "Show untagged" enabled

## Pattern F — Discount expiration
- Signals: net cost up but usage unchanged
- Common causes: SP/RI expiring, EDP/PPA renegotiation, credit
  exhausted
- First check: Billing Console → Cost Management → Reservations &
  Savings Plans → expirations

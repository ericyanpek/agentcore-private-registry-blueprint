# Per-service drilldown links

For each high-cost service, the canonical first-look dashboard /
query and the CloudTrail event names that surface scale-up.

| Service | First dashboard | Key CloudTrail events |
|---|---|---|
| EC2 | Compute Optimizer + EC2 dashboard | `RunInstances`, `StartInstances`, `ModifyInstanceAttribute` |
| Lambda | Lambda → Functions sorted by cost | `CreateFunction`, `UpdateFunctionConfiguration` |
| Fargate / ECS | ECS dashboard, Cluster/Service breakdown | `CreateService`, `UpdateService`, `RegisterTaskDefinition` |
| S3 | S3 Storage Lens (org-wide) | `CreateBucket`, `PutBucketLifecycleConfiguration` (absence) |
| EBS | Snapshot lifecycle dashboard | `CreateVolume`, `CreateSnapshot` |
| RDS / Aurora | Performance Insights → DB cost | `CreateDBInstance`, `ModifyDBInstance` |
| NAT Gateway | VPC Flow Logs aggregated by ENI | `CreateNatGateway` |
| CloudFront | CloudFront → Distribution metrics | `CreateDistribution` |
| Bedrock | Bedrock Console → Usage tab | `InvokeModel*` API call counts |
| OpenSearch | OpenSearch Service domain dashboard | `CreateDomain`, `UpdateDomainConfig` |
| GuardDuty / Macie / Detective | Security Hub, security team owns | `Enable*` (rarely a cost anomaly worth deactivating) |

When the service is not in this table:
1. Cost Explorer → group by `USAGE_TYPE` to find the specific SKU
2. Search SKU code in AWS pricing API for full description
3. Pivot back to the owning service's CloudTrail events

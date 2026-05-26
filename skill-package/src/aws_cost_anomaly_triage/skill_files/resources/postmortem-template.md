# Cost anomaly postmortem template

Fill out and file in the FinOps tracker within 5 business days of
anomaly detection. Even benign anomalies should be documented.

```
## Anomaly summary
- Detected by: [Cost Anomaly Detection / human / customer report]
- Detection time:
- Affected scope: [account / region / service / tag]
- Magnitude: $X over Y days (Z% over baseline)
- Status: [resolved / monitoring / accepted]

## Timeline
- T-0: anomaly first observed
- T+...: triage steps and findings

## Classified pattern
[A-F from anomaly-patterns.md, or "novel" with full description]

## Root cause
[1-3 sentences]

## Remediation taken
[What was done, who did it, when]

## Guardrail added
[What prevents this exact anomaly recurring]

## Cost recovered
[$ saved by remediation, or "n/a" if accepted cost]

## Follow-ups
- [ ] action item with owner and date
```

# aws-cost-anomaly-triage

Agent skill packaged as a PyPI distribution. When installed, the
`install-aws-cost-anomaly-triage` console script copies the skill
files into `~/.claude/skills/aws-cost-anomaly-triage/` so they become
discoverable by Claude Code (and any agent that reads that directory).

This is a text-only skill: it ships a `SKILL.md` plus reference
resources, no business logic Python code. The `pyproject.toml` is
used purely as an artifact distribution mechanism via PyPI / AWS
CodeArtifact.

## Install (consumer)

```
aws codeartifact login --tool pip --domain skills-demo --repository skills-prod --region us-east-1
pip install aws-cost-anomaly-triage
install-aws-cost-anomaly-triage
```

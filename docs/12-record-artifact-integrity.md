# Record ↔ artifact integrity — is what you discovered what you ran?

The Registry is a metadata and governance service. It does not host
artifacts and does not install anything (see the mental-model section in
the README). That decoupling is the right design, but it has a direct
consequence that this blueprint should state plainly:

> **The Registry cannot, by itself, guarantee that the thing you
> discovered is the thing you executed.** It stores a pointer. Keeping the
> pointer and the pointed-at bytes in agreement has to be enforced
> somewhere else.

This page is about where that "somewhere else" is.

## Four different consistency questions

These get conflated, which produces the wrong fix. They are separate
problems with separate mechanisms.

| # | Gap | Question | Enforced by |
|---|---|---|---|
| 1 | record ↔ artifact bytes | The record says `version: 0.1.0`. Are the bytes I install the bytes that were approved? | digest pinning |
| 2 | `skillMd` ↔ wheel's `SKILL.md` | Two copies of the same file exist. Do they agree? | CI assertion at publish time |
| 3 | approved revision ↔ installed version | Approval happened on a revision. Installation resolves later. Same thing? | version pinning + approval-status check |
| 4 | remote record ↔ local `~/.claude/skills/` | The local copy is authoritative once installed. Has anyone edited it? | local attestation manifest |

Gap 2 is self-inflicted and worth calling out: this blueprint stores
`SKILL.md` **twice** — once in the record as
`agentSkills.skillMd.inlineContent`, once inside the wheel. Two copies
with no structural link is a drift generator.

## The split that matters: two consumption paths need different mechanisms

The README's mental model describes two ways Claude Code uses a discovered
skill. For integrity purposes they are **not** variants of one problem:

**Path (b) — persistent install.** The record is a pointer; the wheel is
what executes. Integrity means binding the record to specific bytes, i.e.
a **sha256 digest** the consumer verifies before use. This path can reach
cryptographic-strength assurance.

**Path (a) — embed `SKILL.md` into context for one-off use.** No artifact
is ever fetched. **The record itself is the thing being executed.** A
digest on `packages[]` protects nothing here, because nothing in
`packages[]` is read. What matters is that `skillMd` is trustworthy on its
own terms — CI-derived from the wheel and never hand-written, and treated
as a first-class subject of approval rather than a convenience cache.

This is the most commonly missed point. Adding digests to a registry feels
like solving artifact integrity, but it only covers one of the two paths.
For a skill registry, where "read the SOP and follow it" is a legitimate
and common consumption mode, the *metadata* is executable content.

## Where this repo stands today

Honest accounting, verified against the current code.

`scripts/02_register_skill.py` advertises the package like this:

```python
"packages": [
    {
        "registryType": "pypi",
        "identifier": PYPI_PACKAGE_NAME,
        "version": RECORD_VERSION,
    }
],
```

**No digest.** The strongest statement the record makes is "the skill lives
at this name and version in this repository." That is an identity claim,
not an integrity claim.

What *is* already correct: `scripts/04_consume_skill.py` pins the version
it read from the record —

```python
[str(pip), "install", "--quiet", f"{pkg_name}=={pkg_version}"]
```

so a consumer does not silently float to a newer, unapproved version. The
gap is narrower than "pip installs latest," and also more subtle:

| Gap | Status here |
|---|---|
| 1 — record ↔ bytes | ❌ open. Version-pinned, not digest-pinned |
| 2 — `skillMd` ↔ wheel | ❌ open. No publish-time equality check |
| 3 — approved ↔ installed | 🟡 partial. Version is pinned; approval status of that exact revision isn't re-checked at install |
| 4 — remote ↔ local | ❌ open. `postinstall.py` does `shutil.copytree` and records no provenance |

### Why a version number is weaker than a digest

The specific reason this matters for CodeArtifact, rather than as a general
principle:

CodeArtifact **refuses to republish an asset with different content** —
same name with different bytes returns HTTP 409. So within the life of one
package version, bytes are stable. But a package version **can be deleted**
via `DeletePackageVersions`, and after deletion *"you can freely re-publish
that package version."*

So the sequence delete `0.1.0` → publish a different `0.1.0` is available
to anyone with publish rights, and a record that pins only
`version: 0.1.0` **cannot detect it**. A record pinning a sha256 can.

This is not a hypothetical about a malicious insider; the same sequence
happens when someone "fixes a typo and re-cuts the same version" — the
common, well-intentioned version of the problem.

Related hardening while you're here: `PutPackageOriginConfiguration` can
block upstream publishing for internal package names, which is the
dependency-confusion defense for a repo with an external connection.

## Mechanisms, ordered by strength per unit of effort

### 1. Digest pinning (highest value, available today)

At publish time, read the wheel's hash and put it in the record. CodeArtifact
computes it for you — `ListPackageVersionAssets` returns per-asset `hashes`
including `SHA-256`, so there is no need to hash locally and hope it matches
what was stored:

```
aws codeartifact list-package-version-assets \
  --domain skills-demo --repository skills-prod \
  --format pypi --package aws-cost-anomaly-triage --package-version 0.1.0
```

Carry it in the record. The `skillDefinition` schema has no digest field
for `packages[]`, so until it does, `_meta` is the right home — this repo
already uses reverse-DNS `_meta` extensions for CodeArtifact coordinates
and activation hints:

```json
"_meta": {
  "com.example.integrity": {
    "assetName": "aws_cost_anomaly_triage-0.1.0-py3-none-any.whl",
    "sha256": "<from ListPackageVersionAssets>"
  }
}
```

Consumer side, verify before executing anything. Note that
`pip install --require-hashes` requires a requirements file with every
transitive dependency hashed — worth doing for a locked-down consumer, but
for a text-only skill the direct check is simpler and honest about what it
covers:

```python
# after download, before postinstall
actual = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
if actual != expected_from_record:
    sys.exit("digest mismatch — record and artifact disagree; refusing to activate")
```

The trust shift is the point: from *"trust whatever currently sits at that
version number"* to *"trust these bytes."*

### 2. CI equality check for `skillMd` (closes gap 2, and the only defense for path a)

Assert at publish time that the record's `skillMd` content is byte-identical
to the `SKILL.md` inside the wheel being published. Fail the publish if not.

This is the check flagged as missing in `docs/06`. It is not fastidiousness:
for path (a) consumers, `skillMd` **is** the executed artifact, and this is
the only thing standing between "approved SOP" and "someone edited the
record afterwards."

Run it periodically too, not just at publish — a record can be updated after
approval, so a scheduled re-comparison is drift detection rather than a
one-time gate.

### 3. Re-check approval status at install time (closes gap 3)

`04_consume_skill.py` prints record status during search but doesn't gate on
it. Since `SearchRegistryRecords` returns only approved revisions while
`GetRegistryRecord` returns the latest revision of any status, a consumer
that searches, then gets, then installs can act on a record whose latest
revision is no longer approved. Verify the specific revision you are about
to install is APPROVED, and refuse otherwise.

### 4. Local attestation manifest (only mechanism that touches gap 4)

Have `postinstall.py` write provenance alongside the copied files — record
ARN, revision, package version, verified sha256, install timestamp. Then
local files can be re-hashed and compared later to detect edits to
`~/.claude/skills/`.

Without this, gap 4 is undetectable in principle: nothing about the
installed tree indicates where it came from or whether it still matches.
This is also the gap that shrinks the least with better registry features,
because it lives entirely on the consumer's disk.

### 5. Signing

cosign / sigstore over the artifact, with the public key or identity
recorded in the record. This is the real argument for the OCI item on the
`docs/06` roadmap — not that OCI is a more fashionable format, but that it
brings digest-addressing and signature attachment natively, whereas PyPI
requires bolting both on through `_meta` conventions.

## What GA's record synchronization tells us

The GA feature set makes the shape of this problem clearer, and reveals a
gap AWS has not filled.

**Record synchronization** solves discovery-vs-reality by construction: a
URL-configured record derives its metadata *from the running thing*, so the
description cannot drift from the deployment. Each sync creates a new
revision. That is a genuinely stronger guarantee than any digest scheme,
because there is only one source of truth rather than two that must be kept
equal.

But per the GA docs, auto-synchronization triggers **only** for the
`mcpServer` and `a2aAgentCard` primary descriptors — MCP and AGENT record
types. Explicitly:

- SKILL records **cannot** be auto-synchronized.
- A `source` on the `skillMd` child is *persisted but not used to run sync*.
- CUSTOM records must be created manually with `data` provided directly.

The reason is structural, not an oversight: skills are artifact-backed and
have no live endpoint to poll. **There is nothing to synchronize against.**

So the integrity picture splits by record type:

| | `MCP` / `A2A` | `AGENT_SKILLS` / `SKILL` |
|---|---|---|
| Source of truth | the live endpoint | the published artifact |
| Metadata freshness | managed by AWS, revision per sync | publisher's responsibility |
| Discovered-vs-actual | structurally guaranteed | **must be built** |
| Available mechanism | record synchronization | digest + CI equality check |

**AWS has closed the discovered-vs-actual gap for MCP servers and agents,
and left it open for skills.** That gap is precisely what a private skill
blueprint should fill — and it is a firmer version of this repo's
positioning claim than "AWS has no official private-distribution sample."
A missing sample is a documentation gap; this is a capability gap that
follows from artifact-backed resources not having endpoints to poll.

## Recommended minimum

For anyone adapting this blueprint into something real, in order:

1. Digest in the record + verification before activation (gaps 1, 3).
2. CI assertion that `skillMd` matches the wheel's `SKILL.md`, at publish
   and on a schedule (gap 2 — and the only protection for path a).
3. Attestation manifest written by `postinstall.py` (gap 4).

Signing and OCI are the strong form, and worth waiting for the packaging
standard to settle rather than inventing a local convention.

None of the above is implemented in this repo today. The status table in
this doc is the accurate picture; treat it as the work list.

→ Related: [roadmap](./06-future-optimizations.md) ·
[GA migration](./11-ga-migration.md)

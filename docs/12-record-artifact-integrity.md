# Record ↔ artifact integrity

Registry is a metadata/approval service, not a package installer.
This blueprint binds the approved description to the exact wheel and the copied skill files.

## Implemented in this revision

| Gap | Mechanism |
|---|---|
| Record ↔ artifact bytes | Wheel SHA-256 in the record, verified against CodeArtifact at publication and bytes at consumption |
| Record `skillMd` ↔ packaged `SKILL.md` | Metadata generated from the wheel; source equality at publication; exact equality at consumption |
| Approved release ↔ selected artifact | Exact name/version, discovery-plane-only reads, approved-content recheck after download |
| Remote release ↔ local files | Per-file hashes and provenance; local drift command; no implicit overwrite |

The shared implementation is in `registry_blueprint/artifacts.py`, `registry.py` and `consumer.py`.
This is a **blueprint-specific metadata convention**, not an AWS-standard digest schema:

```json
{
  "_meta": {
    "com.example.codeartifact": {
      "domain": "skills-demo",
      "repository": "skills-prod",
      "domainOwner": "111122223333",
      "region": "us-east-1"
    },
    "com.example.integrity": {
      "asset": "aws_cost_anomaly_triage-0.1.0-py3-none-any.whl",
      "sha256": "<64 lowercase hexadecimal characters>",
      "skillMdSha256": "<64 lowercase hexadecimal characters>",
      "skillPath": "aws_cost_anomaly_triage/skill_files/"
    }
  }
}
```

`packages` also pins the package identifier and version. GA wraps this definition inside
`descriptors.agentSkillsDefinition.data`; `additionalData.skillMd.data` contains the wheel-derived Markdown.

## Publication

The publisher builds one wheel in a fresh output directory, avoiding accidental uploads of old
artifacts. It inspects package identity, dependencies, archive paths and size limits.
It derives `skillMd` from the wheel, checks the source file for agreement, uploads the wheel,
then compares its SHA-256 with CodeArtifact's `ListPackageVersionAssets` hash.

Only then is the record created. The creator cannot approve it with the publisher role.
Existing identical name/version metadata can be reused; changed content requires a new release.
An interrupted upload/registration can be retried with `--wheel ... --skip-upload`;
remote digest validation is never skipped.

## Consumption

1. Search one explicitly configured registry for the exact name/version and `SKILL` type.
2. Batch-get approved details using the discovery plane. Do not read the latest governance record.
3. Verify the metadata names an independently configured trusted repository/owner/region.
4. Download the exact wheel asset through CodeArtifact's SDK, bounded to 20 MiB.
5. Verify SHA-256, filename and wheel METADATA identity, Markdown equality and safe archive paths.
6. Re-read approved discovery details and reject a changed or unavailable release.
7. Extract only `<module>/skill_files/` into a staging directory and rename it into place.

No wheel code, `postinstall.py`, installer entry point or Python dependency executes during activation.
The consumer ignores metadata installation commands and paths. The caller selects the target directory.
If the destination is different, modified or a symlink, activation fails rather than deleting it.

The current packaging scope is deliberately narrow: one platform-independent wheel with no
`Requires-Dist`, at most 20 MiB compressed/expanded and 1000 archive members, a `SKILL.md`
of at most 100 KiB, and one conventional skill directory.

## Local provenance

`.registry-provenance.json` records the registry/record identity, record version, package/source,
wheel hash, installation timestamp and hashes for every copied file.

```bash
python scripts/05_verify_installed_skill.py ~/.claude/skills/aws-cost-anomaly-triage
```

It detects changed, missing, extra files and symlinks. Identical reinstallation is a no-op.
Intentional upgrades require explicitly reviewing/removing the old installation; no silent downgrade
or overwrite mechanism is provided.

## What this does not prove

- A digest verifies consistency, not whether the skill is safe. Review executable instructions and bundled content.
- A local manifest is not signed. Someone who can edit both the files and manifest can forge local consistency.
- Approval and activation are not an atomic transaction. The recheck reduces races but the record can change
  after it, and discovery indexing is eventually consistent.
- Deprecation does not remove previously installed content, block offline execution or revoke CodeArtifact access.
- CodeArtifact download authorization is repository-based, not Registry-status-based. A caller can bypass
  this client; service-side approval gating needs a separate artifact-promotion design.
- Reading inline `skillMd` in an IDE does not run this wheel verifier or retrieve supporting files.
- MCP/A2A metadata synchronization improves freshness but does not prove runtime implementation integrity.
  It is not a substitute for artifact attestation or runtime authorization.

Signing, runtime enforcement, artifact promotion and online revocation checks remain future work.

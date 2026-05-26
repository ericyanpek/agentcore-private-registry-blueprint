#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { CodeArtifactStack } from '../lib/codeartifact-stack';
import { RegistryStack } from '../lib/registry-stack';
import { IdentityStack } from '../lib/identity-stack';

const app = new cdk.App();

const region = app.node.tryGetContext('blueprintRegion') ?? 'us-east-1';
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region,
};

const ca = new CodeArtifactStack(app, 'CodeArtifactStack', {
  env,
  domainName: app.node.tryGetContext('domainName') ?? 'skills-demo',
  repositoryName: app.node.tryGetContext('repositoryName') ?? 'skills-prod',
  description:
    'CodeArtifact PyPI repo backing the private skills blueprint',
});

new RegistryStack(app, 'AgentCoreRegistryStack', {
  env,
  registryName:
    app.node.tryGetContext('registryName') ?? 'skills-demo-registry',
  description:
    'Bedrock AgentCore Registry that catalogs skills published to ' +
    `${ca.domainName}/${ca.repositoryName}`,
});

// Optional end-user identity layer.
//   Set CDK context `enableIdentity=true` to deploy:
//     npx cdk deploy --all -c enableIdentity=true
//
//   Group → repo mapping is configured via context `groupRepoMap`:
//     -c 'groupRepoMap={"finops-readers":"finops-skills-prod","customer-care-readers":"customer-care-skills-prod"}'
//
// Reading docs/10-end-user-access.md before turning this on is
// strongly recommended — the Cognito user pool you create here is
// authoritative for end-user identity, so naming and group structure
// matter.
const enableIdentity = app.node.tryGetContext('enableIdentity') === 'true'
  || app.node.tryGetContext('enableIdentity') === true;
if (enableIdentity) {
  const groupRepoMapRaw = app.node.tryGetContext('groupRepoMap');
  let groupRepoMap: { [k: string]: string } = {};
  if (typeof groupRepoMapRaw === 'string') {
    groupRepoMap = JSON.parse(groupRepoMapRaw);
  } else if (groupRepoMapRaw && typeof groupRepoMapRaw === 'object') {
    groupRepoMap = groupRepoMapRaw as { [k: string]: string };
  }
  new IdentityStack(app, 'IdentityStack', {
    env,
    codeArtifactDomain: ca.domainName,
    groupRepoMap,
    defaultGroupAccessAllRepos:
      app.node.tryGetContext('defaultGroupAccessAllRepos') === 'true',
    description:
      'Cognito User Pool + Identity Pool layer for end-user JWT-based ' +
      'access to private skills (no IAM credentials on user machines).',
  });
}

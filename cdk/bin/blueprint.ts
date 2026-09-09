#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { CodeArtifactStack } from '../lib/codeartifact-stack';
import { RegistryStack } from '../lib/registry-stack';
import { IdentityStack } from '../lib/identity-stack';

const app = new cdk.App();
const stackPrefix = app.node.tryGetContext('stackPrefix') ?? '';
if (stackPrefix && !/^[A-Za-z][A-Za-z0-9-]{0,49}$/.test(stackPrefix)) {
  throw new Error('stackPrefix must start with a letter and contain at most 50 letters, digits or hyphens');
}
const stackId = (name: string): string => stackPrefix ? `${stackPrefix}-${name}` : name;

const region = app.node.tryGetContext('blueprintRegion') ?? 'us-east-1';
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region,
};

const ca = new CodeArtifactStack(app, stackId('CodeArtifactStack'), {
  env,
  domainName: app.node.tryGetContext('domainName') ?? 'skills-demo',
  repositoryName: app.node.tryGetContext('repositoryName') ?? 'skills-prod',
  description:
    'CodeArtifact PyPI repo backing the private skills blueprint',
});

const registry = new RegistryStack(app, stackId('AgentRegistryStack'), {
  env,
  registryName:
    app.node.tryGetContext('registryName') ?? 'skills-demo-registry',
  description:
    'AWS Agent Registry that catalogs skills published to ' +
    `${ca.domainName}/${ca.repositoryName}`,
});

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
  const groupRegistryMapRaw = app.node.tryGetContext('groupRegistryMap');
  const groupRegistryMap = typeof groupRegistryMapRaw === 'string'
    ? JSON.parse(groupRegistryMapRaw)
    : groupRegistryMapRaw ?? {};
  const enableDefaultReader = app.node.tryGetContext('enableDefaultReader') === 'true'
    || app.node.tryGetContext('enableDefaultReader') === true;
  new IdentityStack(app, stackId('IdentityStack'), {
    env,
    codeArtifactDomain: ca.domainName,
    groupRepoMap,
    groupRegistryMap,
    defaultAccess: enableDefaultReader
      ? { registryArn: registry.registryArn, repository: ca.repositoryName }
      : undefined,
    description:
      'Cognito User Pool + Identity Pool layer for end-user JWT-based ' +
      'access to private skills with temporary IAM credentials.',
  });
}

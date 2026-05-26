#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { CodeArtifactStack } from '../lib/codeartifact-stack';
import { RegistryStack } from '../lib/registry-stack';

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

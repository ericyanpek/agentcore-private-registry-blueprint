import * as cdk from 'aws-cdk-lib';
import * as agentregistry from 'aws-cdk-lib/aws-agentregistry';
import { Construct } from 'constructs';

export interface RegistryStackProps extends cdk.StackProps {
  registryName: string;
}

export class RegistryStack extends cdk.Stack {
  public readonly registryArn: string;
  public readonly registryId: string;

  constructor(scope: Construct, id: string, props: RegistryStackProps) {
    super(scope, id, props);

    const registry = new agentregistry.CfnRegistry(this, 'Registry', {
      name: props.registryName,
      description: 'Private skills registry with IAM discovery and manual approval',
      authorizerType: 'AWS_IAM',
      approvalConfiguration: { autoApprovalRules: [] },
    });
    registry.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    this.registryArn = registry.attrRegistryArn;
    this.registryId = registry.attrRegistryId;

    new cdk.CfnOutput(this, 'RegistryArn', { value: this.registryArn });
    new cdk.CfnOutput(this, 'RegistryId', { value: this.registryId });
    new cdk.CfnOutput(this, 'McpEndpoint', {
      value: cdk.Fn.sub(
        'https://agent-registry.${AWS::Region}.api.aws/' +
          'registries/${rid}/mcp',
        { rid: this.registryId },
      ),
      description:
        'MCP endpoint for IDE clients. See docs/04-dynamic-discovery.md',
    });
  }
}

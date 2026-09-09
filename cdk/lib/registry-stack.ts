import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

export interface RegistryStackProps extends cdk.StackProps {
  registryName: string;
}

export class RegistryStack extends cdk.Stack {
  public readonly registryArn: string;
  public readonly registryId: string;

  constructor(scope: Construct, id: string, props: RegistryStackProps) {
    super(scope, id, props);

    const registry = new cdk.CfnResource(this, 'Registry', {
      type: 'AWS::AgentRegistry::Registry',
      properties: {
        Name: props.registryName,
        Description: 'Private skills registry with IAM discovery and manual approval',
        AuthorizerType: 'AWS_IAM',
        ApprovalConfiguration: { AutoApprovalRules: [] },
      },
    });
    registry.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    this.registryArn = registry.getAtt('RegistryArn').toString();
    this.registryId = registry.getAtt('RegistryId').toString();

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

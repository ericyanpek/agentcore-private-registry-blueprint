import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import {
  AwsCustomResource,
  AwsCustomResourcePolicy,
  PhysicalResourceId,
} from 'aws-cdk-lib/custom-resources';
import { Construct } from 'constructs';

export interface RegistryStackProps extends cdk.StackProps {
  registryName: string;
}

/**
 * Provisions a Bedrock AgentCore Registry via AwsCustomResource.
 *
 * Why a custom resource?
 *   AWS Agent Registry is in public preview (2026-04). It does not
 *   yet have an `AWS::BedrockAgentCore::Registry` CloudFormation
 *   resource. We call the SDK directly via AwsCustomResource.
 *
 *   When the L1 resource ships, replace this stack with the
 *   declarative L1. The rest of the blueprint does not depend on
 *   this implementation choice.
 *
 * Lifecycle caveat:
 *   This construct does NOT delete the registry on `cdk destroy`.
 *   Reason: a registry can hold un-deleted records, and a forced
 *   delete via SDK would silently orphan them. The destroy path is:
 *
 *     1. Run the cleanup snippet in cdk/README.md (deletes records,
 *        then deletes the registry via SDK).
 *     2. Run `cdk destroy --all` (removes the CFN custom resource;
 *        the registry is already gone).
 *
 *   This matches how preview-stage AWS resources are commonly
 *   handled until L1 + cascade-delete support arrives.
 */
export class RegistryStack extends cdk.Stack {
  public readonly registryArn: string;
  public readonly registryId: string;

  constructor(scope: Construct, id: string, props: RegistryStackProps) {
    super(scope, id, props);

    const createCr = new AwsCustomResource(this, 'CreateRegistry', {
      onCreate: {
        service: 'bedrock-agentcore-control',
        action: 'CreateRegistry',
        parameters: {
          name: props.registryName,
          description:
            'Private skills registry — catalogs skills published to ' +
            'CodeArtifact. Manual approval; IAM auth.',
          approvalConfiguration: { autoApproval: false },
        },
        physicalResourceId: PhysicalResourceId.fromResponse('registryArn'),
      },
      // No onUpdate / onDelete on purpose — see class docstring.
      policy: AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          actions: [
            'bedrock-agentcore:CreateRegistry',
            'bedrock-agentcore:GetRegistry',
            'bedrock-agentcore:UpdateRegistry',
            'bedrock-agentcore:DeleteRegistry',
            'bedrock-agentcore:ListRegistries',
          ],
          resources: ['*'],
        }),
      ]),
      installLatestAwsSdk: true,
    });

    this.registryArn = createCr.getResponseField('registryArn');
    // ARN format: arn:aws:bedrock-agentcore:<region>:<acct>:registry/<id>
    this.registryId = cdk.Fn.select(
      1,
      cdk.Fn.split('registry/', this.registryArn),
    );

    new cdk.CfnOutput(this, 'RegistryArn', { value: this.registryArn });
    new cdk.CfnOutput(this, 'RegistryId', { value: this.registryId });
    new cdk.CfnOutput(this, 'McpEndpoint', {
      value: cdk.Fn.sub(
        'https://bedrock-agentcore.${AWS::Region}.amazonaws.com/' +
          'registries/${rid}/mcp',
        { rid: this.registryId },
      ),
      description:
        'MCP endpoint for IDE clients. See docs/04-dynamic-discovery.md',
    });
  }
}

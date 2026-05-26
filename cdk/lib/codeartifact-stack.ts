import * as cdk from 'aws-cdk-lib';
import * as codeartifact from 'aws-cdk-lib/aws-codeartifact';
import { Construct } from 'constructs';

export interface CodeArtifactStackProps extends cdk.StackProps {
  domainName: string;
  repositoryName: string;
}

/**
 * Provisions a CodeArtifact domain + a single PyPI repository to back
 * private skill artifact distribution. Uses AWS-managed KMS for at-rest
 * encryption (swap to a customer-managed CMK in Phase 2 — see
 * docs/05-auth-placeholder.md).
 */
export class CodeArtifactStack extends cdk.Stack {
  public readonly domainName: string;
  public readonly repositoryName: string;
  public readonly repositoryArn: string;

  constructor(scope: Construct, id: string, props: CodeArtifactStackProps) {
    super(scope, id, props);

    const domain = new codeartifact.CfnDomain(this, 'Domain', {
      domainName: props.domainName,
      // encryptionKey: omitted → AWS-managed KMS
    });

    const repo = new codeartifact.CfnRepository(this, 'Repository', {
      domainName: props.domainName,
      repositoryName: props.repositoryName,
      description: 'Private agent skills (text + resources, PyPI format)',
      // No upstreams or external connections — private only.
      // Add external connection 'public:pypi' in Phase 2 if you want
      // public-PyPI mirroring for transitive deps.
    });
    repo.addDependency(domain);

    this.domainName = props.domainName;
    this.repositoryName = props.repositoryName;
    this.repositoryArn = cdk.Fn.sub(
      'arn:aws:codeartifact:${AWS::Region}:${AWS::AccountId}:repository/' +
        '${dom}/${repo}',
      { dom: props.domainName, repo: props.repositoryName },
    );

    new cdk.CfnOutput(this, 'DomainName', { value: props.domainName });
    new cdk.CfnOutput(this, 'RepositoryName', {
      value: props.repositoryName,
    });
    new cdk.CfnOutput(this, 'RepositoryArn', { value: this.repositoryArn });
    new cdk.CfnOutput(this, 'PipIndexHint', {
      value: `aws codeartifact login --tool pip --domain ${props.domainName} ` +
        `--repository ${props.repositoryName} --region ${this.region}`,
    });
  }
}

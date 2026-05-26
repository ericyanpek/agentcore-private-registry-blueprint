import * as cdk from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

export interface IdentityStackProps extends cdk.StackProps {
  /**
   * The CodeArtifact domain whose repos this Identity Pool's groups
   * may pull from. The per-group IAM roles are scoped to repositories
   * within this domain.
   */
  codeArtifactDomain: string;

  /**
   * Map of Cognito group name → CodeArtifact repository it's allowed to pull.
   * E.g.,
   *   {
   *     'finops-readers': 'finops-skills-prod',
   *     'customer-care-readers': 'customer-care-skills-prod',
   *   }
   * If empty, only an "everyone" default reader role is created with
   * access to all repos in the domain.
   */
  groupRepoMap?: { [groupName: string]: string };

  /**
   * Whether to also create a "default" authenticated role that has
   * read access to all repos in the domain (i.e., for users in no
   * specific group). Recommended off in production; on for demo.
   */
  defaultGroupAccessAllRepos?: boolean;
}

/**
 * Provisions the Cognito identity layer that lets end-users (without
 * IAM credentials) consume skills.
 *
 * Architecture:
 *
 *   User Pool   (authenticates users; federation-friendly)
 *      │  JWT
 *      ▼
 *   Identity Pool   (translates JWT → temporary IAM credentials)
 *      │  per-group role assumed via STS:AssumeRoleWithWebIdentity
 *      ▼
 *   CodeArtifact   (standard IAM auth — sees the assumed role)
 *
 * The end-user runs `skill-cli login` (a ~80-line Python tool, see
 * skills/skill-cli/), which:
 *   1. opens browser for Cognito SSO
 *   2. trades id_token for temp IAM credentials via Identity Pool
 *   3. stores credentials in OS keyring (NOT a file)
 *   4. exposes them via the standard `credential_process` mechanism
 *
 * Result: the user's machine has zero AWS config files, and pip /
 * boto3 work as if they had IAM credentials. See docs/10-end-user-access.md
 * for the full design.
 */
export class IdentityStack extends cdk.Stack {
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;
  public readonly identityPoolId: string;

  constructor(scope: Construct, id: string, props: IdentityStackProps) {
    super(scope, id, props);

    // ── User Pool ──────────────────────────────────────────────
    this.userPool = new cognito.UserPool(this, 'SkillsUserPool', {
      userPoolName: 'skills-blueprint-user-pool',
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      autoVerify: { email: true },
      standardAttributes: {
        email: { required: true, mutable: false },
      },
      passwordPolicy: {
        minLength: 12,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      mfa: cognito.Mfa.OPTIONAL,
      mfaSecondFactor: { otp: true, sms: false },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.DESTROY, // demo only; use RETAIN in prod
    });

    // App Client — used by skill-cli's OAuth flow
    this.userPoolClient = this.userPool.addClient('SkillsCliClient', {
      userPoolClientName: 'skills-cli',
      authFlows: { userSrp: true },
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
        },
        scopes: [
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls: [
          'http://localhost:8765/callback', // skill-cli local OAuth listener
        ],
      },
      accessTokenValidity: cdk.Duration.hours(1),
      idTokenValidity: cdk.Duration.hours(1),
      refreshTokenValidity: cdk.Duration.days(30),
      preventUserExistenceErrors: true,
    });

    // ── Cognito groups (one per role/team) ─────────────────────
    // Always create the default readers group.
    new cognito.CfnUserPoolGroup(this, 'DefaultReadersGroup', {
      userPoolId: this.userPool.userPoolId,
      groupName: 'skills-readers',
      description: 'Default readers — can search and install approved skills',
      precedence: 100,
    });

    const groupRepoMap = props.groupRepoMap ?? {};
    for (const [groupName] of Object.entries(groupRepoMap)) {
      new cognito.CfnUserPoolGroup(this, `Group_${groupName}`, {
        userPoolId: this.userPool.userPoolId,
        groupName,
        description: `Skills consumers for ${groupName}`,
        precedence: 50,
      });
    }

    // ── Identity Pool ──────────────────────────────────────────
    const identityPool = new cognito.CfnIdentityPool(this, 'SkillsIdentityPool', {
      identityPoolName: 'skills_blueprint_identity_pool',
      allowUnauthenticatedIdentities: false,
      cognitoIdentityProviders: [{
        clientId: this.userPoolClient.userPoolClientId,
        providerName: this.userPool.userPoolProviderName,
        serverSideTokenCheck: true,
      }],
    });
    this.identityPoolId = identityPool.ref;

    // Helper to build a role assumable by Identity Pool authenticated users
    const buildAuthenticatedRole = (
      logicalId: string, repos: string[],
    ): iam.Role => {
      const role = new iam.Role(this, logicalId, {
        assumedBy: new iam.FederatedPrincipal(
          'cognito-identity.amazonaws.com',
          {
            'StringEquals': {
              'cognito-identity.amazonaws.com:aud': identityPool.ref,
            },
            'ForAnyValue:StringLike': {
              'cognito-identity.amazonaws.com:amr': 'authenticated',
            },
          },
          'sts:AssumeRoleWithWebIdentity',
        ),
        description: `Skills reader role — ${logicalId}`,
        maxSessionDuration: cdk.Duration.hours(1),
      });

      // CodeArtifact pull permissions
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'CodeArtifactPullOnly',
        actions: [
          'codeartifact:GetAuthorizationToken',
          'codeartifact:GetRepositoryEndpoint',
          'codeartifact:ReadFromRepository',
          'codeartifact:GetPackageVersionAsset',
          'codeartifact:GetPackageVersionReadme',
          'codeartifact:DescribePackage',
          'codeartifact:DescribePackageVersion',
          'codeartifact:ListPackageVersions',
          'codeartifact:ListPackageVersionAssets',
          'codeartifact:ListPackages',
          'codeartifact:ListRepositories',
        ],
        resources: repos.length === 0
          ? ['*']
          : repos.flatMap((repo) => [
              `arn:aws:codeartifact:${this.region}:${this.account}:domain/${props.codeArtifactDomain}`,
              `arn:aws:codeartifact:${this.region}:${this.account}:repository/${props.codeArtifactDomain}/${repo}`,
              `arn:aws:codeartifact:${this.region}:${this.account}:package/${props.codeArtifactDomain}/${repo}/pypi/*/*`,
            ]),
      }));
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'CodeArtifactBearerToken',
        actions: ['sts:GetServiceBearerToken'],
        resources: ['*'],
        conditions: {
          StringEquals: {
            'sts:AWSServiceName': 'codeartifact.amazonaws.com',
          },
        },
      }));

      // Registry read permissions (search + MCP invoke)
      role.addToPolicy(new iam.PolicyStatement({
        sid: 'RegistryReadOnly',
        actions: [
          'bedrock-agentcore:ListRegistries',
          'bedrock-agentcore:GetRegistry',
          'bedrock-agentcore:ListRegistryRecords',
          'bedrock-agentcore:GetRegistryRecord',
          'bedrock-agentcore:SearchRegistryRecords',
          'bedrock-agentcore:InvokeRegistryMcp',
        ],
        resources: [`arn:aws:bedrock-agentcore:${this.region}:${this.account}:registry/*`],
      }));

      return role;
    };

    // Default authenticated role (skills-readers / catch-all)
    const defaultRole = buildAuthenticatedRole(
      'DefaultReaderRole',
      props.defaultGroupAccessAllRepos ? [] : [],
    );

    // Per-group roles
    const groupRoles: { [groupName: string]: iam.Role } = {};
    for (const [groupName, repoName] of Object.entries(groupRepoMap)) {
      const role = buildAuthenticatedRole(
        `Role_${groupName}`,
        [repoName],
      );
      groupRoles[groupName] = role;
    }

    // ── Role Mapping (group → role) ────────────────────────────
    // CFN map keys must be literal strings. The provider key contains
    // unresolved tokens (UserPool id + Client id), so we wrap the
    // entire roleMappings object in a CfnJson, which defers JSON
    // serialization until deployment time when tokens are concrete.
    const providerKey = `cognito-idp.${this.region}.amazonaws.com/${this.userPool.userPoolId}:${this.userPoolClient.userPoolClientId}`;

    const rules: cognito.CfnIdentityPoolRoleAttachment.MappingRuleProperty[] =
      Object.entries(groupRoles).map(([groupName, role]) => ({
        claim: 'cognito:groups',
        matchType: 'Contains',
        value: groupName,
        roleArn: role.roleArn,
      }));

    const roleMappingsValue = rules.length > 0
      ? new cdk.CfnJson(this, 'RoleMappingsJson', {
          value: {
            [providerKey]: {
              Type: 'Rules',
              AmbiguousRoleResolution: 'Deny',
              IdentityProvider: providerKey,
              RulesConfiguration: {
                Rules: rules.map((r) => ({
                  Claim: r.claim,
                  MatchType: r.matchType,
                  Value: r.value,
                  RoleARN: r.roleArn,
                })),
              },
            },
          },
        })
      : undefined;

    new cognito.CfnIdentityPoolRoleAttachment(this, 'RoleAttachment', {
      identityPoolId: identityPool.ref,
      roles: {
        authenticated: defaultRole.roleArn,
      },
      roleMappings: roleMappingsValue,
    });

    // ── Outputs ────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'UserPoolId', {
      value: this.userPool.userPoolId,
      description: 'For skill-cli config / OIDC discovery URL',
    });
    new cdk.CfnOutput(this, 'UserPoolClientId', {
      value: this.userPoolClient.userPoolClientId,
      description: 'OAuth client id for skill-cli',
    });
    new cdk.CfnOutput(this, 'IdentityPoolId', {
      value: identityPool.ref,
      description: 'For Identity Pool credentials exchange',
    });
    new cdk.CfnOutput(this, 'OidcDiscoveryUrl', {
      value: `https://cognito-idp.${this.region}.amazonaws.com/${this.userPool.userPoolId}/.well-known/openid-configuration`,
      description: 'For Registry JWT authorizer config (if used directly)',
    });
  }
}

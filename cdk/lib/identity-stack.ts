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
   * Each group must also have an explicit entry in groupRegistryMap.
   */
  groupRepoMap?: { [groupName: string]: string };

  groupRegistryMap?: { [groupName: string]: string[] };
  defaultAccess?: { registryArn: string; repository: string };
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
 * The end-user runs `skill-cli login` (a ~500-line Python tool, see
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
    const groupRegistryMap = props.groupRegistryMap ?? {};
    if (
      Object.keys(groupRepoMap).sort().join(',') !==
      Object.keys(groupRegistryMap).sort().join(',')
    ) {
      throw new Error('groupRepoMap and groupRegistryMap must contain the same groups');
    }
    for (const registryArns of Object.values(groupRegistryMap)) {
      if (registryArns.length === 0 || registryArns.some(
        (arn) => !/^arn:aws(?:-[a-z]+)*:agent-registry:[a-z0-9-]+:[0-9]{12}:registry\/[a-zA-Z0-9]{12,16}$/.test(arn),
      )) {
        throw new Error('Each group needs explicit GA registry ARNs; wildcards are not allowed');
      }
    }
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

    const buildAuthenticatedRole = (
      logicalId: string, repository: string | undefined, registryArns: string[],
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

      if (repository !== undefined) {
        if (!/^[a-z][a-z0-9._-]{1,99}$/.test(repository)) {
          throw new Error('Repository names must be explicit, without wildcards');
        }
        role.addToPolicy(new iam.PolicyStatement({
          sid: 'DownloadSkillAsset',
          actions: ['codeartifact:GetPackageVersionAsset'],
          resources: [
            `arn:${this.partition}:codeartifact:${this.region}:${this.account}:package/${props.codeArtifactDomain}/${repository}/pypi/*/*`,
          ],
        }));
      }
      if (registryArns.length > 0) {
        role.addToPolicy(new iam.PolicyStatement({
          sid: 'DiscoverApprovedSkills',
          actions: [
            'agent-registry:SearchDiscoverableRegistryRecords',
            'agent-registry:ListDiscoverableRegistryRecords',
            'agent-registry:InvokeRegistryMcp',
          ],
          resources: registryArns,
        }));
        role.addToPolicy(new iam.PolicyStatement({
          sid: 'ReadApprovedSkills',
          actions: ['agent-registry:GetDiscoverableRegistryRecord'],
          resources: registryArns.map((arn) => `${arn}/record/*`),
        }));
      }

      return role;
    };

    const defaultRole = buildAuthenticatedRole(
      'DefaultReaderRole',
      props.defaultAccess?.repository,
      props.defaultAccess ? [props.defaultAccess.registryArn] : [],
    );

    // Per-group roles
    const groupRoles: { [groupName: string]: iam.Role } = {};
    for (const [groupName, repoName] of Object.entries(groupRepoMap)) {
      const role = buildAuthenticatedRole(
        `Role_${groupName}`,
        repoName,
        groupRegistryMap[groupName],
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
    new cdk.CfnOutput(this, 'DefaultReaderRoleArn', { value: defaultRole.roleArn });
    for (const [groupName, role] of Object.entries(groupRoles)) {
      new cdk.CfnOutput(this, `ReaderRole_${groupName}`, { value: role.roleArn });
    }
    new cdk.CfnOutput(this, 'OidcDiscoveryUrl', {
      value: `https://cognito-idp.${this.region}.amazonaws.com/${this.userPool.userPoolId}/.well-known/openid-configuration`,
      description: 'For Registry JWT authorizer config (if used directly)',
    });
  }
}

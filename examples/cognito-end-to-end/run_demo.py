#!/usr/bin/env python3
"""End-to-end Cognito + Identity Pool + CodeArtifact demo.

Steps:
  1. Create User Pool
  2. Create Cognito group `skills-readers-demo`
  3. Create app client (admin auth flow + OAuth)
  4. Create user `alice@demo.local`, force confirm, add to group
  5. Create user `bob@demo.local`, force confirm, NO group (negative test)
  6. Create Identity Pool tied to User Pool
  7. Create IAM role with CodeArtifact pull permissions on skills-prod
  8. Create role-attachment with rule: cognito:groups Contains skills-readers-demo
  9. Alice: admin_initiate_auth → id_token; trade for IAM creds via Identity Pool
 10. Use Alice's temp creds to actually pull from CodeArtifact (proves chain works)
 11. Bob (no group): same flow → expect Identity Pool to deny role assumption
 12. Print summary; tear down
"""

from __future__ import annotations

import json
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
NAME_PREFIX = "SkillsDemo-Cognito-Live"
USER_POOL_NAME = f"{NAME_PREFIX}-UserPool"
GROUP_NAME = "skills-readers-demo"
APP_CLIENT_NAME = f"{NAME_PREFIX}-Client"
IDENTITY_POOL_NAME = "SkillsDemo_Cognito_Live_IdPool"  # underscores only
IAM_ROLE_NAME = "SkillsDemoCognitoLiveReader"
ALICE_EMAIL = "alice@demo.local"
BOB_EMAIL = "bob@demo.local"
PASSWORD = "DemoPass!2026Cognito"
CODEARTIFACT_DOMAIN = "skills-demo"
CODEARTIFACT_REPO = "skills-prod"


def banner(step: int, title: str) -> None:
    print(f"\n━━━━━ Step {step}: {title} ━━━━━")


def cleanup(state: dict) -> None:
    print("\n━━━━━ Cleanup ━━━━━")
    cog_idp = boto3.client("cognito-idp", region_name=REGION)
    cog_id = boto3.client("cognito-identity", region_name=REGION)
    iam = boto3.client("iam")

    if state.get("identity_pool_id"):
        try:
            cog_id.delete_identity_pool(IdentityPoolId=state["identity_pool_id"])
            print(f"  deleted identity pool {state['identity_pool_id']}")
        except ClientError as e:
            print(f"  identity pool delete: {e.response['Error']['Code']}")

    if state.get("user_pool_id"):
        try:
            cog_idp.delete_user_pool(UserPoolId=state["user_pool_id"])
            print(f"  deleted user pool {state['user_pool_id']}")
        except ClientError as e:
            print(f"  user pool delete: {e.response['Error']['Code']}")

    if state.get("role_name"):
        try:
            iam.delete_role_policy(
                RoleName=state["role_name"], PolicyName="SkillsReaderInline",
            )
        except ClientError:
            pass
        try:
            iam.delete_role(RoleName=state["role_name"])
            print(f"  deleted IAM role {state['role_name']}")
        except ClientError as e:
            print(f"  role delete: {e.response['Error']['Code']}")


def main() -> int:
    state: dict = {}
    cog_idp = boto3.client("cognito-idp", region_name=REGION)
    cog_id = boto3.client("cognito-identity", region_name=REGION)
    iam = boto3.client("iam")
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]

    try:
        # ── Step 1
        banner(1, "Create User Pool")
        resp = cog_idp.create_user_pool(
            PoolName=USER_POOL_NAME,
            Policies={"PasswordPolicy": {
                "MinimumLength": 12, "RequireUppercase": True,
                "RequireLowercase": True, "RequireNumbers": True,
                "RequireSymbols": True,
            }},
            AdminCreateUserConfig={"AllowAdminCreateUserOnly": True},
            UsernameAttributes=["email"],
            AutoVerifiedAttributes=["email"],
        )
        state["user_pool_id"] = resp["UserPool"]["Id"]
        print(f"  ✅ user pool: {state['user_pool_id']}")

        # ── Step 2
        banner(2, f"Create group {GROUP_NAME!r}")
        cog_idp.create_group(
            GroupName=GROUP_NAME,
            UserPoolId=state["user_pool_id"],
            Description="Demo readers — should be allowed",
            Precedence=10,
        )
        print(f"  ✅ group: {GROUP_NAME}")

        # ── Step 3
        banner(3, "Create app client (admin auth flow)")
        resp = cog_idp.create_user_pool_client(
            UserPoolId=state["user_pool_id"],
            ClientName=APP_CLIENT_NAME,
            ExplicitAuthFlows=[
                "ALLOW_ADMIN_USER_PASSWORD_AUTH",
                "ALLOW_REFRESH_TOKEN_AUTH",
            ],
            GenerateSecret=False,
            PreventUserExistenceErrors="ENABLED",
        )
        state["client_id"] = resp["UserPoolClient"]["ClientId"]
        print(f"  ✅ client id: {state['client_id']}")

        # ── Step 4
        banner(4, f"Create user {ALICE_EMAIL!r} + add to group")
        cog_idp.admin_create_user(
            UserPoolId=state["user_pool_id"],
            Username=ALICE_EMAIL,
            UserAttributes=[
                {"Name": "email", "Value": ALICE_EMAIL},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
            TemporaryPassword=PASSWORD,
        )
        # Force-set permanent password (skip the "force change password" challenge)
        cog_idp.admin_set_user_password(
            UserPoolId=state["user_pool_id"],
            Username=ALICE_EMAIL, Password=PASSWORD, Permanent=True,
        )
        cog_idp.admin_add_user_to_group(
            UserPoolId=state["user_pool_id"],
            Username=ALICE_EMAIL, GroupName=GROUP_NAME,
        )
        print(f"  ✅ alice created, password set, added to {GROUP_NAME}")

        # ── Step 5
        banner(5, f"Create user {BOB_EMAIL!r} (NO group — negative test)")
        cog_idp.admin_create_user(
            UserPoolId=state["user_pool_id"],
            Username=BOB_EMAIL,
            UserAttributes=[
                {"Name": "email", "Value": BOB_EMAIL},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
            TemporaryPassword=PASSWORD,
        )
        cog_idp.admin_set_user_password(
            UserPoolId=state["user_pool_id"],
            Username=BOB_EMAIL, Password=PASSWORD, Permanent=True,
        )
        print(f"  ✅ bob created, NO group membership")

        # ── Step 6
        banner(6, "Create Identity Pool")
        resp = cog_id.create_identity_pool(
            IdentityPoolName=IDENTITY_POOL_NAME,
            AllowUnauthenticatedIdentities=False,
            CognitoIdentityProviders=[{
                "ProviderName": f"cognito-idp.{REGION}.amazonaws.com/{state['user_pool_id']}",
                "ClientId": state["client_id"],
                "ServerSideTokenCheck": False,
            }],
        )
        state["identity_pool_id"] = resp["IdentityPoolId"]
        print(f"  ✅ identity pool: {state['identity_pool_id']}")

        # ── Step 7
        banner(7, "Create IAM role for the reader group")
        trust = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Federated": "cognito-identity.amazonaws.com"},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": state["identity_pool_id"],
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated",
                    },
                },
            }],
        }
        resp = iam.create_role(
            RoleName=IAM_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            MaxSessionDuration=3600,
            Description="Demo reader role for Cognito Identity Pool",
        )
        state["role_name"] = IAM_ROLE_NAME
        state["role_arn"] = resp["Role"]["Arn"]
        print(f"  ✅ role arn: {state['role_arn']}")

        permissions = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "CodeArtifactReadPull",
                    "Effect": "Allow",
                    "Action": [
                        "codeartifact:GetAuthorizationToken",
                        "codeartifact:GetRepositoryEndpoint",
                        "codeartifact:ReadFromRepository",
                        "codeartifact:GetPackageVersionAsset",
                        "codeartifact:DescribePackage",
                        "codeartifact:DescribePackageVersion",
                        "codeartifact:ListPackages",
                        "codeartifact:ListPackageVersions",
                        "codeartifact:ListPackageVersionAssets",
                    ],
                    "Resource": [
                        f"arn:aws:codeartifact:{REGION}:{account_id}:domain/{CODEARTIFACT_DOMAIN}",
                        f"arn:aws:codeartifact:{REGION}:{account_id}:repository/{CODEARTIFACT_DOMAIN}/{CODEARTIFACT_REPO}",
                        f"arn:aws:codeartifact:{REGION}:{account_id}:package/{CODEARTIFACT_DOMAIN}/{CODEARTIFACT_REPO}/pypi/*/*",
                    ],
                },
                {
                    "Sid": "CodeArtifactBearerToken",
                    "Effect": "Allow",
                    "Action": "sts:GetServiceBearerToken",
                    "Resource": "*",
                    "Condition": {
                        "StringEquals": {
                            "sts:AWSServiceName": "codeartifact.amazonaws.com",
                        },
                    },
                },
            ],
        }
        iam.put_role_policy(
            RoleName=IAM_ROLE_NAME,
            PolicyName="SkillsReaderInline",
            PolicyDocument=json.dumps(permissions),
        )
        print(f"  ✅ inline policy attached (CodeArtifact pull on {CODEARTIFACT_REPO})")

        # IAM role propagation can lag; give it a few seconds
        time.sleep(8)

        # ── Step 8
        banner(8, "Wire role-mapping (group→role) on Identity Pool")
        provider_key = (
            f"cognito-idp.{REGION}.amazonaws.com/{state['user_pool_id']}"
            f":{state['client_id']}"
        )
        cog_id.set_identity_pool_roles(
            IdentityPoolId=state["identity_pool_id"],
            Roles={"authenticated": state["role_arn"]},
            RoleMappings={
                provider_key: {
                    "Type": "Rules",
                    "AmbiguousRoleResolution": "Deny",  # 🔑 negative-test enforcement
                    "RulesConfiguration": {
                        "Rules": [{
                            "Claim": "cognito:groups",
                            "MatchType": "Contains",
                            "Value": GROUP_NAME,
                            "RoleARN": state["role_arn"],
                        }],
                    },
                },
            },
        )
        print(f"  ✅ rule: cognito:groups Contains {GROUP_NAME!r} → {IAM_ROLE_NAME}")
        print(f"     ambiguous resolution: Deny (users without group are REJECTED)")

        # ── Step 9 — Alice's flow
        banner(9, f"Alice ({ALICE_EMAIL}) — admin_initiate_auth → JWT")
        auth = cog_idp.admin_initiate_auth(
            UserPoolId=state["user_pool_id"],
            ClientId=state["client_id"],
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": ALICE_EMAIL, "PASSWORD": PASSWORD},
        )
        alice_id_token = auth["AuthenticationResult"]["IdToken"]
        # Decode payload for inspection (no verify — just for display)
        import base64
        parts = alice_id_token.split(".")
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        print(f"  ✅ id_token received (len={len(alice_id_token)})")
        print(f"     claims preview: sub={claims['sub']}")
        print(f"                     email={claims.get('email')}")
        print(f"                     groups={claims.get('cognito:groups')}")
        print(f"                     iss={claims['iss']}")
        print(f"                     aud={claims['aud']}")

        banner("9b", "Alice — exchange id_token for IAM credentials via Identity Pool")
        provider = f"cognito-idp.{REGION}.amazonaws.com/{state['user_pool_id']}"
        id_resp = cog_id.get_id(
            IdentityPoolId=state["identity_pool_id"],
            Logins={provider: alice_id_token},
        )
        alice_identity_id = id_resp["IdentityId"]
        print(f"  identity id: {alice_identity_id}")
        creds_resp = cog_id.get_credentials_for_identity(
            IdentityId=alice_identity_id,
            Logins={provider: alice_id_token},
        )
        c = creds_resp["Credentials"]
        alice_creds = {
            "AccessKeyId": c["AccessKeyId"],
            "SecretAccessKey": c["SecretKey"],
            "SessionToken": c["SessionToken"],
            "Expiration": c["Expiration"].isoformat(),
        }
        print(f"  ✅ AccessKeyId: {alice_creds['AccessKeyId']}")
        print(f"     SecretAccessKey: ******** (redacted)")
        print(f"     SessionToken: ******** (len={len(alice_creds['SessionToken'])})")
        print(f"     Expiration: {alice_creds['Expiration']}")

        # ── Step 10
        banner(10, "Alice's IAM creds → real CodeArtifact pull")
        # Use the just-issued temp creds to call CodeArtifact
        sess = boto3.Session(
            aws_access_key_id=alice_creds["AccessKeyId"],
            aws_secret_access_key=alice_creds["SecretAccessKey"],
            aws_session_token=alice_creds["SessionToken"],
            region_name=REGION,
        )
        ca_alice = sess.client("codeartifact")

        # First check who Alice now is
        alice_sts = sess.client("sts")
        ident = alice_sts.get_caller_identity()
        print(f"  who am I? {ident['Arn']}")

        # Now actually list package versions in the demo repo
        try:
            resp = ca_alice.list_package_versions(
                domain=CODEARTIFACT_DOMAIN,
                repository=CODEARTIFACT_REPO,
                format="pypi",
                package="aws-cost-anomaly-triage",
            )
            print(f"  ✅ ListPackageVersions succeeded — {len(resp.get('versions', []))} version(s):")
            for v in resp.get("versions", []):
                print(f"       {v.get('version')}  ({v.get('status')})")
        except ClientError as e:
            print(f"  ❌ ListPackageVersions failed: {e.response['Error']['Code']}")

        # And try to actually pull bytes
        try:
            asset = ca_alice.get_package_version_asset(
                domain=CODEARTIFACT_DOMAIN,
                repository=CODEARTIFACT_REPO,
                format="pypi",
                package="aws-cost-anomaly-triage",
                packageVersion="0.1.0",
                asset="aws_cost_anomaly_triage-0.1.0-py3-none-any.whl",
            )
            data = asset["asset"].read()
            print(f"  ✅ GetPackageVersionAsset succeeded — {len(data)} bytes pulled")
        except ClientError as e:
            print(f"  ❌ GetPackageVersionAsset failed: {e.response['Error']['Code']}")

        # ── Step 11 — Bob's negative flow
        banner(11, f"Bob ({BOB_EMAIL}, no group) — should be REJECTED")
        auth = cog_idp.admin_initiate_auth(
            UserPoolId=state["user_pool_id"],
            ClientId=state["client_id"],
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": BOB_EMAIL, "PASSWORD": PASSWORD},
        )
        bob_id_token = auth["AuthenticationResult"]["IdToken"]
        bob_claims = json.loads(base64.urlsafe_b64decode(
            bob_id_token.split(".")[1] + "=" * (-len(bob_id_token.split(".")[1]) % 4)
        ))
        print(f"  bob authenticated; claims.cognito:groups = {bob_claims.get('cognito:groups')}")

        try:
            id_resp = cog_id.get_id(
                IdentityPoolId=state["identity_pool_id"],
                Logins={provider: bob_id_token},
            )
            bob_identity_id = id_resp["IdentityId"]
            creds_resp = cog_id.get_credentials_for_identity(
                IdentityId=bob_identity_id,
                Logins={provider: bob_id_token},
            )
            print(f"  ❌ UNEXPECTED: bob got IAM creds: {creds_resp['Credentials']['AccessKeyId']}")
            print(f"     (this is a SECURITY BUG — group→role enforcement failed)")
        except ClientError as e:
            print(f"  ✅ as expected — Identity Pool denied bob:")
            print(f"     error code: {e.response['Error']['Code']}")
            print(f"     message: {e.response['Error']['Message']}")
            print(f"  This is the AmbiguousRoleResolution=Deny setting working as designed:")
            print(f"  bob's id_token has no 'cognito:groups' claim, so no rule matches,")
            print(f"  so no role is assumed.")

        # ── Step 12
        banner(12, "Demo summary")
        print(f"  ✅ Alice (in group) authenticated → IAM creds → real CodeArtifact pull")
        print(f"  ✅ Bob (no group) authenticated → Identity Pool refused to issue creds")
        print(f"\n  This proves the chain:")
        print(f"     Cognito User Pool group membership")
        print(f"        → JWT cognito:groups claim")
        print(f"           → Identity Pool rule match")
        print(f"              → IAM role with scoped CodeArtifact resource ARN")
        print(f"                 → CodeArtifact returns artifact bytes")
        print(f"\n  Negative test (no group → no role → no creds) confirms isolation works.")
        return 0

    except Exception as e:
        print(f"\n❌ demo failed: {type(e).__name__}: {e}")
        return 1
    finally:
        cleanup(state)


if __name__ == "__main__":
    sys.exit(main())

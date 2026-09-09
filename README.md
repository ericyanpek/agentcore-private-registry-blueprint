# agentcore-private-registry-blueprint

[English](README.en.md)

基于 **AWS Agent Registry GA + CodeArtifact** 的企业私有 Skills 分发与可信消费蓝图。
Registry 管目录、发现和审批；CodeArtifact 存 wheel；本项目把“已批准记录”与“最终安装的内容”绑定起来。

**状态（2026-09-09）**：代码已迁移到 `agent-registry` namespace。已完成离线 SDK 合约、
制品完整性和 CDK 验证；**本次 GA 改动尚未在真实 AWS 账号完成端到端部署验证**。
不要将原 Preview 演示的验证结果视为 GA 部署验证。

## 闭环

```text
作者 / CI
  └─ 构建唯一 wheel → 从 wheel 提取 SKILL.md + SHA-256
       ├─ CodeArtifact 上传 → 核对服务端资产摘要
       └─ Registry SKILL record → DRAFT → PENDING_APPROVAL
                                              ↓ 独立审批者
                                           APPROVED
                                              ↓
消费者 → 指定 Registry 的发现面 → 精确选择 name/version
       → 从允许的 CodeArtifact 仓库下载 → SHA-256 + SKILL.md 一致性校验
       → 再读发现面确认批准内容未变化
       → 只提取 skill_files/ → 本地来源清单 → 漂移检查
```

消费端不枚举 Registry，不调用治理面的 `GetRegistryRecord`，不运行 wheel 的
`postinstall.py`，不通过 `pip install` 安装远端依赖，也不向 pip 配置写入凭证。
安装位置由调用者选择，记录不能指定任意本地路径或执行命令。

## 快速开始

需要 Python 3.11+、Node.js 20+、支持 Agent Registry GA 的 AWS CLI v2。
以下命令从仓库根目录运行。部署会创建收费资源，先检查 CDK diff。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[publish]'
cd cdk
npm ci
npx cdk synth
npx cdk diff --all
npx cdk deploy --all
cd ..
```

将 `AgentRegistryStack.RegistryArn` 输出配置给发布者、审批者和消费者：

```bash
export AGENT_REGISTRY_ARN='arn:aws:agent-registry:us-east-1:YOUR_ACCOUNT_ID:registry/YOUR_REGISTRY_ID'
```

使用预先配置、权限分离的 AWS profiles：

```bash
AWS_PROFILE=publisher python skills/publish-skill/scripts/publish.py \
  --package-dir skill-package --auto-submit
AWS_PROFILE=curator python scripts/03_approve_skill.py \
  --reason 'Reviewed skill content, artifact digest, and owner'
AWS_PROFILE=consumer python scripts/04_consume_skill.py \
  --target-dir ./demo-skills
python scripts/05_verify_installed_skill.py ./demo-skills/aws-cost-anomaly-triage
```

批准后搜索索引可能尚未更新；未搜到记录时稍后重试，不要改用治理面绕过发现。
脚本不会为你创建这些 AWS profiles。权限配置见 [IAM 分工](docs/09-publishing-iam.md)；
逐步操作、升级和负向验证见 [GA walkthrough](docs/03-demo-walkthrough.md)。
确认安装内容后，可将 `--target-dir` 改成 `~/.claude/skills`。

## 提供的能力

| 部分 | 实现 |
|---|---|
| GA 基础设施 | 原生 `AWS::AgentRegistry::Registry`，IAM 发现、人工审批、Retain |
| 发布 | 单 wheel、服务端摘要核验、从实际制品生成 metadata、name/version 幂等检查 |
| 消费 | 发现面 API、精确版本、来源白名单、内容校验、安全提取、本地来源清单 |
| 权限 | 消费者无治理面读取权限；Cognito group 分别绑定 Registry ARN 与 CodeArtifact repo |
| 漂移检测 | 拒绝覆盖变更过的本地 Skill；检测新增、删除、修改文件 |
| 其他资源 | GA 形状的 MCP、URL 同步、KB、Lambda、Guardrail 示例 |

## 范围与边界

- 当前可信消费路径支持单个、平台无关、无 Python 依赖的 wheel，压缩及解压总量各不超过 20 MiB。
- 摘要匹配证明“与批准内容一致”，不证明 Skill 无恶意或运行安全；审批仍须检查 SOP、脚本与资源内容。
- 本地来源清单不是签名；同时篡改文件与清单可以绕过本地漂移检测。
- Registry 弃用不会撤销已经复制到本地的内容；安装前复查也不是与审批状态变化原子执行的事务。
- Registry 与 CodeArtifact 权限是两层：有仓库下载权限的人仍能绕过本客户端直接下载制品。
  若需要服务端强制“未批准制品无法下载”，需独立的隔离/晋级仓库流程，本版未实现。
- Registry 的搜索过滤器不是行级访问控制；敏感团队用独立 Registry 和显式 IAM 范围隔离。
- OAuth 直连、EventBridge 审批、RAM 共享与组织自动检测是后续扩展示例，不宣称本版已实现。

## 导航

- [为什么需要私有 Skills](docs/01-why-private-skills.md)
- [GA 部署与演示](docs/03-demo-walkthrough.md) · [MCP 发现](docs/04-dynamic-discovery.md)
- [IAM 分工](docs/09-publishing-iam.md) · [终端用户与团队隔离](docs/10-end-user-access.md)
- [Preview 数据迁移](docs/11-ga-migration.md) · [制品完整性](docs/12-record-artifact-integrity.md)
- [CDK 与资源保留](cdk/README.md) · [扩展资源示例](examples/README.md)

`docs/02、05、06、07、08` 保留了调研过程和 Preview 设计；其中历史 API/安装命令不作为当前操作指南。
原 Preview namespace 于 2026-09-17 关闭；已有数据不会自动迁移，先看迁移说明。

# agentcore-private-registry-blueprint

> 🌐 **中文版（本页）** · [English README](./README.en.md)

> 一个可运行的蓝图：在 AWS 上搭建**企业私有、可治理的 AI 资源注册中心** —— 基于 Amazon Bedrock AgentCore Registry + AWS CodeArtifact。
>
> **Day 1**：交付一个端到端验证过的 **Skills 演示**（一键 CDK + 一个真实 skill，可装到 Claude Code）。
>
> **Day N**：同一个 Registry——用同一套模式——还能管理 MCP servers、A2A agents、知识库、Lambda 工具、Bedrock Guardrails、Cedar 策略包、评测数据集，以及任何你想让组织治理的自定义资源。详见
> [docs/07-extending-to-other-resources.md](docs/07-extending-to-other-resources.md)。

**状态**：Preview 阶段参考实现（2026-05）。AWS Agent Registry 处于 public preview，API 可能变更。

---

## 为什么要这个仓库

这个蓝图诞生于 AWS 近期两条产品线的交汇点：

- **Bedrock AgentCore Registry**（preview，2026-04）—— 一个可治理、可搜索的目录服务，**承载 agents、MCP servers/tools、skills，以及任何你想私有化分发的自定义资源**
- **CodeArtifact** —— 与之天然搭配、却很少被联想到一起的私有制品仓库

这两者合在一起，解决了大多数企业还没明确表达、但 2026 年中前必然撞上的问题：**AI 资源已经成为企业 IP，需要和代码、基础设施、数据同等级别的治理**。

Day-1 演示之所以聚焦 **Skills**，是因为它把"私密性"这件事的论点拉得最尖锐：

2025-2026 年间，**Agent Skills 已经成为团队沉淀 SOP 的载体**：财务分析手册、事故排查流程、数据探索方法、合规审查清单。Skill 不再只是 prompt——它是 AI agent 能直接执行的运营 IP，**不需要再让人翻译一遍**。

这就把"skill 放哪里、谁能发布"变成了实打实的治理问题：

- **隐私性** —— 一个财务分析 skill 嵌入了内部毛利口径、客户分级、定价规则。**它不能放在公网 marketplace 或公网 GitHub 上**。
- **合规** —— MAS / HKMA / PBOC、HIPAA、欧盟 AI Act 都把 agent 可执行指令视为可审计的产物。需要版本化、审批留痕、不可变历史。
- **规模化的可发现性** —— 当组织里有 50+ skill 时，搜索和信任信号比 Confluence 页面里的 git URL 更重要。

公网 skill 市场（Anthropic 的、`skills.sh` 这种 npm 风格）和自托管玩家项目（如 iflytek SkillHub）**都不满足企业约束**。AWS 在 2026-04 上线 Bedrock AgentCore Registry 正是为补这个缺口。

本仓库提供缺失的那块拼图：**怎样把 AWS Agent Registry + CodeArtifact 真正接成一个可工作的私有 skill 分发流水线**——含一键基础设施和你可以在自家 Claude Code 上验证的演示 skill。

[→ 完整论证：`docs/01-why-private-skills.md`](docs/01-why-private-skills.md)

## 架构（一分钟版）

<p align="center">
  <img src="docs/images/architecture.svg" alt="架构总览" width="900">
</p>

四个角色：**作者 / CI** 把 skill 同时推到两个后端——制品（PyPI 包）入 **CodeArtifact**，metadata 入 **Agent Registry**。**消费方**（开发者或 Claude Code/AgentCore Runtime）通过 Registry 搜索，按 metadata 里的 `packages[]` 指针从 CodeArtifact `pip install`，落到 `~/.claude/skills/<name>/`，Claude Code 下一个 prompt 自动发现。

[→ 完整架构：`docs/02-architecture.md`](docs/02-architecture.md)

## 蓝图覆盖范围

Day-1 范围（端到端已验证）：

| 关注点 | 用到的 AWS 服务 | 本仓库提供 |
|---|---|---|
| **发现 + 治理** | Bedrock AgentCore Registry | 创建 registry 的 CDK；发布/审批 record 的 Python 脚本；`skillDefinition` 参考 schema |
| **制品存储** | CodeArtifact（PyPI 仓库） | 创建 domain + repo 的 CDK；纯文本 skill 的 `pyproject.toml` 模板 |
| **Skill 格式** | （SKILL.md 规范） | 一个真实示例：`aws-cost-anomaly-triage`，含 frontmatter + 6 份资源文件 |
| **激活** | （消费侧） | `postinstall.py` 控制台脚本 + `04_consume_skill.py` 演示完整 search → install → activate |
| **一键部署** | AWS CDK（TypeScript） | `cdk deploy` 大约 3 分钟全部就位 |
| **认证** | 现用 IAM，JWT/OIDC 已记入文档 | 脚本里 IAM 已能跑；OAuth/JWT 路径作为 Phase 2 |

Day-N 范围（已记入文档，可扩展）：

同一个 Registry 承载 4 种 `descriptorType`。本蓝图演示的是 `AGENT_SKILLS`，其余三种地位完全平等：

| `descriptorType` | 装什么 | Schema |
|---|---|---|
| `AGENT_SKILLS` | 可复用 SOP（本演示） | SKILL.md + skillDefinition v0.1.0 |
| `MCP` | MCP servers / tools | MCP server.json（开放规范） |
| `A2A` | Agents | Google A2A Agent Card |
| `CUSTOM` | 其他一切（KBs、Lambda 工具、Guardrails、Cedar 策略、SFN 状态机、评测集、schema 等） | 你自定义的 JSON 形态 |

`docs/07-extending-to-other-resources.md` 里有一个走通过的"客服中心"完整示例——一个 registry 注册 18 个资源，**横跨全部四种 `descriptorType`**。

## 10 分钟跑通

```bash
# 1. 部署基础设施（CodeArtifact domain + repo，Agent Registry）
cd cdk && npm install && npx cdk deploy --all

# 2. 构建并发布示例 skill 到 CodeArtifact
cd ../skill-package && python3 -m build
aws codeartifact login --tool twine --domain skills-demo --repository skills-prod --region us-east-1
python3 -m twine upload --repository codeartifact dist/*

# 3. 注册、审批、验证端到端发现
cd ../scripts
python3 02_register_skill.py
python3 03_approve_skill.py
sleep 30   # 搜索索引在审批通过后 15-30 秒才会被命中
python3 04_consume_skill.py
```

跑完第 3 步，`~/.claude/skills/aws-cost-anomaly-triage/` 就生成了，**Claude Code 在下一个 prompt 自动把这个 skill 列进可用清单**——和官方内置 skill 平级。

## 作者怎么发布自己的 skill —— 用 publish-skill（一个发布 skill 的 skill）

蓝图里有一个特殊的 skill：**`skills/publish-skill/`**。它本身就是一个 skill，但作用是**帮其他作者把 skill 发布到 Registry**。一旦它装到 `~/.claude/skills/`，作者只要在 Claude Code 里说一句「把这个 skill 发布出去」，整套 build → upload → 注册 → 提交审批的流程就被自动驱动。

```bash
# 一次性配置（每台机器一次）
mkdir -p ~/.skillpublish && cat > ~/.skillpublish/config.toml <<'EOF'
[default]
region = "us-east-1"
codeartifact_domain = "skills-demo"
codeartifact_repository = "skills-prod"
registry_name = "skills-demo-registry"
EOF

# 每次发新 skill
cd path/to/your-new-skill/      # 含 pyproject.toml + src/<pkg>/skill_files/SKILL.md
# 在 Claude Code 里说："publish this skill"
# Claude 触发 publish-skill skill，调用 publish.py：
#   build → twine upload → CreateRegistryRecord → 停在 DRAFT 等你 review
```

**权限是用 IAM 控制的，不是 skill 本身**。即便 publish-skill 装到了机器上，**没有 `codeartifact:PublishPackageVersion` 和 `bedrock-agentcore:CreateRegistryRecord` 权限的人调用脚本会被 IAM 拒绝**。这是真正的护栏；skill 只是降低操作门槛的便利层。

四类角色 + 对应 IAM 策略详见 [docs/09-publishing-iam.md](docs/09-publishing-iam.md)：
- **Reader**：所有人，能搜索 + 安装已审批 skill
- **Publisher**：限定团队的作者，能创建 + 提交审批
- **Curator**：少数人，能审批（**Publisher 不能审自己的 skill**——按职责分离）
- **Admin**：极少数，管 registry 本身

完整的作者侧文档：[docs/08-publishing-workflow.md](docs/08-publishing-workflow.md)。

## 心智模型 —— Registry 是什么、不是什么

关于 AWS Agent Registry 最常见的一个误解：把它当成"skill 下载服务"。**它不是。** 把这一点想清楚，后面的设计就顺了。

**Registry 是一个 metadata 的发现 + 治理服务。它不托管制品，也不安装任何东西。**

每个 registry 暴露的 MCP 端点上**只有一个**工具：

```
search_registry_records(searchQuery, maxResults, filter)
```

没有 `install`，没有 `download`，没有 `activate`。这是**故意的**。和 npm 的角色对照一下：

| | npm 生态 | Agent Registry 生态 |
|---|---|---|
| 搜索服务 | `registry.npmjs.org` | Agent Registry MCP endpoint |
| 搜索命令 | `npm search` | `search_registry_records` |
| 安装命令 | `npm install`（CLI 在客户端跑） | `pip install`（由 Claude Code 的 Bash 工具跑） |
| 本地安装目录 | `~/.node_modules/` | `~/.claude/skills/` |
| 自动加载已装 | Node `require()` 解析 | Claude Code 每次 prompt 扫描 `~/.claude/skills/` |

所以当 Claude Code 用一个私有 skill 时，**有三件相互独立的事在发生——它们在设计上是解耦的**：

```
1. 发现 (远程, 仅 metadata, KB 量级)
   Claude Code → Registry MCP → search_registry_records
   返回：SKILL.md + packages[] 指针
   不传输任何制品

2. 决策 (Claude 推理过程, 没有 API 调用)
   Claude 读 skillMd，决定走哪条：
     (a) 一次性使用：直接把 SKILL.md 内嵌进对话上下文
     (b) 持久安装：通过 Bash 工具触发 pip install
     (c) 跳过：本地已经装过

3. 安装 (仅 2b 时发生，由 Claude Code 自带的 Bash 工具执行)
   pip install <包> 从 CodeArtifact 拉取 + post-install 拷贝
   幂等：同一版本再跑一次 pip install 是 no-op
```

Registry 永远不会**主动推送** skill 到你的机器。Registry 也**不知道**你本地装过哪些 skill。这两件事归 agent runtime（Claude Code）和你的消费脚本管。

### 两层"发现"机制并行运转

```
┌──────────────────────────────────────┐
│ 远程层                               │
│ Registry MCP / SDK                   │
│ → 返回组织内已审批目录的 metadata    │
│ → 不感知你本地的文件系统             │
└──────────────────────────────────────┘
                 ┊  互不通信
                 ┊
┌──────────────────────────────────────┐
│ 本地层                               │
│ Claude Code / Bedrock Runtime        │
│ → 每个 prompt 扫描 ~/.claude/skills/ │
│ → 不感知 Registry 的存在             │
└──────────────────────────────────────┘
```

两层互不通信。**昨天装好的 skill 今天本地层瞬间发现，不发起任何远程调用**。**团队刚发布的新 skill 远程层立刻可搜，但本地什么都不会变**——除非你（或某个 agent）主动选择安装。

### 每种交互的成本

| 场景 | 实际跑了什么 | 网络字节 |
|---|---|---|
| Skill 已经在 `~/.claude/skills/` | 本地扫描 | 0 |
| 搜到一个 skill，Claude 内嵌进上下文一次性用 | `search_registry_records` | ~5KB metadata |
| 搜到 → 决定安装 | search + 从 CodeArtifact `pip install` | ~5KB metadata + ~15KB wheel |
| 同一版本重新装一次 | `pip install` 走本地缓存 no-op | 0 |
| Registry 是 v0.2.0、本地是 v0.1.0 | search + `pip install --upgrade` | metadata + 增量 |

这就是为什么"每次对话都调一下 Registry"完全可接受——**调用是 KB 级 metadata 查询，不是制品传输**。

## 仓库布局

```
.
├── README.md                          # 当前文件（中文）
├── README.en.md                       # 英文版
├── docs/
│   ├── 01-why-private-skills.md            # 企业级动因（Day-1 框架）
│   ├── 02-architecture.md                  # 服务映射 + 图
│   ├── 03-demo-walkthrough.md              # 4 个脚本流程 + 时序
│   ├── 04-dynamic-discovery.md             # MCP endpoint：Claude Code 怎么发现 skill
│   ├── 05-auth-placeholder.md              # 现用 IAM，JWT/OIDC 待补
│   ├── 06-future-optimizations.md          # 跨账号、KMS CMK、EventBridge、OCI 等
│   ├── 07-extending-to-other-resources.md  # MCP、KB、Lambda 工具、Guardrail 等
│   ├── 08-publishing-workflow.md           # 作者视角：怎么发布自己的 skill
│   └── 09-publishing-iam.md                # 平台团队视角：四档 IAM 策略
├── cdk/                               # 一键部署的 TypeScript CDK
│   ├── bin/blueprint.ts
│   ├── lib/codeartifact-stack.ts
│   ├── lib/registry-stack.ts
│   └── package.json
├── skill-package/                     # 可发布的示例 skill
│   ├── pyproject.toml
│   └── src/aws_cost_anomaly_triage/
│       ├── postinstall.py
│       └── skill_files/
│           ├── SKILL.md
│           └── resources/*.md
├── skills/                            # 蓝图自带的 meta-skill
│   └── publish-skill/                 # 发 skill 的 skill
│       ├── SKILL.md
│       ├── resources/publish-skill-runbook.md
│       └── scripts/publish.py
├── scripts/                           # boto3 publish/approve/consume（Day-1）
│   ├── 01_create_registry.py
│   ├── 02_register_skill.py
│   ├── 03_approve_skill.py
│   └── 04_consume_skill.py
└── examples/                          # Day-N 扩展占位
    ├── mcp-server/
    ├── knowledge-base/
    ├── lambda-tool/
    └── guardrail/
```

## 各部分状态

Day-1（Skills，端到端）：

| 模块 | 状态 |
|---|---|
| CodeArtifact + Agent Registry CDK | ✅ 可工作 |
| `aws-cost-anomaly-triage` 示例 skill | ✅ 可工作 |
| 发布 + 审批 + 消费脚本 | ✅ 端到端测过 |
| MCP endpoint 动态发现 | ✅ 文档化；含客户端配置示例 |
| IAM 认证 | ✅ 可工作 |
| `publish-skill` meta-skill（参数化发布器 + 四档 IAM 策略） | ✅ 脚本已 preflight 通过；docs/08+09 已写 |

Day-N 扩展：

| 模块 | 状态 |
|---|---|
| MCP server records (`descriptorType: MCP`) | 📘 文档化于 `07-extending` + `examples/mcp-server/` 占位 |
| Knowledge Base records (CUSTOM) | 📘 文档化于 `07-extending` + `examples/knowledge-base/` 占位 |
| Lambda 工具 records (CUSTOM) | 📘 文档化于 `07-extending` + `examples/lambda-tool/` 占位 |
| Bedrock Guardrails records (CUSTOM) | 📘 文档化于 `07-extending` + `examples/guardrail/` 占位 |
| JWT/OIDC 认证（Cognito/Okta） | 🔶 Phase 2 — 见 `docs/05-auth-placeholder.md` |
| 跨账号消费 | 🔶 Phase 2 |
| CodeArtifact 上的 KMS CMK | 🔶 Phase 2 |
| EventBridge → Slack 审批流水线 | 🔶 Phase 2 |
| OCI 制品分发 | ⏸ 未来 — 等 agentskills/agentskills 规范定稿 |
| GitHub Actions 合并即发布 CI | ⏸ 未来 |

[→ 路线图：`docs/06-future-optimizations.md`](docs/06-future-optimizations.md)

## 为什么是现在（一个 SA 的判断）

2026-Q2 这个时间点，让本蓝图有价值的是两个事实：

1. **AWS Agent Registry 刚发布（2026-04 preview）**。**目前没有 AWS 官方博客或样例仓库把它和 CodeArtifact 串起来做 skill 分发**。本仓库用经过验证的端到端代码补这个空白。
2. **Skills 作为企业 IP 是真问题，但多数团队还没撞上**。第一波客户问"我的私有 skill 放哪里"恰好就在这段时间。手里有一个能跑的蓝图，意味着 SA 对话从"让我研究一下"变成"这个仓库，咱们按你的 IdP 改一下"。

本仓库在 AWS 文档没明说的地方刻意有立场：**对纯文本和脚本类 skill，PyPI-via-CodeArtifact 是推荐的制品后端**；**IAM 是 day-1 路径，JWT/OIDC 是 day-2**；**Registry 应该容纳所有可治理的 AI 资源类型，而不是仅限 skill**。不同意？欢迎开 issue。

## 灵感来源 / 相关工作

- AWS Agent Registry 公开文档与 2026-04 preview 发布博客
- Pinterest 的"中心 registry + 通路（paved path）"MCP 架构（ByteByteGo 深度解读）
- ToolHive / Stacklok Enterprise（MCP 工具方向 production-ready 的对应物）
- iflytek/skillhub（反面案例：协议选错了赛道）
- Anthropic 的 `anthropics/skills` 仓库（格式定义所在）

## 许可证

Apache 2.0。详见 [LICENSE](LICENSE)。

## 免责声明

作者是 AWS Solutions Architect；这是个人蓝图，**不是 AWS 官方发布的参考架构**。在投产前请按你账号实际的合规要求验证。

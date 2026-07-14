# carina 智能路由技术说明

## 1. 文档目的

本文说明 carina 智能路由的设计、配置模型、候选过滤、评分算法、运行指标、控制 API、故障处理和兼容策略，供开发、测试和运维排障使用。

智能路由建立在原有能力之上：请求仍先被转换为协议无关的 `ChatRequest`，路由器选择供应商后，再由对应 adapter 转换为上游协议。已有熔断、健康探测和故障切换语义保持不变。

## 2. 设计目标

- 默认不改变已有用户的 active-provider-first 行为。
- 根据请求模型、流式需求和容量限制排除不兼容供应商。
- 支持管理员通过规则表达业务偏好或硬约束。
- 使用真实请求的成功率、延迟、价格和优先级动态排序。
- 所有路由决策均可通过 preview API 解释。
- 智能路由失败不能绕过现有熔断和 failover 保护。
- 不记录 prompt、响应正文、API Key 等敏感内容。

## 3. 代码结构

| 文件 | 职责 |
| --- | --- |
| `carina/models/__init__.py` | 路由模式、规则、权重、供应商能力和预览请求模型 |
| `carina/routing/policy.py` | 规则匹配、候选过滤、评分、排序和淘汰原因 |
| `carina/routing/metrics.py` | 进程内请求指标、成功率和 EWMA 计算 |
| `carina/router.py` | 调用策略、转发、流式处理、failover 和指标写入 |
| `carina/store/__init__.py` | 路由配置读取和持久化 |
| `carina/server/control_routes.py` | 路由配置、指标和 preview API |
| `carina/web/` | 路由模式、规则和供应商元数据管理界面 |
| `tests/test_routing.py` | 智能路由兼容性、规则、评分、容量和 API 测试 |

## 4. 请求处理流程

```text
客户端请求
  -> OpenAI/Anthropic 请求转换为 ChatRequest
  -> Router 获取所有供应商及当前 RoutingConfig
  -> enabled + CircuitBreaker 初筛
  -> RoutingPolicy 根据模式过滤和排序
  -> 尝试排名第一的供应商
      -> 成功：返回响应并记录指标
      -> AdapterError：记录失败，继续下一个候选
  -> 全部失败：返回 503
```

流式请求只允许在收到首个上游数据块之前切换供应商。首包发给客户端后发生的错误会被记录，但不会重试到其他供应商，以避免重复输出。

## 5. 路由模式

### 5.1 `manual`

默认模式，与修改前行为一致：

1. 排除 disabled 和熔断器不允许访问的供应商。
2. active provider 排在最前。
3. 其余供应商按 `priority` 升序、`name` 升序排列。
4. `model_patterns`、tags、价格等智能路由字段不参与决策。

该模式用于向后兼容、紧急排障和人工固定首选供应商。

### 5.2 `rule`

先执行能力过滤和首条规则匹配，再按以下顺序排序：

1. `prefer_tags` 命中的供应商；
2. active provider；
3. `priority` 较小的供应商；
4. 供应商名称。

### 5.3 `adaptive`

过滤逻辑与 `rule` 相同，但候选供应商使用实时指标综合评分，分数高者优先。分数相同时按 `priority` 和名称保证结果稳定。

## 6. 配置模型

路由配置保存在原有 `config.json` 顶层的 `routing` 字段中：

```json
{
  "routing": {
    "mode": "adaptive",
    "rules": [],
    "weights": {
      "success_rate": 0.30,
      "latency": 0.25,
      "priority": 0.20,
      "cost": 0.15,
      "preference": 0.10
    },
    "latency_target_ms": 2000,
    "ewma_alpha": 0.20,
    "active_provider_bonus": 0.05
  }
}
```

字段含义：

| 字段 | 说明 |
| --- | --- |
| `mode` | `manual`、`rule` 或 `adaptive` |
| `rules` | 按数组顺序匹配的路由规则，第一条命中后停止匹配 |
| `weights` | adaptive 各评分维度的非负权重，计算时自动归一化 |
| `latency_target_ms` | 延迟评分的目标值，必须大于 0 |
| `ewma_alpha` | 延迟 EWMA 新样本权重，范围 `(0, 1]` |
| `active_provider_bonus` | adaptive 中 active provider 的额外加分 |

旧配置中没有 `routing` 字段时，Pydantic 自动补充默认配置并进入 `manual` 模式，无需迁移脚本。

## 7. 供应商路由元数据

每个 provider 新增以下可选字段：

| 字段 | 说明 |
| --- | --- |
| `model_patterns` | 可接受的客户端模型名，使用 shell 通配符，如 `gpt-*`；空数组表示不限制 |
| `capabilities` | 能力集合；当前识别 `streaming`，空集合表示能力未知且不限制 |
| `tags` | 管理员定义的分类，如 `fast`、`cheap`、`reasoning` |
| `context_window` | 上下文窗口 token 上限 |
| `max_output_tokens` | 单次最大输出 token 数 |
| `input_cost_per_million` | 每百万输入 token 价格 |
| `output_cost_per_million` | 每百万输出 token 价格 |

`default_model` 的语义不变：它决定没有客户端模型时 adapter 使用的上游默认模型。`model_patterns` 仅用于判断一个 provider 是否可以承接客户端请求，不执行模型别名转换。

## 8. 规则模型与匹配语义

规则示例：

```json
{
  "name": "reasoning-models",
  "enabled": true,
  "model_patterns": ["o3*", "reasoning-*"],
  "stream": null,
  "provider_ids": [],
  "require_tags": [],
  "prefer_tags": ["reasoning"],
  "strict": false
}
```

请求匹配规则：

- `enabled=false` 的规则被跳过。
- `model_patterns` 非空时，请求必须包含 model 且至少命中一个 pattern。
- `stream` 为 `true` 或 `false` 时，请求的 stream 必须相同；`null` 表示不限。
- 多条规则按配置顺序检查，只应用第一条命中的规则。

规则对 provider 的作用：

- `provider_ids` 非空时，仅列表中的 provider 可用。
- `require_tags` 必须全部存在于 provider tags 中。
- `prefer_tags` 在普通规则中提高排序或评分，但不是硬约束。
- `strict=true` 时，`prefer_tags` 也成为硬约束。
- 非 strict 规则导致所有候选均被淘汰时，系统移除该规则约束并重新执行默认智能路由过滤。
- strict 规则没有候选时不回退，最终返回无可用供应商。

## 9. 候选过滤

`rule` 和 `adaptive` 模式依次检查：

1. provider 已启用；
2. 熔断器允许当前请求；
3. 请求 model 命中 provider 的 `model_patterns`；
4. 流式请求满足 `streaming` capability；
5. `max_tokens` 不超过 provider 的 `max_output_tokens`；
6. 估算上下文不超过 `context_window`；
7. 满足命中规则的 provider id 和 tag 约束。

当前上下文估算不依赖特定 tokenizer：

```text
estimated_input_tokens = ceil((system 字符数 + messages 字符数) / 4)
estimated_total_tokens = estimated_input_tokens + (max_tokens or 0)
```

该估算只用于保护性过滤，不作为计费依据。没有配置容量字段时不会进行对应限制。

## 10. Adaptive 评分算法

基础分数：

```text
base_score = (
    w_success    * success_score
  + w_latency    * latency_score
  + w_priority   * priority_score
  + w_cost       * cost_score
  + w_preference * preference_score
) / sum(weights)

final_score = base_score + active_provider_bonus（仅 active provider）
```

### 10.1 成功率

使用 Beta(1,1) 先验，避免没有历史请求的新供应商被直接判为 0 分：

```text
success_score = (successes + 1) / (requests + 2)
```

新供应商初始为 `0.5`。

### 10.2 延迟

优先使用流式请求首包 EWMA，没有首包数据时使用请求总耗时 EWMA：

```text
latency_score = latency_target_ms / (latency_target_ms + observed_latency_ms)
```

没有历史数据时取 `0.5`。EWMA 更新公式：

```text
new_ewma = alpha * new_sample + (1 - alpha) * old_ewma
```

### 10.3 Priority

在当前合格候选集合中做相对归一化：最低 priority 得 `1`，最高 priority 得 `0`。所有候选 priority 相同时均得 `1`。

### 10.4 成本

将输入与输出单价相加后，在当前合格候选集合中相对归一化：最低价格得 `1`，最高价格得 `0`。缺少任一价格字段时取中性值 `0.5`；所有已知价格相同时得 `1`。

### 10.5 规则偏好

provider tags 命中规则 `prefer_tags` 时得 `1`，否则得 `0.5`。没有命中规则时所有候选均为 `0.5`。

## 11. 指标采集

每个 provider 维护：

- 请求数、成功数、失败数；
- 成功率；
- 总耗时 EWMA；
- 首包耗时 EWMA；
- 输入和输出 token 累计；
- 预估成本累计；
- 最近使用时间。

非流式请求成功后，从标准化响应的 usage 记录 token 和预估成本。流式转换目前没有统一 usage，因此只记录请求结果、总耗时和首包耗时。

指标仅保存在当前进程内存中，carina 重启后清空。健康探测延迟与真实请求延迟分离，adaptive 只使用真实请求指标。

## 12. 故障和熔断语义

- 排名只决定尝试顺序，不替代 CircuitBreaker。
- adapter 在建立连接、请求或首包前返回 `AdapterError` 时，Router 记录失败并尝试下一个候选。
- 非流式请求成功后同时更新健康状态和路由指标。
- 流式请求正常结束后记录成功；首包后的 `AdapterError` 记录失败并向客户端传播。
- 所有候选失败时，客户端得到原有协议格式的 HTTP 503。
- preview 会读取当前熔断状态，但不会发起上游请求或修改指标。

## 13. 控制 API

### 13.1 读取配置

```http
GET /api/routing/config
```

返回完整 `RoutingConfig`。

### 13.2 更新配置

```http
PUT /api/routing/config
Content-Type: application/json
```

请求体使用 `RoutingConfig`。配置通过现有 `ConfigStore` 原子写入 `config.json`，文件权限继续保持 `0o600`。

### 13.3 预览路由决策

```http
POST /api/routing/preview
Content-Type: application/json

{
  "model": "o3-mini",
  "stream": true,
  "max_tokens": 2048,
  "messages": []
}
```

响应示例：

```json
{
  "mode": "adaptive",
  "selected_provider_id": "abc123",
  "candidates": [
    {
      "provider_id": "abc123",
      "provider_name": "reasoning-primary",
      "allowed": true,
      "score": 0.7825,
      "matched_rule": "reasoning-models",
      "reasons": ["matched rule 'reasoning-models'", "active provider bonus"]
    },
    {
      "provider_id": "def456",
      "provider_name": "general",
      "allowed": false,
      "score": null,
      "matched_rule": "reasoning-models",
      "reasons": ["model 'o3-mini' not supported"]
    }
  ]
}
```

preview 不发送真实模型请求，适合配置上线前验证和线上排障。

### 13.4 查看指标

```http
GET /api/routing/metrics
```

返回当前进程中已有请求记录的 provider 指标。尚未接收请求的 provider 不会出现在结果中。

## 14. 控制台使用

Web UI 的 Smart routing 区域用于：

- 切换路由模式；
- 设置延迟目标；
- 以 JSON 数组维护规则。

Provider 表单用于配置 model patterns、tags、capabilities、上下文窗口、最大输出 token 和价格。Provider 列表展示真实请求成功率和 EWMA 延迟。

建议先通过 `rule` 模式确认元数据与规则正确，再切换到 `adaptive`。刚切换 adaptive 时历史指标为空，系统使用中性先验和配置优先级进行排序，随后逐步吸收真实请求数据。

## 15. 配置示例

下面的配置将推理请求优先交给带 `reasoning` 标签的 provider，流式请求优先交给 `fast` provider：

```json
{
  "mode": "adaptive",
  "rules": [
    {
      "name": "reasoning",
      "model_patterns": ["o3*", "reasoning-*"],
      "prefer_tags": ["reasoning"]
    },
    {
      "name": "streaming",
      "stream": true,
      "prefer_tags": ["fast"]
    }
  ],
  "weights": {
    "success_rate": 0.3,
    "latency": 0.25,
    "priority": 0.2,
    "cost": 0.15,
    "preference": 0.1
  },
  "latency_target_ms": 2000,
  "ewma_alpha": 0.2,
  "active_provider_bonus": 0.05
}
```

## 16. 测试覆盖

`tests/test_routing.py` 当前覆盖：

- 旧配置默认进入 manual；
- manual 保持 active provider 优先；
- model pattern 过滤；
- prefer tags 规则排序；
- 非 strict 规则无候选时移除规则约束回退；
- adaptive 使用运行时成功率重新排序；
- context window 过滤及淘汰原因；
- 路由配置和 preview API。

验证命令：

```bash
.venv/bin/ruff check carina tests
.venv/bin/ruff format --check carina tests
.venv/bin/pytest -q
node --check carina/web/app.js
```

## 17. 当前限制与后续方向

- 上下文 token 使用字符数近似，不等同于供应商 tokenizer。
- 指标未持久化，多进程部署时每个 worker 独立学习。
- 当前内部请求模型尚未表达 tools、图片和 JSON Schema，因此不能按这些能力可靠过滤。
- 流式响应没有统一 usage，无法累计流式 token 和成本。
- 当前没有 model alias 映射；客户端 model 仍直接优先于 provider `default_model`。
- Adaptive 是确定性排序，没有流量探索和负载均衡，同分时使用 priority/name 稳定排序。

后续可以增加模型别名、共享指标存储、实际 tokenizer、工具/多模态能力描述、并发负载和限流状态，以及可配置的小比例探索流量。

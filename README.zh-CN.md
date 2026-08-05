# carina

简体中文 | [English](README.md)

carina 是一个本地模型服务代理，提供供应商切换、协议转换和自动故障转移能力。项目受 [cc-switch](https://github.com/farion1231/cc-switch) 启发，后端使用 Python 实现。

你可以注册多个 AI 服务供应商，将客户端统一指向 carina 的本地端点。carina 会选择合适的供应商转发请求，并在 OpenAI Chat Completions 与 Anthropic Messages 协议之间进行转换，同时提供健康检查、自动故障转移、熔断保护和智能路由。

## 功能特性

- 客户端接口：`POST /v1/chat/completions`（OpenAI）和 `POST /v1/messages`（Anthropic）
- 支持客户端协议与上游供应商协议不同的跨协议转换
- 两种接口均支持 SSE 流式响应
- 供应商配置持久化到 `~/.config/carina/config.json`
- 配置文件权限为 `0o600`，采用原子写入并保留备份
- 一键切换供应商、健康监控、自动故障转移和熔断器
- 支持 manual、rule 和 adaptive 三种智能路由模式
- Web 管理界面支持英文与简体中文切换，并记住语言选择
- 提供本地 Web 管理界面和 `/api` 控制接口
- API Key 不写入日志，并在 API 响应中脱敏

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
carina  # 也可以使用 python -m carina
```

打开 [http://127.0.0.1:8787/](http://127.0.0.1:8787/) 管理供应商，然后将客户端请求发送到 carina 的代理接口。

### Docker

```bash
docker build -t carina:local .
docker run --rm -p 8787:8787 -v carina-data:/data carina:local
```

如果无法访问 Docker Hub，可以通过
`--build-arg BASE_IMAGE=<镜像仓库>/library/python:3.12-slim` 指定其他基础镜像仓库。

容器使用非 root 用户运行，监听 `0.0.0.0:8787`，并将持久化配置保存到 `/data/config.json`。

## 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `CARINA_HOST` | `127.0.0.1` | 服务监听地址，默认仅允许本机访问 |
| `CARINA_PORT` | `8787` | 服务监听端口 |
| `CARINA_CONFIG_DIR` | `~/.config/carina` | 配置文件目录 |
| `CARINA_HEALTH_INTERVAL` | `30` | 供应商健康探测间隔，单位为秒 |

## 控制 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/providers` | 获取供应商列表和当前 active id |
| POST | `/api/providers` | 创建供应商 |
| GET/PUT/DELETE | `/api/providers/{id}` | 查询、更新或删除供应商 |
| POST | `/api/providers/{id}/activate` | 将供应商设为 active |
| POST | `/api/providers/{id}/test` | 测试供应商连通性和凭据 |
| GET | `/api/active` | 获取当前 active provider |
| GET | `/api/health` | 获取供应商健康状态和熔断状态 |
| GET/PUT | `/api/routing/config` | 查询或更新路由模式、规则和权重 |
| POST | `/api/routing/preview` | 预览并解释指定请求的路由决策 |
| GET | `/api/routing/metrics` | 获取成功率、延迟、token 和成本指标 |

## 智能路由

智能路由默认使用 `manual` 模式，保持 active provider 优先的原有行为。

- `manual`：active provider 优先，其余供应商按 priority 排序。
- `rule`：根据模型名称、流式请求、供应商标签和能力过滤与排序。
- `adaptive`：在规则路由基础上，综合实时成功率、EWMA 延迟、priority、token 价格和规则偏好评分。

运行指标保存在进程内存中，carina 重启后会清空。完整的过滤、评分、回退和 API 语义参见[智能路由技术说明](docs/smart-routing.md)。

规则示例：

```json
{
  "name": "reasoning",
  "model_patterns": ["o3*", "reasoning-*"],
  "prefer_tags": ["reasoning"]
}
```

## 开发与验证

```bash
.venv/bin/pytest -q
.venv/bin/ruff check carina tests
```

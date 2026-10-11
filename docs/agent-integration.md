# Agent 接入说明

产品核心不依赖 Claude Code、Codex 或任何特定模型。固定计税引擎不调用模型、不联网；网页、命令行、HTTP API 和 Python 包共享同一个计算函数。Agent 只负责准备经人工确认的结构化事实，并选择一种公开接口调用。

## 能力发现

安装后可读取机器可读的能力声明和请求 Schema：

```powershell
overseas-income-tax capabilities
overseas-income-tax schema
```

HTTP 服务提供相同信息：

- `GET /api/v1/capabilities`
- `GET /api/v1/schema/calculation-request`

`contract_version` 表示调用契约版本；`api_version` 表示 URL 主版本。V1 内新增可选字段不会改变已有字段含义。破坏性变更使用新的 API 主版本。

## 命令行

JSON 可来自文件，也可通过标准输入传入。结果默认写到标准输出，错误以 JSON 写到标准错误；成功退出码为 `0`，输入或文件错误为 `2`。

```powershell
overseas-income-tax calculate --input examples/calculation-request.json --output result.json
overseas-income-tax export --input examples/calculation-request.json --output result.xlsx
overseas-income-tax extract --input statement.pdf --output extracted.json
```

支持管道调用：

```powershell
Get-Content -Raw examples/calculation-request.json | overseas-income-tax calculate
```

## HTTP/JSON

先启动本地服务：

```powershell
overseas-income-tax serve --host 127.0.0.1 --port 8765
```

调用计算接口：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8765/api/v1/calculate `
  -ContentType application/json `
  -InFile examples/calculation-request.json
```

其他接口：

- `POST /api/v1/extract`：`multipart/form-data`，字段名为 `file`
- `POST /api/v1/export.xlsx`：请求体与计算接口相同，返回 Excel

每个响应都包含 `X-Overseas-Income-Tax-API-Version`。旧的 `/api/*` 路径暂时作为兼容别名保留，新接入应使用 `/api/v1/*`。

服务默认只绑定本机地址，没有跨域开放，也不建立持久存储。若 Agent 在另一台机器或托管平台运行，应由部署方增加身份认证、TLS、访问控制和数据保留策略后再暴露服务。

## Python

Agent 也可以直接构造 `CalculationRequest`，调用纯函数：

```python
from overseas_income_tax import calculate

result = calculate(calculation_request)
```

JSON 边界可使用 `overseas_income_tax.codec.request_from_dict`；机器可读能力声明可使用 `overseas_income_tax.capabilities()`。

## Agent 的责任边界

Agent 不得绕过人工确认状态，也不能通过请求覆盖规则快照。客户端即使传入 `rule_snapshot`，服务端仍使用内置的权威快照。自动计算只覆盖已核验的境外利息和普通现金股息；其他事项返回待核验清单或仅整理材料。

`SKILL.md` 是支持 Skill 机制的 Agent 可选说明。它不参与程序启动、解析或计算。只要运行环境能调用 Python、命令行或 HTTP，便可接入同一产品契约。

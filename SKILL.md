---
name: overseas-income-tax
description: 中国居民境外收入（美国+香港）个人所得税申报计算。解析 IRS 1042-S 表格、美股券商年度报表、香港银行月结单，按中国人民银行汇率中间价折算人民币，计算利息/股息/红利所得（20%税率）的应补缴税额和境外税收抵免，并生成格式化 Excel 申报表。触发场景：境外收入申报、海外收入报税、1042-S 解析、银行利息计税、跨境税务、个税申报、税额计算、税务报表生成、海外股票股息申报。
---

# Overseas Income Tax — 境外收入税务申报 SKILL

帮中国居民把**美国来源收入**（1042-S + 美股券商报表）和**香港来源收入**（香港银行月结单利息/股息）一键折算为人民币、计算应补缴个税，并生成格式化 Excel 申报表。

## 开始前必读 `references/workflow.md`

完整端到端流程在 `references/workflow.md`。**任何任务都先读它**，它决定了从用户一句话到生成 Excel 的全部步骤。

## 任务路由表

| 用户提到 / 任务 | 必读 reference | 脚本 |
|------|------|------|
| 整体流程、不知从何下手 | `references/workflow.md` | — |
| 1042-S 表格、预扣税 | `references/1042s-parsing.md` | — |
| 美股券商报表、股息、经纪商利息 | `references/broker-statement.md` | — |
| 银行月结单、定期/活期利息 | `references/bank-statement.md` | — |
| 汇率、折算人民币 | `references/exchange-rate.md` | — |
| 税率、应补缴税额、税收抵免 | `references/tax-rules.md` | — |
| 数据核对、防错（Agent 自查清单） | `references/data-integrity.md` | — |
| 生成 Excel 申报表（Agent 当场写代码） | `references/generation-guide.md` | — |

## 脚本（只做纯 I/O，不做判断）

只有两个脚本，且只负责 Agent 做不了的确定性 I/O：

| 脚本 | 职责 |
|------|------|
| `scripts/setup_env.py` | 建虚拟环境、装 openpyxl/pypdf，打印 venv python 路径 |
| `scripts/extract_pdf.py` | 提取 PDF 文本到 .txt（含 Windows 中文编码修复） |

**收入识别、归类、金额计算、校验、Excel 生成全部由 Agent 当场判断和写代码**——和真人手工算税一致。脚本不预置判断逻辑，避免把 Agent 该做的思考固化掉。

## 三条铁律（违反即出错，必须遵守）

完整版见 `references/data-integrity.md`。摘要：

1. **所有数字必须来自原始 PDF 文件，禁止估算**。
2. **利息数据禁止自行按天数/利率推算**，取月结单记载值。
3. **生成 Excel 前必须按 `references/data-integrity.md` 自查清单逐项核对**，不一致项必须解释清楚才能交付。

## 典型触发

用户说"帮我算一下今年的境外税务"/"我要申报境外收入"/"这些月结单和券商结单帮我算税"，或把 PDF 材料放进文件夹后求助——立刻按 `references/workflow.md` 执行。

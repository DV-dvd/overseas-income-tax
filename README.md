# 境外收入税务申报辅助工具

面向中国税收居民，对**已经人工核验、来源地和性质明确的境外利息与普通现金股息**做范围内税额测算，整理证据，并生成申报底稿。它不代为申报，也不把范围外事项包装成全年最终税额。

当前是 V1 开发预览。网页、命令行、版本化 HTTP API、Python 包和 Excel 共用同一个固定计税引擎；模型不参与计税，运行时也不查询网络。产品不依赖 Claude Code、Codex 或任何特定 Agent 厂商。

## 已实现

- 本地网页流程：单独同意、适用性问卷、PDF 文本提取、事实核对、汇率记录、测算与导出
- 规则优先自动预填：已测试的 1042-S、储蓄账户月结单和券商活动报表版式形成待确认候选值
- 多文件上传：各文件独立显示识别状态，单个失败不影响其他材料，重复文件不重复生成事项
- 统一事实模型：原始观察值、经济事项、证据定位、确认原因和修订版本分开保存
- 适用性门禁：居民身份、申报情形、同国其他所得、历史抵免、退税与更正未确认时阻断完整结论
- 固定计税：利息与普通现金股息按规则快照计算，按国家或地区单列抵免账
- 数据完整性：相同文件与相同证据的重复上传不重复计税；有效修订表替代原表；汇总行不参与计税
- 汇总明细勾稽：1042-S 汇总事项与逐笔明细并存时阻断重复计税，需明确标记汇总凭证或删除重复项
- 版本化参考汇率：内置 2025-12-31 外汇管理局 USD/HKD 中间价记录，页面自动填入并保留官方来源
- 同源 Excel：页面与导出文件引用同一个 CalculationResult 和计算指纹
- Agent 中立接口：Python、CLI、HTTP/JSON、能力声明和 JSON Schema 共用版本化契约
- 可复算推导：页面和 Excel 展示文件、页码、原文、汇率、公式与规则版本，并支持随机抽检记录
- 离线消融门禁：覆盖重复上传、修订替代、汇总行误用、表单副本和同版本冲突；移除完整性层后结果必须变差

## 明确不做

- 资本利得和复杂理财的自动计税
- 特殊居民身份、补报往年、已有预缴或更正申报的自动处理
- 自动登录或提交电子税务局 / 个税 App
- 无人核对直接生成最终申报数
- 将 1042-S 任一单一栏位自动视为中国可抵免税额

“暂不支持”不等于“无需申报”。范围外项目会进入待核验清单。

## 本地运行

```powershell
python -m pip install -e ".[dev]"
overseas-income-tax
```

浏览器打开 <http://127.0.0.1:8765>。服务默认只绑定本机地址，文件在请求内存中解析，不建立持久存储。

## Agent 接入

支持三种正式调用方式：

```powershell
# 命令行：适合能执行本地工具的 Agent
overseas-income-tax calculate --input examples/calculation-request.json

# HTTP：适合跨进程或平台型 Agent
overseas-income-tax serve
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/v1/calculate -ContentType application/json -InFile examples/calculation-request.json
```

Python 调用使用 `overseas_income_tax.calculate`。`overseas-income-tax capabilities` 输出机器可读能力，`overseas-income-tax schema` 输出请求 JSON Schema。`SKILL.md` 只是可选适配说明，程序运行时不读取它。

完整契约、稳定性和安全边界见 [Agent 接入说明](docs/agent-integration.md)。

## 验证

```powershell
python -m pytest
python -m experiments.integrity_ablation
```

合成对抗数据只用于回归门禁，不能据此宣称真实用户资料的准确率。上线前仍需建立按“纳税人 × 税年”组织、由独立人员复核的金标准，并完成模型 × 机构规则的 2×2 评估；在此之前模型保持关闭。

自动预填同样不宣称通用准确率。当前只对测试覆盖的 1042-S、储蓄账户月结单和券商活动报表文本版式启用规则候选提取；候选值默认不进入计税，必须由用户确认所得性质、来源地和可抵免金额。替代股息付款作为范围外事项显式阻断最终标签；扫描件及其他未验证版式只整理材料并提示人工核对。

## 结构

```text
src/overseas_income_tax/
├── models.py       # 事实、问卷、规则快照与结果对象
├── integrity.py    # 去重、修订替代、证据完整性
├── eligibility.py  # V1 适用性门禁
├── engine.py       # 固定计税；无模型、无网络、无文件 I/O
├── extraction.py   # PDF 文本 I/O
├── recognition.py  # 规则优先的候选事实识别
├── reference_rates.py # 版本化官方参考汇率
├── exporter.py     # 从 CalculationResult 生成 Excel
├── codec.py        # API 输入边界
├── contract.py     # 能力声明、API 与契约版本
├── cli.py          # Agent 中立命令行接口
├── schemas/        # 机器可读请求契约
└── web.py          # 单体应用的页面与 API
```

模块边界遵循“提取 → 候选 → 核对 → 固定计税 → 展示导出”。替换解析器不应改动税务核心，修改页面或表格样式不应改变金额。

当前完成度见 [V1 实施状态](docs/implementation-status.md)，数据流见 [隐私与数据流](docs/privacy-data-flow.md)，申报入口见 [电脑端申报路径](references/filing-guide.md)。

## 规则依据

- [《中华人民共和国个人所得税法实施条例》](https://www.chinatax.gov.cn/chinatax/n810219/n810744/n3752930/n3752974/c3963364/content.html)
- [财政部、税务总局公告2020年第3号](https://12366.chinatax.gov.cn/bzds/082/082-5-4.html)
- [国家外汇管理局人民币汇率中间价](https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do)

规则快照版本写入每次计算与导出文件。结果仅作为申报辅助，不构成税务意见，最终以主管税务机关确认为准。

## License

MIT

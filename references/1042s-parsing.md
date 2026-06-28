# IRS Form 1042-S 解析规则

1042-S 是 IRS 出具给非美国税务居民、记录"美国来源收入及预扣税"的官方税务凭证。**它是中国申报"境外已缴税额"用于税收抵免的唯一权威凭证**。

## 关键字段定位

PDF 提取出的文本是行内拼接的（字段名紧跟数值），需正则或模式匹配提取：

| 字段 | 文本标记（英文） | 含义 | 用途 |
|------|------|------|------|
| Form identifier | `UNIQUE FORM IDENTIFIER` 前的 10 位数字 | 表格唯一号 | 去重依据 |
| Income code | `1Income code` 下一个数 | 收入类型代码 | 判定收入性质 |
| Gross income | `2Gross income` 下一个数 | 毛收入 | 申报收入 |
| Tax rate | `3bTax rate` 下一个数 | 预扣税率 | 校验 |
| Federal tax withheld | `7aFederal tax withheld` 下一个数 | 已扣美国税 | **境外已缴税额（以此为准）** |
| Recipient's name | `13aRecipient's name` 后 | 收款人姓名 | 核对 |
| Copy 类型 | `Copy B` / `Copy C` / `Copy D` | 副本类型 | 去重 |

## 去重规则（重要）

**一张 1042-S 表格包含 Copy B / Copy C / Copy D 三联，数据完全相同**。按 `Form identifier` 去重，每个 identifier 只保留一份（任选 Copy，通常取 Copy B）。

例如一份 9 页的 1042-S PDF，实际可能只有 3 张表格（每张 3 联 = 9 页）。

## Income Code 对照表（常见）

| 代码 | 收入类型 | 中国申报归类 |
|------|---------|-------------|
| 01 | Interest paid by U.S. obligors（美国利息） | 利息所得 |
| 06 | Dividends paid by U.S. corporations（股息） | 股息红利所得 |
| 33 | Substitute payment-interest（替代支付利息） | 利息所得 |
| 34 | Substitute payment-dividends（替代支付股息） | 股息红利所得 |

## Chapter 3 豁免代码（box 3a）

当 box 3b 税率为 `00.00` 时，box 3a 会标注豁免原因：

- `04` = Exempt under tax treaty（税收协定豁免）
- `05` = Portfolio interest exempt（组合利息豁免，常见于国债ETF利息）
- `00` = 无豁免（正常纳税）

## 境外已缴税额的取值规则

**只采用 1042-S box 7a 的值**，即使券商年度报表显示实际代扣更多。

原因：1042-S 是 IRS 官方凭证，中国税务机关认这个。券商多扣的部分（如实际代扣 $112.75 但 1042-S 只报 $96.00）属于券商预扣与 IRS 申报的差异，需用户另行向券商/IRS 申请调整，**不能直接用于中国税收抵免**。

遇到这种差异，在申报表备注中标注，提醒用户。

## 已知陷阱：收入分类差异

券商年度报表和 1042-S 对同一笔收入的**分类可能不同**：

- **SGOV 等美国国债 ETF**：券商列为"股息"，但 IRS 在 1042-S 中归为"利息"（income code 01，豁免代码 05 组合利息）
- 因此 1042-S 股息合计 ≠ 券商股息合计，差异部分跑到了 1042-S 利息里

**处理原则**：中国申报收入金额时，按 1042-S 的分类填报（利息归利息、股息归股息），券商报表作为补充和交叉验证。两者差异要在申报表注释中说明。

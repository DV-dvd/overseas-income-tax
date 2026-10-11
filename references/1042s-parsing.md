# IRS Form 1042-S：候选事实提取与核对

1042-S 是重要证据之一，但不能把任何单一栏位自动等同于中国税收抵免额。

## 分别记录的字段

- Unique Form Identifier
- 税年、扣缴方、收款人
- Income code 与 Gross income
- Box 7a：Federal tax withheld
- Box 8：Tax withheld by other agents
- Box 9：Overwithheld tax repaid to recipient
- Box 10：Total withholding credit
- 是否 Amended、修订号和被替代版本

报表显示扣税、符合中国规则的已缴所得税、限额内实际抵免是三个不同数。候选识别可以抽取 box 7a/8/9/10，但不得直接给出“可抵免额”。

## 原表、修订表与副本

Copy B/C/D 可能是同一表的副本。内容哈希、表号、税年、扣缴方、收款人和修订号共同用于关联。有效修订表替代原表；存在并列修订、字段冲突或关系不明时必须阻断。

## 所得类别与来源地

Income code 只能作为候选线索。最终类别仍需按中国规则确认。证券代码、券商所在地、币种和交易场所不能单独决定所得来源国家（地区）。

## 抵免凭证

中国认可的抵免凭证范围不自行限定为 1042-S。应核对税款性质、实际缴纳、退税或补偿、税收协定，以及税务机关要求的纳税凭证或替代材料。

依据：[财政部、税务总局公告2020年第3号](https://12366.chinatax.gov.cn/bzds/082/082-5-4.html)

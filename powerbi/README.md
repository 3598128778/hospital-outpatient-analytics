# Power BI Desktop 复现

交付包括可粘贴执行的 Power Query、DAX、主题和建模步骤。**本仓库不包含已经在 Desktop 中保存、验证过的 `.pbix` 文件**。Python 看板可直接运行；Power BI 报表按以下步骤搭建，预计 20–30 分钟。无需购买 LLM 服务即可使用规则摘要。

## 1. 生成并导入

1. 在项目根目录运行 `python -m hospital.pipeline --generate`。
2. Power BI Desktop → 获取数据 → 空白查询 → 高级编辑器，粘贴 `Bundle.pq`。
3. 将 `Root` 修改为项目的 `artifacts` **绝对路径，保留末尾反斜杠**。查询命名为 `Bundle`，关闭其“启用加载”。
4. 分别建立六个空白查询，查询名和公式如下，开启加载：

| 查询名 | 公式 |
| --- | --- |
| Daily | `= Bundle[Daily]` |
| Alerts | `= Bundle[Alerts]` |
| Registrations | `= Bundle[Registrations]` |
| Visits | `= Bundle[Visits]` |
| Charges | `= Bundle[Charges]` |
| Summary | `= Bundle[Summary]` |

5. 关闭并应用。`business_date` 应是日期类型；金额存储字段应是整数分，不要直接当元展示。

## 2. 模型与关系

逐个运行 `measures.dax` 的三个计算表定义（Calendar、Departments、Periods），将 Calendar 标记为日期表，日期列为 Date。

建立以下**一对多、单向**关系。关闭自动检测产生的其他关系，避免循环与重复筛选：

| 一侧 | 多侧 |
| --- | --- |
| Calendar[Date] | Daily[business_date]、Alerts[business_date]、Registrations[business_date] |
| Departments[department] | Daily[department]、Alerts[department]、Registrations[department] |
| Periods[period] | Daily[period]、Registrations[period] |
| Registrations[registration_id] | Visits[registration_id]、Charges[registration_id] |

Visits 每挂号最多一条；若 Power BI 自动设成一对一，请按模型可用选项确保不会使收费反向筛选聚合表。Summary 无关系，它是本次全量批次摘要，不受页面切片器影响。**不要把 Daily 与 Charges 直接关联**。

逐一新建 DAX 度量值；金额/客单价格式设为人民币两位小数，比率设为百分比。不得求 `avg_spend` 列的平均值或把各科室的同比率相加。

## 3. 报表页面与下钻

导入 `theme.json`。页面建议 16:9，顶部注明“模拟数据”。

| 页面 | 图表与字段 | 交互 |
| --- | --- | --- |
| 运营总览 | 门诊量、就诊量、净收费、客单价卡片；Calendar[Date] 折线；Departments[department] 柱图 | 日期、科室、时段切片器来自维表 |
| 科室与时段 | 行＝科室，列＝时段，值＝就诊量的矩阵，设置背景色条件格式 | 右键科室钻取到明细页 |
| 月度对比 | Calendar[YearMonth]、净收费、净收费同比、净收费环比 | 只在完整单月展示比较值；没有历史则为空 |
| 异常与明细 | Alerts 表；Registrations 表；Charges 表 | 钻取字段 department、business_date；挂号单号切片器筛选收费与就诊 |
| 批次解读 | Summary[summary] 多行文本表 | 全量批次摘要；不宣称随页面过滤实时变化 |

异常按科室全天统计，时段切片器不影响 Alerts。请在异常页明确标注此范围，金额 actual/baseline/threshold 的 `net_cents` 行需要除以100后展示。

## 4. 刷新、AI 与核验

重新执行管道后，在 Power BI 点击刷新。若要更新批次 AI 解读，运行 `python -m hospital.report --llm`，再刷新 Summary；不传 `--llm` 时使用规则摘要。

基准验收（seed=42，全量，不加筛选）：门诊量 **41,769**；完成就诊 **38,446**；净收费 **7,692,787.92 元**；客单价 **200.09 元**。这些是模拟运行结果，不是医院业绩。对照 `artifacts/run_report.json`。

完整月同比/环比应与 Streamlit 月表一致；不要拿首页“前等长期间”当作自然月环比。Desktop 中实际导入、视觉布局与 DAX 执行仍需本机验证。

MySQL 模式也会导出相同 CSV，因此可复用全部步骤；需要数据库直连时可使用 `sql/daily_metrics.sql` 作为源查询，但还需补齐日历零值组合才能保持异常和月份覆盖口径，不建议跳过现有导出层。

参考：[Microsoft Csv.Document](https://learn.microsoft.com/en-us/powerquery-m/csv-document)、[DAX DIVIDE](https://learn.microsoft.com/en-us/dax/divide-function-dax)。

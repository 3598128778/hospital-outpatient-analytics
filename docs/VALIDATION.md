# 验收记录

验证日期：2026-10-08；系统：Windows；Python：3.12.14。所有业务数据均由 seed=42 生成。

| 检查 | 实际结果 |
| --- | --- |
| 完整 SQLite 管道 | 运行成功；44,373行原始挂号、38,447行原始就诊、77,894行原始收费 |
| 清洗与审计 | 6条隔离；每表 input=accepted+quarantined |
| 指标计算 | 41,769有效挂号，38,446完成就诊，769,278,792分净收费 |
| 自动测试 | 11 passed, 1 skipped；跳过项为本机无 MySQL 服务的后端一致性测试 |
| Streamlit AppTest | 页面加载、科室/时段筛选、规则摘要生成均通过 |
| 大模型调用 | 请求体与响应解析使用 mock 测试通过；没有配置真实服务密钥，未产生真实 API 调用 |
| Power BI | 已交付 M/DAX、主题与建模说明；未在 Power BI Desktop 中执行，无已验收 PBIX |
| Docker Compose | 已交付配置；本机没有 Docker，未运行本地容器 |
| MySQL CI | 发布后由 GitHub Actions 验证，结果待记录 |

重跑测试命令：`python -m pytest -q`。重跑指标：`python -m hospital.pipeline --generate`。完整输入哈希与结果位于运行生成的 `artifacts/run_report.json`。

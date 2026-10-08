# 从零复现与排障

## Windows（推荐 Python 3.12）

先安装 Python 3.12 并加入 PATH、Git。确认 `python --version` 是3.12，不要用系统中旧的3.7/3.8。

```powershell
git clone https://github.com/3598128778/hospital-outpatient-analytics.git
cd hospital-outpatient-analytics
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m hospital.pipeline --generate
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1
```

浏览器访问 http://127.0.0.1:8501。仓库发布前也可直接进入本地项目目录，从创建环境开始。已有环境可用 `powershell -ExecutionPolicy Bypass -File scripts/run_demo.ps1`，仅对这次运行放开本地脚本策略。

Linux/macOS：`bash scripts/run_demo.sh`，要求 `python3` 为3.12且具备 venv 支持。基础数据管道本身仅使用标准库，界面、MySQL 和测试使用 requirements 中依赖。

顶层依赖固定版本；`requirements-lock.txt` 记录实际验证环境的完整解析版本，便于同平台严格重建。跨平台首选 requirements.txt，CI 每次重新验证解析结果。

## MySQL + Docker Compose

安装 Docker Engine/Desktop，确认 `docker compose version` 可用。此方式会启动独立的 MySQL 8.4 演示库和看板，不修改现有业务库。

```powershell
Copy-Item .env.example .env
# 编辑 .env：更改 MYSQL_ROOT_PASSWORD 和 MYSQL_PASSWORD
docker compose up --build -d
docker compose logs -f app
```

看到 Streamlit 启动后访问 8501；导出文件位于宿主机 artifacts。`docker compose down` 停止服务并保留 MySQL 卷。再次启动会重建模拟数据并替换演示库三张表。不要连接含其他用途数据的同名表。

如只使用已存在的 MySQL（先创建专用库和账号，授予建表/读写权限）：

```powershell
$env:MYSQL_HOST='127.0.0.1'
$env:MYSQL_PORT='3306'
$env:MYSQL_DATABASE='hospital_demo'
$env:MYSQL_USER='hospital'
$env:MYSQL_PASSWORD='你本机设置的密码'
./.venv/Scripts/python.exe -m hospital.pipeline --generate --backend mysql
$env:TEST_MYSQL='1'
./.venv/Scripts/python.exe -m pytest -q tests/test_pipeline.py
```

测试使用该演示库替换固定测试数据，测试后重新运行完整管道。GitHub Actions 配有 MySQL 服务，执行全量 SQLite/MySQL 指标逐字节比对；只有实际 CI 成功后才能视作验证通过。

## AI API 配置

兼容接口必须支持 `POST {LLM_BASE_URL}/chat/completions`、messages、model、temperature 和 max_tokens，并返回 choices[0].message.content。

```powershell
$env:LLM_BASE_URL='https://你的服务域名/v1'
$env:LLM_API_KEY='你的密钥'
$env:LLM_MODEL='你的模型标识'
./.venv/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1
# 或保存全量批次摘要，供 Power BI 刷新
./.venv/Scripts/python.exe -m hospital.report --llm
```

本地 Python 不自动加载 .env；使用上面的环境变量。Docker Compose 自动读取 .env。密钥不会提交 Git，也不会出现在错误提示中。LLM 不可用时可手动选择规则摘要；不会把离线输出冒充模型生成结果。

## 演示路线

1. 首页选择 2026-06-01 至 2026-06-30，查看四个核心指标和月度比较。
2. 查看科室×时段矩阵，将科室切换为儿科。
3. 在异常表找到 6月15日，日期缩小到当天，依次比较上午、下午、晚间。
4. 选择挂号单号，核对一条就诊与多条收费的关系。
5. 改为内科、6月22日，查看收费异常；说明异常只提示偏离，原因需要排班/收费明细等证据。
6. 数据质量页查看6条隔离记录及源行号。
7. AI页先查看输入 JSON，再生成规则摘要；如已配置 API，可切换真实大模型。
8. 按 `powerbi/README.md` 生成同口径 BI 报表并核对全量基准数值。

## 常见问题

- 找不到 streamlit / pytest：使用 `.venv` 中同一个 Python 执行安装和启动。
- 安装报 Python 版本不支持：使用3.12重建虚拟环境；不要提交或拷贝其他机器的 .venv。
- 8501端口占用：增加 `--server.port 8502`。
- MySQL 连接失败：确认服务就绪、密码、端口、专用库名称；Compose 应用内主机名为 mysql，本机为127.0.0.1。
- 没有历史同比：需要完整上一年同月数据，NULL 不是0%。
- SQL 计数偏大：先按 registration_id 汇总收费；不可把原始三表直接 join 后 count。
- Power BI 中文乱码：导入 UTF-8，编码65001；Bundle 已设置。
- GitHub 登录失败：执行 `gh auth login --hostname github.com --git-protocol https --web`，只在 GitHub 官方页面输入设备码。

参考：Streamlit [图表接口](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart)、Microsoft [CSV 数据源](https://learn.microsoft.com/en-us/power-query/connectors/text-csv)。

# Apex Patch Feedback Copilot

中文名：Apex 版本反馈与问题分流助手。

一个本地运行的 Streamlit MVP：导入 EA 官方 Designer’s Notes，把版本改动结构化；接收已授权导出的 B站评论 CSV；通过 SiliconFlow 的 OpenAI-compatible 接口，用默认开启思考的 GLM-5.3-Flash 完成评论语义分析和受限方向总结；由 Python 独立计算透明统计，并提供证据追溯、人工复核、抽样验证和 Markdown/CSV/JSON 导出。

> 内置演示项目、英雄、改动和评论均为虚构内容，不代表 EA 官方信息或真实 Apex 玩家反馈。

## 快速开始

推荐 Python 3.11。项目代码同时兼容 Python 3.10–3.12。
Windows 用户可直接双击项目根目录的 `run_app.bat`。它会创建 `.venv`、检查/安装依赖并启动浏览器；关闭命令窗口即可停止应用。


```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

打开终端显示的本地地址。首次启动自动加载演示项目，不需要 API Key。

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## SiliconFlow 配置

推荐直接在应用左侧展开 **API 与模型设置**：

1. 输入 SiliconFlow API Key 和 Base URL。
2. 点击“测试 API 并获取模型”。
3. 选择文本分析模型与思考强度。
4. 点击“保存 API 与模型”。配置只会写入本机 `.env`，完整 Key 不会在界面回显。


编辑 `.env`：

```dotenv
SILICONFLOW_API_KEY=你的密钥
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_TEXT_MODEL=支持 JSON 输出的文本模型名
SILICONFLOW_REASONING_EFFORT=high
```

### 模型与思考强度

版本导入与评论分析共用同一个文本模型，默认 `zai-org/GLM-5.3-Flash`。该模型的思考能力**始终开启、无法关闭**，只能通过 `reasoning_effort` 调节深度：

| 取值 | 含义 | 适用 |
| --- | --- | --- |
| `low` | 思考链最短 | 大批量预跑、先看分布 |
| `high`（默认） | 平衡速度与判断质量 | 日常分析 |
| `max` | 思考链最长，token 消耗最高 | 少量疑难评论 |

未识别的取值会被上游静默解析成 `max`（最贵的一档），因此应用会把它收敛回 `high`，不会在无意中放大账单。思考内容按输出 token 计费，API 控制台会分别显示正文与思考的字符数。

密钥不会写入代码、项目 JSON、导出文件或应用日志。未配置时，模型按钮会给出配置提示，其他页面和完整演示模式仍可用。
### Windows Schannel 传输保护

- 所有 SiliconFlow 结构化请求默认只发送一次；超时、空响应、429、5xx 和流式中断均不会自动重试。
- Windows curl 使用 HTTP/1.1。若仅发生 Schannel missing close_notify，应用只在 HTTP 2xx、无损坏 SSE 分片、完整 JSON 文档和 Pydantic 数据结构全部通过时复用本次响应，不会发送第二次请求。
- finish_reason=length、内容过滤、截断 JSON 或结构校验失败不会保存；API 控制台会显示正文/思考字符数、chunks、usage 是否返回、可能计费状态和自动重试状态。
## B站评论 CSV 导入

推荐先使用原项目作者维护的 [新版浏览器扩展](https://github.com/1dyer/bilibili-comments-extension) 导出 CSV；也兼容 [bilibili-comment-crawler](https://github.com/1dyer/bilibili-comment-crawler) 的导出字段。

1. 在有权处理目标评论的前提下，用扩展或 Python 工具导出 CSV。
2. 打开“评论导入与语义分析”，上传 CSV，可选填写 B站来源页。
3. 确认授权并设置本次导入上限；默认 200 条，导入过程不调用任何模型 API。
4. 应用只保留评论正文、点赞数、时间和回复关系。用户名、UID、IP属地、头像、签名、等级、性别和会员状态会在进入项目之前丢弃。

同一评论会使用不可逆匿名指纹去重，因此后续导入更大的增量 CSV 不会重复写入。应用不读取浏览器 Cookie、不保存原始 CSV，也不绕过平台访问限制。

## 三阶段 AI 流水线

1. 评论导入：B站 CSV 直接匿名化结构化，全程不调用模型。
2. Python 清洗、RapidFuzz 去重，并应用人工关键词与社区别名词典。
3. 文本模型按 10–20 条分批结合平台、点赞、回复上下文和来源文件映射改动；程序验证 comment_id 和原文引用。
4. Python 独立计算统计并生成人工复核队列；可选方向总结只能基于固定统计，不可改写计数。

### 分析进度、中断与续跑

分析按批执行：**每批一次请求，每批结束立即落盘**，然后才发起下一批。由此得到三个保证：

- **进度可见**：界面显示「已分析 N/M 条」、当前批次号，以及累计的输入 / 输出 / 思考 token。
- **随时可停**：点击「停止分析（保留已完成部分）」后，本轮已返回的结果全部保留并提示完成条数；直接关闭浏览器同理。
- **续跑不重复计费**：再次点击分析只会请求**尚无分析结果**的评论，中断前已完成的不会重新发送。

若某批请求失败（网络、配额、会话调用上限或结构校验不过），已保存的前几批不受影响，修正后继续即可。

### 请求负载与输出预算

每批请求都必须自带改动清单，因此它是长语料上最大的输入开销。应用只发送影响映射判断的 7 个改动字段、截断长文本、评论行使用短键并省略空字段，整批共用的来源文件提升到批次层。代表性语料上（20 改动 × 20 评论）单批负载从 20,742 字符降到 7,698 字符，约减少 63%。

输出侧只有 `reasoning_summary` 与 `evidence_quote` 是自由文本。提示词限定其长度，`CommentAnalysis` 再做一次兜底裁剪，避免模型啰嗦时拖垮整批的 token 预算。

## EA 获取规则

- 仅允许 `https://ea.com` 与 `https://www.ea.com`。
- 自动入口为 `https://www.ea.com/games/apex-legends/apex-legends/news`。
- 请求设置 User-Agent、连接/读取超时和最多两次有限重试，并验证最终重定向域名。
- 自动发现失败时可手动粘贴 EA 官方文章 URL，不阻塞演示或后续本地流程。

## 项目结构

```text
app.py                          Streamlit 入口（仅页面配置、全局样式、调用 shell）

src/core/                       领域层：数据契约与纯计算，不依赖 Streamlit / 网络 / 环境变量
    paths.py                    统一的路径常量（唯一允许推导项目根目录的地方）
    settings.py                 .env 读取与保存，Settings 值对象
    models.py                   Pydantic 数据契约与模型输出纠错
    analytics.py                refresh_reviews：统计重算 + 复核队列收敛
    aggregation.py              透明统计
    validation.py               抽样验证指标
    deduplicator.py             精确/模糊去重
    comment_cleaner.py          文本清洗
    community_aliases.py        社区别名词典与 workspace 覆盖
    article_parser.py           文章章节解析
    bilibili_importer.py        B站导出 CSV 匿名化导入
    review_manager.py           复核队列与审计记录
    reporting.py                Markdown/CSV/JSON 导出

src/integrations/               外部系统适配：网络、文件系统、前端组件
    siliconflow_client.py       OpenAI-compatible 客户端与 JSON 校验
    api_monitor.py              API 调用、Token 与传输恢复记录
    ea_fetcher.py               EA 白名单抓取
    project_store.py            项目 JSON 原子写入
    comment_store.py            评论语料持久化
    prompt_store.py             提示词文件与会话内覆盖

src/services/                   用例编排：组合 core 与 integrations，不依赖 Streamlit
    project_service.py          项目引导、语料恢复与保存
    article_service.py          文章导入与改动清单编辑/合并
    comment_service.py          导入、清洗、去重、人工修正
    analysis_service.py         语义分析、方向总结、抽样验证
    change_history.py           改动清单历史快照
    patch_structurer.py         改动结构化
    comment_analyzer.py         评论语义分析
    insight_generator.py        第三阶段受限方向总结
    demo_data.py                虚构演示项目和截图生成

src/ui/                         Streamlit 表现层：布局、组件与 HTML 片段
    app_shell.py                装配 AppContext 并路由到当前主线步骤
    state.py                    AppContext：会话状态与依赖容器
    theme.py                    全局样式与配色常量
    charts.py                   堆叠条、改动卡片、引用等 HTML 片段
    components/
        stepper.py              主线步骤导航：进度 + 唯一入口
        sidebar.py              API 配置与会话控制（编辑器收进「高级」）
        review_panel.py         人工复核表单与队列
        export_panel.py         导出区
        api_settings.py / api_console.py / editors.py
    pages/                      四个主线步骤页，统一暴露 render(ctx)
        import_page.py          ① 提取更新内容
        comments_page.py        ② 评论收集
        analysis_page.py        ③ 分析评论
        results_page.py         ④ 统计结果

data/demo/                      演示 JSON
workspace/                      用户本地项目
tests/                          pytest 测试
```

## 界面主线

界面按「提取更新内容 → 评论收集 → 分析评论 → 统计结果」四步组织，顶部步骤条既是导航也是进度条，每步显示该步的实时数字（改动数 / 评论数 / 已分析数 / 待复核数）。没有第二个导航入口。

- **① 提取更新内容**：左侧取文章（自动查找 / 粘贴 URL / 演示项目）并结构化，右侧是改动清单表格与确认。
- **② 评论收集**：左侧导入 CSV，右侧是清洗与去重表格，可直接修正原文与人工关键词。
- **③ 分析评论**：启动分析（进度、批次、token、可停止），下方是改动 × 立场速览表和人工复核队列。
- **④ 统计结果**：指标、改动矩阵（带条形进度）、改动卡片与代表性评论；方向总结、抽样验证、导出收在折叠面板里。

### 分层约定

依赖方向只允许单向：`ui → services → core`，`integrations → core`。

- `core` 不 import Streamlit，不读环境变量，不发起网络请求 —— 因此可以在没有 UI 的情况下直接测试。
- `services` 接收普通数据、返回普通数据；需要进度反馈时由 UI 传入回调，服务本身不知道 Streamlit 的存在。
- `ui` 只做控件与渲染，业务判断一律下沉到 `services` / `core`。
- 任何需要定位项目文件的模块都从 `core.paths` 取路径，不要再写 `Path(__file__).parents[n]`。

## 已知边界

- 评论 CSV 是便利样本，不能代表全部玩家；讨论频率不等于问题严重度。
- 不自动抓取社区、不读取或保存 Cookie、不绕过验证码；只接收用户有权处理的导出 CSV，并可选保存去跟踪参数后的 B站来源页。
- 不判断版本整体成败、不预测在线率/留存、不生成精确平衡数值。
- EA 页面结构变化时规则解析可能降级；界面会保留手动 URL 和人工编辑兜底。
- 真实 SiliconFlow 调用必须由使用者配置模型后验证；不同模型对 `json_object` 的兼容性可能不同。


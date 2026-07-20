# Agent Router

一个规则优先、可替换 LLM 的 AI Agent 专家与 Skill 自动路由 MVP。

## 已实现

- 专家（expert）与 Skill 的统一注册模型
- 基于关键词、标签、能力和约束的可解释打分
- 自动选择 1 个专家 + 若干 Skill
- FastAPI API：`/health`、`/catalog`、`/route`
- 无需真实 LLM 即可运行和测试
- 通过 `Router` 协议预留 LLM rerank 扩展点

## 启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
uvicorn app.main:app --app-dir src --reload
```

打开 http://127.0.0.1:8000/docs。

## 示例

```powershell
curl.exe -X POST http://127.0.0.1:8000/route `
  -H "Content-Type: application/json" `
  -d '{"task":"分析销售数据并生成可视化报表","constraints":{"no_external_write":true}}'
```

## 下一步

1. 用 embedding 做语义召回（保留规则分数作为安全下限）。
2. 增加 LLM reranker，只允许它在候选集内重排。
3. 接入真实 Skill 执行器与审计日志。
4. 增加离线评测集：任务、期望专家、期望 Skill、风险等级。

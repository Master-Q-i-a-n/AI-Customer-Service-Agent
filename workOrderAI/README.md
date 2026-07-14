# AI Customer Service Agent AI Service

FastAPI AI 服务，使用 LangChain、LangGraph、Milvus Lite 和通义千问模型提供客服 Agent、检索增强问答、历史案例记忆、工单分析与离线评测能力。

## 能力范围

- **顾客侧 Agent**：售前扫地机器人咨询、知识问答、订单/使用记录查询、售后故障和退款协助。
- **售前推荐**：维护预算、户型、地面、宠物、基站和噪音等会话状态；通过 Spring Boot 商品工具查询真实 SKU，支持商品详情和两款对比。
- **工单辅助**：工单分类、优先级和情绪分析，以及管理员回复建议。
- **RAG 与案例记忆**：知识库支持 HyDE、BM25 与向量混合检索、重排和来源回传；已解决工单可沉淀为历史案例并在相似问题中召回。
- **质量控制**：LangGraph 工作流包含语义路由、分支处理、Self-Check 和最多一次重写；业务事实由工具接口提供。

## 本地启动

### 1. 安装依赖

项目推荐使用根目录 `AGENTS.md` 中的 Conda Python 环境：

```powershell
D:\anaconda3\envs\Agent\python.exe -m pip install -r workOrderAI\requirements.txt
```

### 2. 配置环境变量

推荐在仓库根目录 `.env` 中配置，或在 PowerShell 会话中设置：

```powershell
$env:DASHSCOPE_API_KEY='your_api_key'
$env:AI_MYSQL_HOST='127.0.0.1'
$env:AI_MYSQL_PORT='3306'
$env:AI_MYSQL_USER='root'
$env:AI_MYSQL_PASSWORD='your_password'
$env:AI_MYSQL_DATABASE='work_order'
```

可选的 LangSmith 配置：

```powershell
$env:LANGSMITH_API_KEY='your_langsmith_api_key'
$env:LANGSMITH_TRACING='true'
$env:LANGSMITH_PROJECT='ai-customer-service-agent'
```

环境变量会覆盖 `config.yaml` 中相应配置。不要提交 `.env`、真实 API Key、`data/`、`logs/` 或评测结果。

### 3. 启动 FastAPI

在仓库根目录执行：

```powershell
D:\anaconda3\envs\Agent\python.exe -m workOrderAI.main
```

默认监听 `http://127.0.0.1:8003`，可访问 `http://127.0.0.1:8003/docs` 查看 OpenAPI 文档。

## 与 Spring Boot 的边界

AI 服务通过内部接口查询商品、订单、退款和当前用户记录，内部调用使用 `X-Internal-Agent-Token`。模型不得自行生成价格、库存、订单状态、退款资格或金额；退款执行必须由 Spring Boot 后端重新校验，并经过管理员审核。

## 评测

在仓库根目录执行：

```powershell
D:\anaconda3\envs\Agent\python.exe -m workOrderAI.evals.run --suite core --mode local
D:\anaconda3\envs\Agent\python.exe -m workOrderAI.evals.run --suite presale --mode local --skip-judge
```

评测套件和 LangSmith 同步说明见 [evals/README.md](evals/README.md)。

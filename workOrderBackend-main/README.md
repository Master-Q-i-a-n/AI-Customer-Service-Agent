# AI Customer Service Agent Backend

Spring Boot + MySQL 业务服务，负责认证、商品、订单、物流、退款、工单、文件和 AI 会话持久化。AI 服务可以生成建议和发起受控工具调用，但商品事实、退款资格、退款金额和执行状态均以后端规则与数据库为准。

## 主要职责

- 顾客与管理员认证、会话和权限。
- 商品与 SKU 数据：为售前 Agent 提供真实的价格、库存和结构化参数查询。
- 订单、物流、使用记录、退款申请和管理员审核。
- 工单创建、分类结果保存、回复记录和历史案例沉淀。
- AI 客服会话：首条消息才创建会话；历史会话使用软删除，删除后不再对用户可见。
- 调用 FastAPI AI 服务，并通过内部令牌保护商品、订单和退款工具接口。

## 本地启动

### 1. 前置环境

- JDK 17
- Maven 3.8+
- MySQL 8
- 已启动的 AI 服务，默认地址为 `http://127.0.0.1:8003`

先创建数据库：

```sql
CREATE DATABASE work_order
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 2. 配置环境变量

```powershell
$env:WORKORDER_DB_URL='jdbc:mysql://127.0.0.1:3306/work_order?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai'
$env:WORKORDER_DB_USERNAME='root'
$env:WORKORDER_DB_PASSWORD='your_password'
$env:WORKORDER_AI_SERVICE_BASE_URL='http://127.0.0.1:8003'
$env:WORKORDER_AI_INTERNAL_TOKEN='local-refund-agent'
```

`WORKORDER_AI_INTERNAL_TOKEN` 必须与 AI 服务调用内部业务接口时使用的令牌一致。

### 3. 启动服务

```powershell
$env:JAVA_HOME='D:\Java\jdk-17'
$env:NO_PROXY='localhost,127.0.0.1,::1'
mvn spring-boot:run
```

服务默认监听 `http://127.0.0.1:8080`。在本项目约定的本地环境中，也可使用根目录 `AGENTS.md` 中的 Maven 路径执行命令。

## 数据初始化与访问地址

- 启动时执行 `src/main/resources/workorder-schema.sql` 并补齐演示数据。
- 演示账号：`user / user123`、`admin / admin123`。
- 健康检查：`http://127.0.0.1:8080/api/health`
- Swagger：`http://127.0.0.1:8080/swagger-ui.html`
- 上传文件默认位于 `${user.dir}/uploads`，可通过 `WORKORDER_UPLOAD_DIR` 修改。

## 测试

```powershell
mvn test
```

可使用仓库根目录的 Docker Compose 一次启动 MySQL、AI 服务、后端和前端；完整说明见 [根 README](../README.md)。

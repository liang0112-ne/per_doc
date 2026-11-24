# per_doc 总体框架设计

> 项目的**唯一架构事实来源**。每完成一个模块必须回填本文档的进度表。
> 需求与范围见《per_doc 重构方案》，编码规范见 `.cursor/rules/` 与 `*/rules/`。

---

## 1. 项目定位

**per_doc** 是从 MinDoc（Go + Beego）重构建的轻量级文档管理与录入系统。

- 当前阶段目标：**基础的 Markdown 文档写入与存储**
- 架构要求：为文件解析、向量索引、智能体对话、工具调用预留插槽

---

## 2. 技术栈

| 层 | 选型 | 版本 |
|---|---|---|
| 后端语言 | Python | 3.12+ |
| 后端框架 | FastAPI | 0.115+ |
| ORM | SQLAlchemy | 2.0（`Mapped[]` 语法） |
| 校验 | Pydantic v2 | 2.x |
| 迁移 | Alembic | 1.13+ |
| 数据库 | SQLite（默认）/ PostgreSQL | - |
| 前端 | Vue | 3.4+ |
| 前端语言 | TypeScript | 5.x（strict） |
| 构建 | Vite | 5.x |
| 状态 | Pinia | 2.x |
| UI | Element Plus | 2.x |

---

## 3. 总体架构

### 3.1 后端分层

```text
app/
├── main.py              应用入口、异常处理器、中间件
├── core/                横切：配置、安全、依赖注入、异常
├── db/                  数据访问基础设施：engine、session、fts
├── models/              SQLAlchemy 表映射（只声明结构）
├── schemas/             Pydantic 数据契约
├── api/                 HTTP 边界：解析→校验→调 service→组装
├── services/            业务核心：规则、事务边界、权限判定
├── plugins/             ★ 扩展插槽
│   ├── base.py            所有 Protocol 的唯一契约来源
│   ├── registry.py        唯一注册入口
│   ├── parser/  indexer/  agent/  tool/
│   ├── renderer/  exporter/  storage/
└── utils/               纯函数工具
```

**依赖方向（单向，禁止反向）**

```text
api → services → plugins(base + registry) → models → db
                              ↑
                        具体插件实现（仅被 registry 引用）
```

### 3.2 前端分层

```text
src/
├── api/                 Axios 封装 + TS 类型（HTTP 出口唯一）
├── components/          可复用组件
├── composables/         组合式函数
├── layouts/             布局
├── views/               页面级组件
├── stores/              Pinia
├── plugins/             ★ 扩展插槽
│   ├── base.ts            契约类型唯一来源
│   ├── registry.ts        唯一注册入口
│   ├── renderer/  panel/  toolbar/
├── router/
├── utils/
└── assets/
```

### 3.3 核心不变式

1. `api/` 层不写 ORM 查询，不写 `db.commit()`
2. `services/` 层不抛 `HTTPException`，不 import `Depends`
3. 核心存储逻辑**只依赖 `plugins/base.py` 的 Protocol**，不 import 具体插件
4. 插件之间不互相 import
5. 前端组件不 import `axios`，只走 `api/`
6. 核心组件不 import 具体插件，只遍历 `registry`

---

## 4. 扩展插槽设计

### 4.1 后端插槽

| 插槽 | Protocol | 用途 | 状态 |
|---|---|---|---|
| 文件解析 | `DocumentParser` | PDF/Word/Excel/OCR → Markdown | ⬜ 仅接口 |
| 向量索引 | `VectorIndexer` | 切片 → Embedding → 向量库 | ⬜ 仅接口 |
| 智能体 | `DocumentAgent` | 检索增强问答 | ⬜ 仅接口 |
| 工具 | `AgentTool` | 智能体可调用工具 | ⬜ 仅接口 |
| 渲染器 | `MarkdownRenderer` | Markdown → HTML | ⬜ 仅接口（B8 实现） |
| 导出器 | `DocumentExporter` | PDF/EPUB/DOCX | ⬜ 仅接口（B12 实现） |
| 存储后端 | `StorageBackend` | 本地/对象存储 | ⬜ 仅接口（B11 实现） |

**插件接入五步**：定义 Protocol → 实现 → 注册 → 写单测 → service 通过 registry 调用。

### 4.2 前端插槽

| 插槽 | 契约 | 用途 | 状态 |
|---|---|---|---|
| 渲染器扩展 | `RendererPlugin` | 渲染后处理 | ⬜ 仅类型 |
| 侧边面板 | `PanelPlugin` | AI 对话等侧栏 | ⬜ 仅类型 |
| 工具栏扩展 | `ToolbarExtension` | 编辑器按钮 | ⬜ 仅类型 |

### 4.3 未来演进示意

```text
当前:
   文档 CRUD ──→ Markdown 存储 ──→ Markdown 渲染 ──→ 页面

未来（不改核心存储逻辑）:
   文档 CRUD ──→ Markdown 存储 ──→ Markdown 渲染 ──→ 页面
                        │              ↑
                        │         渲染器插件
                        ↓
              解析插件 → 向量索引插件 → 智能体插件 → 面板插件（前端）
                                              ↓
                                        工具插件（外部能力）
```

---

## 5. 模块进度总表

**状态标记**：✅ 已完成　🚧 进行中　⬜ 未开始　❌ 已废弃

> 规则：每完成一个模块，**立即**回填本表 + 更新 §6 详细记录。
> 本表必须与代码实际进度一致。

### 5.1 后端模块

| # | 模块 | 路径 | 状态 | 完成日期 | 依赖 | 备注 |
|---|---|---|---|---|---|---|
| B1 | 基础设施 | `core/`, `db/` | ✅ | 2026-11-24 | - | 配置、异常、依赖注入、engine |
| B2 | 数据层 | `models/`, `migrations/` | ✅ | 2026-11-24 | B1 | 7 张表 + Alembic |
| B3 | 插件骨架 | `plugins/base.py`, `plugins/registry.py` | ✅ | 2026-11-24 | B1 | Protocol + 注册表，无实现 |
| B4 | 认证模块 | `api/auth.py`, `services/auth_service.py` | ✅ | 2026-11-24 | B1,B2 | 登录/登出/注册/改密 + Session + CSRF |
| B5 | 文档库模块 | `api/spaces.py`, `services/space_service.py` | ✅ | 2026-11-24 | B2,B4 | 空间 CRUD + 访问密码 |
| B6 | 文档树模块 | `api/tree.py`, `services/tree_service.py` | ✅ | 2026-11-24 | B5 | 树构建 + 排序分配 + 节点移动 |
| B7 | 文档模块 | `api/documents.py`, `services/document_service.py` | ⬜ | - | B6,B3 | 核心 CRUD + 乐观锁 |
| B8 | 渲染模块 | `plugins/renderer/` | ⬜ | - | B3 | Markdown → HTML |
| B9 | 历史版本模块 | `services/history_service.py` | ⬜ | - | B7 | 版本/恢复/对比 |
| B10 | 搜索模块 | `api/search.py`, `services/search_service.py` | ⬜ | - | B2,B7 | FTS5 + jieba |
| B11 | 附件模块 | `api/attachments.py`, `plugins/storage/` | ⬜ | - | B3,B7 | 上传下载 |
| B12 | 导出模块 | `plugins/exporter/` | ⬜ | - | B3,B8 | PDF |
| B13 | 后台模块 | `api/admin.py`, `services/admin_service.py` | ⬜ | - | B4,B5 | 配置/用户/日志 |
| B14 | 迁移脚本 | `scripts/migrate_from_mindoc.py` | ⬜ | - | B2 | 存量导入 |

### 5.2 前端模块

| # | 模块 | 路径 | 状态 | 完成日期 | 依赖 | 备注 |
|---|---|---|---|---|---|---|
| F1 | 工程骨架 | `vite.config.ts`, `main.ts`, `router/` | ⬜ | - | - | Vite + TS + 路由 |
| F2 | 插件骨架 | `plugins/base.ts`, `plugins/registry.ts` | ⬜ | - | F1 | 契约类型 + 注册表 |
| F3 | API 层 | `api/` | ⬜ | - | F1 | http.ts + types + 资源函数 |
| F4 | 状态层 | `stores/` | ⬜ | - | F3 | auth/spaces/document/app |
| F5 | 通用组件 | `components/` | ⬜ | - | F1 | EmptyState/DiffViewer 等 |
| F6 | 登录页 | `views/LoginView.vue` | ⬜ | - | F3,F4 | |
| F7 | 首页 | `views/HomeView.vue` | ⬜ | - | F3,F4 | 卡片网格 + 分组 |
| F8 | 文档树组件 | `components/DocTree.vue` | ⬜ | - | F4 | 递归 + 拖拽 |
| F9 | 渲染组件 | `components/MarkdownViewer.vue` | ⬜ | - | F2 | 阅读与预览共用 |
| F10 | 阅读页 | `views/ReaderView.vue` | ⬜ | - | F8,F9 | 三栏布局 |
| F11 | 编辑器组件 | `components/MarkdownEditor.vue` | ⬜ | - | F9 | CodeMirror + 工具栏 |
| F12 | 编辑页 | `views/EditorView.vue` | ⬜ | - | F8,F11 | 三栏 + 自动保存 |
| F13 | 历史抽屉 | `components/HistoryDrawer.vue` | ⬜ | - | F5,F4 | 版本列表/恢复/对比 |
| F14 | 后台页 | `views/AdminView.vue` | ⬜ | - | F3,F4 | 四 Tab |
| F15 | 设置页 | `views/ProfileView.vue` | ⬜ | - | F3,F4 | |
| F16 | 移动端适配 | 各页响应式 | ⬜ | - | F6-F15 | 侧栏抽屉化 |

### 5.3 里程碑

| 里程碑 | 包含模块 | 判定标准 | 状态 |
|---|---|---|---|
| **M1 骨架就绪** | B1, B2, B3 | `init_db` 建库成功，接口文档可访问 | ✅ B1/B2/B3 完成 |
| **M2 后端闭环** | B4–B12 | curl 完成「登录→建库→建文档→保存→搜索→附件」 | ⬜ |
| **M3 前端 MVP** | F1–F13 | 浏览器完成上述全流程，界面达到原型 | ⬜ |
| **M4 可上线** | B13, B14, F14–F16 | Docker 部署成功，存量数据迁移通过校验 | ⬜ |

---

## 6. 模块完成记录

> 每完成一个模块追加一条。格式：模块号、日期、完成内容、**与设计的偏差**、遗留待办。

（暂无记录，重构开始后按模块逐条追加。）


### B1 基础设施（2026-11-24）

**完成内容**

| 文件 | 职责 |
|---|---|
| `app/core/config.py` | `Settings`（`PER_DOC_` 前缀，`.env` 加载）、CSV 列表解析、前缀规范化、`database_url` / `sqlite_path` / `upload_path` 派生属性 |
| `app/core/exceptions.py` | `AppError` 基类 + 9 个子类，统一 `code`/`message`/`detail`/`http_status` |
| `app/core/security.py` | Argon2id 哈希、密码校验、会话签名（itsdangerous）、CSRF Token、登录失败锁定器 `LoginAttemptLimiter` |
| `app/core/legacy_password.py` | mindoc-master 存量密码兼容校验（移植自 `utils/password.go`） |
| `app/core/deps.py` | `get_db` / `read_session` / `read_csrf_token` / `verify_csrf` / `issue_csrf_token` |
| `app/core/logging.py` | 根 logger 与 uvicorn 日志格式统一 |
| `app/db/base.py` | `Base`（DeclarativeBase）+ 命名约定 `MetaData` |
| `app/db/session.py` | `build_engine`、`engine`、`SessionLocal`、`session_scope`、`create_all` |
| `app/main.py` | FastAPI 实例、CORS、4 个全局异常处理器、`/api/health` |
| `tests/` | 43 条用例，覆盖配置、异常、安全、依赖注入、engine、异常响应 |

**与设计的偏差**

1. **存量密码算法与方案描述不符**：重构方案 §5.3 描述 mindoc 使用 MD5，实际 `mindoc-master/utils/password.go` 是自定义 SHA-512/SHA-256/SHA-224 三段拉伸方案，格式为 `salt_secret$interation$hash$salt`。已按真实实现移植到 `app/core/legacy_password.py`，供 B4 首登升级 Argon2id 使用；MD5 兼容代码已删除。
2. **`app/db/fts.py` 未创建**：方案 §5.1 目录含 `db/fts.py`，但 FTS5 同步触发器依赖 `md_documents` 表结构（属 B2），按「不夹带其他模块功能」原则推迟到 B10。
3. **Python 版本**：本机可用解释器为 3.10.9（未装 3.12），代码按 3.12 语法规范编写并兼容 3.10 运行；`pyproject.toml` 仍声明 `requires-python = ">=3.12"`。
4. **`current_user` 依赖未实现**：`app/core/deps.py` 仅预留装配位置，`current_user` / `current_user_optional` 依赖 `app.models.Member`，属 B4 产物。

**遗留待办**

- B2：`models/` 7 张表 + Alembic 初始迁移，`create_all` 需替换为 `alembic upgrade head`
- B4：登录失败锁定器接入 `auth_service`，存量密码首登升级 Argon2id
- B4：`current_user` / `current_user_optional` 依赖实现
- 部署：`PER_DOC_SECRET_KEY` 必须替换为随机长字符串

### B2 数据层（2026-11-24）

**完成内容**

| 文件 | 职责 |
|---|---|
| `app/models/member.py` | `md_members` 用户表 |
| `app/models/space.py` | `md_spaces` 文档库表 |
| `app/models/document.py` | `md_documents` 文档表 |
| `app/models/history.py` | `md_document_history` 历史版本表 |
| `app/models/attachment.py` | `md_attachments` 附件表 |
| `app/models/option.py` | `md_options` 系统配置表 |
| `app/models/log.py` | `md_logs` 操作日志表 |
| `app/db/base.py` | 新增 `table_name()`，按 `settings.db_prefix` 拼表名 |
| `app/migrations/env.py` | Alembic 环境：连接串取自 settings，`render_as_batch=True` 支持 SQLite |
| `app/migrations/versions/0001_create_initial_tables.py` | 初始迁移（revision `0001`），`downgrade()` 完整可回滚 |
| `scripts/init_db.py` | 建库（`alembic upgrade head`）+ 创建管理员 + 写默认配置项 |
| `tests/test_models.py` | 30 条：表清单、约束、默认值、级联、外键、server_default |
| `tests/test_migrations.py` | 6 条：真实执行 upgrade/downgrade/重复升级/裸 SQL 插入 |

**关键决策**

1. **表名走 `table_name()` 工厂**：模型层不写死 `md_` 字面量，改 `db_prefix` 即整体切换，测试中已加断言守护。
2. **所有列带 `server_default`**：裸 SQL 插入也能落默认值，不依赖 ORM 层 Python 侧 `default=`。
3. **外键级联策略**：`md_document_history.document_id` 与 `md_attachments.document_id` 用 `ondelete="CASCADE"`；`md_documents.space_id` 不级联（避免误删整库文档），删除逻辑由 B7 service 显式控制。
4. **`md_spaces` 不设 `doc_count` 缓存字段**：按重构方案 §4.3 改为实时统计，避免缓存与实际不一致。
5. **`md_options` 用 `option_key/option_value`**：原 mindoc 的 `option_name/option_value/option_title/remark` 精简为 KV 形态。

**与设计的偏差**

1. **表名与方案 §4.3 不一致**：方案写的是 `md_books` / `md_attachment`（沿用 mindoc 原名），实际 mindoc-master 的 `TableName()` 返回 `books` / `attachment`，即真实表名是 `md_books` / `md_attachment`。per_doc 采用新名 `md_spaces` / `md_attachments`（语义重命名），存量迁移时在 B14 做字段映射。
2. **迁移目录位置**：方案 §5.1 写 `backend/migrations/`，本文档 §7 写 `backend/app/migrations/`。按 ARCHITECTURE §7（唯一事实来源）落在 `app/migrations/`，`alembic.ini` 的 `script_location` 已同步。
3. **`alembic.ini` 内容精简**：连接串不再硬编码，改由 `app/migrations/env.py` 从 `settings` 注入；同时因 Windows 默认 GBK 编码无法解析中文注释，`alembic.ini` 注释改为英文。
4. **配置与 engine 改为惰性解析**（B1 遗留项一并修复）：`settings` 改为 `_SettingsProxy` 惰性代理，`engine` / `SessionLocal` 改为惰性构建。原因是模块导入期固定配置导致测试改环境变量不生效，测试曾误写开发库。现已用 `conftest.py` 的 autouse 夹具隔离，验证测试运行后不再产生 `data/` 目录。
5. **`db/fts.py` 仍未创建**：等 B10。
6. **`md_options` 未建索引**：`option_key` 已 unique，查询走唯一索引，无需额外索引。

**遗留待办**

- B3：`plugins/base.py` + `plugins/registry.py` 骨架
- B7：文档删除时需在 service 层显式递归清理子节点与历史版本（当前依赖数据库级联仅覆盖直接子表）
- B10：FTS5 虚表与同步触发器（`db/fts.py`）
- B14：存量迁移脚本需做 `md_books` → `md_spaces`、`md_attachment` → `md_attachments` 的表名与字段映射
- 部署：生产环境应执行 `alembic upgrade head`，禁止使用 `create_all()`

### B3 插件骨架（2026-11-24）

**完成内容**

| 文件 | 职责 |
|---|---|
| `app/plugins/base.py` | 7 个 Protocol + `PluginMeta`，唯一契约来源 |
| `app/plugins/registry.py` | 7 个插槽的注册/查询函数，`registry_snapshot()` 自检视图 |
| `app/plugins/__init__.py` | `register_all()` 唯一注册入口 |
| `app/plugins/{parser,indexer,agent,tool,renderer,exporter,storage}/__init__.py` | 7 个插槽目录，声明实现约定 |
| `app/main.py` | 启动时调用 `register_all()`；新增 `GET /api/plugins` |
| `tests/test_plugins.py` | 53 条：Protocol 契约、鸭子类型、注册表读写、无空壳、无反向 import |

**Protocol 契约**

| Protocol | 必须实现的方法 |
|---|---|
| `DocumentParser` | `meta` / `supported_extensions()` / `parse()` |
| `VectorIndexer` | `meta` / `index()` / `remove()` / `search()` |
| `DocumentAgent` | `meta` / `chat()` |
| `AgentTool` | `meta` / `name()` / `parameters()` / `execute()` |
| `MarkdownRenderer` | `meta` / `render()` |
| `DocumentExporter` | `meta` / `supported_formats()` / `export()` |
| `StorageBackend` | `meta` / `save()` / `read()` / `delete()` / `exists()` |

**关键决策**

1. **严格按规则 §13.6 只留接口**：未实现的插槽不写任何空壳类，`base.py` 内除 7 个 Protocol 与 `PluginMeta` 外无具体类（测试用例 `test_no_builtin_plugin_classes` 守护）。
2. **注册表提供按能力查询的便捷函数**：`get_parser_by_extension()` / `get_exporter_by_format()` / `get_default_renderer()` / `get_default_storage()`，让 service 侧不必知道插件名约定。
3. **实例化失败不冒泡**：`_instantiate()` 捕获构造异常并记日志返回 `None`，避免坏插件导致整个应用启动失败。
4. **`PluginMeta` 用 frozen dataclass**：插件元信息不可变，防止运行时被篡改影响调度。
5. **`register_all()` 目前是空实现**：这是**唯一注册入口**，各插件实现落位后在此逐个注册，保证「新增插件时主流程零改动」。

**与设计的偏差**

1. **§4.1 插槽状态表修正**：原表把渲染器 / 导出器 / 存储后端标为「✅ 基础实现」，但代码中并不存在这些实现。已按实际进度改为「⬜ 仅接口」并标注落位模块（B8 / B12 / B11）。
2. **`PluginMeta` 增加 `capabilities` 字段**：原设计只有 name / version / description，扩展一个能力标签元组，便于后续按能力筛选插件（如「支持 OCR 的解析器」）。
3. **新增 `GET /api/plugins` 接口**：设计文档未提及，但后台管理页（B13）需要展示插件状态；该接口只读，不影响核心流程。

**遗留待办**

- B8：实现 `MarkdownRenderer`（markdown-it-py），在 `register_all()` 注册
- B11：实现 `StorageBackend`（本地文件系统），文件名随机化防路径穿越
- B12：实现 `DocumentExporter`（PDF）
- B3 后续：解析器 / 索引器 / 智能体 / 工具按需实现，每个实现单独成模块并配单测

### B4 认证模块（2026-11-24）

**完成内容**

| 文件 | 职责 |
|---|---|
| `app/core/session.py` | 会话负载构造、Cookie 签发与清除（HTTP 语义，不含业务规则） |
| `app/core/identity.py` | 账号 / 邮箱 / 密码强度格式校验（纯函数，无状态） |
| `app/core/deps.py` | 补齐 `current_user` / `current_user_optional` / `require_csrf` / `require_csrf_if_present` |
| `app/core/security.py` | 修复 `LoginAttemptLimiter` 的失败计数丢失 bug（B1 遗留） |
| `app/schemas/auth.py` | `LoginRequest` / `RegisterRequest` / `PasswordChangeRequest` / `MemberOut` / `LoginResponse` / `CsrfResponse` |
| `app/services/auth_service.py` | 认证业务核心：登录校验、锁定策略、存量密码升级、注册、改密 |
| `app/api/auth.py` | 6 个认证接口 |
| `app/api/router.py` | 业务路由统一挂载入口（新建） |
| `app/main.py` | 挂载 `api_router`；校验错误响应做 JSON 安全化 |
| `tests/test_auth_service.py` | 43 条：格式规则、登录、锁定、存量密码升级、注册、改密 |
| `tests/test_auth_api.py` | 21 条：6 个接口的契约测试 |

**接口清单**

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | `/api/auth/login` | 登录，写入会话 Cookie，返回用户与 CSRF Token | 公开 |
| POST | `/api/auth/logout` | 登出，清除会话 Cookie | 会话有效时需 CSRF |
| GET | `/api/auth/me` | 当前登录用户信息 | 登录 |
| POST | `/api/auth/register` | 注册（受 `allow_register` 控制） | CSRF |
| PUT | `/api/auth/password` | 修改当前用户密码 | 登录 + CSRF |
| GET | `/api/auth/csrf` | 下发 CSRF Token | 公开 |

**关键决策**

1. **会话负载自带 CSRF Token**：`{"member_id", "csrf_token", "login_at"}` 一并签名进 Cookie，写操作只需回传请求头中的 Token，比服务端存储更简单且天然随会话失效。
2. **CSRF Token 存会话而非独立 Cookie**：避免「双提交 Cookie」需要前端额外维护第二个 Cookie 的复杂度；前端从 `/api/auth/csrf` 取一次并缓存即可。
3. **`require_csrf` 与 `require_csrf_if_present` 分离**：登出必须幂等（会话已失效也应放行），但会话有效时仍要校验 CSRF，防止被跨站请求强制登出。
4. **账号不存在与密码错误返回同一提示**：不暴露账号是否注册，降低账号枚举风险。
5. **存量密码升级在「校验通过的那一刻」完成**：哈希不可逆，明文只在认证成功的那一次调用中可得，由 `authenticate` 透传给 `_upgrade_password_hash`，不落库、不入日志。
6. **账号格式在 Pydantic 层就拒绝**：`LoginRequest` / `RegisterRequest` 的 `field_validator` 直接拦下非法账号，避免无谓的数据库查询。
7. **`core/identity.py` 独立成文件**：账号 / 邮箱 / 密码规则被 schema 与 service 同时使用，抽出来避免正则散落（规则：公共逻辑只维护一份）。
8. **时间戳统一由数据库 `func.now()` 产生**：`last_login_time` 用 `update().values(func.now())` 而非 Python 侧 `datetime.now()`，避免与 `create_time` 的时区口径不一致。

**与设计的偏差**

1. **接口路径去掉了「找回密码」**：重构方案 §6.2 列了 `POST /api/auth/password/reset` 与 `/reset/confirm`，但 §2.2 项目边界未包含邮件找回，且规则禁止引入 SMTP 相关功能。本模块未实现，B4 状态标 ✅ 时在此显式声明为「有意不做」，后续如需支持应作为独立模块立项。
2. **注册要求 CSRF Token**：方案未明确注册接口的 CSRF 要求。本实现要求前端先调 `/api/auth/csrf` 取 Token，理由是注册会创建账号，属于写操作，不应可被跨站触发。
3. **登出接口在会话有效时也要求 CSRF**：方案未细化。此举是为了防止「跨站强制登出」，代价是前端登出前必须确保已缓存 Token。
4. **`session_max_age` 与 `remember` 的关系**：方案只说 7 天有效期，未提「记住我」。本实现中 `remember=False` 写会话 Cookie（浏览器关闭即失效），`remember=True` 写持久化 Cookie（7 天）。
5. **`/api/auth/me` 返回 `MemberOut` 而非包裹对象**：方案登录接口写的是 `{ user: {...} }`，故登录响应沿用 `LoginResponse` 包裹；`/me` 单资源直接返回对象，与「成功直接返回数据对象」的通用约定一致。

**遗留待办**

- B5：`/api/spaces` 列表需区分「登录用户全部 + 公开库」，可直接复用 `current_user_optional`
- B7：文档删除时需在 service 层显式递归清理子节点与历史版本
- B13：后台管理页需要用户列表、启用/禁用、重置密码接口，届时在 `api/admin.py` 复用 `auth_service` 的密码哈希能力
- 部署：`PER_DOC_SECRET_KEY` 必须替换为随机长字符串；`PER_DOC_SESSION_COOKIE_SECURE=true` 仅在 HTTPS 下开启
- 部署：`PER_DOC_ALLOW_REGISTER=false` 可关闭公开注册

### B5 文档库模块（2026-11-24）

**完成内容**

| 文件 | 职责 |
|---|---|
| `app/utils/identifier.py` | `identify` 生成与校验（文档库 / 文档两套正则） |
| `app/core/session.py` | 新增访问凭据 Cookie 的签发 / 清除 / 解析 |
| `app/core/security.py` | `sign_session` / `unsign_session` 支持自定义 salt |
| `app/core/config.py` | 新增 `access_cookie_name` 配置项 |
| `app/schemas/space.py` | `SpaceCreate` / `SpaceUpdate` / `SpaceOut` / `SpaceBrief` / `SpaceListOut` / `AccessCheckOut` / `AccessSubmit` |
| `app/services/space_service.py` | 文档库 CRUD、可见性判定、访问密码校验、级联清理 |
| `app/api/spaces.py` | 7 个文档库接口 |
| `app/api/router.py` | 挂载 `spaces.router` |
| `tests/test_space_service.py` | 63 条：标识规则、增删改查、可见性、访问密码 |
| `tests/test_spaces_api.py` | 28 条：7 个接口的契约与权限 |

**接口清单**

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| GET | `/api/spaces` | 文档库列表（支持 `group_name` / `keyword` 过滤） | 公开（按可见性过滤） |
| POST | `/api/spaces` | 创建文档库 | 登录 + CSRF |
| GET | `/api/spaces/{key}` | 文档库详情 | 公开（私有库需授权） |
| PUT | `/api/spaces/{key}` | 更新文档库 | 创建者 + CSRF |
| DELETE | `/api/spaces/{key}` | 删除文档库（含全部文档） | 创建者 + CSRF |
| GET | `/api/spaces/{key}/access` | 查询访问授权状态 | 公开 |
| POST | `/api/spaces/{key}/access` | 提交访问密码 | 公开 |

**关键决策**

1. **建库时自动创建根节点 + 空白文档**：移植自 `mindoc-master/models/BookModel.go` 的 `Book.Insert`，后续文档挂在根节点下，保证每个库一上来就有可编辑的入口。
2. **`identify` 未填时从名称自动推导**：`suggest_identify()` 把名称转成小写短横线形式；纯中文名无法转出 ASCII 前缀，退化为「前缀 + 随机后缀」保证唯一。
3. **访问密码用独立 Cookie + 独立 salt**：私有库的授权写在 `per_doc_access` Cookie 里，用 `per_doc.access` salt 签名，与会话令牌（`per_doc.session` salt）互不可冒用；一个 Cookie 记录已授权的多个库 id，避免每个库各发一个 Cookie。
4. **私有库切换状态时的密码策略**：公开 → 私有必须提供密码；私有 → 公开会**清除**已存的密码哈希，避免残留凭据。
5. **公开库忽略访问密码**：创建公开库时即使传了 `access_password` 也不落库，避免留下「公开库其实有密码」的困惑状态。
6. **登录态校验前置到查库之前**：`PUT` / `DELETE` 先校验登录再查文档库，否则未登录者可通过 404 / 403 的差异探测文档库是否存在。
7. **`doc_count` 实时统计**：按 B2 决策不设缓存字段，列表每次实时 `count`，保证与实际一致。
8. **删除时显式清理文档**：`md_documents.space_id` 按 B2 决策不级联，`delete_space` 显式 `DELETE` 文档；历史版本与附件在表上已配 `ondelete="CASCADE"`，随文档一并清理。

**与设计的偏差**

1. **`GET /api/spaces/{key}/tree` 未在本模块实现**：该接口属于 B6 文档树模块，按「不夹带其他模块功能」原则推迟。B5 只负责库本身的 CRUD。
2. **未实现「复制文档库」**：mindoc 的 `Book.Copy` 会递归复制文档与附件，重构方案 §6.2 的接口清单也未列出该能力，故本模块不做。
3. **未实现「导入 zip / docx 文档库」**：mindoc 有 `ImportBook` / `ImportWordBook`，但重构方案未列入接口清单，且涉及 zip / docx 解析依赖，留待后续按需立项。
4. **删除权限收紧为「仅创建者」**：重构方案 §5.4 只写「登录用户可读写全部文档库」，未区分创建者。本实现收紧为仅创建者可改删，理由是 per_doc 没有团队协作，删除是不可逆操作，应保守。若需放开为「任意登录用户可删」，改 `space_service._require_owner` 一处即可。
5. **列表接口新增 `group_name` / `keyword` 查询参数**：方案只写了「文档库列表（登录用户全部 + 公开库）」，未定义过滤参数。原型页有「分类分组」区块，故补上这两个过滤维度。
6. **`SpaceOut` 新增 `is_owner` 字段**：前端需要区分「我的库」与「他人公开库」以决定是否显示编辑入口，该字段由后端计算而非前端比对。

**遗留待办**

- B6：实现 `GET /api/spaces/{key}/tree`，复用 B5 的 `require_space` 与可见性判定
- B7：文档删除时需在 service 层显式递归清理子节点与历史版本
- B11：附件存储目录按 `space.identify` 分目录（mindoc 的 `uploads/{identify}` 约定），B11 实现 `StorageBackend` 时对齐
- B13：后台管理页的文档库列表与删除操作可复用本模块的 service
- 部署：`PER_DOC_ACCESS_COOKIE_NAME` 可自定义访问凭据 Cookie 名（默认 `per_doc_access`）

### B6 文档树模块（2026-11-24）

**完成内容**

| 文件 | 职责 |
|---|---|
| `app/services/tree_service.py` | 树构建、排序值分配、同级重排、节点移动与环校验 |
| `app/schemas/tree.py` | `TreeNodeOut` / `TreeSpaceOut` / `SpaceTreeOut` 数据契约 |
| `app/api/tree.py` | `GET /api/spaces/{key}/tree` 接口 |
| `app/api/router.py` | 挂载 `tree.router` |
| `tests/test_tree_service.py` | 25 条：树构建、排序分配、节点移动 |
| `tests/test_tree_api.py` | 7 条：接口契约与权限 |

**接口清单**

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| GET | `/api/spaces/{key}/tree` | 读取文档树（递归结构） | 公开（私有库需授权） |

**关键决策**

1. **服务端拼树，不返回扁平列表**：mindoc 的 `FindDocumentTree` 返回扁平节点列表交给 jstree 自行拼装，per_doc 直接在 `build_tree` 中按 `parent_id` 递归嵌套，前端只负责渲染与拖拽，减少前端拼树逻辑与不一致风险。
2. **一次查询拉全量节点**：先 `list_documents` 拉取该库全部节点并建立 `document_id → 节点` 索引，再统一挂载父子关系，避免 N+1 查询。
3. **脏数据降级而非丢弃**：父节点不存在的节点降级为顶层节点，保证「孤儿节点」不会连带丢失其子树之外的同级数据；`is_dir` 由是否有子节点推导，不依赖 `is_open`。
4. **排序值取同级最大值 + 1**：mindoc 的 `InsertOrUpdate` 取「同级已有节点数 + 1」，在同级 `order_sort` 被外部批量改写后可能产生重复值；本模块改为取 `max(order_sort) + 1`，保证唯一。
5. **移动时先重排旧父级再改父级**：必须先按旧父级重排（排除正在移动的节点）再修改 `parent_id`，否则同一 Session 内查询条件会因父级已变更而漏掉旧父级下的其它节点，导致排序值错乱（已在自测中捕获并修复）。
6. **环校验沿 `parent_id` 向上回溯**：禁止把节点挂到自身、自身子节点或更深后代之下，并带环检测防止脏数据导致的死循环。
7. **service 层返回内部 dataclass 而非 Pydantic schema**：service 不产出响应契约，`TreeNode` → `TreeNodeOut` 的转换在 api 层完成，保持「api 组装响应」的分层约定。

**与设计的偏差**

1. **节点移动的 HTTP 接口推迟到 B7**：重构方案 §6.2 把 `POST /api/spaces/{key}/documents/{id}/move` 列在文档路由下，属 B7 范围。本模块只交付 `GET .../tree`，但把移动与排序维护的完整逻辑（`move_document` / `reorder_siblings` / `validate_move`）实现在 `tree_service` 中并配齐单测，B7 直接调用即可，不重复实现。
2. **未实现 `is_open` 的语义改写**：mindoc 的 `is_open` 取 0 收起 / 1 展开 / 2 空目录。本模块按原值透传给前端，不在读取路径上推断展开状态——展开状态是用户偏好，应由显式写操作（B7）变更，读路径隐式改写会导致「读一次就展开」的意外行为。
3. **未实现 `DocumentTree` 的 `state` / `a_attr` 字段**：mindoc 的这两个字段服务于 jstree 的选中态与展开态，per_doc 前端用 Vue 组件自行管理选中态，无需服务端下发。
4. **`total` 字段为新增**：方案 §6.3 的响应示例没有总数，但前端分页与空状态判断需要文档总数，故在响应中补上（实时统计，与 B5 的 `doc_count` 口径一致）。

**遗留待办**

- B7：`POST /api/spaces/{key}/documents/{id}/move` 接口需调用 `tree_service.move_document`，写操作要加 CSRF 校验
- B7：新建文档时用 `tree_service.next_order_sort` 分配 `order_sort`，不要另写一套计数逻辑
- B7：文档删除时需在 service 层显式递归清理子节点与历史版本，并调用 `reorder_siblings` 消除旧父级下的排序空洞
- B7：`is_open` 的展开/收起需要独立的写接口（当前无入口）
- B8：渲染模块落地后，`Document.content` 的 HTML 内容不影响树结构，本模块无需改动

---

## 7. 目录交付物

```text
per_doc/
├── .cursor/rules/      # 全局规则（global.mdc / personal.mdc）
├── backend/
│   ├── rules/          # 后端规则
│   ├── app/            # 应用代码
│   │   ├── migrations/ # Alembic（env.py + versions/）
│   │   ├── core/      # 配置、异常、安全、会话、依赖注入
│   │   ├── db/        # Base、engine、session
│   │   ├── models/    # 7 张表映射
│   │   ├── schemas/   # Pydantic 数据契约
│   │   ├── api/       # HTTP 边界（router.py 统一挂载）
│   │   ├── services/  # 业务核心
│   │   ├── utils/     # 纯函数工具（identify 生成等）
│   │   └── plugins/   # base.py（契约）+ registry.py（注册表）+ 7 个插槽目录
│   ├── scripts/        # init_db / 迁移脚本
│   └── tests/
├── frontend/
│   ├── rules/          # 前端规则
│   └── src/
├── docs/
│   └── ARCHITECTURE.md # ★ 本文档
├── prototype/          # 界面原型（评审用）
└── RULES.md            # 规则索引
```

---

# per_doc Rules 索引

本目录统一存放项目开发过程中的所有规则文件。

## 目录结构

```
per_doc/
├── .cursor/rules/          ← 全局规则（Cursor 自动加载）
│   ├── global.mdc          全局规则：架构、扩展插槽、模块化流程、安全、Git
│   └── personal.mdc        个人偏好：代码规范、目录组织、扩展性设计、自测流程
├── frontend/rules/         ← 前端规则
│   └── frontend.mdc        Vue 3 / TS / Pinia / 插件插槽规范
├── backend/rules/          ← 后端规则
│   └── backend.mdc         FastAPI / SQLAlchemy 2.0 / 插件插槽规范
├── docs/
│   └── ARCHITECTURE.md     ← 总体框架设计 + 模块进度总表（每完成模块回填）
└── prototype/              ← HTML 原型（评审用）
```

## 优先级

```
personal.mdc  （个人偏好：怎么写代码、怎么工作）
      ↓  冲突时项目规范优先
global.mdc    （全局规则：架构、插槽、模块化流程、必须怎么做）
      ↓  冲突时更具体者优先
frontend.mdc / backend.mdc
```

## 扩展性规则的分工

同一套扩展理念按层次拆到三个文件，避免重复维护：

| 内容 | 所在文件 | 章节 |
|---|---|---|
| 抽象原则、依赖方向、YAGNI | `global.mdc` | §12 扩展性设计 |
| 插件目录约定、Protocol 签名、注册表用法 | `backend.mdc` | §13 扩展插槽规范 |
| 契约类型、注册表用法、核心组件如何消费 | `frontend.mdc` | §12 扩展插槽规范 |
| 预留插槽清单与状态 | `docs/ARCHITECTURE.md` | §4 扩展插槽设计 |
| 模块化开发流程、自测要求 | `global.mdc` | §13、§14 |
| 模块级自测方式（pytest / 浏览器实测） | `backend.mdc` / `frontend.mdc` | §11 |
| 总体设计与进度追踪 | `docs/ARCHITECTURE.md` | §5、§6 |

## 说明

| 文件 | 作用范围 | 加载方式 |
|---|---|---|
| `global.mdc` | 前后端全部代码 | `alwaysApply: true`，自动生效 |
| `personal.mdc` | 前后端全部代码 | `alwaysApply: true`，自动生效 |
| `frontend.mdc` | `frontend/src/**` 及前端配置 | 按 `globs` 匹配自动生效 |
| `backend.mdc` | `backend/**/*.py` 等 | 按 `globs` 匹配自动生效 |

`frontend/rules/` 与 `backend/rules/` 放在项目内而非 `.cursor/rules/` 下，是为了**让规则文件随代码一起版本管理**，团队成员 clone 后即可获得同样的约束，不依赖本地 Cursor 配置。

如果希望 Cursor 也自动读取这两个目录，可在 `.cursor/settings.json` 中添加：

```json
{
  "rules": [
    "per_doc/frontend/rules/**/*.mdc",
    "per_doc/backend/rules/**/*.mdc"
  ]
}
```

## 新增规则时

1. 归类到正确的目录（全局 / 前端 / 后端）
2. 更新本文件的目录结构说明
3. 保持 `.mdc` frontmatter 格式：`description` + `globs` + `alwaysApply`

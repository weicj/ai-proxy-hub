# AI Proxy Hub 项目结构

这个仓库按职责分成下面几类：

- `ai_proxy_hub/`
  后端主包，按职责拆成 `constants`、`utils`、`protocols`、`local_keys`、`path_utils`、`app_paths`、`file_io`、`config_logic`、`config`、`network`、`client_switch`、`store`、`http_server`、`service_controller`、`service_controller_helpers`、`cli_app`、`entrypoints` 等模块。
- `router_server.py`
  兼容入口层，保留旧导入路径，内部转发到 `ai_proxy_hub`。
- `ai_proxy_hub/__main__.py`
  当前推荐的模块入口，支持通过 `python3 -m ai_proxy_hub` 启动。
- `web/`
  前端界面资源。`web/index.html` 只保留结构骨架，`web/app-theme.css` / `web/app.css` / `web/app-effects.css` 分担主题变量、主布局和效果样式；
  交互脚本按层拆到 `web/app-*.js`：
  `app-02-foundation.js` 负责常量、i18n、图标、HTTP 基础；
  `app-02-model.js` 负责配置归一化、路由状态和选择器；
  `app-02-core.js` 负责保存与脏状态；
  `app-03-*` / `app-04-*` / `app-05-*` 负责 UI、运行状态、上游管理、用量和启动绑定，其中上游管理已拆成 `app-03-upstream-render.js`、`app-03-upstream-editor.js` 和兼容入口 `app-03-upstreams.js`。
- `tests/`
  自动化测试，覆盖路由、故障切换、路径解析和配置行为。
- `scripts/`
  构建和发布脚本，例如 GitHub Release、Homebrew、winget、`.deb` 产物生成、发布产物校验、发布快照同步、远程 Linux 冒烟验证。
- `examples/`
  示例配置，只放脱敏样例，不放真实密钥，也可放外部测试环境变量模板。
- `docs/`
  项目说明、结构说明、FAQ、发布流程说明、外部测试环境说明，以及后续可扩展的架构文档。
- `.github/workflows/`
  CI / Release 工作流。

本地运行时文件建议不要放进仓库根目录：

- 真正使用中的配置文件应放在系统用户目录下的应用配置目录。
- 临时调试产物放在 `tmp/`，不参与发布。
- `__pycache__/`、`dist/` 这类生成文件不纳入版本管理。
- `build/`、`*.egg-info/` 这类打包生成物可随时重建，不应作为源码的一部分长期保留。

当前仓库整理后的目标是：

- 根目录只保留入口兼容层和项目元数据。
- 后端逻辑优先放进 `ai_proxy_hub/`，避免继续把功能堆回单文件。
- 纯常量、纯工具函数、路径选择、本地 key、配置归一化和客户端切换逻辑优先落到小模块，减少 `legacy_impl.py` 的噪音。
- `legacy_impl.py` 仅保留尚未完全迁移的兼容承载逻辑，新的实现优先落在独立模块。
- 示例配置与真实配置分离。
- 前端、测试、脚本、文档各自独立，便于后续发布到 GitHub 和包管理器。

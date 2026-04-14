# 贡献指南

感谢你考虑为 AI Proxy Hub 做出贡献！

## 如何贡献

### 报告 Bug

如果你发现了 bug，请创建一个 Issue 并包含：

1. **清晰的标题**：简要描述问题
2. **复现步骤**：详细的步骤说明
3. **期望行为**：你期望发生什么
4. **实际行为**：实际发生了什么
5. **环境信息**：
   - 操作系统和版本
   - Python 版本
   - AI Proxy Hub 版本
6. **日志/截图**：如果可能，提供相关日志或截图

### 提出新功能

如果你有新功能的想法：

1. 先检查 Issues 中是否已有类似建议
2. 创建一个 Feature Request Issue
3. 清楚地描述：
   - 功能的用途和价值
   - 预期的使用场景
   - 可能的实现方式

### 提交代码

#### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/weicj/ai-proxy-hub.git
cd ai-proxy-hub

# 安装依赖
python3 -m pip install -e .

# 运行测试
python3 -m unittest discover -s tests -v
```

#### 代码规范

- **Python 风格**：遵循 PEP 8
- **命名规范**：
  - 函数和变量：`snake_case`
  - 类名：`PascalCase`
  - 常量：`UPPER_CASE`
- **注释**：
  - 复杂逻辑需要注释说明
  - 公共函数需要 docstring
- **类型提示**：尽可能使用类型注解

#### 提交流程

1. **Fork 仓库**
2. **创建分支**：
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```
3. **编写代码**：
   - 保持提交粒度合理
   - 编写清晰的提交信息
4. **运行测试**：
   ```bash
   python3 -m unittest discover -s tests -v
   ```
5. **提交更改**：
   ```bash
   git add .
   git commit -m "feat: add new feature"
   # 或
   git commit -m "fix: resolve issue #123"
   ```
6. **推送分支**：
   ```bash
   git push origin feature/your-feature-name
   ```
7. **创建 Pull Request**

#### 提交信息规范

使用语义化的提交信息：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `style:` 代码格式（不影响功能）
- `refactor:` 重构
- `perf:` 性能优化
- `test:` 测试相关
- `chore:` 构建/工具相关

示例：
```
feat: add HTTP connection pool for better performance

- Implement connection pooling mechanism
- Add connection lifecycle management
- Reduce handshake overhead
```

### Pull Request 指南

好的 PR 应该：

1. **单一职责**：一个 PR 只做一件事
2. **清晰描述**：
   - 解决了什么问题
   - 如何解决的
   - 相关的 Issue 编号
3. **测试覆盖**：如果可能，添加测试
4. **文档更新**：如果改变了 API 或功能，更新文档
5. **代码质量**：
   - 通过所有测试
   - 没有明显的代码异味
   - 遵循项目的代码规范

### 代码审查

所有提交都需要经过代码审查：

- 保持开放和友好的态度
- 及时响应审查意见
- 如果不同意某个建议，礼貌地说明理由

## 开发指南

### 项目结构

```
ai-proxy-hub/
├── ai_proxy_hub/          # 后端主包（constants/utils/protocols/local_keys/path_utils/app_paths/file_io/config_logic/store/http_server/service_controller/cli_app 等）
├── start.py               # 推荐脚本入口
├── ai_proxy_hub/__main__.py # 推荐模块入口（python -m ai_proxy_hub）
├── router_server.py       # 兼容入口
├── cli_modern.py          # CLI 界面
├── web/                   # Web 控制台（index.html + app-*.js）
└── tests/                 # 测试文件
```

### 关键模块

- **ConfigStore**: 配置管理和持久化
- **RouterRequestHandler**: HTTP 请求处理和路由
- **InteractiveConsoleApp**: CLI 控制台
- **ModernCLI**: 现代化 CLI 界面
- **ServiceController**: 服务生命周期管理

### 添加新功能

1. **纯配置/工具逻辑**：优先放进 `ai_proxy_hub/constants.py`、`utils.py`、`protocols.py`、`local_keys.py`、`path_utils.py`
2. **路由逻辑**：在 `RouterRequestHandler` 或相关独立模块中添加
3. **CLI 命令**：在 `InteractiveConsoleApp` 中添加菜单项
4. **Web 界面**：在 `web/index.html` 与 `web/app-*.js` 中添加 UI 和 API 调用
5. **配置项**：在 `ConfigStore` 和对应的规范化逻辑中添加验证和默认值

### 测试

- 为新功能编写单元测试
- 确保现有测试通过
- 测试跨平台兼容性（如果可能）

## 社区准则

- 尊重所有贡献者
- 保持建设性的讨论
- 欢迎新手提问
- 帮助他人成长

## 许可证

提交代码即表示你同意将代码以项目的许可证发布。

## 问题？

如果有任何问题，欢迎：
- 创建 Issue 讨论
- 在 PR 中提问
- 查看现有的文档和代码

感谢你的贡献！🎉

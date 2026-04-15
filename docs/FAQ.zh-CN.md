# AI Proxy Hub 常见问题

[![Docs](https://img.shields.io/badge/Docs-FAQ-2563eb)](../README.zh-CN.md)
[![Homebrew](https://img.shields.io/badge/Homebrew-available-16a34a)](https://github.com/weicj/homebrew-aiproxyhub)
![winget](https://img.shields.io/badge/winget-planned-6b7280)
![APT](https://img.shields.io/badge/APT-planned-6b7280)

## AI Proxy Hub 是什么？

AI Proxy Hub 是一个面向 AI 客户端和上游 API 的本地控制层。它提供统一入口、多种路由策略、订阅感知的可用性处理、本地 API Key 管理，以及 Web 和 CLI 两种控制界面。

## 它主要面向哪些客户端和协议？

当前项目重点围绕以下客户端生态展开：

- Codex
- Claude Code
- Gemini CLI

当前支持的协议工作区包括：

- OpenAI-compatible
- Claude / Anthropic
- Gemini

## 这个项目只能本地用吗？

主要设计目标是本地或私有网络环境。需要时可以开启局域网访问，但它并不定位为公网多租户高安全网关。

## 它需要 root 或管理员权限吗？

正常运行不需要。项目的目标运行方式是普通用户权限，并使用当前用户可写的配置目录。

但安装阶段如果平台本来就要求提权，可以直接用 `sudo`，例如：

- `sudo apt install ./ai-proxy-hub_<version>_all.deb`
- `sudo dpkg -i ai-proxy-hub_<version>_all.deb`

所以这里要区分两件事：安装可以提权，日常运行不应依赖它。

## 一个本地 API Key 能否只允许某一种协议使用？

可以。本地 Key 可以按协议范围进行限制。

## 当前支持哪些路由模式？

当前支持：

- 手动控制
- 顺序优先
- 轮询负载
- 网络质量优先

## 什么叫订阅感知的上游控制？

每个上游可以带一个或多个订阅记录，用来表示：

- 无限使用
- 周期性重置
- 定额消耗

这样路由器就能区分普通可用、临时耗尽、订阅过期，以及后续恢复窗口。

## 不同协议可以分别设置路由吗？

可以。项目按协议工作区组织，因此路由行为、本地入口设置和上游顺序都可以按协议分别配置。

## 它既支持 Web 管理，也支持终端管理吗？

是的。Web 控制台和交互式 CLI 都是第一等控制界面。

## 这个项目能打包分发吗？

可以。仓库已经包含以下工具链：

- 可移植的 `.tar.gz` 和 `.zip` 产物
- 可选 `.deb` 生成
- 面向 Homebrew 和 winget 流程的元数据生成
- 基于 `.deb` 生成本地 APT 仓库暂存目录
- 在 GPG 可用时支持 APT 仓库签名流程

## 它现在已经完全适合包管理器公开发布了吗？

还没有完全收尾。Homebrew 已经可用，并且是当前推荐的 macOS 安装方式，但更完整的公开包管理器发布链路仍在持续整理中。

## 项目采用什么许可证？

Apache License 2.0。

# 执行环境

2026-09-14 修订：目标平台为 Unix 系统（macOS/Linux）。开发、构建与验证在 Unix 主机执行；容器执行使用 Linux 容器运行时（Docker Engine）。文件名保留 `linux-environment.md` 以维持既有引用，内容以本页为准。

历史记录（2026-09-13 前）中的 WSL Ubuntu 证据仍属于其原环境与版本范围，不自动迁移为当前平台通过结论；新宿主必须重新生成路径与物理身份 manifest，不复制旧机器的 inode/device 标识。

不要把任何单一宿主的专有路径或语义（WSL 的 `/mnt/c`、开发者机器用户目录等）引入产品依赖；平台相关行为在产品代码中按 `sys.platform` 显式分支，并记录各分支的验证范围。

依赖版本见 [依赖说明](../docs/dependencies.md)，装配配置与重建步骤见 [开发说明](../docs/development.md)。开发者绝对路径、device/inode、Docker 执行身份和依赖 manifest 必须在新宿主重新观测和生成；旧证据中的值不是可移植配置。

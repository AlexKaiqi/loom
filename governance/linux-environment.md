# Linux 执行环境

产品、构建与验证面向 Linux。WSL 开发使用发行版的原生 Linux 文件系统；不要把 NTFS 的 `/mnt/c` 路径当作文件语义与性能验证环境。

依赖版本见 [依赖说明](../docs/dependencies.md)，装配配置与重建步骤见 [开发说明](../docs/development.md)。开发者绝对路径、device/inode、Docker 执行身份和依赖 manifest 必须在新宿主重新观测和生成；旧证据中的值不是可移植配置。

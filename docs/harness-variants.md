# Harness 变体（git 分支 + worktree）

底座（`main`）与 Harness 解耦：Runtime 只解释当前绑定的那棵 `lore_harness/` 树。一种组合就是一条分支；同时跑多种组合靠 **worktree**，不是插件装卸。

## 分支名 = 依赖栈

斜线表示「在上一层上再叠一层」，与 rebase 父分支同一条路径。Git 不允许一条分支名是另一条的前缀（不能同时存在 `h/kernel` 与 `h/kernel/pin`），所以**每个栈节点都以 `/root` 收尾**：

```
main
h/kernel/root
h/kernel/pin/root
h/kernel/archive/root
h/kernel/pin/archive/root
```

`h/kernel/pin/archive/root` 的父是 `h/kernel/pin/root`。需要「无 pin 的 archive」走 `h/kernel/archive/root`，不要在运行时把两枝拼起来。`--harness` 可以写完整分支名，也可以写去掉 `/root` 的栈路径（如 `kernel/pin`）。

## worktree

主工作副本停在 `main`。每个要同时访问的组合一个 worktree（路径可读）：

```sh
git worktree add ../loom-h-kernel h/kernel/root
git worktree add ../loom-h-kernel-pin h/kernel/pin/root
git worktree add ../loom-h-kernel-archive h/kernel/archive/root
git worktree add ../loom-h-kernel-pin-archive h/kernel/pin/archive/root
```

登记时把 `--harness` 指到该 worktree 的 `lore_harness/`，或把 `loom harnesses` 已列出的分支名交给 `--harness`。同一 Host 上两个 Work 可以各绑一棵树。

## 底座更新

`main` 前进后按栈 rebase，从短到长：

```sh
git rebase main h/kernel/root
git rebase h/kernel/root h/kernel/pin/root
git rebase h/kernel/root h/kernel/archive/root
git rebase h/kernel/pin/root h/kernel/pin/archive/root
```

Rebase 后是新 digest。新 Work 用新绑定；已登记 Work 仍是登记时的字节。复现一次对比钉 **commit SHA**，不钉分支名。

## 本树是什么

当前 checkout 的 `lore_harness/` **就是** kernel：objective → shell → `work.completed` 声明。pin / archive 在对应分支上改这同一棵树，不在 `main` 上并排目录。

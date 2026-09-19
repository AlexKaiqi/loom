# Harness 变体（git 分支 + worktree）

底座（`main`）与 Harness 解耦：Runtime 只解释当前绑定的那棵 `lore_harness/` 树。一种组合就是一条分支；同时跑多种组合靠 **worktree**，不是插件装卸。

## 分支名 = 依赖栈

斜线表示「在上一层上再叠一层」，与 rebase 父分支同一条路径：

```
main
h/kernel
h/kernel/pin
h/kernel/archive
h/kernel/pin/archive
```

`h/kernel/pin/archive` 的父是 `h/kernel/pin`。需要「无 pin 的 archive」走 `h/kernel/archive`，不要在运行时把两枝拼起来。

## worktree

主工作副本停在 `main`。每个要同时访问的组合一个 worktree（路径可读）：

```sh
git worktree add ../loom-h-kernel h/kernel
git worktree add ../loom-h-kernel-pin h/kernel/pin
git worktree add ../loom-h-kernel-archive h/kernel/archive
git worktree add ../loom-h-kernel-pin-archive h/kernel/pin/archive
```

登记时把 `--harness` 指到该 worktree 的 `lore_harness/`，或把分支名交给 `loom harnesses` 已列出的路径。同一 Host 上两个 Work 可以各绑一棵树。

## 底座更新

`main` 前进后按栈 rebase，从短到长：

```sh
git rebase main h/kernel
git rebase h/kernel h/kernel/pin
git rebase h/kernel h/kernel/archive
git rebase h/kernel/pin h/kernel/pin/archive
```

Rebase 后是新 digest。新 Work 用新绑定；已登记 Work 仍是登记时的字节。复现一次对比钉 **commit SHA**，不钉分支名。

## 本树是什么

当前 checkout 的 `lore_harness/` **就是** kernel：objective → shell → `work.completed` 声明。pin / archive 在对应分支上改这同一棵树，不在 `main` 上并排目录。

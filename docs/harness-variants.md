# Harness 变体（git 分支 + worktree）

底座（`main`）与 Harness 解耦：Runtime 只解释当前绑定的那棵 `lore_harness/` 树。一种组合就是一条分支；同时跑多种组合靠 **worktree**，不是插件装卸。

## 分支名 = 依赖栈

斜线表示「在上一层上再叠一层」。Git 不允许一条分支名是另一条的前缀，所以**每个栈节点都以 `/root` 收尾**。

从最简 kernel 出发。Archive 是必须层：只缩小 **Projection**（少列文件），不改 Surface 上的文件。Plan 叠在 archive 上。Goal 的 objective/acceptance 已是 Surface 上的 Fact，投影每轮读出来即可，没有单独的 pin 枝。

```
main
h/kernel/root
h/kernel/archive/root
h/kernel/archive/plan/root
```

## worktree

```sh
git worktree add ../loom-h-kernel h/kernel/root
git worktree add ../loom-h-kernel-archive h/kernel/archive/root
git worktree add ../loom-h-kernel-archive-plan h/kernel/archive/plan/root
```

`--harness` 可以是该 worktree 的 `lore_harness/`，或 `loom harnesses` 列出的分支名。

## 底座更新

```sh
git rebase main h/kernel/root
git rebase h/kernel/root h/kernel/archive/root
git rebase h/kernel/archive/root h/kernel/archive/plan/root
```

身份是拷进 Work 时的 tree digest，不是分支名。

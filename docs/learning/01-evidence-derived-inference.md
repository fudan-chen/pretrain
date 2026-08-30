# 01 · OBSERVED、DERIVED、INFERRED：别把三种句子混成一种

## 本章问题

“Paloma 低于预测，所以 Hero 训练很好”这句话包含了几层不同性质的判断？

答案是至少三层：一个观测值、一次派生计算和一个解释性推断。它们需要不同的证据要求。

## OBSERVED：直接观测

示例：

> step 32,999 的 `eval_dropless/paloma/macro_loss` 原始值为 2.2781243324279785（页面显示 2.27812）。

一条合格的 OBSERVED claim 至少需要：

- 原始 metric key；
- run ID 和 step；
- 观测时间；
- 本地 evidence artifact；
- artifact checksum；
- 采样方式。

“图上看起来大概 2.28”不够。“官方说目前很好”也不是这个 metric 的直接观测。

## DERIVED：确定性计算

示例：

> step 32,999 的 canonical residual 为 `2.2781243324279785 − 2.3465101574845844 = -0.06838582505660584`。

DERIVED claim 除了 evidence，还必须记录：

- `method_id`；
- 公式或算法；
- 输入值；
- 参数与固定假设；
- 代码或测试位置；
- 不确定性状态。

同一实测值可以因为 baseline 定义不同而得到方向相反的 residual。因此“计算器算对了”远远不够，问题定义也必须可见。

## INFERRED：解释性判断

示例：

> 当前点估计没有显示 Hero 弱于 matched-progress 参考，但不能声称显著领先。

INFERRED claim 必须额外包含：

- 置信度；
- 替代解释；
- 什么证据会推翻它；
- 适用的 recipe regime；
- 明确限制。

当前 claim 被标记为 `support=insufficient_evidence`、`confidence=low`，因为只有四个 rung，当前范围是敏感性 envelope 而非统计置信区间。

## 来源冲突怎么办

本项目采用以下优先级：

```text
实际 run config / 原始 metric
  > 固定 commit 的源码
  > issue / comment 叙述
  > 本仓库或其他二手总结
```

这不是说 issue 没价值。Issue 很适合说明意图、事件和团队判断，但当 issue 写“cosine”而实际 run config 是 `lr_schedule=linear` 时，页面应显示实际配置，并把冲突作为冲突记录，而不是悄悄挑一个更好讲故事的版本。

## Claim 最小结构

```json
{
  "id": "hero.paloma.matched-progress.step-32999",
  "kind": "DERIVED",
  "support": "supported",
  "statement": "实测比 matched-progress 点预测低 0.06839",
  "as_of": "...",
  "evidence": ["eval artifact", "baseline artifact"],
  "derivation": {
    "method_id": "marin-matched-progress-v1"
  },
  "uncertainty": {
    "kind": "sensitivity_only",
    "significance": "not_assessed"
  }
}
```

## 为什么页面不能直接写结论

旧版页面把“已过 25%”“TPU v5p”“cosine decay”等文字硬编码进 HTML。数据更新不会自动修正文案，于是页面的数值是新的、解释却是旧的。

v2 的规则是：

```text
HTML 只能渲染 current_status.json 和 claim_ledger.json
```

如果没有合法 claim，页面宁可显示“证据不足”，也不补写一个顺畅故事。

## 自测

请给以下句子标记类型：

1. “W&B meta 的 device variant 是 GB200。”
2. “176 replicas × 4 devices = 704 configured device slots。”
3. “704 configured slots 说明 11 个 NVL72 rack 中每一张卡都被充分利用。”

答案：1 是 OBSERVED；2 是 DERIVED；3 是 INFERRED，而且当前证据不足。配置容量不能改写成实时活跃率。

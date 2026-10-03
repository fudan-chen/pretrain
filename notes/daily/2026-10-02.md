# Marin 每日追踪 · 2026-10-02

- UTC 窗口：`2026-10-02T00:00:00Z` 至 `2026-10-03T00:00:00Z`（结束时间不含）
- 可变来源防漏观察至：`2026-10-03T08:11:50Z`（可能与次日重叠）
- 实际采集时间：`2026-10-03T08:11:50Z`
- 总体状态：`success`

## 来源状态

| 来源 | 状态 | 证据条目 | HTTP 尝试 |
| --- | --- | ---: | ---: |
| [GitHub Issues 与评论](https://github.com/marin-community/marin/issues) | success | 591 | 36 |
| [GitHub commits](https://github.com/marin-community/marin/commits/main) | success | 22 | 1 |
| [Hugging Face 模型与数据集](https://huggingface.co/marin-community) | success | 1 | 2 |
| [Marin 官网](https://marin.community/) | success | 1 | 1 |

## GitHub 工程记录

共 19 个更新 issue、158 条评论证据。
另有 13 个跨午夜补充观察、401 条评论上下文（不计入目标日数量）。
- [#9612 Rollout Engine: one engine for TaskSpec rollouts](https://github.com/marin-community/marin/issues/9612) · open · 40 条评论
- [#7104 iris - login status dump](https://github.com/marin-community/marin/issues/7104) · open · 5 条评论
- [#7101 infra - try rolling out context management strategies](https://github.com/marin-community/marin/issues/7101) · open · 2 条评论
- [#7088 levanter: add DenseMixer-style dense-forward router gradient for MoE SFT/midtraining](https://github.com/marin-community/marin/issues/7088) · open · 1 条评论
- [#6898 [datakit] pin/checksum the download modules for reproducible normalize inputs](https://github.com/marin-community/marin/issues/6898) · closed · 2 条评论
- [#6897 [datakit] give the decontam bloom eval corpus a version tag so it stops re-keying per region](https://github.com/marin-community/marin/issues/6897) · closed · 2 条评论
- [#6896 [levanter/datakit] thread tokenizer revision through load_tokenizer for a true byte-pin](https://github.com/marin-community/marin/issues/6896) · closed · 2 条评论
- [#6889 Determine MFU impact of MLA at target model size d5260](https://github.com/marin-community/marin/issues/6889) · closed · 3 条评论
- [#6848 [grug] Track source-push inbox MGPU MoE research](https://github.com/marin-community/marin/issues/6848) · closed · 4 条评论
- [#6522 Agent MoE Experiment: Multi-head Latent Attention with simplified attention block](https://github.com/marin-community/marin/issues/6522) · closed · 14 条评论
- [#9576 [ci] Unrelated dependency changes select the full Levanter TPU suite](https://github.com/marin-community/marin/issues/9576) · closed · 5 条评论
- [#9514 Marin Belay Intake](https://github.com/marin-community/marin/issues/9514) · open · 7 条评论
- [#8506 Hero Run / Ongoing Status](https://github.com/marin-community/marin/issues/8506) · open · 57 条评论
- [#9630 Add Skill2Env to RL Data Atlas](https://github.com/marin-community/marin/issues/9630) · open · 1 条评论
- [#9691 [experiment] Dr. Doom: reduce Grug SFT doom loops with online FTPO](https://github.com/marin-community/marin/issues/9691) · closed · 2 条评论
- [#9036 [inference] Large vLLM checkpoints exceed engine-ready timeout](https://github.com/marin-community/marin/issues/9036) · closed · 0 条评论
- [#9176 [skyrl] Add PivotRL pivot-state training support](https://github.com/marin-community/marin/issues/9176) · open · 7 条评论
- [#9462 [levanter] Unblock Snowball training on AMD GPUs](https://github.com/marin-community/marin/issues/9462) · open · 2 条评论
- [#9704 [marina] Host an MFU tracker with commit attribution per hardware lane](https://github.com/marin-community/marin/issues/9704) · closed · 2 条评论
- [#9636 [grug] Benchmark OLMo-core kernels for incremental MoE speedups](https://github.com/marin-community/marin/issues/9636) · open · 2 条评论 · 跨午夜补充
- 其余 12 个 issue 见原始证据文件。

## 代码变化

共 22 个 commit。
- [`ab0da00`](https://github.com/marin-community/marin/commit/ab0da00df254ca0d52648df9169ca284cb5789af) [zephyr] Pickle shuffled items with the stdlib pickler (#9699)
- [`06583c6`](https://github.com/marin-community/marin/commit/06583c6027ee03676f5ce5ff33eeff5f4cc1a7b2) [iris] Preserve retry resources during Kubernetes cleanup (#9705)
- [`44bc366`](https://github.com/marin-community/marin/commit/44bc366a131466eaaadf2968ed1d62aac55a2376) [levanter] Expose the pure-JAX flash attention to Grug as xla_flash (#9692)
- [`f0a9d85`](https://github.com/marin-community/marin/commit/f0a9d853c5ef6a71d35f6b22931fd983662e4c6c) [CatCountCanary] Offer dry and gate presets with optional export (#9643)
- [`50a59cb`](https://github.com/marin-community/marin/commit/50a59cb3eded805369e4011579f63e84047260e8) [dependencies] Advance external runtimes (#9702)
- [`305d2fc`](https://github.com/marin-community/marin/commit/305d2fc3c927883223b96c8da4c0a7f20979d725) Scope hero training alerts to the production Iris user (#9700)
- [`6ece0f4`](https://github.com/marin-community/marin/commit/6ece0f4722f34a21f33d3db4acb22a59a027a196) Port verifyit grading logic and tests into Marin
- [`deb6a33`](https://github.com/marin-community/marin/commit/deb6a33ce2823c8e1adb03523f7b0a5b4eea2da9) Rename the verifier package to verifyit (#9698)
- [`3fd01d4`](https://github.com/marin-community/marin/commit/3fd01d43a2921923ca6e3633743a0fd97f38af00) [deps] Match the pipeline FA4 stack to Levanter's GPU pins (#9353)
- [`3545416`](https://github.com/marin-community/marin/commit/3545416247ac4b03303282c6802b74071d82b660) [datakit] Cut Python work in the decontamination mark pass (#9690)
- [`6c02d75`](https://github.com/marin-community/marin/commit/6c02d75098dfd946ec30af603d65557ea8d02e4f) [inference] Extend vLLM engine startup deadline
- [`7f1e217`](https://github.com/marin-community/marin/commit/7f1e2171e7a0d2e63f3093bb33c85d2e2617f18c) Preserve eval filter identity and vLLM chat templates (#9407)
- [`8b4abd3`](https://github.com/marin-community/marin/commit/8b4abd3c15eb8bc1b909d16935170e417812c94a) [fray] Add MI355X peak FLOPs (#9688)
- [`5e41ad3`](https://github.com/marin-community/marin/commit/5e41ad3e6446f313bc05ec797d67b859cc820ed9) [iris] Read process CPU ticks after the process name (#9686)
- [`e8e6ba7`](https://github.com/marin-community/marin/commit/e8e6ba7727e35cdea19c4d811114f66016947b78) [levanter] Record the launch commit and dirty state in W&B (#9637)
- [`3ee6cc3`](https://github.com/marin-community/marin/commit/3ee6cc3e05c4fa2526fa4c3bae53cb4055e4c25c) [dependencies] Advance external runtimes (#9677)
- [`89ac0d7`](https://github.com/marin-community/marin/commit/89ac0d770506f7e27ca217760ec5ca3246694e7e) [dependencies] Advance external runtimes (#9649)
- [`d5ddcfb`](https://github.com/marin-community/marin/commit/d5ddcfbc1d922b3fb679ac1156aef3604844f582) [ci] Select Levanter TPU tests by dependency impact (#9580)
- [`f5693b8`](https://github.com/marin-community/marin/commit/f5693b8671c340ac48207a603470e44b5dbb952d) Bump the uv group across 2 directories with 2 updates (#9634)
- [`ca3c675`](https://github.com/marin-community/marin/commit/ca3c6751066054f15f43eb5df2442b669034312b) [evaldash] Show grades for MRCR samples (#9509)
- 其余 2 个 commit 见原始证据文件。

## Hugging Face 产物

更新模型 0 个，更新数据集 1 个。
- [marin-community/verifier-unification-evidence](https://huggingface.co/datasets/marin-community/verifier-unification-evidence) · dataset · `2026-10-02T22:31:50.000Z`

## 官网快照

- [MarinTarget Paloma eval loss, preregistered at 18T tokens](https://marin.community/) · SHA-256 `89ff61a36cc23bbfd15bbb61bdb7f674071c06a9991bd98a5e563e0b208a9232` · 10727 bytes

---
本页由确定性脚本生成；完整正文、评论、元数据和错误见同日 `data/snapshots`。

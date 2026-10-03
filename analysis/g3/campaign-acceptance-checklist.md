# 对 01 新 campaign runner 的共同验收清单

总体状态：WAITING。candidate_runner_commit=unknown。仅已知旧 runner 4fcfadfb02e2c50e0dffde7b12ec6f2336fd1bd8；不能把它当成尚未收到的 campaign 实现。本轮 GPU 授权=0；下列排程是提案，不是可执行派单或额度授予。

## 平衡派单提案

随机和 AI 各六次搜索；每次使用完整固定 split、三轮训练（epochs=3）、相同固定模型/评分/预处理。这里“三轮”指每个 trial 的三个 epoch，不是三次可以追加的搜索。建议预锁三 seed 为 42/43/44，需主控在首次派单前确认并写入清单，确认后不得按结果调整。

| 搜索槽位 | Random worker | AI worker | 两策略相同训练 seed |
| --- | --- | --- | --- |
| 1 | 5090-01 | 5090-02 | 42 |
| 2 | 5090-02 | 5090-01 | 42 |
| 3 | 5090-01 | 5090-02 | 43 |
| 4 | 5090-02 | 5090-01 | 43 |
| 5 | 5090-01 | 5090-02 | 44 |
| 6 | 5090-02 | 5090-01 | 44 |

每个策略在每台设备正好三次，每台设备各见三个相同 seed；同一策略下一槽等待上一槽结果，避免 AI 获取未来结果。两策略的同序号槽位配对安排，记录排队/其他负载；禁止任意把慢任务换机或失败后追加第七次。此布局减少策略与设备完全绑定，但不能消除所有时间/硬件差异，设备应作为分析分层变量。不要把六次试验称为六条独立 campaign。

三个 baseline seeds 为单独的一组探索性基线，不属于 random/AI 各六次；其配置、三 epoch、参考设备、预算和执行许可必须另行冻结，不能直接复用 G2 一 epoch 结果填数。可将 baseline 固定在一个预先指定的参考设备以便解释 seed 波动，但这不证明跨设备等价；2sigma 仅作探索提示。

搜索空间须同一份 hash 锁定清单；可变项建议仅 learning_rate、weight_decay、augmentation、batch_size，取值域由主控统一确定且是合同允许范围的子集。seed、epochs=3、timeout、model、dataset、split、评估函数及工作机分配由控制面冻结，不让策略自由扩大预算。Random 的采样分布、采样 RNG seed、重复配置处理须预先公布；AI 只接收同一任务边界和允许的历史 validation 结果。两策略不能通过拒绝配置、免费重试或不同采样范围获得隐藏预算。具体搜索空间/随机采样实现目前 WAITING。

## 准入与验收矩阵

以下均须针对收到的新完整 commit 重新验收，不能继承旧实现的 PASS。

| ID | 要求与所需证据 | 状态 |
| --- | --- | --- |
| C01 | 主控交付完整 campaign commit/合同祖先及审阅 diff；独立 clean worktree；版本与实际部署一致 | WAITING |
| C02 | 合同 pins/完整 freeze、相同数据 hash 和 golden split；GPU/驱动/确定性设置记录 | WAITING |
| C03 | 新额度是独立获批的 campaign 授权；保留旧耗尽 .g1-quota，不删除/重置、不用换目录绕过；总账覆盖两机所有预留 | WAITING |
| C04 | Random/AI 各六槽、epochs=3、相同空间/hash 与上表种子/设备分配；失败/超时/重试也占槽，不额外补足六个成功 | WAITING |
| C05 | 公平记账：候选数、训练样本轮数、GPU 时间、墙钟、推理/编排成本分别记录；确认/基线预算单列、规则对称 | WAITING |
| C06 | 只允许白名单变更；拒绝未知键、代码/路径/评分函数输入；固定字段改动/越界/NaN/seed/hash/commit 冲突均拒绝 | WAITING |
| C07 | Agent 实际身份无写评分代码/runner/结果/测试标签权限；可信评分工件只读且 hash 固定；代码检查不能被同 UID 修改绕过；用受限 CPU 检查验证拒绝，不修改旧环境策略 | WAITING |
| C08 | 同 ID 同请求幂等、冲突拒绝、恢复不重计/漏计；失联/歧义状态需人工审阅；只有本任务进程被回收 | WAITING |
| C09 | 成功/失败/timeout 明确，失败指标 null；request/result/commit/seed/hash/split 全部匹配，非法准入也有可关联审计记录 | WAITING |
| C10 | 真实 Omnigent 角色链与工具执行日志；Result 绑定 Decision 的实际指标，结果影响后续决定并落实下一次请求；mock/静态脚本不计真实链 | WAITING |
| C11 | baseline 三 seed 的样本 s/2s 只作为探索；六次搜索/单轨迹不宣称充分统计证据；如实报告无优势 | WAITING |
| C12 | 候选模型工件保存/封存；最终名单及确认规则先锁定；只执行一次最终测试阶段，每个预选模型一次；test 不反馈调参 | WAITING |
| C13 | CPU/离线用例与真实 GPU 验收独立标注；GPU 只在下一轮显式授权后运行，预算/timeout 由批准协议决定 | WAITING |

需要主控与 01 一起明确：campaign 新合同是否扩展旧 300 秒上限、非法提交是否占搜索槽、模型确认预算和 checkpoint 格式、最终评估权限/账本以及完整 Omnigent 接口。都不能由 02 擅自改公共 schema 或实现第二 runner。本轮不申请额外 GPU，也不重测已知 bwrap/认证失败。

# 精确旧 runner 的评估边界审查

审查对象固定为 4fcfadfb02e2c50e0dffde7b12ec6f2336fd1bd8；文中位置为该 commit 的源文件行号。当前 G3 只读检查，不运行 runner。新 campaign runner 尚未收到；对它的结论一律 WAITING。

| 边界 | 已实现 / 实证 | 缺口与结论 |
| --- | --- | --- |
| train / validation 分离 | schemas/split.py:11-22 固定 PCG64 seed 后拆分、排序并核 hash；G2 原始索引重新检查 45000/5000、不交叉、覆盖全部50000，hash匹配 | validation 是调参评分集，不是最终 test；长期自适应使用有选优偏差 |
| official test 分离 | runner/data.py:33-38 仅 extractfile/pickle.load 五个 data_batch；engine.py:86-88 使用该数据及固定 split。G2 data.json 报 official_test_read=false，与静态实现吻合 | 归档校验读全归档字节；无 test 样本评分代码，也无最终测试阶段；同一归档含 test，不能从布尔字段推断 Agent 被 OS 隔离禁止读取 test |
| Agent 白名单 | schemas/contracts.py:15-28 strict/extra=forbid，固定 model/dataset/split，lr/decay/augmentation/epochs/batch/seed/timeout 有范围；cli.py:39-43 在分配前验证；无任意可执行路径/评分函数配置入口 | 是 API 输入限制，不是部署权限。Agent 的真实工具/身份/写权限未知；当前合同仍允许 epochs 1..3、seed/timeout/batch 变化，不能声称已锁成 campaign 的3 epoch与固定派单 |
| 评分函数固定 | engine.py:115 和133-157 固定 CrossEntropyLoss、全量 validation accuracy/loss；model.py:7-25 固定结构和预处理；engine.py:36-42 检查 clean HEAD 和approved | 操作者对当前 engine.py 可写（只读 os.access 观察，未尝试修改）；无只读挂载、独立评分权限或哈希签名执行机制证据。代码载入与快照检查不消除并发替换风险；不能宣称运行时 Agent 无法改评分 |
| 结果/身份保留 | contracts.py:37-54 RFC8785 hash和seed一致；161-169 match_result；cli.py:26-35 从request复制身份，126-133非成功指标清空并追加结果；storage.py:30-46拒绝覆盖同名记录；G2两份成功原始记录全部匹配 | 正常路径追加保留不等于抗同UID篡改。G2没有真实失败样本；历史CPU/mock验证不能替代GPU故障实证 |
| 失败与中断 | cli.py:109-133记录timeout/失败/取消；contracts.py:109-131规定error与null指标；cli.py:79-88无结果/歧义状态要求人工审查 | 准入前失败在cli.py:168-175仅stderr+exit1，不一定有持久request/Result；不可捕获父进程崩溃可留下无终态attempt，需要下一版审计/恢复规则 |
| 额度与可重复提交 | storage.py:64-90固定两槽；cli.py:60-94请求不可替换、复用或追加attempt；G2两槽原样留存 | 旧两槽已耗尽，不支持12次campaign；不得靠删除账本或换目录解锁。新额度机制需主控新授权与01实现，本轮不改 |
| 真实科学闭环 | contracts.py:141-159定义Decision字段和ID约束 | agents/与orchestrator/在该commit只有.gitkeep；没有已执行的Omnigent角色链。Decision模型不将其metrics自动绑定到具体Result数值，实际消费/选择/派单与因果记录仍缺 |

以上源码位置与字节 hash 已保存，所见评分代码可写只说明当前操作者权限；不能据此断定未部署 Agent 的具体权限。建议的可信只读执行、独立最终评分身份、跨机 campaign 总账均未在本轮实现。

G2 已验证 seed42 accuracy 0.5646、seed43 0.5686，均完整一轮训练；不构成 AI-vs-random 比较，不证明显著优势或完整科学闭环。对旧 runner 数据/结果路径的静态与离线结论为已审查；运行时 Agent 防篡改、最终测试、真实角色链及新 campaign 均为未验证/WAITING。

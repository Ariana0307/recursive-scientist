# 精确 G3 campaign runner 独立验收 — G4

目标/实际验收commit均为931049af15ddafa12a5163e924a3ea84bbfbbf3f；origin/dev/campaign-5090-01与之相同。独立干净执行worktree，未修改runner/schema/评分。G4只做静态和CPU/mock验收，未初始化GPU、未创建真实campaign授权。

结论：在“无shell/文件工具的科研模型 + 可信操作者”边界下，固定三种子baseline授权/持久化/评分绑定的受测路径通过。不是对同UID任意程序的OS防篡改认证，也不是十二任务搜索runner的授权或GPU复验。

| 项目 | 实际位置（目标commit） | 验收范围与结果 |
| --- | --- | --- |
| 授权绑定 | runner/campaign.py:84-118 | 授权绑定clean commit、method SHA256与policy；镜像一致和HMAC校验；篡改签名/commit/method拒绝：CPU PASS |
| 父进程检查 | campaign_cli.py:19-45；campaign.py:154-180 | 先校验环境/请求/授权，锁定额度并在spawn前持久预留，再次校验并传封闭memfd能力：静态与失败/取消mock PASS |
| 子进程检查 | campaign.py:194-220；campaign_cli.py:86-92 | 检查FD seal、签名、持久slot、父PID、方法、完整request；primary一次性claim后才进训练；父不匹配、请求变更和重放拒绝：CPU PASS。实际训练函数用stub代替 |
| 额度持久化 | campaign.py:121-140、154-180 | 主/镜像连续slot、锁、三次上限、孤儿fail-closed、失败/取消/spawn失败仍占槽；并发末槽与新进程重启测试：CPU PASS；旧账本未动 |
| 固定config与seed | campaign.py:143-151、166-177；runner/g3-method.json | config除seed外必须等于固定baseline；只能42/43/44且按序；epochs=3、timeout300，模型不能传路径/command/quota/campaign；CPU PASS。不能接收45..47搜索任务 |
| 评分hash和等价性 | campaign.py:43-48；runner/evaluate.py:6-21 | SHA256精确匹配68d34bb53116e8d1debc77b65b08320c52836a5b31414a7a32239b33b5d79bc7；临时改动评分副本被拒；旧评分AST与CPU数值等价：PASS |
| 结果与统计 | campaign_cli.py:61-75；campaign_summary.py:records/summary | request/Result、code/seed与reservation匹配；三成功才计算mean及ddof1 sigma，缺失/失败为null；best严格改善追加；合成测试PASS，不当作真实G3复验 |

CPU运行总计82 passed（75项仓库测试+7项独立检查），2.16秒；进程内CUDA初始化守卫记录0次尝试、cuda_initialized=false。测试隔离至全新临时目录，合成授权使用假commit；该夹具不构成实际训练许可，不把临时key/授权文件打包。真实campaigns和campaign-authority路径前后都不存在，旧runs/两槽文件逐hash核对不变。

没有收到01原始G3 run/预测/授权证据。主控报告seeds42/43/44为.6712/.6636/.6564，mean=.6637333333333333，sigma=.007400900846068241，2sigma=.014801801692136482；这些数值来自主控提供，未独立重算。已审查统计方法，不等于已验证其原始测量输入。

限制与等待：同UID shell可读key/改代码和记录，不在所称边界内；HMAC+chmod+clean Git不是OS不可篡改。操作者工具权限隔离和真实Omnigent链未端到端验证。当前实现只支持三种子baseline，不是六轮random/AI搜索；随机列表/搜索空间/新授权仍WAITING。没有保存权重，无最终测试执行器/一次性test账本；不重训、不评分。准入前拒绝或不可捕获崩溃可能仅留下错误/不完整记录，应保留并人工审查，不自动退款/补跑。

正式标准位于docs/success_criteria.md，最终协议在docs/final_test_protocol.md，冻结排程提案在docs/search_schedule.md。科研Agent不得修改这些规则；版本变动只能由主控审阅，不能根据已见结果修改本轮标准。

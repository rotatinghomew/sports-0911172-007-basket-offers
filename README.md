# 赛事周边商品关联发现与可兑现组合优惠工作台

这是体育商业团队使用的本地业务工具，现有能力包括人工业务登记、状态核对、事务执行和变更追溯，并在净购物篮之上提供关联发现、统计检验与组合优惠小范围试用。经营数据采用本地合成记录，不含真实个人资料，也不需要外部账户。现有业务操作见 `docs/业务约定.md`。关联结论只描述历史共现，不自动产生经营决策或“搭售增收”的因果判断。

## 环境与运行

使用 Python 3.11，业务运行只使用标准库和内置 SQLite（Fisher 精确检验与 BH 校正均为标准库实现，无统计依赖）。测试与打包另需安装精确锁定的构建工具；Docker 镜像与冻结任务环境均在准备阶段安装它们，正式业务回放不访问网络。全部演示离线执行，写入用户指定的本地数据库；不指定数据库时只在内存中运行，不产生文件。

```bash
python3 -m pip install -r requirements-build.txt
```

```bash
python3 -m product demo
python3 -m product demo --db /tmp/basket-offers.sqlite3
python3 -m product inspect --db /tmp/basket-offers.sqlite3
python3 -m product discover --db /tmp/basket-offers.sqlite3 --id d1
```

`discover` 先回放 `--file`/默认历史，再写入一条 `discovery` 记录：按日期切分发现与持出样本，输出每个候选商品对的支持度、置信度、提升度、Fisher 检验与 FDR，以及 `association` / `promotion_induced` / `undetermined` 三分类和客群、赛程阶段分层指标。拆单按 purchase 合并、赠品与退货从净篮子剔除、促销来源分流，试用核销不会回流为自然证据。

业务数据的完整顺序保存在 `data/demo.json`。也可将同格式的操作序列交给现有操作台执行，每项为业务操作名称与参数对象，不会隐式替换已有数据。

```bash
python3 -m product replay --file data/demo.json
```

## 组合试用

选中 `association` 规则后，用 `trials.create` 绑定发现编号与规则编号，传入毛利、折扣与名额；预检不通过（规则非关联结论、毛利不足、库存缺件、优惠互斥等）会拒绝或在 `trials.attempt` 写入带原因码的 `unfulfilled`，不替换商品、不沿用旧证据。`trials.report` 回到本次试用汇总净收入、退货、换货与未兑现，并附发现截止日前的自然流描述性基线。

## 测试与编译

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q product tests
python3 -m build --wheel --no-isolation
sh scripts/verify.sh
```

测试覆盖业务链、非法操作回滚、重复编号、变更历史与磁盘重启。演示与测试的数据互相隔离，重复执行使用新的内存实例；持久库内的重复业务编号会被拒绝，不要在同一个库中重复导入演示。

## 容器

```bash
docker build -t basket-offers .
docker run --rm --network none basket-offers
```

容器仅运行本项目，不依赖旁路服务。常规测试和演示合计通常在数秒内完成；本地核验脚本 `scripts/verify.sh` 将演示输出放在临时目录并清理，运行预算为九十秒。后续新增功能也应保持小规模业务样本可快速复验，不要求预设统计方向。

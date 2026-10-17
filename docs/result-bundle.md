# 比较结果包 v1

`scripts/compare_joints.py --bundle PATH` 生成普通 UTF-8 JSON/CSV 目录。它保存两种接头计算成功且 S–N 曲线完整覆盖时的结果，不改变原有的刚度分配、雨流计数或损伤模型。示例数据均为合成数据。

`manifest.json` 是最后写入的完整性清单，不列入自己的文件哈希。顶层字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 整数 `1` |
| `kind` | `"joint-comparison"` |
| `status` | `"complete"` |
| `mean_stress_model` | `"none"` |
| `bin_width_mpa` | 原比较使用的有限正分箱宽度 |
| `source_input_sha256` | 原始 profile、loads、sn，以及可选 input_config 的字节哈希 |
| `files` | 包内数据文件清单 |

每项文件包含 `path`、`role`、`sha256`。`sha256` 为文件原始字节的 64 位小写十六进制 SHA-256。`path` 使用 `/` 分隔的规范相对路径，不能有绝对路径、盘符、反斜线、空段、`.` 或 `..`；链接解析后仍须在包内。一个文件路径和一个 `(role, case)` 只能出现一次。方案文件带有 `case: "stiff_joint"` 或 `"soft_joint"`；公共文件省略 case。文件单位用 `units` 对象标明。

| role | 文件 | case |
| --- | --- | --- |
| `loads` | `loads.csv` | 省略 |
| `load_summary` | `load-summary.json` | 省略 |
| `sn_curve` | `sn.json` | 省略 |
| `comparison` | `comparison.json` | 省略 |
| `profile` | `<case>.json` | 对应方案 |
| `stress` | `<case>-stress.csv` | 对应方案 |
| `cycles` | `<case>-cycles.csv` | 对应方案 |
| `history` | `<case>-history.json` | 对应方案 |
| `fatigue` | `<case>-fatigue.json` | 对应方案 |

loads 单位为 `{"time_s":"s","force_n":"N"}`，stress 为 `{"time_s":"s","stress_mpa":"MPa"}`。cycles 为 `{"range_mpa":"MPa","mean_mpa":"MPa","count":"cycles","start_index":"sample_index","end_index":"sample_index"}`；S–N 为 `{"amplitude_mpa":"MPa","cycles_to_failure":"cycles"}`。其余 JSON 的字段含义沿用两个 CLI 的文档。

循环 CSV 使用 `range_mpa,mean_mpa,count,start_index,end_index`，保留半循环、均值和原标准应力数组的零基索引。未重新分箱或按直方图近似；恒值应力的 CSV 只有表头。`from-cycles` 能复用这些记录，但不能由循环恢复原采样总数。

包内的标准载荷和应力已完成单位换算与标定，重新读取使用默认参数。`load-summary.json` 的 source_format 仅说明转换来源，canonical_format 说明标准 CSV；不可把 source_format 再次应用到已转换文件。

原始采集字节、原始采集预设和基础接头文件不另存副本；保存的是原始身份哈希、实际转换参数、两种接头实际参数，以及本次捕获的曲线字节。原采集数据不能从标准文件无损恢复。`comparison.json` 的 input_sha256 对应源字节，manifest 中每个文件的 sha256 对应导出字节，两者不可互换。

消费程序应先检查版本、状态、单位和路径，再核对所需文件的哈希；本项目配套的 fatigue 重分析辅助命令会核对所有列出的文件。文件清单和报告是数据，不是可执行命令。重分析结果应写到包外，保留原结果。

文件先在临时兄弟目录算完，独占创建最终目录后转移，manifest 最后发布。已有目标永不覆盖。进程中断时可能出现缺清单的部分目录；清单存在仍需要核对哈希。此格式不提供对恶意修改整包的签名认证，也不证明传感器、曲线或模型适用性。

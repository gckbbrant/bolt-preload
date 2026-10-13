# 螺栓预紧连接分析工具

`bolt-preload` 是一个 MoonBit 库和本地命令行工具。输入连接刚度、已知预紧力和轴向外载，计算螺栓拉力、剩余夹紧力、分离载荷和名义应力。它也能将外载记录转换为应力 CSV，供独立的疲劳工具使用。

## 运行

需要 MoonBit 工具链；native 后端需要本机 C 编译环境。本项目实际验证于 moon `0.1.20260920 (914d7da)`、moonc `v0.10.14+7d59c7ec9`，运行依赖锁定为 `moonbitlang/async@0.22.4`。计算核心同时支持 native 和 JS，文件 CLI 使用 native。

在项目目录运行：

```sh
moon run --target native cmd/main -- analyze samples/joint.json --force 5000 --json _build/static.json --svg _build/joint.svg
moon run --target native cmd/main -- history samples/joint.json samples/loads.csv --stress _build/stress.csv --json _build/history.json
```

单工况示例得到 **11000 N 螺栓力、6000 N 夹紧力、220 MPa 应力**。分离外载为 12500 N。[保存的结果](samples/static.json)由同一 CLI 生成。

![螺栓力与剩余夹紧力](samples/joint.svg)

## 输入与计算

连接配置 JSON 的四个字段均为有限正数：

| 字段 | 含义 | 单位 |
|---|---|---|
| `bolt_stiffness_n_per_mm` | 螺栓轴向刚度 kb | N/mm |
| `joint_stiffness_n_per_mm` | 被连接件轴向刚度 kj | N/mm |
| `preload_n` | 已知安装预紧力 Fi | N |
| `stress_area_mm2` | 螺栓有效拉应力面积 As | mm² |

外载 F 是非负轴向拉力。采用分离前的线弹性模型：

```text
C = kb / (kb + kj)
Fb = Fi + C * F
Fc = Fi - kj / (kb + kj) * F
Fsep = Fi / (kj / (kb + kj))
stress = Fb / As
```

`Fb - Fc = F`，应力单位 N/mm² 即 MPa。刚度由使用者依据实际几何与材料提供。模型与公式依据参见 [NASA Fastener Design Manual](https://ntrs.nasa.gov/citations/19900009424)；该实现限定轴向线弹性载荷分配，未实现完整紧固件标准校核、剪切、弯曲、多螺栓分配、塑性、松弛或温度效应。

载荷 CSV 为未加引号的两列：

```csv
time_s,force_n
0,0
1,5000
2,0
```

时间必须有限且严格递增，力有限且非负。接受 UTF-8 BOM、CRLF 和空行。导出的应力 CSV 使用 `time_s,stress_mpa`。

达到或超过 Fsep 时，单工况返回 `SeparationReached`；历史结果保留此前有效样本及首个分离位置，不再恢复后续分析，不导出完整应力文件。历史 JSON 的 `sample_index` 从 0 开始；未分离时可选 `separation` 字段省略。

CLI 返回码：0 表示所请求计算完成，1 表示历史发生分离，2 表示输入、单工况模型或文件操作错误。输出路径不能覆盖输入或彼此重合；路径检查后会清除已存在的指定输出，避免失败后残留旧应力文件。

## 调用计算核心

在调用方 `moon.pkg` 中导入 `"gckbbrant/bolt-preload" @joint`。公开接口与类型见 [pkg.generated.mbti](pkg.generated.mbti)。

- `analyze_joint(profile, force)` 返回单工况结果或结构化错误。
- `analyze_load_history(profile, loads)` 返回有效应力前缀与可选分离事件。
- `parse_load_csv`、`stress_csv` 负责明确单位的文件交换。
- `render_svg` 生成载荷分配图。

完整的独立调用示例位于 [examples/basic/main.mbt](examples/basic/main.mbt)：

```sh
moon run --target native examples/basic
moon run --target js examples/basic
```

发布前在本地消费模块，可将调用方与本项目列入同一个 `moon.work`，调用方 `moon.mod` 引入 `gckbbrant/bolt-preload@0.1.0`；工作区将其解析为本地源码。[MoonBit 本地依赖说明](https://docs.moonbitlang.com/en/latest/toolchain/moon/module.html#local-dependencies)

## 与 fatigue-spectrum 配套

两个项目各自能独立使用，通过 CSV 组合。假定 `fatigue-spectrum` 位于同级目录，在本项目运行：

```sh
python scripts/compare_joints.py --fatigue ../fatigue-spectrum
```

该脚本使用 `samples/loads.csv` 的合成载荷，分别运行两个 CLI，结果保存在 [samples/comparison.json](samples/comparison.json)。Python 脚本无需额外依赖。

| 示例方案 | 刚度比 C | 最低夹紧力 | 最大名义应力 | 未修正均值的模型损伤 |
|---|---:|---:|---:|---:|
| kj = 800000 N/mm | 0.2 | 3600 N | 232 MPa | 7.5024×10⁻⁶ |
| kj = 300000 N/mm | 0.4 | 5200 N | 264 MPa | 1.200384×10⁻⁴ |

这里连接件变软使夹紧力卸载变慢，也使螺栓增载更大。比较同时保留循环均值。演示曲线采用 `N = 10¹⁰ / amplitude⁴`，不是材料试验数据；结果用于展示计算关系，不代表设备疲劳寿命。

## 测试

```sh
moon check --target native
moon test --target native
moon test --target js
python tests/test_cli.py
```

核心测试覆盖手算、力平衡、分离临界点、完整输入校验、公开记录的导出限制及 CSV。CLI 测试覆盖分离阻断、旧结果清除、输入路径保护与文件单位。Python 仅用于测试和配套示例。

许可证：[Apache-2.0](LICENSE)。

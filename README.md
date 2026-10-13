# 螺栓预紧连接分析工具

用 MoonBit 计算轴向拉力下的螺栓载荷、剩余夹紧力、分离条件和名义应力。
核心接口为 `analyze_joint` 与 `analyze_load_history`。长度采用 mm，力采用 N，应力采用 MPa。

模型限定为单螺栓、轴向、分离前线弹性连接。达到分离条件后不外推应力，载荷历史保留有效前缀与分离位置。

运行核心测试：`moon test --target native`。

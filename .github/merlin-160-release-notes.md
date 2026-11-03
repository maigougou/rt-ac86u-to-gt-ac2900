> **这个固件从未在真机上运行过。** 它可能无法启动、Wi-Fi 不可用、跑不到 160 MHz，也可能让路由器变砖。只适合会用 CFE 救援模式恢复的人测试，不要刷到你依赖的主路由上，风险自负。
>
> Never run on real hardware. It may fail to boot or brick the router. Use at your own risk.

这不是 Asuswrt-Merlin 或华硕的官方固件。遇到问题请到[本仓库](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/issues/new?template=hardware-report.md)反馈，不要找 Merlin 或华硕。

## 改了什么

只适用于 RT-AC86U，型号不变。相对 Asuswrt-Merlin 386.14_2 只改两处：

1. 用同一份源码里 GT-AC2900 的 `dhd.o` 覆盖 RT-AC86U 的，带入 160 MHz 法规表。
2. 给 RT-AC86U 加上 `BW160M=y`。

## 使用

1. 核对下面的 SHA-256，再运行 `python3 tools/fwtool.py verify 固件文件 --expect RT-AC86U`。
2. 按[教程](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/blob/main/docs/build-merlin-160.md#刷入和验证)备份、刷入和验证。
3. 把结果提交为[硬件测试报告](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/issues/new?template=hardware-report.md)。

已知风险：你所在的地区可能仍然没有 160 MHz 信道；Wi-Fi 法规数据比原版旧；未验证 AiMesh，测试时请不要开启。详情见[已知风险](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/blob/main/docs/build-merlin-160.md#已知风险)。

## 许可和源码

固件含 GPL 等开源组件，以及华硕和博通的闭源组件，不适用本仓库代码的 MIT 许可证。编译使用的源码：

- Asuswrt-Merlin 386.14_2：[带 160 MHz 改动的分支](https://github.com/maigougou/asuswrt-merlin.ng/tree/386.14_2-160mhz)（基于[未修改的标签](https://github.com/maigougou/asuswrt-merlin.ng/tree/386.14_2)，[上游](https://github.com/RMerl/asuswrt-merlin.ng/tree/386.14_2)）
- [工具链提交 d1af80e](https://github.com/RMerl/am-toolchains/tree/d1af80e6b6686a4edc680386c09a8361453dd5c1)
- 本仓库的 `tools/merlin160.py` 和 `tools/build-merlin-160.sh`（提交见下方）

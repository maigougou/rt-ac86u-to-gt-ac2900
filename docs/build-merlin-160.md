# 编译保持 RT-AC86U 型号的 160 MHz 固件

这份教程编译的是 Asuswrt-Merlin 386.14_2，型号仍是 RT-AC86U，不需要刷成 GT-AC2900。本仓库不提供编译好的固件。

> **先读这段：** 这条路线**没有在真机上验证过**。编译成功只说明能生成镜像，不代表 160 MHz 能正常工作。刷机可能让路由器变砖，风险自负。

## 原理

| 文件 | RT-AC86U | GT-AC2900 |
|---|---|---|
| `dhd.o` 代码段 | 相同 | 相同 |
| 内嵌 Wi-Fi 固件版本 | 10.10.122.20 | 10.10.122.20 |
| CLM 法规数据版本 | 9.12.4 | 9.11.6 |
| CLM 里的 160 MHz 信道、子信道和速率表 | **没有** | 有 |

Merlin 源码里已经带有两个型号的 `dhd.o`，所以补丁只改两处：

1. 用 GT 的 `dhd.o` 覆盖 RT 的，带入 160 MHz 表。
2. 给 RT-AC86U 加上 `BW160M=y`，否则系统不会请求 160 MHz。

## 编译

需要 x86_64 的 Ubuntu 20.04（Windows 上可用 WSL2），以及至少 50 GB 磁盘空间。

**用 Docker（和 CI 相同的流程）：** 在本项目目录运行。脚本会完成全部步骤，并把日志和检查报告写到 `out/`：

```bash
mkdir -p out
```

```bash
docker run --rm -v "$PWD:/project:ro" -v "$PWD/out:/out" ubuntu:20.04 bash /project/tools/build-merlin-160.sh /project /out
```

这种方式下固件留在容器里，脚本结束后会被删除。要留下固件，请用下面的手动方式。

**手动：** 先按 [Merlin 编译 Wiki](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Compile-Firmware-from-source) 安装依赖、设置工具链，然后获取源码：

```bash
cd ~ && git clone --depth 1 --branch 386.14_2 https://github.com/RMerl/asuswrt-merlin.ng
```

打补丁。工具会核对 `dhd.o` 的哈希，不是 386.14_2 的源码会被拒绝。把路径换成本项目的位置：

```bash
python3 /path/to/this/project/tools/merlin160.py patch ~/asuswrt-merlin.ng
```

编译：

```bash
cd ~/asuswrt-merlin.ng/release/src-rt-5.02hnd && make rt-ac86u
```

固件在 `release/src-rt-5.02hnd/image/`，选以 `_ubi.w` 结尾的文件。不要用文件名带 `cferom` 或 `pureubi` 的镜像。

## 刷机前检查

校验镜像：

```bash
python3 tools/fwtool.py verify 你的固件_ubi.w --expect RT-AC86U
```

确认驱动带有 160 MHz 表：

```bash
find ~/asuswrt-merlin.ng/release/src-rt-5.02hnd -name dhd.ko -exec python3 tools/merlin160.py check-dhd {} \;
```

输出里应有 `CLM data has 160 MHz tables`。

## 刷入和验证

先按 [Linux](usage-linux.md) 或 [Windows](usage-windows.md) 教程的第 4 阶段备份。型号没变，所以在 **系统管理 → 固件升级** 正常上传即可，不需要 `arm`。

刷完后，先确认当前地区有没有 160 MHz 信道：

```bash
ssh "$RT_HOST" wl -i eth6 chanspecs -b 5 -w 160
```

如果有输出，到无线设置勾选启用 160 MHz，选 36 信道和 160 MHz，再确认实际状态：

```bash
ssh "$RT_HOST" 'wl -i eth6 chanspec; nvram get wl1_bw_cap'
```

应显示 `36/160` 这类信道和 `15`。

## 已知风险

- **地区可能没有 160 MHz：** GT 的 CLM 含 CN/0、63、64、65、68、69、230，但每个版本是否开放 160 MHz 还没有解析。如果上面的第一条命令没有输出，说明这个补丁在你的地区不够。请不要为此改成不符合当地法规的地区。
- **法规数据回退：** GT 的 CLM 比 RT 的旧。RT 现有的地区版本里，只有 Q2/178 在 GT 里缺失。
- **AiMesh：** `BW160M` 会改变 `cfg_param.h`，而 `cfg_server` 和 `libcfgmnt.so` 是不会重新编译的预编译文件。先用单台路由器测试，不要开 AiMesh。
- **DFS：** 36 信道的 160 MHz 覆盖 52–64 这些 DFS 信道，检测到雷达时可能切换信道或降低频宽。
- **其他版本：** 补丁只适用于 386.14_2。

## 恢复

补丁不改 CFE 和分区表。如果刷坏了，理论上可以用 CFE 救援网页刷回官方 RT 固件，步骤见 [README](../README.md) 的“变砖救援”。这一点同样没有实测。

欢迎提交[硬件测试报告](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/issues/new?template=hardware-report.md)。

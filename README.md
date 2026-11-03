# RT-AC86U 转 GT-AC2900 工具包

把华硕 RT-AC86U 刷成 GT-AC2900 固件，并保留回退路径。这里有一套固件分析结论、跨平台的校验和备份工具，以及详细教程。

> [!WARNING]
> **本项目还没有在真机上验证过，作者手上也没有 RT-AC86U。** 结论来自对官方固件和开源代码的静态分析，加上少量论坛报告。Asuswrt-Merlin 的开发者 RMerlin 明确不建议这样做，理由是硬件不同。刷机可能让路由器变砖，也可能影响保修，风险自负。

**开始使用：** [Windows 教程](docs/usage-windows.md) · [Linux 教程](docs/usage-linux.md)（含 macOS 差异）

## 值不值得刷

这只是固件层面的转换。两机 SoC 和无线芯片相同，主要硬件差异是 GT 多了 Aura RGB 控制器和 Turbo 按键。

- **能得到：** 160 MHz、LACP/链路聚合、GeForce NOW、Alexa/IFTTT/Google Assistant，以及 GT 版界面。
- **得不到：** Aura RGB 和 Turbo 键，这两样靠硬件。
- **代价：**
  - 部分 LED 可能失控。
  - GT 官方固件 51582（2025-03）比 RT 官方固件 52334（2026-05）旧，少 14 个月的安全修复，所以最终建议换成 Merlin GT 版。
  - 这台机器能否稳定跑 160 MHz 还没有实测。

## 验证状态

| 项目 | 状态 |
|---|---|
| 镜像解析和校验（`fwtool.py`） | 已在官方 GT 51582 和 RT 52334 镜像上通过 |
| 流程工具（`ac86u2gt.py`） | 已在 macOS 上用模拟路由器测试；Linux 和 Windows 由 CI 覆盖，首次运行结果待确认 |
| 路由器端脚本（`router-check.sh`） | 用 POSIX shell 测试过，依赖的命令已对照两个固件确认存在；没有在真实 BusyBox 上运行 |
| 备份真实闪存 | **未验证**，遇到 NAND 坏块时的表现未知 |
| CFE 救援网页刷入 GT 固件 | **未验证**，静态分析显示应放行 |
| Firmware Restoration 工具刷入 | 有 2019 年的论坛成功报告，**新版固件未验证** |
| `skip_crc` 跨型号刷入 | **未验证**，只确认了校验会放行 |
| Merlin GT 镜像 | **未分析**，下载源对分析环境返回 403 |
| 刷机后的 Wi-Fi、LED 和稳定性 | **未验证** |
| 保持 RT 型号的 160 MHz 固件 | CI 已编译成功，镜像通过 12/12 项校验，rootfs 里的 `dhd.ko` 带 160 MHz 表，已发布[测试版](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/releases/tag/merlin-160-386.14_2-test1)；**未上机** |

### 需要真机测试

如果你有 RT-AC86U，最有价值的是下面这些报告，可以按风险从低到高逐级做，随时可以停：

1. 只跑 `pre` 和 `backup`，完全只读。
2. 用 CFE 救援网页刷入，再用同样的方法刷回 RT 固件。
3. 长期使用，报告 160 MHz、LED 和稳定性。

请用 [硬件测试报告模板](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/issues/new?template=hardware-report.md) 提交，并隐去 MAC 和序列号。

## 分析结论

"已确认"指在官方 GT 51582 和 RT 52334 镜像或 Merlin `386_x` 分支源码上直接检查过。

| 事实 | 依据 |
|---|---|
| SoC（BCM4906）、内存、闪存、无线（BCM4366E + BCM4365E）和 FCC ID 相同 | 第三方硬件库 |
| `94908.dtb` 字节完全相同 | 已确认 |
| `cferom` 完全相同 | 已确认（源码树中的副本） |
| `cferam` 只差 1 个指针和编译时间戳，指针只用于组合固件（comfw）选型 | 已确认 |
| 两个内核都内置 `94906REF` 和 `GT-AC2900` 两个 Board ID | 已确认 |
| RT 的 Board ID 是 `94906REF`，存在 CFE NVRAM 里，**本项目不改它** | 源码 |
| 镜像末尾是 64 字节 vtoken 加 20 字节 WFI 标签，CRC 为 CRC32 取反 | 已确认 |
| 两个固件的 dropbear 都支持 ed25519，新版 OpenSSH 可以直接连接 | 已确认 |

### 三道校验

| 路径 | 校验内容 | 对跨型号镜像 |
|---|---|---|
| 固件 Web 升级 | `check_imagefile`：CRC 和 `productid` | RT 拒绝 GT，GT 也拒绝 RT |
| 同上，且 `nvram set skip_crc=1` | 跳过 CRC **和**型号检查，用一次后自动清零 | 放行（两个固件都有此分支，跨型号未实测） |
| CFE 救援网页 | 芯片 ID、标签版本、标签 CRC、镜像 CRC；CFE 中没有 `productid` 字样 | 应放行（静态分析） |

**有一处矛盾：** 论坛里有人说救援路径和 Web UI 一样会查型号。这和上面的静态分析不符，也和"用恢复工具刷入成功"的报告不符。所以教程安排了备用路线。

## 刷完后的预期行为

以下来自源码推断，尚未实测。

| 项目 | 预期 | 原因 |
|---|---|---|
| Aura RGB | 没有 | 板上没有 I2C 控制器（地址 0x4E），代码检测不到会直接返回 |
| `aura_rgb_nt` 守护进程 | 每 6 秒轮询一次 | 设 `aurargb_enable=0` 可暂停 |
| 复位 / WPS / Wi-Fi / LED 按键 | 正常 | 两机 GPIO 相同（23 / 22 / 15 / 14） |
| Turbo 键 | **有误触风险** | GT 把 GPIO20 当按键读，而它在 RT 上是 WAN 指示灯 |
| 电源 / WAN / USB 指示灯 | 可能常亮、常灭或不跟随状态 | GT 固件不配置这些 `led_*_gpio` |
| Wi-Fi 指示灯 | 可能异常 | `ledbh` 取值不同（GT 为 1，RT 为 7） |
| 重启后不亮的老毛病 | 不会修好 | 论坛报告转换后仍会出现 |
| Game Port 第 1 级优先 | 可能缺失 | 论坛报告 |

本项目**不修改** `territory_code`。曾有英版用户询问转换后信道缺失、功率偏低的问题，没有得到回答，所以 `post` 会对比转换前后的信道数和发射功率。

## 官方固件

官方固件请从华硕下载，本仓库不转发。

| 固件 | 下载 | `.w` 文件的 SHA-256 |
|---|---|---|
| GT 51582 | [FW_GT_AC2900_300438651582.zip](https://dlcdnets.asus.com/pub/ASUS/wireless/GT-AC2900/FW_GT_AC2900_300438651582.zip) | `5f98933b4d788400d561fcd92da6cf96a4815f6952a4ad835624382aeac54fe2` |
| RT 52334 | [FW_RT-AC86U_300438652334.zip](https://dlcdnets.asus.com/pub/ASUS/wireless/RT-AC86U/FW_RT-AC86U_300438652334.zip) | `1b4fe984e13afdf0a69c11bda759f3222822e12f5b8c929da33f334f2cc7483f` |

## 变砖救援

按顺序尝试：

1. **CFE 救援网页。** 只要 `cferom` 和 `cferam` 完好就能进，刷固件不会动 `cferom`。上传 RT 的 `.w` 文件，步骤见教程。
2. **华硕 Firmware Restoration 工具或 TFTP。** 论坛报告 TFTP 比官方工具稳定，CFE 里也有 TFTP 服务端，本项目没有验证过。
3. **串口。** 主板有 4 针 UART，可以进 CFE 命令行看报错。**不要轻易使用 `w` 命令**，它会写整片闪存。
4. **Wi-Fi 校准或 MAC 丢失。** 从备份恢复 `misc1`/`misc2`。这一步风险高，先核对 `state/backup/proc_mtd.txt` 的分区号，并阅读 [JackMerlin 的 HND 指南](https://github.com/JackMerlin/How-to-flash-the-CFE-of-RT-AC86U-and-other-HND-routers/blob/main/README-zh_CN.md)。

## 不改型号开启 160 MHz

官方 RT 固件的 Wi-Fi 法规数据里没有 160 MHz 表，这才是 RT-AC86U 没有 160 MHz 选项的直接原因。可以保持 RT-AC86U 型号，刷一个带 160 MHz 表的 Merlin 386.14_2，这样 LED 和按键都不受影响。步骤和风险见 [教程](docs/build-merlin-160.md)。

可以自己编译，也可以下载 CI 编译的[测试版](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/releases/tag/merlin-160-386.14_2-test1)。这个固件同样**没有真机验证**，只适合会用 CFE 救援模式恢复的人测试。

## 工具

需要 Python 3.8+ 和 OpenSSH 客户端，没有第三方依赖。

| 文件 | 作用 | 会改路由器吗 |
|---|---|---|
| [tools/fwtool.py](tools/fwtool.py) | 离线解析和校验 `.w` 镜像（`info` / `verify` / `compare`） | 不会 |
| [tools/router-check.sh](tools/router-check.sh) | 路由器端健康报告 | 不会 |
| [tools/ac86u2gt.py](tools/ac86u2gt.py) | 流程工具（见下表） | 只有 `arm` 和 `disarm` |
| [tools/merlin160.py](tools/merlin160.py) | 给 Merlin 源码打 160 MHz 补丁，并检查编译结果 | 不会 |

| 命令 | 作用 |
|---|---|
| `check-fw IMAGE MODEL` | 校验镜像，不需要路由器 |
| `pre` | 只读报告，保存为 `state/pre.txt` |
| `backup` | 备份所有 MTD 分区、nvram 和 `/jffs` |
| `arm IMAGE` | 校验镜像和备份，确认后设置 `skip_crc=1`（不写入闪存） |
| `disarm` | 设置 `skip_crc=0` |
| `post` | 只读报告，并与 `pre.txt` 对比 |

工具不会自动刷机，上传固件这一步必须手动完成。`state/` 里有密码、Wi-Fi 密钥和序列号，**不要提交或公开**，`.gitignore` 已排除它。

运行测试（不接触任何真实设备）：

```bash
python3 -m unittest discover -s tests
```

## 许可证

代码和文档以 [MIT 许可证](LICENSE) 发布。许可证不提供任何担保，刷机造成的损失由操作者自行承担。

[160 MHz 测试版](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/releases/tag/merlin-160-386.14_2-test1)是修改过的 Merlin 固件，含 GPL 等开源组件和华硕、博通的闭源组件，不适用 MIT 许可证，也不是 Merlin 或华硕的官方版本。编译所用的 Merlin 源码保存在[这个 fork](https://github.com/maigougou/asuswrt-merlin.ng/tree/386.14_2)。

## 免责声明

本项目与华硕（ASUS）、Broadcom 和 Asuswrt-Merlin 项目没有任何关联。文中商标归各自所有者所有。

## 来源

- [RT-AC86U converted to GT-AC2900 reboot fix?（含 RMerlin 的反对意见）](https://www.snbforums.com/threads/rt-ac86u-converted-to-gt-ac2900-reboot-fix.60012/)
- [Convert ASUS RT-AC86U to ROG Rapture GT-AC2900（UKTechHub 实测报告）](https://uktechhub.com/forums/topic/asus-rt-ac86u-vs-rog-rapture-gt-ac2900-flash-hack/)
- [GT-AC2900 Merlin-compatible?](https://www.snbforums.com/threads/gt-ac2900-merlin-compatible.61568/)
- [RMerl/asuswrt-merlin.ng `386_x` 分支](https://github.com/RMerl/asuswrt-merlin.ng/tree/386_x)
- [Merlin 支持设备列表](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)
- [JackMerlin：HND 路由器 NVRAM 分区指南](https://github.com/JackMerlin/How-to-flash-the-CFE-of-RT-AC86U-and-other-HND-routers/blob/main/README-zh_CN.md)
- [GT-AC2900 硬件规格（DeviWiki）](https://deviwiki.com/wiki/ASUS_GT-AC2900)
- [RT-AC86U 硬件规格（TechInfoDepot）](https://techinfodepot.shoutwiki.com/wiki/ASUS_RT-AC86U)
- [华硕：救援模式](https://www.asus.com/us/support/faq/1000814/) 和 [硬复位](https://www.asus.com/support/faq/1039074/)
- [GT-AC2900 官方固件页](https://asus.com/supportonly/rog%20rapture%20gt-ac2900/helpdesk_bios)

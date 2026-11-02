---
name: 硬件测试报告
about: 报告在真实 RT-AC86U 上运行本项目的结果
title: "[硬件报告] "
labels: hardware-report
---

<!-- 提交前请隐去 MAC 地址、序列号、Wi-Fi 名称和密码。不要附上 state/ 目录里的文件。 -->

## 环境

- 路由器硬件版本（标签上的 H/W Ver.）：
- 销售地区：
- 操作前的固件版本：
- 刷入的固件版本：
- 电脑系统（Windows / Linux / macOS）及版本：
- 本项目的提交版本：

## 做到了哪一步

- [ ] `pre`
- [ ] `backup`
- [ ] 刷入 GT 固件
- [ ] 恢复出厂
- [ ] `post`
- [ ] 刷回 RT 固件

## 刷入方式

- [ ] CFE 救援网页
- [ ] Firmware Restoration 工具
- [ ] `skip_crc`（`arm`）
- [ ] 其他：

结果（成功或失败，以及页面或工具的提示）：

## 工具输出

`pre` 和 `post` 的 PASS / WARN / FAIL 行：

```text

```

`/proc/mtd` 内容（`state/backup/proc_mtd.txt`）：

```text

```

`backup` 是否有警告？`unstable.txt` 里列了哪些分区？

## 刷机后的表现

| 项目 | 结果 |
|---|---|
| 2.4G / 5G Wi-Fi | |
| 160 MHz 是否协商成功 | |
| 信道数、发射功率与转换前相比 | |
| LAN / WAN / USB | |
| 复位 / WPS / Wi-Fi / LED 按键 | |
| 电源 / WAN / USB / Wi-Fi 指示灯 | |
| 软重启 3 次是否都正常 | |
| 日志中是否有反复的 `TURBO` | |
| 连续运行时长，是否有异常重启 | |

## 其他说明

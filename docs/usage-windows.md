# Windows 使用教程

适用于 Windows 10（1809 及以上）和 Windows 11。下面的命令都在 **PowerShell** 中执行。

> **先读这段：** 本项目还没有在真机上验证过，操作可能让路由器变砖，风险自负。动手前请先读 [README](../README.md) 的"刷完后的预期行为"和"尚未验证"。

## 流程总览

| 阶段 | 内容 | 会改动路由器吗 |
|---|---|---|
| 1 | 安装环境 | 不会 |
| 2 | 下载并校验固件 | 不会 |
| 3 | 开启 SSH，配置密钥 | 只改 SSH 设置 |
| 4 | 预检和备份 | 不会 |
| 5 | 刷入 GT 固件 | **会** |
| 6 | 恢复出厂 | **会** |
| 7 | 验收 | 关闭 Aura 轮询时会 |
| 8 | 升级到 Merlin（建议） | **会** |

**需要准备：** 一根网线、一台带网口的电脑（或 USB 网卡），以及至少 1 GB 磁盘空间。如果这台路由器是你的主路由，再备一个手机热点。

## 第 1 阶段：安装环境

检查 Python。需要 3.8 或更高版本：

```powershell
py --version
```

如果提示找不到命令，用下面的命令安装，然后重新打开 PowerShell：

```powershell
winget install Python.Python.3.12
```

检查 SSH 客户端：

```powershell
ssh -V
```

如果提示找不到命令，**以管理员身份**打开 PowerShell，运行：

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
```

获取本项目。在 [GitHub 页面](https://github.com/maigougou/rt-ac86u-to-gt-ac2900) 点 **Code → Download ZIP** 并解压，或者用 Git 克隆。然后进入项目目录，后面的命令都在这里执行：

```powershell
cd C:\路径\到\项目目录
```

## 第 2 阶段：下载并校验固件

创建目录：

```powershell
New-Item -ItemType Directory -Force firmware
```

下载华硕官方的 GT 固件。要写 `curl.exe`，因为旧版 PowerShell 里的 `curl` 是别的命令：

```powershell
curl.exe -fL -o firmware\gt.zip https://dlcdnets.asus.com/pub/ASUS/wireless/GT-AC2900/FW_GT_AC2900_300438651582.zip
```

下载 RT 固件，回退时要用：

```powershell
curl.exe -fL -o firmware\rt.zip https://dlcdnets.asus.com/pub/ASUS/wireless/RT-AC86U/FW_RT-AC86U_300438652334.zip
```

解压：

```powershell
Expand-Archive firmware\gt.zip -DestinationPath firmware -Force
```

```powershell
Expand-Archive firmware\rt.zip -DestinationPath firmware -Force
```

校验两个文件：

```powershell
py tools\ac86u2gt.py check-fw firmware\GT-AC2900_3.0.0.4_386_51582-gb956e1b_ubi.w GT-AC2900
```

```powershell
py tools\ac86u2gt.py check-fw firmware\RT-AC86U_3.0.0.4_386_52334-gd500e53_ubi.w RT-AC86U
```

两个都必须显示 `OK: 12/12 checks passed`。再核对文件哈希：

```powershell
Get-FileHash firmware\*.w -Algorithm SHA256
```

结果应与 README 中列出的值一致。

## 第 3 阶段：开启 SSH 并配置密钥

Windows 的 OpenSSH 不支持连接复用，备份时每个分区都要重新连接。用密码的话要输入几十次，所以这里**强烈建议用密钥**。

生成密钥。提示输入路径和口令时，可以直接回车：

```powershell
ssh-keygen -t ed25519
```

显示公钥并复制：

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

登录路由器网页（通常是 `http://192.168.50.1`），打开 **系统管理 → 系统设置**：

1. 启用 SSH，选择 **LAN only**（仅局域网）。
2. 把公钥粘贴到 **Authorized Keys**。
3. 点击应用。

设置路由器地址。`admin` 换成你的路由器管理账号，这个设置只对当前窗口有效：

```powershell
$env:RT_HOST = "admin@192.168.50.1"
```

测试连接，第一次会询问是否信任主机，输入 `yes`。应该输出 `RT-AC86U`：

```powershell
ssh $env:RT_HOST "nvram get productid"
```

## 第 4 阶段：预检和备份

这两步对路由器只读。

```powershell
py tools\ac86u2gt.py pre
```

输出里只要有 `FAIL` 就停下来，先排查原因。报告保存在 `state\pre.txt`。

```powershell
py tools\ac86u2gt.py backup
```

需要几分钟。如果出现 `do not flash`，就不要继续。如果出现 `changed while being read`，说明该分区正被系统写入，备份可能不是完整快照，这个分区的结果记录在 `unstable.txt`。

备份完成后：

1. 把整个 `state` 文件夹复制到 U 盘或另一台电脑。
2. 不要放进 OneDrive 等云同步目录，也不要上传到 GitHub，里面有密码和 Wi-Fi 密钥。
3. 在路由器网页导出一份 `.CFG` 配置文件，只用于回退到 RT 固件后恢复。

## 第 5 阶段：刷入 GT 固件

三条路线任选一条，按推荐顺序排列。全程**不要断电**，也让电脑保持不休眠。

### 路线 A：CFE 救援网页（首选）

**1. 设置静态 IP。** 拔掉路由器的 WAN 线，电脑关闭 Wi-Fi，用网线接路由器的 LAN1 口。

先查网卡名称：

```powershell
Get-NetAdapter
```

**以管理员身份**打开 PowerShell，把 `以太网` 换成你的网卡名称：

```powershell
netsh interface ipv4 set address name="以太网" static 192.168.1.10 255.255.255.0
```

也可以用图形界面：设置 → 网络和 Internet → 以太网 → IP 分配 → 编辑 → 手动，IPv4 地址填 `192.168.1.10`，子网掩码填 `255.255.255.0`。

**2. 进入救援模式。** 关掉路由器电源，按住 Reset 键再开机，直到电源灯开始慢闪，然后松开。

**3. 确认已连通：**

```powershell
ping 192.168.1.1
```

**4. 上传固件。** 用浏览器打开 `http://192.168.1.1`，选择 `firmware` 目录里的 GT `.w` 文件并上传。

**5. 等待。** 至少等 5 分钟，直到路由器自行重启。

**6. 恢复网卡设置**（管理员 PowerShell）：

```powershell
netsh interface ipv4 set address name="以太网" dhcp
```

如果页面提示镜像非法，改用路线 B 或 C。

### 路线 B：华硕 Firmware Restoration 工具

论坛上的转换成功报告用的就是这个工具，但那是 2019 年的早期固件版本。

1. 从[华硕 RT-AC86U 支持页](https://www.asus.com/supportonly/RT-AC86U/HelpDesk_Download)的"Utilities"下载 Firmware Restoration 并安装。
2. 按路线 A 的第 1、2 步设置静态 IP，进入救援模式。
3. 按[华硕说明](https://www.asus.com/us/support/faq/1000814/)临时关闭防火墙。
4. **以管理员身份**运行工具，选择 GT 的 `.w` 文件并上传。如果文件框里看不到它，把文件类型切换为"所有文件"。
5. 等路由器自行重启，然后重新开启防火墙，并恢复网卡设置。

### 路线 C：Web UI 加 `skip_crc`

这条路线跨型号未实测，路由器保持正常联网即可。

```powershell
py tools\ac86u2gt.py arm firmware\GT-AC2900_3.0.0.4_386_51582-gb956e1b_ubi.w
```

工具会校验镜像和备份，然后要求输入确认词 `FLASH GT-AC2900`。之后到路由器网页的 **系统管理 → 固件升级** 上传同一个文件。

如果决定不刷，**务必执行**：

```powershell
py tools\ac86u2gt.py disarm
```

## 第 6 阶段：恢复出厂

必须做，因为两个型号的 nvram 默认值不同。

1. 按[华硕说明](https://www.asus.com/support/faq/1039074/)做硬复位。
2. 把电脑恢复为自动获取 IP，然后打开 `http://192.168.50.1`（打不开就试 `http://192.168.1.1`）。
3. 按向导手动配置。**不要导入 RT 的 `.CFG`。**
4. 关闭自动固件更新。
5. 重新开启 SSH 并粘贴公钥，方法同第 3 阶段。复位会清空这些设置。

路由器的 SSH 主机密钥也会变，要先清除旧记录，否则 SSH 会拒绝连接：

```powershell
ssh-keygen -R 192.168.50.1
```

## 第 7 阶段：验收

```powershell
py tools\ac86u2gt.py post
```

它会确认型号已变，MAC 和序列号未变，并报告信道数、发射功率和国家码的变化。如果有 `FAIL`，或者发射功率、信道数明显下降，就[回退](#回退)。

关闭 Aura 轮询，因为板上没有这个控制器：

```powershell
ssh $env:RT_HOST "nvram set aurargb_enable=0; nvram commit; reboot"
```

路由器重启后再运行一次 `post`，确认输出里有 `INFO pause_aura_rgb_nt=1`。

然后人工核对：

- [ ] 2.4G 和 5G 都能连接，用 iperf 对比转换前的速度
- [ ] 5G 选 160 MHz 后，客户端确实协商到 160 MHz
- [ ] 所有 LAN 口、WAN 口和 USB 正常
- [ ] 观察 24 小时：无异常重启，系统日志里没有反复的 `TURBO`
- [ ] 软重启 3 次，全部正常回来

欢迎把结果提交到 [Issues](https://github.com/maigougou/rt-ac86u-to-gt-ac2900/issues/new?template=hardware-report.md)。

160 MHz 通常要占用 DFS 信道，请遵守当地无线电法规。

## 第 8 阶段：升级到 Merlin（建议）

GT 官方固件比 RT 官方固件旧，缺少后来的安全修复。到 [Asuswrt-Merlin](https://www.asuswrt-merlin.net/) 下载 GT-AC2900 的版本，解压后校验：

```powershell
py tools\ac86u2gt.py check-fw firmware\你下载的文件_ubi.w GT-AC2900
```

通过后走 **系统管理 → 固件升级** 正常上传。此时型号一致，不需要 `arm`。文件名带 `cferom` 或 `pureubi` 的镜像会被工具拒绝，不要用它们。

## 回退

GT 固件的 Web 界面也会拒绝 RT 镜像，所以回退同样要走特殊路线。

- **CFE 或 Firmware Restoration：** 步骤同第 5 阶段，改为上传 RT 的 `.w` 文件。
- **`skip_crc`：** 工具会根据当前型号自动判断方向，确认词是 `FLASH RT-AC86U`：

```powershell
py tools\ac86u2gt.py arm firmware\RT-AC86U_3.0.0.4_386_52334-gd500e53_ubi.w
```

完成后硬复位，再导入第 4 阶段导出的 `.CFG`。

## 常见问题

| 现象 | 处理 |
|---|---|
| `py` 找不到命令，或打开了微软商店 | 重新安装 Python，或把命令里的 `py` 换成 `python` |
| `ssh not found` | 按第 1 阶段安装 OpenSSH 客户端 |
| `no router given` | 当前窗口没设置 `$env:RT_HOST`，新开窗口后要重新设置 |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | 执行 `ssh-keygen -R 路由器IP`，复位后这是正常现象 |
| `Permission denied` | 用户名要用路由器管理账号；确认公钥已粘贴并点了应用 |
| `Connection refused` 或超时 | 确认 SSH 已开启且 IP 正确；可用 `ipconfig` 查"默认网关" |
| 备份时反复要密码 | 按第 3 阶段配置密钥 |
| `192.168.1.1` 打不开 | 确认电脑是静态 IP，Wi-Fi 已关闭，电源灯在慢闪 |
| `netsh` 报拒绝访问 | 要用管理员身份打开 PowerShell |
| 刷完后 10 分钟仍无响应 | 断电重新进救援模式，再刷一次 RT 固件；还不行就看 README 的"变砖救援" |

# Linux 使用教程

适用于常见的桌面 Linux 发行版。macOS 的步骤基本相同，差异写在[文末](#macos-差异)。

> **先读这段：** 本项目还没有在真机上验证过，操作可能让路由器变砖，风险自负。动手前请先读 [README](../README.md) 的"刷完后的预期行为"和"尚未验证"。

## 流程总览

| 阶段 | 内容 | 会改动路由器吗 |
|---|---|---|
| 1 | 安装环境 | 不会 |
| 2 | 下载并校验固件 | 不会 |
| 3 | 开启 SSH | 只改 SSH 设置 |
| 4 | 预检和备份 | 不会 |
| 5 | 刷入 GT 固件 | **会** |
| 6 | 恢复出厂 | **会** |
| 7 | 验收 | 关闭 Aura 轮询时会 |
| 8 | 升级到 Merlin（建议） | **会** |

**需要准备：** 一根网线、一台带网口的电脑（或 USB 网卡），以及至少 1 GB 磁盘空间。如果这台路由器是你的主路由，再备一个手机热点。

## 第 1 阶段：安装环境

需要 Python 3.8 或更高版本、OpenSSH 客户端、curl 和 unzip。

Debian / Ubuntu：

```bash
sudo apt install python3 openssh-client curl unzip
```

Fedora：

```bash
sudo dnf install python3 openssh-clients curl unzip
```

Arch：

```bash
sudo pacman -S python openssh curl unzip
```

获取本项目并进入项目目录，后面的命令都在这里执行：

```bash
git clone https://github.com/maigougou/rt-ac86u-to-gt-ac2900.git
```

```bash
cd rt-ac86u-to-gt-ac2900
```

## 第 2 阶段：下载并校验固件

创建目录：

```bash
mkdir -p firmware
```

下载华硕官方的 GT 固件：

```bash
curl -fL -o firmware/gt.zip https://dlcdnets.asus.com/pub/ASUS/wireless/GT-AC2900/FW_GT_AC2900_300438651582.zip
```

下载 RT 固件，回退时要用：

```bash
curl -fL -o firmware/rt.zip https://dlcdnets.asus.com/pub/ASUS/wireless/RT-AC86U/FW_RT-AC86U_300438652334.zip
```

解压：

```bash
unzip -o firmware/gt.zip -d firmware
```

```bash
unzip -o firmware/rt.zip -d firmware
```

校验两个文件：

```bash
python3 tools/ac86u2gt.py check-fw firmware/GT-AC2900_3.0.0.4_386_51582-gb956e1b_ubi.w GT-AC2900
```

```bash
python3 tools/ac86u2gt.py check-fw firmware/RT-AC86U_3.0.0.4_386_52334-gd500e53_ubi.w RT-AC86U
```

两个都必须显示 `OK: 12/12 checks passed`。再核对文件哈希：

```bash
sha256sum firmware/*.w
```

结果应与 README 中列出的值一致。

## 第 3 阶段：开启 SSH

登录路由器网页（通常是 `http://192.168.50.1`），打开 **系统管理 → 系统设置**，启用 SSH 并选择 **LAN only**（仅局域网）。

Linux 上工具会复用 SSH 连接，所以用密码也只需输入几次。想免密的话：

生成密钥（已有密钥可跳过）：

```bash
ssh-keygen -t ed25519
```

显示公钥，把它粘贴到同一页的 **Authorized Keys**，然后点击应用：

```bash
cat ~/.ssh/id_ed25519.pub
```

设置路由器地址。`admin` 换成你的路由器管理账号，这个设置只对当前终端有效：

```bash
export RT_HOST=admin@192.168.50.1
```

测试连接，第一次会询问是否信任主机，输入 `yes`。应该输出 `RT-AC86U`：

```bash
ssh "$RT_HOST" nvram get productid
```

## 第 4 阶段：预检和备份

这两步对路由器只读。

```bash
python3 tools/ac86u2gt.py pre
```

输出里只要有 `FAIL` 就停下来，先排查原因。报告保存在 `state/pre.txt`。

```bash
python3 tools/ac86u2gt.py backup
```

需要几分钟。如果出现 `do not flash`，就不要继续。如果出现 `changed while being read`，说明该分区正被系统写入，备份可能不是完整快照，这个分区的结果记录在 `unstable.txt`。

可以自行复核备份：

```bash
(cd state/backup && sha256sum -c MANIFEST.sha256)
```

备份完成后：

1. 把整个 `state` 目录复制到 U 盘或另一台机器。
2. 不要上传到任何公开位置，里面有密码和 Wi-Fi 密钥。
3. 在路由器网页导出一份 `.CFG` 配置文件，只用于回退到 RT 固件后恢复。

## 第 5 阶段：刷入 GT 固件

全程**不要断电**，也让电脑保持不休眠。

### 路线 A：CFE 救援网页（首选）

**1. 设置静态 IP。** 拔掉路由器的 WAN 线，关闭 Wi-Fi，用网线接路由器的 LAN1 口。

查网卡名称：

```bash
ip -br link
```

使用 NetworkManager 的系统（大多数桌面发行版），把 `enp3s0` 换成你的网卡名称。路由器重启时网口会断开再连接，而 NetworkManager 配置能在这之后自动恢复，所以优先用这种方法：

```bash
sudo nmcli connection add type ethernet ifname enp3s0 con-name asus-rescue ipv4.method manual ipv4.addresses 192.168.1.10/24
```

```bash
sudo nmcli connection up asus-rescue
```

```bash
nmcli radio wifi off
```

没有 NetworkManager 的系统：

```bash
sudo ip link set enp3s0 up
```

```bash
sudo ip addr add 192.168.1.10/24 dev enp3s0
```

**2. 进入救援模式。** 关掉路由器电源，按住 Reset 键再开机，直到电源灯开始慢闪，然后松开。

**3. 确认已连通：**

```bash
ping -c 3 192.168.1.1
```

**4. 上传固件。** 用浏览器打开 `http://192.168.1.1`，选择 `firmware` 目录里的 GT `.w` 文件并上传。

**5. 等待。** 至少等 5 分钟，直到路由器自行重启。

**6. 恢复网络设置。** NetworkManager：

```bash
sudo nmcli connection delete asus-rescue
```

```bash
nmcli radio wifi on
```

没有 NetworkManager 的系统：

```bash
sudo ip addr del 192.168.1.10/24 dev enp3s0
```

如果页面提示镜像非法，改用路线 B。

华硕的 Firmware Restoration 工具没有 Linux 版。论坛上还有人报告用 TFTP 比官方工具稳定，本项目没有验证过这种方式，请仅作为备选。

### 路线 B：Web UI 加 `skip_crc`

这条路线跨型号未实测，路由器保持正常联网即可。

```bash
python3 tools/ac86u2gt.py arm firmware/GT-AC2900_3.0.0.4_386_51582-gb956e1b_ubi.w
```

工具会校验镜像和备份，然后要求输入确认词 `FLASH GT-AC2900`。之后到路由器网页的 **系统管理 → 固件升级** 上传同一个文件。

如果决定不刷，**务必执行**：

```bash
python3 tools/ac86u2gt.py disarm
```

## 第 6 阶段：恢复出厂

必须做，因为两个型号的 nvram 默认值不同。

1. 按[华硕说明](https://www.asus.com/support/faq/1039074/)做硬复位。
2. 把电脑恢复为自动获取 IP，然后打开 `http://192.168.50.1`（打不开就试 `http://192.168.1.1`）。
3. 按向导手动配置。**不要导入 RT 的 `.CFG`。**
4. 关闭自动固件更新。
5. 重新开启 SSH，方法同第 3 阶段。复位会清空这些设置。

路由器的 SSH 主机密钥也会变，要先清除旧记录，否则 SSH 会拒绝连接：

```bash
ssh-keygen -R 192.168.50.1
```

## 第 7 阶段：验收

```bash
python3 tools/ac86u2gt.py post
```

它会确认型号已变，MAC 和序列号未变，并报告信道数、发射功率和国家码的变化。如果有 `FAIL`，或者发射功率、信道数明显下降，就[回退](#回退)。

关闭 Aura 轮询，因为板上没有这个控制器：

```bash
ssh "$RT_HOST" 'nvram set aurargb_enable=0; nvram commit; reboot'
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

```bash
python3 tools/ac86u2gt.py check-fw firmware/你下载的文件_ubi.w GT-AC2900
```

通过后走 **系统管理 → 固件升级** 正常上传。此时型号一致，不需要 `arm`。文件名带 `cferom` 或 `pureubi` 的镜像会被工具拒绝，不要用它们。

## 回退

GT 固件的 Web 界面也会拒绝 RT 镜像，所以回退同样要走特殊路线。

- **CFE 救援网页：** 步骤同第 5 阶段，改为上传 RT 的 `.w` 文件。
- **`skip_crc`：** 工具会根据当前型号自动判断方向，确认词是 `FLASH RT-AC86U`：

```bash
python3 tools/ac86u2gt.py arm firmware/RT-AC86U_3.0.0.4_386_52334-gd500e53_ubi.w
```

完成后硬复位，再导入第 4 阶段导出的 `.CFG`。

## 常见问题

| 现象 | 处理 |
|---|---|
| `ssh not found` | 按第 1 阶段安装 OpenSSH 客户端 |
| `no router given` | 当前终端没设置 `RT_HOST`，新开终端后要重新设置 |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | 执行 `ssh-keygen -R 路由器IP`，复位后这是正常现象 |
| `Permission denied` | 用户名要用路由器管理账号；确认公钥已粘贴并点了应用 |
| `Connection refused` 或超时 | 确认 SSH 已开启且 IP 正确；可用 `ip route` 查默认网关 |
| `192.168.1.1` 打不开 | 确认 `ip addr` 里有 `192.168.1.10`，Wi-Fi 已关闭，电源灯在慢闪 |
| 静态 IP 过一会儿消失 | NetworkManager 覆盖了手动设置，改用上面的 `nmcli` 方法 |
| 刷完后 10 分钟仍无响应 | 断电重新进救援模式，再刷一次 RT 固件；还不行就看 README 的"变砖救援" |

## macOS 差异

其余命令与 Linux 相同。

**安装 Python：** 系统没有 `python3` 时，从 [python.org](https://www.python.org/downloads/) 安装，或用 Homebrew：

```bash
brew install python
```

**校验哈希：**

```bash
shasum -a 256 firmware/*.w
```

**查网卡名称：**

```bash
networksetup -listallnetworkservices
```

**设置静态 IP**（把 `Ethernet` 换成上一步查到的名称）：

```bash
sudo networksetup -setmanual "Ethernet" 192.168.1.10 255.255.255.0
```

**恢复自动获取：**

```bash
sudo networksetup -setdhcp "Ethernet"
```

**关闭和打开 Wi-Fi：** 用菜单栏操作即可。

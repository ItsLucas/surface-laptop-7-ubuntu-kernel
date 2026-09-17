# Surface Laptop 7：Ubuntu 26.10 自动内核构建

为13.8英寸 Snapdragon X Elite / Romulus13 跟踪 Ubuntu 26.10（stonking）的官方 generic 内核，叠加已整理的 Wi-Fi、QSPI触控板、SPI触摸屏和GPIO/电源管理补丁。每天北京时间11:17检查，也可手动运行；GitHub计划任务可能延迟。

## 自动更新与通知

- 从发行版 `linux-image-generic` 的当前候选依赖解析内核版本和ABI，再取**同版本**的 `linux-source-*` 与 `linux-buildinfo-*-generic`。没有固定7.2；Ubuntu切换到7.3时会自动选择7.3源码和配置。
- 只使用stonking、stonking-updates、stonking-security，不跟踪proposed，也不会自动换到下一版Ubuntu。
- Ubuntu版本、补丁、构建脚本、workflow或公开模块证书改变才重建。手动选择force可强制重建；每次产物的内核release都唯一，便于并存。
- 五个补丁按series严格依次应用，`--fuzz=0`。任何补丁冲突、源/config不同步、工具链变化或编译失败，都使构建失败；不自动跳过、反向应用或让AI自动改补丁。
- 失败时自动创建/更新一个GitHub Issue，`@仓库所有者`并附运行链接。通知邮件/推送依赖所有者的GitHub通知设置。后续成功构建自动关闭该Issue。GitHub基础设施整体故障时通知任务也可能无法运行。
- 成功后发布 **prerelease / unsigned candidate**，含校验清单、官方输入版本、补丁哈希、构建日志和未签名内核模块；编译成功不代表已通过实机验收。

## Secure Boot与本地签名

GitHub只需要仓库变量 `MODULE_CERT_PEM`，内容是模块签名密钥对应的**公开PEM证书**，供内核内建信任。禁止上传私钥；此仓库不保存机器固件、个人校准、网络配置或MOK口令。

在仓库Settings → Secrets and variables → Actions → Variables添加该变量。也可在已登录gh的终端使用：

```sh
gh variable set MODULE_CERT_PEM --repo OWNER/REPO < /path/to/module-public-cert.pem
```

如果本机只有DER证书，先用 `openssl x509 -inform DER -in module.der -out module.pem` 转换公开证书即可。CI私钥为空；不会自动安装、生成本机initrd、登记MOK、改默认内核或重启。

下载Release产物，核对SHA256SUMS，在普通用户目录解压并审阅BUILD.json、config差异及日志。然后使用本机已登记的模块密钥和启动密钥签名：

```sh
sudo python3 ci/sign-local.py \
  --bundle /path/to/sl7-RELEASE-unsigned \
  --output /path/to/new-signed-output \
  --module-key /path/to/local-module-private-key \
  --module-cert /path/to/local-module-public-cert.pem \
  --boot-key /path/to/local-boot-private-key \
  --boot-cert /path/to/local-boot-public-cert.pem
```

本地需要openssl、sbsigntool、kmod、zstd、dpkg及Stubble Python依赖（如python3-pefile）。脚本验证文件清单、内建模块证书与私钥匹配、ARM64模块release；逐个签名并验证模块CMS签名，再签内层EFI、嵌入Romulus13设备树并签外层EFI，最终生成可并存deb。整个过程只写新的暂存目录，不安装。

此deb没有修改启动项的维护脚本。获准安装后，需用本机dracut、现有板级固件/模块配置生成对应initrd，并安排独立启动项；保持当前已验证内核、官方内核与5秒回退菜单。确认Secure Boot、Wi-Fi/MAC、蓝牙、触控板移动/点击/轻触/双指滚动、触屏、冷启动、熄屏/解锁和deep恢复后，才考虑切换默认。私钥丢失或更换需要另行处理信任登记，不能关闭Secure Boot绕过。

## 补丁与支持范围

| 补丁 | 内容 |
|---|---|
| 0001 | Romulus13 ath12k硬rfkill workaround |
| 0002 | ELLX来源的QSPI/GPI/SPI HID transport及触控板设备树移植 |
| 0003 | 本机GTCH SPI触摸屏设备树 |
| 0004 | SPI HID系统睡眠、关机和电源生命周期 |
| 0005 | GPIO供电/reset职责分离、触屏跟随内置屏幕省电 |

来源见[PROVENANCE.md](PROVENANCE.md)。0004/0005原补丁说明中的test字样来自2026-09-15阶段归档；之后已在基线7.2.0-5.5上使用，但不意味着任意新版本自动通过实测。13英寸与15英寸的设备树不可混用。

保留现有修复版iptsd、指尖/拇指联合校准、UEFI推导MAC服务和显示恢复服务；这些不随每次内核构建重装。本地iptsd睡眠钩子曾按SPI HID模块版本判断，未来修改模块版本或升级iptsd时也要审阅。偶发触控板/EC卡住和USB4扩展坞链路问题没有被本CI宣称解决。

云端使用GitHub ARM64标准runner、固定digest的Ubuntu26.10基础容器，并从APT获取当前Ubuntu工具链。保留官方debug/BTF配置；构建前释放临时runner的预装SDK空间，空间不足就失败。公开仓库标准runner免费，产物存储仍应定期管理。Actions附件保留7/14天，Release保留以便回退。

参考：[Ubuntu内核构建](https://documentation.ubuntu.com/kernel/how-to/develop-customise/build-kernel/)、[GitHub托管runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。

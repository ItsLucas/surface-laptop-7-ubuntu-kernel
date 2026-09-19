# Surface Laptop 7：Ubuntu 26.10 自动内核构建

为13.8英寸 Snapdragon X Elite / Romulus13 跟踪 Ubuntu 26.10（stonking）的官方 generic 内核，叠加已整理的 Wi-Fi、QSPI触控板、SPI触摸屏和GPIO/电源管理补丁。每天北京时间11:17检查，也可手动运行；GitHub计划任务可能延迟。

## 自动更新与通知

- 从发行版 `linux-image-generic` 的当前候选依赖解析内核版本和ABI，再取**同版本**的 `linux-source-*` 与 `linux-buildinfo-*-generic`。没有固定7.2；Ubuntu切换到7.3时会自动选择7.3源码和配置。
- 只使用stonking、stonking-updates、stonking-security，不跟踪proposed，也不会自动换到下一版Ubuntu。
- Ubuntu版本、补丁、构建脚本、workflow或公开模块证书改变才重建。手动选择force可强制重建；每次产物的内核release都唯一，便于并存。
- 五个补丁按series严格依次应用，`--fuzz=0`。任何补丁冲突、源/config不同步、工具链变化或编译失败，都使构建失败；不自动跳过、反向应用或让AI自动改补丁。
- 失败时自动创建/更新一个GitHub Issue，`@仓库所有者`并附运行链接。通知邮件/推送依赖所有者的GitHub通知设置。后续成功构建自动关闭该Issue。GitHub基础设施整体故障时通知任务也可能无法运行。
- 成功后发布 **prerelease / signed candidate**，含校验清单、官方输入版本、补丁哈希、构建日志、签名后的内核deb及可独立重签的未签名构建包；编译和验签成功不代表已通过实机验收。

## Secure Boot与GitHub Secrets签名

GitHub只需要仓库变量 `MODULE_CERT_PEM`，内容是模块签名密钥对应的**公开PEM证书**，供内核内建信任。构建任务不接触私钥；源码仓库不保存证书、私钥、机器固件、个人校准、网络配置或MOK口令。

在仓库Settings → Secrets and variables → Actions → Variables添加该变量。也可在已登录gh的终端使用：

```sh
gh variable set MODULE_CERT_PEM --repo OWNER/REPO < /path/to/module-public-cert.pem
```

如果本机只有DER证书，先用 `openssl x509 -inform DER -in module.der -out module.pem` 转换公开证书即可。签名私钥按用户要求保存在下述专用Environment的加密Secrets中；不会自动安装、生成本机initrd、登记MOK、改默认内核或重启。

仓库Environment `secure-boot-signing` 配置为仅允许main分支部署，并保存四个Secrets：

- `SL7_MODULE_KEY_PEM`：现有模块签名私钥。
- `SL7_MODULE_CERT_PEM`：配套公开模块证书，必须与MODULE_CERT_PEM变量相同。
- `SL7_BOOT_KEY_PEM`：现有EFI启动签名私钥。
- `SL7_BOOT_CERT_PEM`：配套公开启动证书。

可用 `gh secret set NAME --env secure-boot-signing --repo OWNER/REPO < /path/to/file` 设置。四项材料不得提交到Git。签名任务仅在main分支运行；PR检查不使用Environment或Secrets。签名工具镜像在注入Secrets之前构建，实际签名容器禁用网络；私钥仅写入容器/tmp的临时内存文件，子进程环境不再携带Secrets，结束后删除，不上传为Artifact。

模块使用Ubuntu提供的kmodsign，校验证书与私钥匹配、模块CMS签名以及内外两层EFI签名；不执行构建产物中的sign-file程序。保留原来已登记的密钥，因此本机无需重新登记MOK。对main分支、签名脚本和Environment的写权限等同于使用这些签名密钥的权限，应仅交给可信维护者。

成功Release提供签名内核deb、`linux-sl7-support`集成包、`linux-sl7`更新元包、SIGNING.json和RELEASE-SHA256SUMS，以及源码包、官方配置包、未签名构建包和日志。CI只构建和发布；用户通过APT安装后，包会自动生成匹配initrd并更新GRUB。

## APT软件源与自动安装

软件源为 **https://mirrors.5cena.cc/sl7/**，仅适用于Ubuntu 26.10 / arm64 / 13.8英寸Romulus13及已有GRUB2环境。`candidate`接收签名候选；实机验收后才晋升`stable`，尚无验收版本时stable为空。

```sh
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://mirrors.5cena.cc/sl7/sl7-archive-keyring.asc | sudo tee /etc/apt/keyrings/sl7-archive-keyring.asc >/dev/null
curl -fsSL https://mirrors.5cena.cc/sl7/sl7.sources | sudo tee /etc/apt/sources.list.d/sl7.sources >/dev/null
sudo apt update
sudo apt install linux-sl7
```

软件源公钥指纹为`EFC66FC43239A82F1909B2A6283F87158DF052D9`。下载的sources文件订阅candidate；只接收实机验收版本可将Components改为stable。保留`linux-sl7`元包后，后续执行`sudo apt upgrade`即可跟随内核更新。

安装包使用标准`/boot/vmlinuz-版本`、`/boot/config-版本`和`/boot/System.map-版本`布局。内核postinst调用Ubuntu的`linux-run-hooks`，由发行版dracut生成`/boot/initrd.img-版本`，再由GRUB钩子更新菜单。升级并存；卸载清理对应initrd及菜单；当前运行内核的删除交给Ubuntu的`linux-check-removal`。生成失败会使包配置失败，可在修正问题后用`sudo dpkg --configure -a`重试，不会自动重启。

设备树同时随包安装到`/usr/lib/linux-image-版本/qcom/x1e80100-microsoft-romulus13.dtb`，供发行版`flash-kernel`安装钩子使用。它直接提取自已签名EFI的`.dtbauto`，与镜像内设备树逐字节一致；不重新编译或修改签名镜像。安装测试包含`flash-kernel`及Romulus13机型配置，以覆盖这条实际安装路径。早期`sl7.5.1`包漏装了这份独立DTB，可能卡在`zz-flash-kernel`；这是打包缺陷，不要求重装系统。

SL7专用dracut配置只作用于`*-sl7.*`版本，加入SPI HID/GPI驱动并保留本机现有Wi-Fi board覆盖文件，不向官方内核强加未提供的模块。现有固件、dracut配置、GRUB板级参数、iptsd及校准继续沿用。两个已知旧固定默认项`sl7-combined-kernel`和`sl7-spi-touchscreen-test`会迁移到GRUB默认第一项；其他自定义默认值（包括saved）保留。旧菜单项也保留。旧SL7内核不会被autoremove自动删除，验收后可显式`apt purge linux-image-具体版本`释放空间。

APT源签名与Secure Boot信任是两套机制。原有机器已登记对应启动密钥，无需再次登记。新机器首次使用需通过`mokutil --test-key /usr/share/sl7-kernel/内核版本/boot-cert.der`检查，未登记时用`sudo mokutil --import`导入该文件并在重启的MOK界面确认；不要在完成登记前选择新内核，也不要关闭Secure Boot绕过。该源目前不提供headers/DKMS开发包，不替代机器固件和用户态配置。

首批`7.2.0-5.5+sl7.4.1+pkg1`从已签名Release重打包，内核release仍为`7.2.0-5-sl7.4.1`，EFI与模块字节不变。原Release内的旧deb仍是无安装钩子的历史产物；使用APT源中的新包。软件源部署、签名、同步与晋升说明见[repo/README.md](repo/README.md)。

如果希望自行重签：下载未签名构建包，核对SHA256SUMS，在普通用户目录解压并审阅BUILD.json、config差异及日志，然后使用本机密钥：

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

本地重签也生成上述三个配套deb，应一起交给`apt install ./linux-*.deb`处理依赖和自动配置。保持当前已验证内核、官方内核与回退菜单；新候选仍需确认Secure Boot、Wi-Fi/MAC、蓝牙、触控板移动/点击/轻触/双指滚动、触屏、冷启动、熄屏/解锁和deep恢复。私钥丢失或更换需要另行处理信任登记。

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

# 改为15英寸Romulus15：上机检查清单（2026-09-25）

## 背景

测试机实际是15英寸Surface Laptop 7。以前的记录都写成13.8英寸Romulus13，原因是装机时加载了Romulus13设备树，后面的判断都照这个设备树反推。三方面证据都指向15英寸：

- 用户确认机器是15英寸。
- 固件175.235.235和15英寸同属175.x系列；13.8英寸是144.x（见stubble的`hwids/txt`记录）。
- 专门做15英寸的[omarchy-surface-laptop7](https://github.com/denislopt/omarchy-surface-laptop7)，SPI触摸屏的引脚和本仓库0003完全一致：SPI10、GPIO64供电、GPIO48复位、GPIO51中断。

以前能正常用的原因：

- 上游两份设备树只差`model`和`compatible`。
- Stubble的两份硬件ID清单共用5个系列级CHID，15英寸也能匹配到Romulus13清单。

两个尺寸在SMBIOS里只有SKU不同：13.8英寸是`Surface_Laptop_7th_Edition_2036`，15英寸是`…_2037`。

## 本次改动

- 补丁0001、0002、0003、0005改为作用于`x1e80100-microsoft-romulus15.dts`和`microsoft,romulus15`。改后补丁在Ubuntu `7.3.0-5.5`源码上以`--fuzz=0`全部应用，结果与旧版逐文件一致，只有文件名和机型字符串不同。设备树部分在上游v7.2上同样严格应用。
- 构建romulus15.dtb；签名时使用stubble的romulus15硬件ID清单；安装包附带的DTB也改为romulus15.dtb。
- PLD功耗驱动的机型判断改为`microsoft,romulus15`。
- `linux-sl7-support`的postinst按SMBIOS SKU `…_2037`，把`/etc/flash-kernel/machine`设为`Microsoft Surface Laptop 7 (15 inch)`：
  - 文件原值是13.8英寸时，旧值备份到`/var/lib/sl7-kernel/`。
  - 管理员自定义的其他值保持不动，只打印提示。
- image包遇到SKU `…_2036`（13.8英寸）拒绝安装。
- GRUB清理脚本同时识别新旧两种DTB名称，旧SL7内核仍能从菜单启动，不带`devicetree`命令。

不做这个迁移会怎样：flash-kernel在旧设备树下按13.8英寸查找`romulus13.dtb`，新包里没有这个文件，内核postinst就会失败。容器测试已按此场景复现，加上迁移后通过。

## 1. 上机前先看，只读不改

把输出记下来：

```sh
cat /sys/class/dmi/id/{sys_vendor,product_name,product_sku,bios_version}
tr '\0' '\n' </proc/device-tree/model; echo
tr '\0' '\n' </proc/device-tree/compatible
ls -l /etc/flash-kernel/machine 2>/dev/null && cat /etc/flash-kernel/machine
uname -r; mokutil --sb-state
dpkg -l 'linux-image-*sl7*' linux-sl7 linux-sl7-support | grep '^ii'
```

预期结果：
- `product_sku`为`Surface_Laptop_7th_Edition_2037`。
- 当前model仍显示13.8 inch，因为正在运行的是旧内核。

**如果SKU不是`…_2037`，先停下来，把输出发给我。**迁移逻辑只识别这个值。

## 2. 先修改本机Wi-Fi MAC脚本（必须）

`/usr/local/libexec/sl7-wifi-mac`（维护仓库`config/system-root`中的同一个文件）只接受`microsoft,romulus13`。新内核启动后它会报错，Wi-Fi就拿不到UEFI出厂MAC。改为新旧两种设备树都接受，过渡期间旧内核也能正常用：

```sh
sudo cp -a /usr/local/libexec/sl7-wifi-mac /usr/local/libexec/sl7-wifi-mac.before-romulus15
sudo python3 - <<'EOF'
from pathlib import Path
p = Path('/usr/local/libexec/sl7-wifi-mac'); t = p.read_text()
old = ("    if b'microsoft,romulus13' not in compatible:\n"
       "        raise RuntimeError('This configuration is scoped to Surface Laptop 7 Romulus13')\n")
new = ("    if not {b'microsoft,romulus13', b'microsoft,romulus15'} & set(compatible):\n"
       "        raise RuntimeError('This configuration is scoped to the Surface Laptop 7')\n")
assert t.count(old) == 1, 'unexpected script content; review manually'
p.write_text(t.replace(old, new))
EOF
sudo /usr/local/libexec/sl7-wifi-mac show   # 应仍输出原来的 78:86:2e:5e:ec:47
```

`sl7-bt-address`只检查model中是否含`Microsoft Surface Laptop 7`，不用改。iptsd和校准按USB ID匹配，也不受影响。

## 3. 安装新内核

新包要等本分支合并到main、CI签名发布后，才会进入candidate源。

```sh
sudo apt update && sudo apt install linux-sl7
```

安装输出里应出现：

```
linux-sl7-support: SMBIOS SKU identifies a 15-inch Surface Laptop 7; set /etc/flash-kernel/machine to 'Microsoft Surface Laptop 7 (15 inch)'
Using DTB: qcom/x1e80100-microsoft-romulus15.dtb
```

装完后检查（把`NEW`换成新内核版本）：

```sh
sudo dpkg --audit                                   # 应无输出
cat /etc/flash-kernel/machine                       # Microsoft Surface Laptop 7 (15 inch)
ls /boot/dtbs/NEW/qcom/x1e80100-microsoft-romulus15.dtb
awk '/^menuentry|^submenu|^\tmenuentry/{e=$0} /devicetree/{print e}' /boot/grub/grub.cfg
# 上一条只允许列出官方generic内核，任何SL7条目都不应出现
```

## 4. 首次启动

不要先改默认启动项。在GRUB的高级选项里手动选新内核，旧SL7内核和官方内核都保留作回退。启动后检查：

```sh
tr '\0' '\n' </proc/device-tree/model; echo        # Microsoft Surface Laptop 7 (15 inch)
mokutil --sb-state; cat /sys/kernel/security/lockdown
rfkill list; journalctl -k -b | grep -i 'Surface Laptop 7 rfkill workaround'
systemctl status sl7-wifi-mac --no-pager; ip link show wlP4p1s0
journalctl -k -b | grep -i 'spi-hid\|spi_hid' | head
sensors | grep -A9 -i pld                           # PLD功耗通道（sl7_pld_device）
```

实机验收：
- Wi-Fi连接正常，MAC与原来一致。
- 蓝牙正常。
- 触控板：移动、物理点击、轻触、双指滚动。
- 触摸屏可用。
- 熄屏后解锁正常。
- deep睡眠后恢复：Wi-Fi、触控板、触摸屏都要恢复。
- 冷启动正常。

最关键的是Wi-Fi。0001的rfkill绕过现在按romulus15匹配，如果匹配不上，`rfkill list`会显示hard blocked。

## 5. 回退与清理

- 新内核有问题：直接在GRUB里选旧SL7内核启动。它们内嵌Romulus13设备树，GRUB条目不带`devicetree`，仍可用。
- 迁移完成后，flash-kernel按15英寸查找DTB，而旧SL7包里只有romulus13.dtb。所以不要对旧内核执行`dpkg-reconfigure`；在旧内核仍是最新SL7版本时，也不要删除新内核。
- 新内核验收通过后，用`sudo apt purge linux-image-旧版本`清掉Romulus13时期的内核。
- 如需撤销机型设置：原文件的备份（如果有）在`/var/lib/sl7-kernel/flash-kernel-machine.before-sl7`。没有这个备份说明原来没有该文件，删除`/etc/flash-kernel/machine`即可。

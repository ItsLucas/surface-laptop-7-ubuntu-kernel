# SPI HID 与 Windows 对齐：0007–0017 实机验收（2026-09-27）

0007–0015 只改 `drivers/hid/spi-hid/`（触控板和触摸屏共用的传输驱动），0015 另给触摸屏设备树加 `irq-gpios`；0016 只在 `spi-geni-qcom` 里加一行日志；0017 只改两份 QSPI 引脚设备树。依据是本机 Windows `hidspi.sys`、`HidSpiCx.sys`（微软公开符号）和 `qcspi8380.sys` 的静态分析，以及驱动包里解码后的 `BSRC_QSPI*.bin`。尚未在实机验证。

0007–0012 随 PR #9 进入 `sl7.20260927.1`；0013–0017 在其后的内核里，模块版本 `sl7.20260927.2`。

| 补丁 | 问题 | Windows 做法 |
|---|---|---|
| 0007 | 报告体内的 content length 未与报文长度比对，可越界读 8 KiB 缓冲；多分片报告被当成多个完整报告 | `ProcessBody` 校验长度；分片累积，1 秒超时 |
| 0008 | 用 `completion_done()` 判断是否有请求在等，设备自发复位被吞掉，`device_initiated_reset_count` 永远为 0 | `VerifyResetResponse` → `EvtDeviceReset` 通知上层重新配置 |
| 0009 | GET/SET_FEATURE 解锁后才读响应，并发请求可覆盖 | — |
| 0010 | 输出报告长度未按 4 字节对齐 | `SendWriteToBus` 补零到 4 的倍数 |
| 0011 | 触控板供电由固件打开且 boot-on，驱动从未真正断电；无复位响应的设备永远不会被枚举或重试 | ACPI `_PS3/_PS0`；启动时复位后有 2 秒定时器 |
| 0012 | 除 -ENODEV 外的供电错误都变成无限 -EPROBE_DEFER | — |
| 0013 | 0008 之后 `create_device_work`/`refresh_device_work` 已无人排队，HIDSPI 版本检查随之失效 | — |
| 0014 | 无论 content ID 是否为 0 都把它当报告 ID 交给 HID core | 仅在 content ID 非 0 时前置报告 ID |
| 0015 | 触摸屏中断为下降沿，每次中断只读一份报告；读报告期间线又被拉低时不会再有边沿，输入卡住 | — |
| 0016 | Windows 在 `GENI_IF_DISABLE_RO` bit 0 置位时跳过 GPI 寄存器设置，我们每条消息都写；该位在本机的值未知 | 置位时跳过（本补丁只记日志） |
| 0017 | QSPI 引脚为 `bias-disable`，触摸屏 6 mA | D0 下全部下拉；触控板 6 mA，触摸屏 4 mA |

## 运行时开关

`reset_recovery`（可在运行时修改）：
- `2`（默认）：重新读取描述符，并重建 HID 设备，iptsd 会重启并重设模式。
- `1`：只重新读取描述符。
- `0`：只计数、只记日志，行为与旧驱动一致。

保护措施：
- 主机发出 SET_FEATURE 后 3 秒内的复位不重建设备（改模式本身可能导致复位）。
- 两次重建之间至少间隔 10 秒。

```sh
cat /sys/module/spi_hid/parameters/reset_recovery
echo 1 | sudo tee /sys/module/spi_hid/parameters/reset_recovery   # 如触控板反复重连
```

## 验收步骤

1. 确认版本：

   ```sh
   modinfo spi_hid | grep -i version            # sl7.20260927.1（PR #9）或 .2（含 0013–0017）
   ```

2. 查看两个设备的描述符：

   ```sh
   journalctl -k -b | grep -E 'HID-SPI|spi_hid|spi-hid'
   ```

   - 应各有一行 `HID-SPI 045e:0c77 ...`（触控板）和 `045e:0c6f ...`（触摸屏）。
   - 请记下 `input / output / fragment` 三个数值。fragment 小于 input，就说明设备会分片。

3. 冷启动（完全关机再开机）测试触控板：
   - probe 多约 1 秒是正常的：上电前先断电 0.5 秒，再加稳压器 0.5 秒的启动延时（0005 的 `startup-delay-us`）。
   - 不应出现 `No reset response after power on`。如果出现，把前后日志发回。

4. 复现"快速点击后停顿"，同时开着：

   ```sh
   journalctl -kf | grep -E 'Device-initiated reset|recreating|Unresponsive|exceeds body|partial report'
   ```

   - 停顿时如果出现 `Device-initiated reset N`，说明之前的停顿确实是设备自发复位。触控板应在一两秒内由 iptsd 恢复。
   - `cat /sys/bus/spi/devices/spi*/device_initiated_reset_count` 应随之增加。

5. 0013–0017 的额外检查（`sl7.20260927.2` 起）：

   ```sh
   journalctl -k -b | grep -E 'FIFO_IF_DISABLE|Unsupported version'
   cat /sys/bus/spi/devices/spi*/irq_reread_count
   sudo grep -E '^ ?gpio(40|41|42|43|49|50|66|67|76|77|78|79) ' /sys/kernel/debug/gpio
   ```

   - 每个 QSPI 控制器一行 `QSPI GENI_IF_DISABLE_RO FIFO_IF_DISABLE=N`，请把 N 发回：它决定要不要像 Windows 那样跳过 GPI 寄存器设置。
   - 不应出现 `Unsupported version`。
   - 触摸屏（`spi1.0`）的 `irq_reread_count` 大于 0，说明确实出现过读取期间又有新报告的情况；触控板是电平中断，恒为 0。
   - 引脚应显示 `pull down`；gpio40–43、49、50 为 4mA，其余 6mA。

6. 回归检查：
   - 触控板：移动、物理点击、轻触、双指滚动。
   - 触摸屏。
   - 熄屏后解锁（触摸屏跟随面板上下电）。
   - deep 睡眠 3 轮。

## 回退

- 在 GRUB 高级选项里选择上一个 SL7 内核即可。
- 只想关闭 0008 的新行为时，写入 `/etc/modprobe.d/spi-hid.conf`：

  ```
  options spi_hid reset_recovery=0
  ```
- 触控板或触摸屏在 `sl7.20260927.2` 上失灵、而 `.1` 正常时，先怀疑 0017（引脚电气设置）：从 `patches/series` 里去掉这一行重新构建即可，其余补丁不依赖它。

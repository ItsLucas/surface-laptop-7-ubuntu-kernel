# SPI HID 与 Windows 对齐：0007–0012 实机验收（2026-09-27）

这组补丁只改 `drivers/hid/spi-hid/`（触控板和触摸屏共用的传输驱动），依据是本机 Windows `hidspi.sys`、`HidSpiCx.sys`（微软公开符号）和 `qcspi8380.sys` 的静态分析。尚未在实机验证。

| 补丁 | 问题 | Windows 做法 |
|---|---|---|
| 0007 | 报告体内的 content length 未与报文长度比对，可越界读 8 KiB 缓冲；多分片报告被当成多个完整报告 | `ProcessBody` 校验长度；分片累积，1 秒超时 |
| 0008 | 用 `completion_done()` 判断是否有请求在等，设备自发复位被吞掉，`device_initiated_reset_count` 永远为 0 | `VerifyResetResponse` → `EvtDeviceReset` 通知上层重新配置 |
| 0009 | GET/SET_FEATURE 解锁后才读响应，并发请求可覆盖 | — |
| 0010 | 输出报告长度未按 4 字节对齐 | `SendWriteToBus` 补零到 4 的倍数 |
| 0011 | 触控板供电由固件打开且 boot-on，驱动从未真正断电；无复位响应的设备永远不会被枚举或重试 | ACPI `_PS3/_PS0`；启动时复位后有 2 秒定时器 |
| 0012 | 除 -ENODEV 外的供电错误都变成无限 -EPROBE_DEFER | — |

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
   modinfo spi_hid | grep -i version            # sl7.20260927.1
   ```

2. 查看两个设备的描述符：

   ```sh
   journalctl -k -b | grep -E 'HID-SPI|spi_hid|spi-hid'
   ```

   - 应各有一行 `HID-SPI 045e:0c77 ...`（触控板）和 `045e:0c6f ...`（触摸屏）。
   - 请记下 `input / output / fragment` 三个数值。fragment 小于 input，就说明设备会分片。

3. 冷启动（完全关机再开机）测试触控板：
   - probe 多约 0.5 秒是正常的，这是上电前先断电。
   - 不应出现 `No reset response after power on`。如果出现，把前后日志发回。

4. 复现"快速点击后停顿"，同时开着：

   ```sh
   journalctl -kf | grep -E 'Device-initiated reset|recreating|Unresponsive|exceeds body|partial report'
   ```

   - 停顿时如果出现 `Device-initiated reset N`，说明之前的停顿确实是设备自发复位。触控板应在一两秒内由 iptsd 恢复。
   - `cat /sys/bus/spi/devices/spi*/device_initiated_reset_count` 应随之增加。

5. 回归检查：
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

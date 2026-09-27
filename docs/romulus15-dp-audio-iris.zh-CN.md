# DisplayPort 音频与 Iris 视频编解码：0018–0019 实机验收（2026-09-27）

两个补丁都只改 `x1e80100-microsoft-romulus15.dts`，做法与 Surface Pro 11（同为 X1E）的对应补丁一致。尚未在实机验证。

| 补丁 | 改动 | 依据 |
|---|---|---|
| 0018 | 声卡加 DisplayPort0/1 两条 DAI 链路（两个 USB-C 口） | Romulus 拓扑已有 `DISPLAY_PORT_RX_0/1` 后端和混音器；本机使用的 UCM（与 ThinkPad T14s 共用）已有 HDMI0/HDMI1 设备，只缺机器驱动创建的 `DP0 Jack`/`DP1 Jack` |
| 0019 | 启用 `video-codec@aa00000`，固件为 `qcom/x1e80100/microsoft/Romulus/qcvss8380.mbn` | SP11 同样用 Windows 驱动里微软签名的 `qcvss8380.mbn` |

## Iris 固件（必须先装）

固件要微软签名，只能从 Windows 取。本机 Windows 分区启用了 BitLocker，Linux 下读不到，所以请在 Windows 里找出文件：

```powershell
Get-ChildItem C:\Windows\System32\DriverStore\FileRepository -Recurse -Filter qcvss8380.mbn
```

复制到 Linux，放在已有的 ADSP/CDSP 固件旁边：

```sh
sudo install -m 0644 qcvss8380.mbn /lib/firmware/updates/qcom/x1e80100/microsoft/Romulus/
```

没有这个文件也能启动：Iris 在第一次打开设备时才加载固件，缺文件时只是打开失败，内核日志里有 `Direct firmware load ... failed`。

## 验收步骤

1. Iris：

   ```sh
   journalctl -k -b | grep -i iris
   v4l2-ctl --list-devices                       # 应有 qcom-iris 解码器和编码器
   ```

   用硬件解码播放一段 H.264 视频（例如 `gst-launch-1.0 playbin uri=file:///path/to/video.mp4`，或 mpv `--hwdec=v4l2m2m-copy`），确认没有 `firmware` 或 `sys error` 报错。

2. DisplayPort 音频：先在两个 USB-C 口各接一次显示器。

   ```sh
   amixer -c0 controls | grep 'DP[01] Jack'      # 应有两行
   ```

   - 声音设置里应出现 HDMI / DisplayPort 输出，切过去播放声音。
   - 拔掉显示器后，输出应回到扬声器或耳机。
   - 左右两个口都要测。

## 回退

- 在 GRUB 里选上一个 SL7 内核即可。
- 只去掉 0019（Iris）时，从 `patches/series` 删掉该行重新构建即可。0019 的补丁上下文接在 0018 追加的内容后面，所以只去掉 0018 时需要重新生成 0019。

# Redmi Note 7 专用系统

## 已验证的硬件范围

实际机型为 **Redmi Note 7，代号 lavender**，不是其他同名或相近 Redmi 产品。原系统 MIUI 12.5.7 / Android 10，RAM 6 GB，屏幕 1080×2340。定制基线是 LineageOS 18.1 / Android 11 `userdebug`。

这是一套旧分支工程测试系统，使用工程签名；不等同于维护中的安全日用 ROM。不得把这套镜像直接刷入其他机型，也不要在刷入后重新锁定 Bootloader。

## 环境与源码

工程使用 Windows + WSL2 Ubuntu 22.04，专用用户 `rembuild`，Android 源码放在 Linux ext4 文件系统，宿主 D 盘存放 WSL 磁盘。实测为 16 GB 内存、16 GB swap、4 个构建任务。建议准备约 300 GB 可用空间并留余量；实际占用取决于源码、产物和缓存。

`scripts/initialize-source-manifest.sh` 初始化 Lineage 分支；`manifests/rem-lavender.xml` 固定设备树；`patches/resolved-source-manifest.xml` 记录本次解析后的上游提交。下载工具 [git-repo](https://gerrit.googlesource.com/git-repo) 和 Android/Lineage 构建依赖后，按官方环境要求安装 OpenJDK、编译器、Git LFS 等依赖。

本工程脚本默认 `/home/rembuild/android/lineage`，主要 Python 脚本和 `build-rem.sh` 可用 `REM_ANDROID_TREE` 覆盖。部分历史守护脚本仍面向 WSL 的 `/mnt/c`、`/mnt/d` 和专用用户；迁移环境需先审阅路径与磁盘检查，不能直接照抄运行。

| 源码 | 固定提交 |
| --- | --- |
| LineageOS/android_device_xiaomi_lavender | `8d0e035cb03683baba0a54b86f5c8977890721c4` |
| LineageOS/android_device_xiaomi_sdm660-common | `985b95d82172bc2b363ee3beec97669a2eba2a8b` |
| LineageOS/android_kernel_xiaomi_sdm660 | `2e69f2ae550dcfbde1ffb6daa11492762b122191` |
| LineageOS/android_hardware_xiaomi | `a1633051c96997aea4c00dbdef7c734b1d4f8a9d` |
| the-muppets/proprietary_vendor_xiaomi | `5ef13fcc9aad481069a58e5a1dc945ee0c31f270`，仅 lavender / sdm660-common |

源码曾有 867 个项目；项目数不是字节数。断点续传保留已完成的 Git 对象，源码百分比与 Ninja 编译百分比也不是同一指标。守护脚本保留低空间停止、锁、进度状态和可恢复逻辑。

## 厂商文件与产品导入

厂商二进制不随仓库发布。自行准备固定版本的 scoped vendor archive，使用 `verify-vendor-archive.py` 对照 `proprietary-files*.txt` 校验。未带上游 hash 的条目只能确认存在；不应描述为全部经过 hash 验证。旧归档中的差异需要固定字节替换并重新验证，不能直接放宽 hash。

相关脚本会读取本机 `evidence/` 校验收据；这些收据不公开，也不能拿别人的收据冒充自己的验证。`install-verified-vendor.py` 只有在当前收据与文件匹配后才安装到源码树。

在手机系统目录准备外部形象和视觉依赖（下一篇），然后依次审阅和运行：

```bash
mkdir -p rem-phone-system/evidence
python3 rem-phone-system/scripts/import-rem-product.py
python3 rem-phone-system/scripts/fix-qti-bluetooth-headers.py
python3 rem-phone-system/scripts/fix-first-boot-integration.py
# 先准备已验证的厂商归档，再运行摄像头修复：
python3 rem-phone-system/scripts/fix-camera-runtime.py
bash rem-phone-system/scripts/build-rem.sh
```

这些修复是对固定上游代码的定向处理；如果匹配条件不成立，应检查版本，不要跳过检查。`import-rem-product.py` 会修改构建产品和 Quickstep HOME 声明。构建目标为 `rem_lavender-userdebug`，完整 OTA 使用 `m bacon`。

## 三项关键修复

**蓝牙编译头文件。** QTI 蓝牙需要 Android `system/bt/main/shim/dumpsys.h`，修复 include 路径，保留原日志脱敏和加密逻辑。对应补丁 `qti-bluetooth-shim-header.patch`。

**桌面反复崩溃。** RemBody 接管 HOME 后，Quickstep 仍假设自身有 HOME Activity。保留最近任务服务，移除竞争 HOME 声明，并对空 ResolveInfo 与 `mHasOwnHome` 做处理，回退 `RecentsActivity`。对应两份 `rem-*home*.patch`。

**启动和相机。** DTBO 需要与原厂设备匹配的 overlay；增量构建还需显式 DTBO 依赖，防止 OTA 混入旧产物。后摄像头 XML 曾引用不存在的 HFR 240 tuning 库，使用经核对的成对 XML 配置，并校验 89 个库引用。没有靠关闭 SELinux 修复。

## 解锁与安装流程

本工程先由机主用小米官方工具绑定账号/SIM、完成 Bootloader 解锁并清空数据。复现者要独立完成厂商允许的解锁流程；本仓库不提供解锁绕过。

刷写前核对：USB 唯一目标、`lavender`、解锁状态、电量、boot/recovery/dtbo/vbmeta 与 OTA 来自同一验证批次，以及可用的原厂恢复文件。先验证 Recovery 能启动，再格式化数据和 ADB sideload 安装 OTA；不要把不同批次镜像拼在一起。

`scripts/install-first-boot-fix.py` 保留了本项目的修复包门禁（USB 身份 hash、6 小时有效期、产物 hash、Recovery 安装结果、分区回读）。它依赖本地生成的 `artifact-manifest.json` 和本机收据，**不是首次安装的一键命令**。离线测试只测试门禁，不执行刷写。

Recovery 中 `Apply update → Apply from ADB` 等待传输；传输退出码不足以证明安装成功，还需核对 Recovery 的 `/tmp/last_install` 和产物一致性。成功后 `Reboot system now`，完成初始化并授权 USB 调试，检查开机 HOME、录音回放、前后摄像头。

## 后续组件更新

```bash
REM_BUILD_TARGET=RemBody bash rem-phone-system/scripts/build-rem.sh
```

同包名 `com.rem.body`、同签名更新可保留配置；内核、DTBO 和厂商驱动变更仍需要相应镜像或 OTA。当前手机基础 ROM 安装后，视觉和对话功能通过后续同签名组件更新到了 v37。早期留存 ROM 不自动包含这些后续更新；公开源码包含后续实现，重新构建前仍需补齐外部资源。

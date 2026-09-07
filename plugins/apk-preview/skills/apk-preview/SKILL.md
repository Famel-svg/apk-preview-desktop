---
name: apk-preview
description: Run, inspect, navigate, and visually compare Android APKs in a dedicated local emulator.
---

# APK Preview

1. Call `apk_preview_doctor` before first device action.
2. Use only AVDs returned by `apk_preview_list_avds`.
3. Start visible session unless user requests headless execution.
4. Install only APK path explicitly supplied or created inside current workspace.
5. Launch package from `apk_preview_list_apps`.
6. Call `apk_preview_inspect_screen` after install, launch, display change, or interaction.
7. Use current screenshot coordinates only; refresh before another coordinate action.
8. Never attempt physical device, AVD deletion, data wipe, credentials, or real personal data.
9. For responsive review, compare `phone_compact`, `phone_standard`, and `tablet`.
10. Stop session only when user requests it or task explicitly requires cleanup.

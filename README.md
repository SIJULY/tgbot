# Cloud Manager Panel Telegram Bot

> 专为 Cloud Manager 三合一面板设计的配套 Telegram 机器人，让您随时随地通过手机轻松管理您的云端资源。

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-v6.x-blue.svg)](https://core.telegram.org/bots/api)

这是一个功能强大、交互友好的 Telegram 机器人，它通过 API 与您的 Cloud Manager 面板进行通信，实现了对 OCI (Oracle Cloud Infrastructure) 账户及其实例的全面管理。

## ✨ 主要功能

-   **多账户管理**：自动从您的面板加载所有已配置的 OCI 账户，通过按钮清晰地在多个账户间切换操作。

-   **全面的实例操作**：
    -   **基础控制**：✅ 开机、🛑 关机、🔄 重启、🗑️ 终止实例。
    -   **网络管理**：一键更换公网 IP (IPv4)、分配 IPv6 地址。
    -   **实例选择**：清晰列出账户下的所有实例及其当前状态，方便您选择要操作的目标。

-   **交互式实例创建 (纯按钮操作)**：
    -   **自动命名**：无需手动输入，机器人会自动以 `instance-月日-时分` 的格式生成实例名称。
    -   **规格选择**：通过点击按钮，轻松选择 ARM / AMD 规格。
    -   **参数配置**：通过按钮交互式选择 OCPU 核心数、内存大小、磁盘容量。
    -   **流程引导**：整个过程由机器人引导，清晰明了。

-   **强大的自动抢占实例功能**：
    -   与创建实例共享同一套友好、便捷的按钮式交互流程。
    -   提交任务后，机器人会驱动面板后台进行**持续循环尝试**，直到成功创建实例。

-   **异步任务与状态通知**：
    -   所有耗时操作（如开机、创建、抢占）均作为后台任务提交，机器人会立即响应。
    -   任务完成后（无论成功或失败），机器人会**主动发送消息通知**您任务结果，无需您反复查询。
    -   可以随时在机器人上查看“正在运行”和“已完成”的任务列表。

-   **安全与易用性**：
    -   **权限控制**：通过 `AUTHORIZED_USER_IDS` 配置，确保只有您授权的用户才能操作机器人。
    -   **便捷入口**：在 Telegram 对话框的菜单中内置 `/start` 命令，随时一键唤出主菜单。
    -   **流畅体验**：在执行完一项主要操作后（如提交创建任务），机器人会自动返回上一级菜单，方便您继续操作。

## 📸 界面截图



| 主菜单 (账户选择) | 账户功能菜单 |
| :---: | :---: |
| <img width="599" height="244" alt="image" src="https://github.com/user-attachments/assets/05c89275-328d-4c5d-8dee-5ea0bda2f65d" />| <img width="614" height="286" alt="image" src="https://github.com/user-attachments/assets/42b3c0cb-8049-4f57-bdc0-0a4f6d8f4359" />|
| **实例操作菜单** | **参数选择界面** |
| <img width="614" height="246" alt="image" src="https://github.com/user-attachments/assets/c16f7f81-8492-4573-b7a3-fb5450eba33e" /> | <img width="314" height="376" alt="image" src="https://github.com/user-attachments/assets/0a3891d9-9b75-49c1-8afb-78884cca504c" /> |


## 🚀 一键安装

本项目支持一键部署。只需在您的服务器上（推荐 Debian / Ubuntu 系统）运行以下单行命令，即可根据引导完成所有安装和配置。

```bash
bash <(curl -sL https://raw.githubusercontent.com/SIJULY/tgbot/main/install_tgbot.sh)
```

脚本将自动处理 Python 环境、程序文件、依赖库以及 `systemd` 后台服务。

## 📖 使用说明

1.  在 Telegram 中找到您创建的机器人。
2.  发送 `/start` 命令，或直接点击输入框左下角的 **☰ 菜单** 按钮。
3.  根据菜单提示开始操作。

## 🛠️ 配置

在执行一键安装脚本时，您需要提供以下四项信息：

1.  `PANEL_URL`: 您的 Cloud Manager 面板的访问地址 (例如: `https://xxx.com`)。
2.  `PANEL_API_KEY`: 在您的面板“TG & API 设置”中获取的“TG Bot 助手 API 密钥”。
3.  `BOT_TOKEN`: 您从 BotFather 获取的 Telegram 机器人 TOKEN。
4.  `AUTHORIZED_USER_IDS`: 您的个人 Telegram 用户 ID (纯数字)，用于授权。

安装完成后，所有配置信息将保存在 `/opt/tgbot/bot.py` 文件中，您可以随时修改并重启服务。

---

希望这份文档能帮助您更好地了解和使用这个项目！

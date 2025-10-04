#!/bin/bash

#=================================================
#	System Required: Debian/Ubuntu
#	Description: One-click script to install a standalone Cloud Manager Telegram Bot
#	Author: Gemini
#=================================================

set -e

# --- Color codes ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# --- Variables ---
BOT_PY_URL="https://raw.githubusercontent.com/sijuly/main/bot.py"
INSTALL_DIR="/opt/tgbot"

# --- Check for root privileges ---
if [ "$(id -u)" != "0" ]; then
   echo -e "${RED}错误：此脚本必须以 root 权限运行。${NC}"
   echo -e "${YELLOW}请尝试使用 'sudo ./install_tgbot.sh'${NC}"
   exit 1
fi

echo -e "${GREEN}=====================================================${NC}"
echo -e "${GREEN}  独立的 Cloud Manager Telegram Bot 安装脚本...${NC}"
echo -e "${GREEN}=====================================================${NC}"

# --- 1. 收集用户输入 ---
echo -e "\n${YELLOW}请根据提示输入您的配置信息 (这些信息可以从您的面板获取):${NC}"
read -p "➡️ 请输入您的面板URL (例如: https://xxxxx.com): " PANEL_URL
read -p "➡️ 请输入您的面板API密钥 (TG Bot 助手 API 密钥): " PANEL_API_KEY
read -p "➡️ 请输入您的Telegram机器人TOKEN: " BOT_TOKEN
read -p "➡️ 请输入您的Telegram用户ID (纯数字): " AUTHORIZED_USER_IDS

# --- 2. 安装系统依赖 ---
echo -e "\n${GREEN}正在更新软件包列表并安装依赖 (python3, pip, venv, wget)...${NC}"
apt-get update > /dev/null
# 确保 wget 已安装，用于下载文件
apt-get install -y python3 python3-pip python3-venv wget

# --- 3. 创建安装目录和虚拟环境 ---
echo -e "\n${GREEN}将在 ${INSTALL_DIR} 目录中安装机器人...${NC}"
mkdir -p $INSTALL_DIR
echo -e "${GREEN}正在创建 Python 虚拟环境...${NC}"
python3 -m venv ${INSTALL_DIR}/venv

# --- 4. 下载 bot.py 文件 ---
echo -e "\n${GREEN}正在从 GitHub 下载 bot.py 文件...${NC}"
wget -O ${INSTALL_DIR}/bot.py $BOT_PY_URL
if [ $? -ne 0 ]; then
    echo -e "${RED}错误：下载 bot.py 文件失败。请检查您的网络或 GitHub 链接是否正确。${NC}"
    exit 1
fi

# --- 5. 替换配置文件中的占位符 ---
echo -e "${GREEN}正在根据您的输入配置 bot.py 文件...${NC}"
# 使用 sed 命令查找并替换文件中的占位符
# 注意：为了处理URL中的特殊字符'/'，我们使用'|'作为sed的分隔符
sed -i "s|PANEL_URL = \".*\"|PANEL_URL = \"${PANEL_URL}\"|" ${INSTALL_DIR}/bot.py
sed -i "s|PANEL_API_KEY = \".*\"|PANEL_API_KEY = \"${PANEL_API_KEY}\"|" ${INSTALL_DIR}/bot.py
sed -i "s|BOT_TOKEN = \".*\"|BOT_TOKEN = \"${BOT_TOKEN}\"|" ${INSTALL_DIR}/bot.py
sed -i "s|AUTHORIZED_USER_IDS = \[.*\]|AUTHORIZED_USER_IDS = [${AUTHORIZED_USER_IDS}]|" ${INSTALL_DIR}/bot.py

echo -e "${GREEN}配置文件写入成功！${NC}"

# --- 6. 安装 Python 依赖 ---
echo -e "\n${GREEN}正在虚拟环境中安装所需的 Python 库...${NC}"
# 激活虚拟环境并安装库
source ${INSTALL_DIR}/venv/bin/activate
pip install python-telegram-bot httpx

# --- 7. 创建 systemd 服务文件 ---
echo -e "\n${GREEN}正在创建并配置 systemd 服务...${NC}"
cat << EOF > /etc/systemd/system/tgbot.service
[Unit]
Description=Telegram Bot for Cloud Manager
After=network.target

[Service]
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# --- 8. 启动并设置开机自启 ---
echo -e "${GREEN}正在重载 systemd 并启动 tgbot 服务...${NC}"
systemctl daemon-reload
systemctl enable tgbot
systemctl start tgbot

# --- 9. 显示最终信息 ---
echo -e "\n${GREEN}======================================================${NC}"
echo -e "${GREEN}🎉 Telegram Bot 已成功安装并启动！${NC}"
echo -e "${GREEN}======================================================${NC}"
echo -e "\n${YELLOW}您可以使用以下命令来管理您的机器人服务：${NC}"
echo -e "  - 查看状态: ${GREEN}systemctl status tgbot${NC}"
echo -e "  - 启动服务: ${GREEN}systemctl start tgbot${NC}"
echo -e "  - 停止服务: ${GREEN}systemctl stop tgbot${NC}"
echo -e "  - 重启服务: ${GREEN}systemctl restart tgbot${NC}"
echo -e "  - 查看实时日志: ${GREEN}journalctl -u tgbot -f --no-pager${NC}"
echo -e "\n${YELLOW}配置文件位于: ${GREEN}${INSTALL_DIR}/bot.py${NC}"
echo -e "如果需要修改配置，请编辑该文件后，使用 'systemctl restart tgbot' 重启服务。"
echo -e "\n现在您可以去 Telegram 和您的机器人对话了！"

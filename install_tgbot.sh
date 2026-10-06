#!/bin/bash

#=================================================
#   System Required: Debian/Ubuntu
#   Description: Cloud Manager Telegram Bot 管理脚本 (安装/卸载)
#   作者: 小龙女她爸
#=================================================

# --- Color codes ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# --- Variables ---
BOT_PY_URL="https://raw.githubusercontent.com/sijuly/tgbot/main/bot.py"
INSTALL_DIR="/opt/tgbot"
SERVICE_FILE="/etc/systemd/system/tgbot.service"

# --- Check for root privileges ---
if [ "$(id -u)" != "0" ]; then
   echo -e "${RED}错误：此脚本必须以 root 权限运行。${NC}"
   echo -e "${YELLOW}请尝试使用 'sudo bash $0'${NC}"
   exit 1
fi

# ==========================================
# 函数: 安装逻辑
# ==========================================
install_bot() {
    echo -e "${GREEN}=====================================================${NC}"
    echo -e "${GREEN}  开始安装 Cloud Manager Telegram Bot...${NC}"
    echo -e "${GREEN}=====================================================${NC}"

    # 1. 收集用户输入
    echo -e "\n${YELLOW}请根据提示输入您的配置信息 (这些信息可以从您的面板获取):${NC}"
    read -p "➡️ 请输入您的面板URL (例如: https://xxxxx.com): " PANEL_URL
    read -p "➡️ 请输入您的面板API密钥 (TG Bot 助手 API 密钥): " PANEL_API_KEY
    read -s -p "➡️ 请输入您的Telegram机器人TOKEN: " BOT_TOKEN
    echo
    read -p "➡️ 请输入您的Telegram用户ID (纯数字): " AUTHORIZED_USER_IDS

    # 2. 安装系统依赖
    echo -e "\n${GREEN}正在更新软件包列表并安装依赖 (python3, pip, venv, wget)...${NC}"
    apt-get update > /dev/null
    apt-get install -y python3 python3-pip python3-venv wget

    # 3. 创建安装目录和虚拟环境
    echo -e "\n${GREEN}将在 ${INSTALL_DIR} 目录中安装机器人...${NC}"
    mkdir -p $INSTALL_DIR
    echo -e "${GREEN}正在创建 Python 虚拟环境...${NC}"
    python3 -m venv ${INSTALL_DIR}/venv

    # 4. 下载 bot.py 文件
    echo -e "\n${GREEN}正在从 GitHub 下载 bot.py 文件...${NC}"
    wget -O ${INSTALL_DIR}/bot.py $BOT_PY_URL
    if [ $? -ne 0 ]; then
        echo -e "${RED}错误：下载 bot.py 文件失败。请检查您的网络或 GitHub 链接是否正确。${NC}"
        exit 1
    fi

    # 5. 替换配置文件中的占位符
    echo -e "${GREEN}正在根据您的输入配置 bot.py 文件...${NC}"
    sed -i "s|PANEL_URL = \".*\"|PANEL_URL = \"${PANEL_URL}\"|" ${INSTALL_DIR}/bot.py
    sed -i "s|PANEL_API_KEY = \".*\"|PANEL_API_KEY = \"${PANEL_API_KEY}\"|" ${INSTALL_DIR}/bot.py
    sed -i "s|BOT_TOKEN = \".*\"|BOT_TOKEN = \"${BOT_TOKEN}\"|" ${INSTALL_DIR}/bot.py
    sed -i "s|AUTHORIZED_USER_IDS = \[.*\]|AUTHORIZED_USER_IDS = [${AUTHORIZED_USER_IDS}]|" ${INSTALL_DIR}/bot.py
    echo -e "${GREEN}配置文件写入成功！${NC}"

    # 6. 安装 Python 依赖
    echo -e "\n${GREEN}正在虚拟环境中安装所需的 Python 库...${NC}"
    source ${INSTALL_DIR}/venv/bin/activate
    pip install python-telegram-bot httpx

    # 7. 创建 systemd 服务文件
    echo -e "\n${GREEN}正在创建并配置 systemd 服务...${NC}"
    cat << EOF > $SERVICE_FILE
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

    # 8. 启动并设置开机自启
    echo -e "${GREEN}正在重载 systemd 并启动 tgbot 服务...${NC}"
    systemctl daemon-reload
    systemctl enable tgbot
    systemctl start tgbot

    # 9. 显示最终信息
    echo -e "\n${GREEN}======================================================${NC}"
    echo -e "${GREEN}🎉 Telegram Bot 已成功安装并启动！${NC}"
    echo -e "${GREEN}======================================================${NC}"
    echo -e "\n${YELLOW}您可以使用以下命令来管理您的机器人服务：${NC}"
    echo -e "  - 查看状态: ${GREEN}systemctl status tgbot${NC}"
    echo -e "  - 重启服务: ${GREEN}systemctl restart tgbot${NC}"
    echo -e "  - 查看日志: ${GREEN}journalctl -u tgbot -f --no-pager${NC}"
    echo -e "\n${YELLOW}提示：同一个 Telegram Bot Token 只能有一个程序使用 polling/getUpdates。${NC}"
    echo -e "${YELLOW}如果日志出现 409 Conflict，请检查是否有其他机器人实例或旧 token 仍在运行。${NC}"
}

# ==========================================
# 函数: 卸载逻辑
# ==========================================
uninstall_bot() {
    echo -e "${YELLOW}=====================================================${NC}"
    echo -e "${YELLOW}  开始卸载 Cloud Manager Telegram Bot...${NC}"
    echo -e "${YELLOW}=====================================================${NC}"
    
    echo -e "正在停止服务..."
    systemctl stop tgbot 2>/dev/null || true
    systemctl disable tgbot 2>/dev/null || true
    
    if [ -f "$SERVICE_FILE" ]; then
        echo -e "正在删除系统服务文件..."
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
    fi
    
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "正在删除安装目录及所有文件..."
        rm -rf "$INSTALL_DIR"
    fi
    
    echo -e "${GREEN}✅ 卸载完成！所有相关文件和服务已清除。${NC}"
}

# ==========================================
# 主菜单
# ==========================================
clear
echo -e "${GREEN}Cloud Manager Telegram Bot 管理脚本${NC}"
echo "-----------------------------------"
echo "  1) 安装 / 重装 Bot"
echo "  2) 卸载 Bot"
echo "  0) 退出"
echo "-----------------------------------"
read -p "请输入选项 [1-2]: " choice

case $choice in
    1)
        install_bot
        ;;
    2)
        read -p "确定要卸载吗？(y/n): " confirm
        if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
            uninstall_bot
        else
            echo "已取消。"
        fi
        ;;
    0)
        exit 0
        ;;
    *)
        echo -e "${RED}无效选项，退出。${NC}"
        exit 1
        ;;
esac

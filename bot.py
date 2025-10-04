import asyncio
import httpx
import logging
from datetime import datetime
from typing import List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

# --- 1. 配置信息 ---
PANEL_URL = "Your Panel URL Placeholder"
PANEL_API_KEY = "Your API Key Placeholder"
BOT_TOKEN = "Your Bot Token Placeholder"
AUTHORIZED_USER_IDS = [123456789] 

# --- 日志配置 ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# --- UI辅助函数 ---
def create_title_bar(title: str) -> List[InlineKeyboardButton]:
    return [InlineKeyboardButton(f"❖ {title} ❖", callback_data="ignore")]

def get_footer_ruler() -> List[InlineKeyboardButton]:
    left_button_text = "─────« Cloud"
    right_button_text = "Manager »────" 
    return [
        InlineKeyboardButton(left_button_text, callback_data="ignore"),
        InlineKeyboardButton(right_button_text, callback_data="ignore")
    ]


# --- 2. API 客户端 ---
BASE_URL = f"{PANEL_URL}/api/v1/oci"
HEADERS = {"Authorization": f"Bearer {PANEL_API_KEY}", "Content-Type": "application/json"}

async def api_request(method: str, endpoint: str, **kwargs):
    async with httpx.AsyncClient() as client:
        try:
            url = f"{BASE_URL}/{endpoint}"
            response = await client.request(method, url, headers=HEADERS, timeout=30.0, **kwargs)
            response.raise_for_status()
            if not response.content: return {}
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"API Error: {e.response.status_code} - {e.response.text}")
            try: return {"error": e.response.json().get("error", "未知API错误")}
            except: return {"error": f"API返回了非JSON错误: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return {"error": str(e)}

# --- 3. Telegram 机器人逻辑 ---
def authorized(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in AUTHORIZED_USER_IDS:
            if update.callback_query: await update.callback_query.answer("🚫 您没有权限。", show_alert=True)
            else: await update.message.reply_text("🚫 您没有权限操作此机器人。")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def poll_task_status(chat_id: int, context: ContextTypes.DEFAULT_TYPE, task_id: str, task_name: str):
    max_retries, retries = 120, 0
    while retries < max_retries:
        await asyncio.sleep(5)
        result = await api_request("GET", f"task-status/{task_id}")
        if result and result.get("status") in ["success", "failure"]:
            final_message = f"🔔 *任务完成通知*\n\n*任务名称*: `{task_name}`\n\n*结果*:\n`{result.get('result')}`"
            await context.bot.send_message(chat_id=chat_id, text=final_message, parse_mode=ParseMode.MARKDOWN)
            return
        retries += 1
    await context.bot.send_message(chat_id=chat_id, text=f"🔔 *任务超时*\n\n任务 `{task_name}` 轮询超时（超过10分钟），请在网页端查看最终结果。")

# --- 菜单构建函数 ---

# 这是您提供的、测试通过的新版本函数
async def build_param_selection_menu(form_data: dict, action_type: str, context: ContextTypes.DEFAULT_TYPE):
    shape = form_data.get('shape')
    is_flex = shape and "Flex" in shape
    text = f"⚙️ *请配置实例参数*\n*{'抢占任务' if action_type == 'start_snatch' else '创建任务'}*\n\n"
    text += f"实例名称: `{form_data.get('display_name_prefix', 'N/A')}`\n"
    # 根据您的建议，这里只显示缩写，让消息体更简洁
    text += f"实例规格: `{'ARM' if shape and 'A1.Flex' in shape else ('AMD' if shape else '尚未选择')}`\n"
    
    keyboard = [create_title_bar("参数配置")]
    all_params_selected = True
    
    if is_flex:
        ocpu_val = form_data.get('ocpus')
        text += f"OCPU: `{ocpu_val or '尚未选择'}`\n"
        keyboard.append([InlineKeyboardButton("─── 实例CPU规格 ───", callback_data="ignore")])
        options = {"1": "1 OCPU", "2": "2 OCPU", "3": "3 OCPU", "4": "4 OCPU"}
        option_buttons = [InlineKeyboardButton(f"{'✅ ' if str(ocpu_val) == k else ''}{v}", callback_data=f"form_param:ocpus:{k}") for k, v in options.items()]
        # 修改：从两行双列改为一行四列
        keyboard.append(option_buttons)
        if not ocpu_val: all_params_selected = False

    if is_flex:
        mem_val = form_data.get('memory_in_gbs')
        text += f"内存: `{f'{mem_val} GB' if mem_val else '尚未选择'}`\n"
        keyboard.append([InlineKeyboardButton("─── 实例运行内存规格 ───", callback_data="ignore")])
        options = {"6": "6 GB", "12": "12 GB", "18": "18 GB", "24": "24 GB"}
        option_buttons = [InlineKeyboardButton(f"{'✅ ' if str(mem_val) == k else ''}{v}", callback_data=f"form_param:memory_in_gbs:{k}") for k, v in options.items()]
        # 修改：从两行双列改为一行四列
        keyboard.append(option_buttons)
        if not mem_val: all_params_selected = False

    if shape:
        disk_val = form_data.get('boot_volume_size')
        text += f"磁盘大小: `{f'{disk_val} GB' if disk_val else '尚未选择'}`\n"
        keyboard.append([InlineKeyboardButton("─── 实例硬盘大小 ───", callback_data="ignore")])
        options = {"50": "50 GB", "100": "100 GB", "150": "150 GB", "200": "200 GB"}
        option_buttons = [InlineKeyboardButton(f"{'✅ ' if str(disk_val) == k else ''}{v}", callback_data=f"form_param:boot_volume_size:{k}") for k, v in options.items()]
        # 修改：从两行双列改为一行四列
        keyboard.append(option_buttons)
        if not disk_val: all_params_selected = False

    if action_type == 'start_snatch':
        text += f"重试间隔: `{form_data.get('min_delay', '45')}-{form_data.get('max_delay', '90')} 秒`"

    if all_params_selected:
        keyboard.append([InlineKeyboardButton("🚀 确认提交", callback_data="form_submit")])
        
    alias = context.user_data.get('alias')
    keyboard.append([InlineKeyboardButton("❌ 取消操作", callback_data=f"back:account:{alias}")])
    
    keyboard.append(get_footer_ruler())
    return text, InlineKeyboardMarkup(keyboard)

async def build_main_menu():
    profiles = await api_request("GET", "profiles")
    if not profiles or "error" in profiles:
        return None, f"❌ 无法从面板获取账户列表: {profiles.get('error', '未知错误') if profiles else '无响应'}"
    if not profiles:
        return None, "面板中尚未配置任何OCI账户。"

    # 按照您的新要求构建键盘
    keyboard = [
        # 1. 使用新的标题
        create_title_bar("Cloud Manager Panel Telegram Bot"),
        # 2. “查看所有任务”按钮在最上方
        [InlineKeyboardButton("📝 查看抢占实例任务", callback_data="tasks:all")],
        # 3. 增加一个分隔标题
        [InlineKeyboardButton("👇 OCI 账户选择", callback_data="ignore")]
    ]

    # 4. 添加账户列表
    for i in range(0, len(profiles), 2):
        row = [InlineKeyboardButton(profiles[i], callback_data=f"account:{profiles[i]}")]
        if i + 1 < len(profiles):
            row.append(InlineKeyboardButton(profiles[i+1], callback_data=f"account:{profiles[i+1]}"))
        keyboard.append(row)
    
    # 5. 添加页脚
    keyboard.append(get_footer_ruler())
    
    return InlineKeyboardMarkup(keyboard), "请选择要操作的 OCI 账户:"

async def build_account_menu(alias: str):
    # 最终修正：移除此处的“查看任务”按钮
    keyboard = [
        create_title_bar(f"账户: {alias}"),
        [InlineKeyboardButton("🖥️ 实例操作", callback_data=f"menu:instances:{alias}")],
        [InlineKeyboardButton("➕ 创建实例", callback_data=f"start_create:{alias}"), InlineKeyboardButton("🤖 抢占实例", callback_data=f"start_snatch:{alias}")],
        [InlineKeyboardButton("⬅️ 返回主菜单", callback_data=f"back:main")]
    ]
    keyboard.append(get_footer_ruler())
    return InlineKeyboardMarkup(keyboard), f"已选择账户: *{alias}*\n请选择功能模块:"

async def build_instance_action_menu(alias: str):
    keyboard = [
        create_title_bar("实例操作"),
        [InlineKeyboardButton("✅ 开机", callback_data=f"action:{alias}:START"), InlineKeyboardButton("🛑 关机", callback_data=f"action:{alias}:STOP")],
        [InlineKeyboardButton("🔄 重启", callback_data=f"action:{alias}:RESTART"), InlineKeyboardButton("🗑️ 终止", callback_data=f"action:{alias}:TERMINATE")],
        [InlineKeyboardButton("🌐 更换IP", callback_data=f"action:{alias}:CHANGEIP"), InlineKeyboardButton("🌐 分配IPv6", callback_data=f"action:{alias}:ASSIGNIPV6")],
        [InlineKeyboardButton("⬅️ 返回", callback_data=f"back:account:{alias}")],
    ]
    keyboard.append(get_footer_ruler())
    return InlineKeyboardMarkup(keyboard), f"请为账户 *{alias}* 选择实例操作类型:"

async def build_instance_selection_menu(alias: str, action: str, context: ContextTypes.DEFAULT_TYPE):
    instances = await api_request("GET", f"{alias}/instances")
    if not instances or "error" in instances: return None, f"..."
    if not instances: return None, f"..."
    context.user_data['instance_list'] = instances
    keyboard = [create_title_bar("选择实例")]
    for index, inst in enumerate(instances):
        display_text = f"{inst['display_name']} ({inst['lifecycle_state']})"
        keyboard.append([InlineKeyboardButton(display_text, callback_data=f"exec:{index}")])
    keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data=f"back:instances:{alias}")])
    keyboard.append(get_footer_ruler())
    return InlineKeyboardMarkup(keyboard), f"请选择要执行 *{action}* 操作的实例:"

async def build_task_menu():
    """全局任务查询菜单"""
    keyboard = [
        create_title_bar("任务查询"),
        [InlineKeyboardButton("🏃 查看运行中的任务", callback_data="tasks:view:snatch:running")],
        [InlineKeyboardButton("✅ 查看已完成的任务", callback_data=f"tasks:view:snatch:completed")],
        [InlineKeyboardButton("⬅️ 返回主菜单", callback_data="back:main")],
    ]
    keyboard.append(get_footer_ruler())
    return InlineKeyboardMarkup(keyboard), f"请选择要查看的任务类型:"

@authorized
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    reply_markup, text = await build_main_menu()
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

@authorized
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "ignore":
        return

    parts = query.data.split(":")
    command = parts[0]
    
    if command == "start_create" or command == "start_snatch":
        alias = parts[1]
        context.user_data.clear()
        context.user_data['action_in_progress'] = command
        context.user_data['alias'] = alias
        prefix = "instance" if command == "start_create" else "snatch"
        timestamp = datetime.now().strftime("%m%d-%H%M")
        auto_name = f"{prefix}-{timestamp}"
        context.user_data['form_data'] = {'display_name_prefix': auto_name, 'shape': 'VM.Standard.A1.Flex'}
        text, reply_markup = await build_param_selection_menu(context.user_data['form_data'], command, context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return
        
    if command == "form_param":
        key, value = parts[1], parts[2]
        context.user_data['form_data'][key] = value
        if key == 'shape':
            context.user_data['form_data'].pop('ocpus', None)
            context.user_data['form_data'].pop('memory_in_gbs', None)
        action_type = context.user_data['action_in_progress']
        text, reply_markup = await build_param_selection_menu(context.user_data['form_data'], action_type, context)
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except BadRequest as e:
            if "Message is not modified" not in str(e): raise e
        return

    if command == "form_submit":
        await submit_form(update, context, context.user_data.get('form_data', {}))
        return

    if command == "account":
        alias = parts[1]
        context.user_data['current_alias'] = alias
        reply_markup, text = await build_account_menu(alias)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    elif command == "menu":
        menu_type, alias = parts[1], parts[2]
        if menu_type == "instances":
            reply_markup, text = await build_instance_action_menu(alias)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        # 移除了 menu:tasks 的处理逻辑
    elif command == "action":
        alias, action = parts[1], parts[2]
        context.user_data['current_alias'] = alias
        context.user_data['current_action'] = action
        await query.edit_message_text(text=f"正在为账户 *{alias}* 获取实例列表...", parse_mode=ParseMode.MARKDOWN)
        reply_markup, text = await build_instance_selection_menu(alias, action, context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    elif command == "exec":
        alias = context.user_data.get('current_alias')
        action = context.user_data.get('current_action')
        instance_list = context.user_data.get('instance_list')
        if not all([alias, action, instance_list]):
            await query.edit_message_text("会话已过期或信息不完整...", reply_markup=None)
            return
        instance_index = int(parts[1])
        selected_instance = instance_list[instance_index]
        instance_id = selected_instance['id']
        vnic_id = selected_instance.get('vnic_id')
        await query.edit_message_text(text=f"正在为实例 *{selected_instance['display_name']}* 发送 *{action}* 命令...", parse_mode=ParseMode.MARKDOWN)
        payload = {"action": action, "instance_id": instance_id, "instance_name": selected_instance['display_name']}
        if vnic_id: payload['vnic_id'] = vnic_id
        result = await api_request("POST", f"{alias}/instance-action", json=payload)
        
        keyboard = [
            create_title_bar("命令结果"),
            [InlineKeyboardButton("⬅️ 返回账户菜单", callback_data=f"back:account:{alias}")],
            get_footer_ruler()
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if result and result.get("task_id"):
            task_id = result.get("task_id")
            task_name = f"{action} on {selected_instance['display_name']}"
            text = f"✅ 命令发送成功！\n任务ID: `{task_id}`\n\n机器人将在后台为您监控任务，完成后会主动通知您。"
            asyncio.create_task(poll_task_status(update.effective_chat.id, context, task_id, task_name))
        else:
            text = f"❌ 命令发送失败: {result.get('error', '未知错误')}"
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        context.user_data.pop('instance_list', None)
        context.user_data.pop('current_action', None)
    
    elif command == "tasks":
        if parts[1] == 'all':
            reply_markup, text = await build_task_menu()
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        elif parts[1] == 'view':
            task_type, task_status = parts[2], parts[3]
            status_text = "运行中" if task_status == "running" else "已完成"
            await query.edit_message_text(text=f"正在查询所有账户 *{status_text}* 的 *{task_type}* 任务...", parse_mode=ParseMode.MARKDOWN)
            
            tasks = await api_request("GET", f"tasks/{task_type}/{task_status}")
            
            keyboard = [
                create_title_bar("所有任务列表"),
                [InlineKeyboardButton("⬅️ 返回", callback_data="tasks:all")],
                get_footer_ruler()
            ]
            back_keyboard = InlineKeyboardMarkup(keyboard)

            if not tasks or "error" in tasks:
                await query.edit_message_text(text=f"❌ 查询任务失败: {tasks.get('error', '未知错误')}", reply_markup=back_keyboard)
                return
            
            text = f"所有账户 *{status_text}* 的 *{task_type}* 任务:\n\n"
            if not tasks:
                text += "没有找到相关任务记录。"
            else:
                for task in tasks[:10]:
                    status_icon = ""
                    if task_status == 'completed':
                        status_icon = "✅" if task.get("status") == "success" else "❌"
                    task_alias = task.get('alias', 'N/A')
                    text += f"*{task.get('name')}* (账户: {task_alias}) {status_icon}:\n`{task.get('result', '无结果')}`\n\n"
            await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

    elif command == "back":
        target = parts[1]
        alias = parts[2] if len(parts) > 2 else context.user_data.get('alias')
        if target == "main":
            await start_command(update, context)
        elif target == "account":
            context.user_data.clear()
            reply_markup, text = await build_account_menu(alias)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        elif target == "instances":
            reply_markup, text = await build_instance_action_menu(alias)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def submit_form(update: Update, context: ContextTypes.DEFAULT_TYPE, form_data: dict):
    action_type = context.user_data.get('action_in_progress')
    alias = context.user_data.get('alias')
    form_data.setdefault('min_delay', 45)
    form_data.setdefault('max_delay', 90)
    payload = form_data.copy()
    numeric_keys = ['ocpus', 'memory_in_gbs', 'boot_volume_size', 'min_delay', 'max_delay']
    for key in numeric_keys:
        if key in payload:
            try:
                if key in ['ocpus', 'memory_in_gbs']: payload[key] = float(payload[key])
                else: payload[key] = int(payload[key])
            except (ValueError, TypeError):
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ 参数 {key} 的值 `{payload[key]}` 无效。")
                return
    payload.setdefault('os_name_version', 'Canonical Ubuntu-22.04')
    endpoint = "create-instance" if action_type == "start_create" else "snatch-instance"
    await update.callback_query.edit_message_text(f"正在提交任务...", parse_mode=ParseMode.MARKDOWN)
    result = await api_request("POST", f"{alias}/{endpoint}", json=payload)
    if result and result.get("task_id"):
        task_id = result.get("task_id")
        task_name = payload.get('display_name_prefix', 'N/A')
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ 任务提交成功！\n任务ID: `{task_id}`")
        asyncio.create_task(poll_task_status(update.effective_chat.id, context, task_id, task_name))
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ 任务提交失败: {result.get('error', '未知错误')}")
    context.user_data.clear()
    await asyncio.sleep(1)
    reply_markup, text = await build_account_menu(alias)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def post_init(application: Application):
    await application.bot.set_my_commands([BotCommand("start", "打开主菜单")])

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    logger.info("Bot 启动成功！")
    application.run_polling()

if __name__ == "__main__":
    main()

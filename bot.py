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

async def build_param_selection_menu(form_data: dict, action_type: str, context: ContextTypes.DEFAULT_TYPE):
    shape = form_data.get('shape')
    is_flex = shape and "Flex" in shape
    text = f"⚙️ *请配置实例参数*\n*抢占任务*\n\n"
    text += f"实例名称: `{form_data.get('display_name_prefix', 'N/A')}`\n"
    
    spec_text = '尚未选择'
    if shape:
        if 'A1.Flex' in shape: spec_text = 'ARM'
        elif 'E2.1.Micro' in shape: spec_text = 'AMD'
    text += f"实例规格: `{spec_text}`\n"
    
    keyboard = [create_title_bar("参数配置")]
    all_params_selected = True
    
    keyboard.append([InlineKeyboardButton("─── 实例机型选择 ───", callback_data="ignore")])
    shape_options = {
        "VM.Standard.A1.Flex": "ARM",
        "VM.Standard.E2.1.Micro": "AMD"
    }
    shape_buttons = [InlineKeyboardButton(f"{'✅ ' if shape == k else ''}{v}", callback_data=f"form_param:shape:{k}") for k, v in shape_options.items()]
    keyboard.append(shape_buttons)
    if not shape: all_params_selected = False

    if is_flex:
        ocpu_val = form_data.get('ocpus')
        text += f"OCPU: `{ocpu_val or '尚未选择'}`\n"
        keyboard.append([InlineKeyboardButton("─── 实例CPU规格 ───", callback_data="ignore")])
        options = {"1": "1 OCPU", "2": "2 OCPU", "3": "3 OCPU", "4": "4 OCPU"}
        option_buttons = [InlineKeyboardButton(f"{'✅ ' if str(ocpu_val) == k else ''}{v}", callback_data=f"form_param:ocpus:{k}") for k, v in options.items()]
        keyboard.append(option_buttons)
        if not ocpu_val: all_params_selected = False

        mem_val = form_data.get('memory_in_gbs')
        text += f"内存: `{f'{mem_val} GB' if mem_val else '尚未选择'}`\n"
        keyboard.append([InlineKeyboardButton("─── 实例运行内存规格 ───", callback_data="ignore")])
        options = {"6": "6 GB", "12": "12 GB", "18": "18 GB", "24": "24 GB"}
        option_buttons = [InlineKeyboardButton(f"{'✅ ' if str(mem_val) == k else ''}{v}", callback_data=f"form_param:memory_in_gbs:{k}") for k, v in options.items()]
        keyboard.append(option_buttons)
        if not mem_val: all_params_selected = False

    if shape:
        disk_val = form_data.get('boot_volume_size')
        text += f"磁盘大小: `{f'{disk_val} GB' if disk_val else '尚未选择'}`\n"
        keyboard.append([InlineKeyboardButton("─── 实例硬盘大小 ───", callback_data="ignore")])
        options = {"50": "50 GB", "100": "100 GB", "150": "150 GB", "200": "200 GB"}
        option_buttons = [InlineKeyboardButton(f"{'✅ ' if str(disk_val) == k else ''}{v}", callback_data=f"form_param:boot_volume_size:{k}") for k, v in options.items()]
        keyboard.append(option_buttons)
        if not disk_val: all_params_selected = False
    else:
        all_params_selected = False

    text += f"\n重试间隔: `{form_data.get('min_delay', '45')}-{form_data.get('max_delay', '90')} 秒`"

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

    keyboard = [
        create_title_bar("Cloud Manager Panel Telegram Bot"),
        [InlineKeyboardButton("📝 查看抢占实例任务", callback_data="tasks:all")],
        [InlineKeyboardButton("👇 OCI 账户选择", callback_data="ignore")]
    ]

    for i in range(0, len(profiles), 2):
        row = [InlineKeyboardButton(profiles[i], callback_data=f"account:{profiles[i]}")]
        if i + 1 < len(profiles):
            row.append(InlineKeyboardButton(profiles[i+1], callback_data=f"account:{profiles[i+1]}"))
        keyboard.append(row)
    
    keyboard.append(get_footer_ruler())
    
    return InlineKeyboardMarkup(keyboard), "请选择要操作的 OCI 账户:"

async def build_account_menu(alias: str, context: ContextTypes.DEFAULT_TYPE):
    instances = await api_request("GET", f"{alias}/instances")
    context.user_data['instance_list'] = instances

    keyboard = [
        create_title_bar(f"账户: {alias}"),
        [
            InlineKeyboardButton("🖥️ 实例操作", callback_data=f"menu:instances:{alias}"),
            InlineKeyboardButton("🤖 创建及抢占实例", callback_data=f"start_snatch:{alias}")
        ],
        [InlineKeyboardButton("👇 选择下方实例以执行操作 👇", callback_data="ignore")]
    ]
    
    if isinstance(instances, list) and instances:
        for i in range(0, len(instances), 2):
            row = []
            inst1 = instances[i]
            row.append(InlineKeyboardButton(f"{inst1['display_name']} ({inst1['lifecycle_state']})", callback_data=f"exec:{i}"))
            
            if i + 1 < len(instances):
                inst2 = instances[i+1]
                row.append(InlineKeyboardButton(f"{inst2['display_name']} ({inst2['lifecycle_state']})", callback_data=f"exec:{i+1}")) # 修正了这里的小BUG
            keyboard.append(row)
    elif not instances:
        keyboard.append([InlineKeyboardButton("该账户下没有实例", callback_data="ignore")])
    else:
        error_msg = instances.get('error', '未知错误') if isinstance(instances, dict) else '获取失败'
        keyboard.append([InlineKeyboardButton(f"❌ 获取实例列表失败: {error_msg}", callback_data="ignore")])

    keyboard.append([InlineKeyboardButton("⬅️ 返回主菜单", callback_data=f"back:main")])
    keyboard.append(get_footer_ruler())

    return InlineKeyboardMarkup(keyboard), f"已选择账户: *{alias}*\n请选择功能模块或下方的一个实例:"

# --- 关键修改：恢复此页面的双列布局 ---
async def build_instance_action_menu(alias: str):
    keyboard = [
        create_title_bar("实例操作"),
        # 恢复为双列布局
        [InlineKeyboardButton("✅ 开机", callback_data="perform_action:START"), InlineKeyboardButton("🛑 关机", callback_data="perform_action:STOP")],
        [InlineKeyboardButton("🔄 重启", callback_data="perform_action:RESTART"), InlineKeyboardButton("🗑️ 终止", callback_data="perform_action:TERMINATE")],
        [InlineKeyboardButton("🌐 更换IP", callback_data="perform_action:CHANGEIP"), InlineKeyboardButton("🌐 分配IPv6", callback_data="perform_action:ASSIGNIPV6")],
        # 返回按钮保持单行
        [InlineKeyboardButton("⬅️ 返回", callback_data=f"back:account:{alias}")],
    ]
    keyboard.append(get_footer_ruler())
    return InlineKeyboardMarkup(keyboard), f"请为账户 *{alias}* 选择实例操作类型:"

async def build_task_menu():
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
        prefix = "snatch"
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
        await query.edit_message_text(f"正在为账户 *{alias}* 加载实例列表...", parse_mode=ParseMode.MARKDOWN)
        reply_markup, text = await build_account_menu(alias, context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return

    elif command == "menu":
        menu_type, alias = parts[1], parts[2]
        if menu_type == "instances":
            await query.answer("请直接点击下方您想操作的实例。", show_alert=True)
            return
            
    elif command == "exec":
        instance_index = int(parts[1])
        alias = context.user_data.get('current_alias')
        instance_list = context.user_data.get('instance_list')

        if not all([alias, instance_list is not None]):
            await query.edit_message_text("会话已过期，请返回重试。", reply_markup=None)
            return
        
        selected_instance = instance_list[instance_index]
        context.user_data['selected_instance_for_action'] = selected_instance 
        
        reply_markup, text = await build_instance_action_menu(alias)
        await query.edit_message_text(f"已选择实例: *{selected_instance['display_name']}*\n请选择要执行的操作：", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return

    elif command == "perform_action":
        action = parts[1]
        alias = context.user_data.get('current_alias')
        selected_instance = context.user_data.get('selected_instance_for_action')

        if not all([alias, action, selected_instance]):
            await query.edit_message_text("会话已过期，请返回重试。", reply_markup=None)
            return

        instance_id = selected_instance['id']
        instance_name = selected_instance['display_name']
        vnic_id = selected_instance.get('vnic_id')

        await query.edit_message_text(text=f"正在为实例 *{instance_name}* 发送 *{action}* 命令...", parse_mode=ParseMode.MARKDOWN)
        
        payload = {"action": action, "instance_id": instance_id, "instance_name": instance_name}
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
            task_name = f"{action} on {instance_name}"
            text = f"✅ 命令发送成功！\n任务ID: `{task_id}`\n\n机器人将在后台为您监控任务，完成后会主动通知您。"
            asyncio.create_task(poll_task_status(update.effective_chat.id, context, task_id, task_name))
        else:
            text = f"❌ 命令发送失败: {result.get('error', '未知错误')}"
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        context.user_data.pop('selected_instance_for_action', None)
        return
    
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

            if isinstance(tasks, dict) and "error" in tasks:
                await query.edit_message_text(text=f"❌ 查询任务失败: {tasks.get('error', '未知错误')}", reply_markup=back_keyboard)
                return
            
            if not isinstance(tasks, list):
                await query.edit_message_text(text=f"❌ 查询失败: API返回了意外的数据格式。", reply_markup=back_keyboard)
                return

            text = f"所有账户 *{status_text}* 的 *{task_type}* 任务:\n\n"
            if not tasks:
                text += "目前没有正在运行的抢占实例任务。"
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
            context.user_data['current_alias'] = alias
            await query.edit_message_text(f"正在为账户 *{alias}* 加载实例列表...", parse_mode=ParseMode.MARKDOWN)
            reply_markup, text = await build_account_menu(alias, context)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def submit_form(update: Update, context: ContextTypes.DEFAULT_TYPE, form_data: dict):
    action_type = context.user_data.get('action_in_progress')
    alias = context.user_data.get('alias')
    form_data.setdefault('min_delay', 45)
    form_data.setdefault('max_delay', 90)
    payload = form_data.copy()

    shape = payload.get('shape', '')
    if 'E2.1.Micro' in shape:
        payload['ocpus'] = 1
        payload['memory_in_gbs'] = 1

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
    
    context.user_data['current_alias'] = alias
    await context.bot.send_message(chat_id=update.effective_chat.id, text="操作完成，返回账户菜单...")
    reply_markup, text = await build_account_menu(alias, context)
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

import asyncio
import httpx
import logging
import json
import re # <<< 1. 新增导入 re 模块
from datetime import datetime, timezone
from typing import List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

# --- 配置信息 ---
PANEL_URL = "Your Panel URL Placeholder"
PANEL_API_KEY = "Your API Key Placeholder"
BOT_TOKEN = "Your Bot Token Placeholder"
AUTHORIZED_USER_IDS = [123456789]

# --- 日志配置 ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 辅助函数 ---
def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def format_elapsed_time_tg(start_time_str: str) -> str:
    try:
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - start_time
        days = delta.days
        seconds = delta.seconds
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if days > 0: parts.append(f"{days}天")
        if hours > 0: parts.append(f"{hours}小时")
        if minutes > 0: parts.append(f"{minutes}分")
        if not parts: return "不到1分钟"
        return "".join(parts)
    except (ValueError, TypeError):
        return "未知"

def create_title_bar(title: str) -> List[InlineKeyboardButton]:
    return [InlineKeyboardButton(f"❖ {title} ❖", callback_data="ignore")]

# --- 修改点 1: 调整页脚函数，使其能接收参数，并且默认不显示关闭按钮 ---
def get_footer_ruler(add_close_button: bool = False) -> List[List[InlineKeyboardButton]]:
    """
    生成菜单页脚。
    :param add_close_button: 如果为 True，则在底部添加“关闭窗口”按钮。
    """
    footer = [
        [
            InlineKeyboardButton("─────« Cloud", callback_data="ignore"),
            InlineKeyboardButton("Manager »────", callback_data="ignore")
        ]
    ]
    if add_close_button:
        footer.append([InlineKeyboardButton("❌ 关闭窗口", callback_data="close_window")])
    return footer

# --- API 客户端  ---
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

# --- Telegram 机器人逻辑  ---
def authorized(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in AUTHORIZED_USER_IDS:
            if update.callback_query: await update.callback_query.answer("🚫 您没有权限。", show_alert=True)
            else: await update.message.reply_text("🚫 您没有权限操作此机器人。")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def send_and_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    try:
        sent_message = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(5)
        await context.bot.delete_message(chat_id=chat_id, message_id=sent_message.message_id)
    except Exception as e:
        logger.warning(f"发送或删除临时消息时出错: {e}")

async def poll_task_status(chat_id: int, context: ContextTypes.DEFAULT_TYPE, task_id: str, task_name: str):
    max_retries, retries = 120, 0
    while retries < max_retries:
        await asyncio.sleep(5)
        result = await api_request("GET", f"task-status/{task_id}")
        if not result or not result.get("status"):
            retries += 1
            continue
        status = result.get("status")
        if status == "success":
            logger.info(f"任务 {task_id} ({task_name}) 成功，由后端处理通知，机器人轮询结束。")
            return
        if status == "failure":
            final_message = f"🔔 *任务失败通知*\n\n*任务名称*: `{task_name}`\n\n*原因*:\n`{result.get('result')}`"
            await context.bot.send_message(chat_id=chat_id, text=final_message, parse_mode=ParseMode.MARKDOWN)
            return
        retries += 1
    await context.bot.send_message(chat_id=chat_id, text=f"🔔 *任务超时*\n\n任务 `{task_name}` 轮询超时（超过10分钟），请在网页端查看最终结果。")

# --- 菜单构建函数 (已全部更新为使用新的页脚) ---
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
    shape_options = {"VM.Standard.A1.Flex": "ARM","VM.Standard.E2.1.Micro": "AMD"}
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
    keyboard.append([InlineKeyboardButton("⬅️ 返回", callback_data=f"back:account:{alias}")])
    keyboard.extend(get_footer_ruler(add_close_button=False))
    return text, InlineKeyboardMarkup(keyboard)

async def build_main_menu():
    profiles = await api_request("GET", "profiles")
    if not profiles or "error" in profiles:
        return None, f"❌ 无法从面板获取账户列表: {profiles.get('error', '未知错误') if profiles else '无响应'}"
    if not profiles:
        return None, "面板中尚未配置任何OCI账户。"
    profiles.sort(key=natural_sort_key)
    keyboard = [
        create_title_bar("Cloud Manager Panel Telegram Bot"),
        [InlineKeyboardButton("📝 查看抢占实例任务", callback_data="tasks:running:1")],
        [InlineKeyboardButton("👇 OCI 账户选择", callback_data="ignore")]
    ]
    for i in range(0, len(profiles), 2):
        row = [InlineKeyboardButton(profiles[i], callback_data=f"account:{profiles[i]}")]
        if i + 1 < len(profiles):
            row.append(InlineKeyboardButton(profiles[i+1], callback_data=f"account:{profiles[i+1]}"))
        keyboard.append(row)
    keyboard.extend(get_footer_ruler(add_close_button=True)) # 只在主菜单显示关闭按钮
    return InlineKeyboardMarkup(keyboard), "请选择要操作的 OCI 账户:"

async def build_account_menu(alias: str, context: ContextTypes.DEFAULT_TYPE):
    instances = await api_request("GET", f"{alias}/instances")
    context.user_data['instance_list'] = instances
    keyboard = [
        create_title_bar(f"账户: {alias}"),
        [InlineKeyboardButton("🤖 创建及抢占实例", callback_data=f"start_snatch:{alias}")],
        [InlineKeyboardButton("👇 选择下方实例以执行操作 👇", callback_data="ignore")]
    ]
    if isinstance(instances, list) and instances:
        for i in range(0, len(instances), 2):
            row = []
            inst1 = instances[i]
            row.append(InlineKeyboardButton(f"{inst1['display_name']} ({inst1['lifecycle_state']})", callback_data=f"exec:{i}"))
            if i + 1 < len(instances):
                inst2 = instances[i+1]
                row.append(InlineKeyboardButton(f"{inst2['display_name']} ({inst2['lifecycle_state']})", callback_data=f"exec:{i+1}"))
            keyboard.append(row)
    elif not instances:
        keyboard.append([InlineKeyboardButton("该账户下没有实例", callback_data="ignore")])
    else:
        error_msg = instances.get('error', '未知错误') if isinstance(instances, dict) else '获取失败'
        keyboard.append([InlineKeyboardButton(f"❌ 获取实例列表失败: {error_msg}", callback_data="ignore")])
    keyboard.append([InlineKeyboardButton("⬅️ 返回主菜单", callback_data=f"back:main")])
    keyboard.extend(get_footer_ruler(add_close_button=False))
    return InlineKeyboardMarkup(keyboard), f"已选择账户: *{alias}*\n请选择功能模块或下方的一个实例:"

async def build_instance_action_menu(alias: str):
    keyboard = [
        create_title_bar("实例操作"),
        [InlineKeyboardButton("✅ 开机", callback_data="perform_action:START"), InlineKeyboardButton("🛑 关机", callback_data="perform_action:STOP")],
        [InlineKeyboardButton("🔄 重启", callback_data="perform_action:RESTART"), InlineKeyboardButton("🗑️ 终止", callback_data="perform_action:TERMINATE")],
        [InlineKeyboardButton("🌐 更换IP", callback_data="perform_action:CHANGEIP"), InlineKeyboardButton("🌐 分配IPv6", callback_data="perform_action:ASSIGNIPV6")],
        [InlineKeyboardButton("⬅️ 返回", callback_data=f"back:account:{alias}")],
    ]
    keyboard.extend(get_footer_ruler(add_close_button=False))
    return InlineKeyboardMarkup(keyboard), "请选择要执行的操作："

def build_pagination_keyboard(view: str, current_page: int, total_pages: int) -> List[List[InlineKeyboardButton]]:
    keyboard = []
    running_text = "🏃 运行中的任务"
    completed_text = "✅ 已完成的任务"
    keyboard.append([
        InlineKeyboardButton(running_text, callback_data="tasks:running:1"),
        InlineKeyboardButton(completed_text, callback_data="tasks:completed:1")
    ])
    if total_pages > 1:
        nav_row = []
        if current_page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"tasks:{view}:{current_page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton("⬅️ 上一页", callback_data="ignore"))
        nav_row.append(InlineKeyboardButton(f"• {current_page}/{total_pages} •", callback_data="ignore"))
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton("下一页 ➡️", callback_data=f"tasks:{view}:{current_page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton("下一页 ➡️", callback_data="ignore"))
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("⬅️ 返回主菜单", callback_data=f"back:main")])
    keyboard.extend(get_footer_ruler(add_close_button=False))
    return keyboard

async def show_all_tasks(query: Update.callback_query, view: str = 'running', page: int = 1):
    await query.edit_message_text(text="*正在查询所有抢占任务...*", parse_mode=ParseMode.MARKDOWN)
    try:
        running_tasks, completed_tasks = await asyncio.gather(
            api_request("GET", "tasks/snatch/running"),
            api_request("GET", "tasks/snatch/completed")
        )
    except Exception as e:
        logger.error(f"获取任务列表时API请求失败: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ 返回主菜单", callback_data="back:main")]]
        keyboard.extend(get_footer_ruler(add_close_button=False))
        await query.edit_message_text(f"❌ 获取任务列表失败: {e}", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    source_list, title = [], ""
    if view == 'running':
        source_list = running_tasks if isinstance(running_tasks, list) else []
        source_list.reverse()
        title = ""
    elif view == 'completed':
        source_list = completed_tasks if isinstance(completed_tasks, list) else []
        title = ""
    total_items = len(source_list)
    total_pages = (total_items + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE if total_items > 0 else 1
    page = max(1, min(page, total_pages))
    start_index = (page - 1) * TASKS_PER_PAGE
    end_index = start_index + TASKS_PER_PAGE
    tasks_on_page = source_list[start_index:end_index]
    text = f"❖ *任务详情* ❖  (第 {page}/{total_pages} 页)\n\n"
    text += title
    if not tasks_on_page:
        text += "_当前分类下没有任务记录。_\n\n"
    else:
        for task in tasks_on_page:
            if view == 'running':
                result_str = task.get('result', '')
                try:
                    result_data = json.loads(result_str)
                    details = result_data.get('details', {})
                    alias = f"账号：{task.get('alias', 'N/A')}"
                    shape_type = "ARM" if "A1" in details.get('shape', '') else "AMD"
                    specs = f"{details.get('ocpus')}核/{details.get('memory')}GB/{details.get('boot_volume_size', '50')}GB"
                    elapsed_time = format_elapsed_time_tg(result_data.get('start_time'))
                    attempt = f"【{result_data.get('attempt_count', 'N/A')}次】"
                    text += (f"*{task.get('name', 'N/A')}*\n"
                             f"{alias}\n"
                             f"机型：{shape_type}\n"
                             f"参数：{specs}\n"
                             f"运行时间：{elapsed_time}{attempt}\n\n")
                except (json.JSONDecodeError, TypeError):
                    text += f"_{task.get('alias', 'N/A')}: {task.get('name', 'N/A')} - {result_str or '获取状态中...'}\n\n_"
            elif view == 'completed':
                status_icon = "✅" if task.get("status") == "success" else "❌"
                task_alias = task.get('alias', 'N/A')
                task_name = task.get('name', 'N/A')
                full_result = task.get('result', '无结果')
                param_text = ""
                details = task.get('details', {}) 
                if details and isinstance(details, dict):
                    try:
                        shape_type = "ARM" if "A1" in details.get('shape', '') else "AMD"
                        specs = f"{details.get('ocpus')}核/{details.get('memory')}GB/{details.get('boot_volume_size', '50')}GB"
                        param_text = f"机型：{shape_type}\n参数：{specs}\n"
                    except Exception as e:
                        logger.warning(f"无法格式化已完成任务的参数: {e}")
                        param_text = ""
                text += f"{status_icon} *{task_name}* (_{task_alias}_)\n{param_text}{full_result}\n\n"
    reply_markup = InlineKeyboardMarkup(build_pagination_keyboard(view, page, total_pages))
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"编辑任务消息时出错: {e}")
            await query.answer("❌ 更新消息时出错，请重试。", show_alert=True)

# --- 命令和回调处理器  ---
@authorized
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    
    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except BadRequest:
            pass
    if update.message:
        try:
            await update.message.delete()
        except BadRequest:
            pass

    reply_markup, text = await build_main_menu()
    
    await update.effective_chat.send_message(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

@authorized
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "ignore": return
    
    if query.data == "close_window":
        try:
            await query.message.delete()
        except BadRequest as e:
            if "Message to delete not found" in str(e):
                await query.answer("窗口已被关闭。")
            else:
                logger.error(f"关闭窗口时出错: {e}")
                await query.answer("❌ 关闭窗口失败。", show_alert=True)
        return

    parts = query.data.split(":")
    command = parts[0]
    
    if command == "tasks":
        view = parts[1] if len(parts) > 1 else 'running'
        page = int(parts[2]) if len(parts) > 2 else 1
        await show_all_tasks(query, view, page)
        return

    if command == "perform_action":
        action, alias = parts[1], context.user_data.get('current_alias')
        selected_instance = context.user_data.get('selected_instance_for_action')
        chat_id = update.effective_chat.id
        if not all([alias, action, selected_instance]):
            asyncio.create_task(send_and_delete_message(context, chat_id, "❌ 会话已过期，请返回重试。"))
            return
        action_text_map = {"START": "开机", "STOP": "关机", "RESTART": "重启", "TERMINATE": "终止", "CHANGEIP": "更换IP", "ASSIGNIPV6": "分配IPv6"}
        action_text = action_text_map.get(action, action)
        if action in ['STOP', 'TERMINATE']:
            pending = context.user_data.get('pending_confirmation')
            if (pending and pending['action'] == action and pending['instance_id'] == selected_instance['id'] and (datetime.now() - pending['timestamp']).total_seconds() < 5):
                context.user_data.pop('pending_confirmation', None)
                feedback_text = f"✅ *{action_text}* 命令已确认并发送..."
                asyncio.create_task(send_and_delete_message(context, chat_id, feedback_text))
            else:
                context.user_data['pending_confirmation'] = {'action': action, 'instance_id': selected_instance['id'], 'timestamp': datetime.now()}
                warning_text = f"⚠️ *危险操作！* 请在5秒内再次点击 *{action_text}* 按钮以确认。"
                asyncio.create_task(send_and_delete_message(context, chat_id, warning_text))
                return
        else:
            feedback_text = f"✅ *{action_text}* 命令已发送..."
            asyncio.create_task(send_and_delete_message(context, chat_id, feedback_text))
        
        instance_id, instance_name, vnic_id = selected_instance['id'], selected_instance['display_name'], selected_instance.get('vnic_id')
        payload = {"action": action, "instance_id": instance_id, "instance_name": instance_name}
        if vnic_id: payload['vnic_id'] = vnic_id
        result = await api_request("POST", f"{alias}/instance-action", json=payload)
        if result and result.get("task_id"):
            asyncio.create_task(poll_task_status(chat_id, context, result.get("task_id"), f"{action} on {instance_name}"))
        else:
            asyncio.create_task(send_and_delete_message(context, chat_id, f"❌ 命令发送失败: {result.get('error', '未知错误')}"))
        return

    if command == "start_create" or command == "start_snatch":
        alias = parts[1]
        context.user_data.clear()
        context.user_data.update({'action_in_progress': command, 'alias': alias})
        auto_name = f"snatch-{datetime.now().strftime('%m%d-%H%M')}"
        context.user_data['form_data'] = {'display_name_prefix': auto_name, 'shape': 'VM.Standard.A1.Flex'}
        text, reply_markup = await build_param_selection_menu(context.user_data['form_data'], command, context)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return
        
    if command == "form_param":
        key, value = parts[1], parts[2]
        context.user_data['form_data'][key] = value
        if key == 'shape': context.user_data['form_data'].pop('ocpus', None); context.user_data['form_data'].pop('memory_in_gbs', None)
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

    if command == "exec":
        instance_index, alias = int(parts[1]), context.user_data.get('current_alias')
        instance_list = context.user_data.get('instance_list')
        if not all([alias, instance_list is not None]):
            await query.answer("会话已过期或信息不完整，请返回重试。", show_alert=True)
            return
        selected_instance = instance_list[instance_index]
        context.user_data['selected_instance_for_action'] = selected_instance
        reply_markup, text = await build_instance_action_menu(alias)
        await query.edit_message_text(f"已选择实例: *{selected_instance['display_name']}*\n请选择要执行的操作：", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return
    
    if command == "back":
        target = parts[1]
        if target == "main":
            await start_command(update, context)
        elif target == "account":
            alias = parts[2] if len(parts) > 2 else context.user_data.get('current_alias')
            context.user_data.clear()
            context.user_data['current_alias'] = alias
            await query.edit_message_text(f"正在为账户 *{alias}* 加载实例列表...", parse_mode=ParseMode.MARKDOWN)
            reply_markup, text = await build_account_menu(alias, context)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# --- 表单提交和主程序入口 ---
async def submit_form(update: Update, context: ContextTypes.DEFAULT_TYPE, form_data: dict):
    alias = context.user_data.get('alias')
    chat_id = update.effective_chat.id
    await update.callback_query.answer("正在提交任务...")
    payload = form_data.copy()
    payload.setdefault('min_delay', 45)
    payload.setdefault('max_delay', 90)
    if 'E2.1.Micro' in payload.get('shape', ''):
        payload['ocpus'], payload['memory_in_gbs'] = 1, 1
    numeric_keys = ['ocpus', 'memory_in_gbs', 'boot_volume_size', 'min_delay', 'max_delay']
    for key in numeric_keys:
        if key in payload and payload[key] is not None:
            try:
                payload[key] = float(payload[key]) if key in ['ocpus', 'memory_in_gbs'] else int(payload[key])
            except (ValueError, TypeError):
                await send_and_delete_message(context, chat_id, f"❌ 参数 {key} 的值 `{payload[key]}` 无效。")
                return
    payload.setdefault('os_name_version', 'Canonical Ubuntu-22.04')
    action_type = context.user_data.get('action_in_progress')
    endpoint = "snatch-instance" if action_type == "start_snatch" else "create-instance"
    task_name = payload.get('display_name_prefix', 'N/A')
    result = await api_request("POST", f"{alias}/{endpoint}", json=payload)
    await update.callback_query.delete_message()
    if result and result.get("task_id"):
        task_id = result.get("task_id")
        start_message = f"✅ *抢占任务已提交!*\n\n*账户*: `{alias}`\n*任务名称*: `{task_name}`\n\n机器人将在后台开始尝试..."
        asyncio.create_task(send_and_delete_message(context, chat_id, start_message))
        asyncio.create_task(poll_task_status(chat_id, context, task_id, task_name))
    else:
        error_message = f"❌ 任务提交失败: {result.get('error', '未知错误')}"
        asyncio.create_task(send_and_delete_message(context, chat_id, error_message))
    context.user_data.clear()
    asyncio.create_task(send_and_delete_message(context, chat_id, "正在返回账户菜单..."))
    context.user_data['current_alias'] = alias
    reply_markup, text = await build_account_menu(alias, context)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# --- 修改点 2: 彻底修正左下角菜单按钮的行为 ---
async def post_init(application: Application):
    """
    在机器人启动后，设置其命令和菜单按钮。
    """
    # 1. 定义一个对用户可见的命令列表
    commands = [
        BotCommand("start", "主菜单")  # 将描述文字直接放在这里
    ]
    await application.bot.set_my_commands(commands)
    
    #    将左下角的菜单按钮明确设置为默认类型。
    #    这会告诉客户端显示一个通用的菜单图标 (≡)，
    #    点击后，由于我们只有一个命令，它会直接发送 /start
    await application.bot.set_chat_menu_button(menu_button=MenuButtonDefault())

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    logger.info("Bot 启动成功！")
    application.run_polling()

if __name__ == "__main__":
    main()

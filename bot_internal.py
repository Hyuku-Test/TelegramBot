import os
import logging
import csv
import io
import aiohttp
import requests
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

CACHED_TRAINING_DATA = {}

# ================= ⚙️ CẤU HÌNH HỆ THỐNG S2 (BẢO MẬT TUYỆT ĐỐI) =================
# Danh sách Admin và Tên tương ứng
ADMINS = {
    1494664481: "HuyDQ",
    2093523276: "TuanTVA"
}

# Lấy thông tin từ GitHub Secrets và dùng .strip() để loại bỏ hoàn toàn dấu xuống dòng (\n) hoặc khoảng trắng thừa
TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
GOOGLE_SHEETS_CSV_URL = os.getenv("MY_SECRET_URL", "").strip()
WEB_APP_URL = os.getenv("MY_SECRET_APPSCRIPTS", "").strip()
# ==================================================================================

CHỜ_TÊN, CHỜ_CÂU_HỎI, ADMIN_CHỜ_REPLY = range(3)

def load_data_from_sheets(csv_url):
    global CACHED_TRAINING_DATA
    if not csv_url:
        logging.error("Lỗi: URL Google Sheets trống!")
        return False
    try:
        response = requests.get(csv_url, timeout=10)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            f = io.StringIO(response.text)
            reader = csv.DictReader(f)
            new_data = {}
            for row in reader:
                if row.get('id'):
                    new_data[row['id'].strip()] = {
                        "title": row['title'].strip(),
                        "content": row['content'].strip()
                    }
            CACHED_TRAINING_DATA = new_data
            logging.info("Đồng bộ dữ liệu thành công!")
            return True
    except Exception as e:
        logging.error(f"Lỗi đọc Sheets: {e}")
        return False

# Hàm tạo bàn phím động dựa trên chuỗi danh mục con (menu:a,b,c)
def build_dynamic_keyboard(content_string, current_key, root_key):
    raw_keys = content_string.replace("menu:", "").split(",")
    menu_keys = [k.strip() for k in raw_keys if k.strip()]
    keyboard = []
    
    prefix = "go_train:" if root_key == "tai_lieu_training" else "go_script:"
    
    for key in menu_keys:
        if key in CACHED_TRAINING_DATA:
            keyboard.append([InlineKeyboardButton(CACHED_TRAINING_DATA[key]['title'], callback_data=f"{prefix}{key}")])
            
    # Xử lý nút quay lại ở các tầng menu con trung gian
    if current_key != root_key:
        parent_key = root_key
        for p_key, p_val in CACHED_TRAINING_DATA.items():
            if p_val['content'].startswith("menu:"):
                if current_key in [k.strip() for k in p_val['content'].replace("menu:", "").split(",")]:
                    parent_key = root_key if p_key == "menu_main" else p_key
                    break
        keyboard.append([InlineKeyboardButton("⬅️ Quay lại", callback_data=f"{prefix}{parent_key}")])
        
    return InlineKeyboardMarkup(keyboard)

# LỆNH /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 <b>CHÀO MỪNG BẠN ĐẾN VỚI TRỢ LÝ ADS TEAM S2</b>\n\n"
        "📚 /training - Mở Menu 'Tài liệu Training Internal'\n"
        "💻 /scripts - Mở Menu chứa kho mã nguồn Scripts Automation\n"
        "❓ /ask - Gửi câu hỏi Q&A trực tiếp cho Admin"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# LỆNH /training
async def training_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    root_item = CACHED_TRAINING_DATA.get("tai_lieu_training")
    if not root_item:
        await update.message.reply_text("❌ Không tìm thấy ID 'tai_lieu_training' trong Sheets. Vui lòng kiểm tra lại cột id.")
        return
    reply_markup = build_dynamic_keyboard(root_item['content'], "tai_lieu_training", "tai_lieu_training")
    await update.message.reply_text(f"📚 <b>{root_item['title'].upper()}</b>:", reply_markup=reply_markup, parse_mode="HTML")

# LỆNH /scripts
async def scripts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    root_item = CACHED_TRAINING_DATA.get("scripts")
    if not root_item:
        await update.message.reply_text("❌ Không tìm thấy ID 'scripts' trong Sheets. Vui lòng kiểm tra lại cột id.")
        return
    reply_markup = build_dynamic_keyboard(root_item['content'], "scripts", "scripts")
    await update.message.reply_text(f"💻 <b>{root_item['title'].upper()}</b>:", reply_markup=reply_markup, parse_mode="HTML")

# LỆNH /ask
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data['state'] = CHỜ_TÊN
    await update.message.reply_text("<b>Dân hỏi Bộ Trưởng trả lời</b>\n\n👉 Đầu tiên, vui lòng nhập vào <b>Tên của bạn</b> là gì:", parse_mode="HTML")

# XỬ LÝ BIỂU MẪU Q&A
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get('state')
    user_id = update.effective_user.id
    user_text = update.message.text.strip()
    
    # Nếu là Admin gửi câu trả lời
    if state == ADMIN_CHỜ_REPLY and user_id in ADMINS:
        target_user_id = context.user_data.get('target_user_id')
        replier_name = ADMINS[user_id]
        
        if WEB_APP_URL:
            async def send_reply_async():
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(WEB_APP_URL, json={
                            "action": "reply", 
                            "user_id": target_user_id, 
                            "answer": user_text,
                            "replier": replier_name
                        }, timeout=10)
                except Exception as e: logging.error(f"Lỗi ghi đè Sheets: {e}")
            asyncio.create_task(send_reply_async())
                
        user_msg = f"🔔 <b>THÔNG BÁO: BẠN ĐÃ CÓ CÂU TRẢ LỜI TỪ BỘ TRƯỞNG!</b>\n\n💬 <b>Câu trả lời:</b> {user_text}"
        try:
            await context.bot.send_message(chat_id=target_user_id, text=user_msg, parse_mode="HTML")
            await update.message.reply_text("✅ <b>Đã gửi câu trả lời thành công!</b>", parse_mode="HTML")
        except Exception as e: await update.message.reply_text(f"❌ Lỗi gửi tin nhắn cho User: {e}")
        context.user_data.clear()
        return

    if state == CHỜ_TÊN:
        context.user_data['user_name'] = user_text
        context.user_data['state'] = CHỜ_CÂU_HỎI
        await update.message.reply_text(f"🤝 Chào <b>{user_text}</b>! Tiếp theo, vui lòng nhập vào <b>Nội dung câu hỏi</b> của bạn:", parse_mode="HTML")
    elif state == CHỜ_CÂU_HỎI:
        user_name = context.user_data.get('user_name')
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if WEB_APP_URL:
            async def send_ask_async():
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(WEB_APP_URL, json={"action": "ask", "time": current_time, "user_id": user_id, "name": user_name, "question": user_text}, timeout=10)
                except Exception as e: logging.error(f"Lỗi đẩy Sheets: {e}")
            asyncio.create_task(send_ask_async())
                
        await update.message.reply_text("✅ <b>Gửi thành công!</b> Câu hỏi đã được chuyển trực tiếp tới Admin.", parse_mode="HTML")
        admin_keyboard = [[InlineKeyboardButton("✍️ Trả lời câu hỏi này", callback_data=f"reply_to:{user_id}")]]
        admin_text = f"🚨 <b>BẠN CÓ CÂU HỎI Q&A MỚI!</b>\n\n👤 <b>Người hỏi:</b> {user_name} (ID: {user_id})\n💬 <b>Nội dung:</b> {user_text}"
        
        for admin_id in ADMINS.keys():
            try:
                await context.bot.send_message(chat_id=admin_id, text=admin_text, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode="HTML")
            except Exception as e: logging.error(f"Lỗi gửi Admin {admin_id}: {e}")
        context.user_data.clear()

# XỬ LÝ CLICK NÚT BẤM
async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith("reply_to:"):
        if user_id not in ADMINS: return
        
        current_admin_name = ADMINS[user_id]
        target_user = data.split(":")[1].strip()
        context.user_data['state'] = ADMIN_CHỜ_REPLY
        context.user_data['target_user_id'] = target_user
        
        for admin_id, admin_name in ADMINS.items():
            if admin_id != user_id:
                try:
                    notify_msg = f"🔔 <b>THÔNG BÁO:</b> Admin <b>{current_admin_name}</b> đã đảm nhận việc trả lời câu hỏi của User ID {target_user}."
                    await context.bot.send_message(chat_id=admin_id, text=notify_msg, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Lỗi gửi thông báo cho admin còn lại {admin_id}: {e}")

        await query.message.reply_text(f"👉 Chào <b>{current_admin_name}</b>, vui lòng nhập nội dung phản hồi cho thành viên vào ô chat:", parse_mode="HTML")
        return

    if data.startswith("go_train:"):
        target_key = data.split(":")[1].strip()
        if target_key in CACHED_TRAINING_DATA:
            item = CACHED_TRAINING_DATA[target_key]
            content = item['content']
            
            if content.startswith("menu:"):
                await query.edit_message_text(text=f"📂 <b>{item['title'].upper()}</b>\nVui lòng lựa chọn tiếp:", reply_markup=build_dynamic_keyboard(content, target_key, "tai_lieu_training"), parse_mode="HTML")
            else:
                await query.edit_message_text(text=f"📄 <b>{item['title'].upper()}</b>\n\n{content}", reply_markup=None, parse_mode="HTML")
        return

    if data.startswith("go_script:"):
        target_key = data.split(":")[1].strip()
        if target_key in CACHED_TRAINING_DATA:
            item = CACHED_TRAINING_DATA[target_key]
            content = item['content']
            
            if content.startswith("menu:"):
                await query.edit_message_text(text=f"📂 <b>{item['title'].upper()}</b>\nVui lòng lựa chọn tiếp:", reply_markup=build_dynamic_keyboard(content, target_key, "scripts"), parse_mode="HTML")
            else:
                title_upper = item['title'].upper()
                await query.edit_message_text(text=f"🚀 <b>{title_upper}</b>\n\n⚙️ <i>Nội dung đang được đẩy xuống dưới dưới dạng file đính kèm...</i>", reply_markup=None, parse_mode="HTML")
                
                custom_note = ""
                if "LABEL SHEET" in title_upper: custom_note = "\n⚠️ <b>LƯU Ý:</b> Nhớ thay <b>ID Merchant</b> của tài khoản đang quản lý."
                elif "LABEL ADS" in title_upper: custom_note = "\n⚠️ <b>LƯU Ý:</b> Nhớ thay <b>URL sheet Supplemental</b>."
                elif any(kw in title_upper for kw in ["SEARCH", "PMAX", "COLLECTION", "BRAND"]): custom_note = "\n⚠️ <b>LƯU Ý:</b> Nhớ thay <b>URL sheet Auto Ads</b> của cá nhân bạn."

                clean_content = content.strip().replace('\\n', '\n').replace('\r\n', '\n').replace('\r', '\n')
                file_buffer = io.BytesIO(clean_content.encode('utf-8'))
                file_buffer.name = f"{item['title'].replace(' ', '_')}.txt"
                
                await query.message.reply_document(document=file_buffer, caption=f"✅ <b>Gửi thành công file script: {item['title']}</b>{custom_note}", parse_mode="HTML")
        return

# LỆNH ĐỒNG BỘ THỦ CÔNG
async def update_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in ADMINS: return
    await update.message.reply_text("🔄 Đang nạp dữ liệu từ Google Sheets về bộ nhớ đệm...")
    if load_data_from_sheets(context.bot_data.get("csv_url")):
        await update.message.reply_text("✅ Đồng bộ hoàn tất!", parse_mode="HTML")

async def main_run():
    if not TOKEN:
        logging.error("Lỗi nghiêm trọng: Cấu hình TELEGRAM_TOKEN trống hoặc sai định dạng!")
        return
        
    load_data_from_sheets(GOOGLE_SHEETS_CSV_URL)
    application = Application.builder().token(TOKEN).build()
    application.bot_data["csv_url"] = GOOGLE_SHEETS_CSV_URL
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("training", training_command))
    application.add_handler(CommandHandler("scripts", scripts_command))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("update_data", update_data_command))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    application.add_handler(CallbackQueryHandler(handle_button_click))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    logging.info("Bot đang chạy an toàn trên máy ảo GitHub Actions...")
    # Sửa thành 21000 giây (5 tiếng 50 phút) để bot online lâu nhất có thể
    await asyncio.sleep(21000) 
    
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main_run())

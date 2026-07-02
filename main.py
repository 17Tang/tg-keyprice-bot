import os
import threading
import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import twstock
import telebot
from curl_cffi import requests
from flask import Flask

# ==========================================
# ⚙️ 核心設定區
# ==========================================
TG_TOKEN = os.environ.get('TG_TOKEN')
bot = telebot.TeleBot(TG_TOKEN)

# 建立超強偽裝 Session，完美模擬 Chrome 瀏覽器底層特徵
yf_session = requests.Session(impersonate="chrome")

# ==========================================
# 🌐 Web Server (應付 Render 的 Port 掃描)
# ==========================================
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Telegram Bot is running smoothly on Render!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 📊 數據下載與關鍵價計算
# ==========================================
def get_status(price, reference_price):
    return "🔴大於" if price > reference_price else "🟢小於"

def calculate_stock_prices(stock_id):
    target = stock_id.upper().strip()
    
    # 精準分流判定
    if target in ["TWII", "^TWII"]:
        yf_id = "^TWII"
        is_tw_stock = False
    elif target in ["TWO", "TWO.TW", "^TWO"]:
        yf_id = "TWO.TW"
        is_tw_stock = False
    else:
        is_tw_stock = target.replace(".", "").isdigit() and len(target) >= 4
        yf_id = f"{target}.TW" if is_tw_stock else target

    try:
        # 使用 yfinance 下載歷史資料
        ticker = yf.Ticker(yf_id, session=yf_session)
        df = ticker.history(period="6mo")
        
        # 針對上櫃股票的防呆處理
        if is_tw_stock and df.empty:
            yf_id = f"{target}.TWO"
            ticker = yf.Ticker(yf_id, session=yf_session)
            df = ticker.history(period="6mo")
            
        if df.empty or len(df) < 3:
            return f"⚠️ <b>{target}</b> ({yf_id}) 獲取資料失敗或歷史數據不足。\n------------------------\n"

        # 去除時區資訊
        df.index = df.index.tz_localize(None)

        # 最新收盤/現價 (T)
        latest_data = df.iloc[-1]
        latest_date = df.index[-1].strftime("%Y-%m-%d")
        latest_close = latest_data['Close']

        # 今日防守價 (由 T-1 K線推算)
        prev1_data = df.iloc[-2]
        prev1_date = df.index[-2].strftime("%Y-%m-%d")
        p1_h, p1_l = prev1_data['High'], prev1_data['Low']
        
        today_key = (p1_h + p1_l) / 2
        today_short_def = p1_h + (p1_h - p1_l) * 0.382
        today_long_def = p1_l - (p1_h - p1_l) * 0.382

        # 昨日防守價 (由 T-2 K線推算)
        prev2_data = df.iloc[-3]
        prev2_date = df.index[-3].strftime("%Y-%m-%d")
        p2_h, p2_l = prev2_data['High'], prev2_data['Low']
        
        yesterday_key = (p2_h + p2_l) / 2
        yesterday_short_def = p2_h + (p2_h - p2_l) * 0.382
        yesterday_long_def = p2_l - (p2_h - p2_l) * 0.382

        # 周月線計算
        df_weekly = df.resample('W-FRI').agg({'High': 'max', 'Low': 'min'})
        week_data = df_weekly.iloc[-2] if df.index[-1].weekday() != 4 else df_weekly.iloc[-1]
        week_key = (week_data['High'] + week_data['Low']) / 2

        df_monthly = df.resample('ME').agg({'High': 'max', 'Low': 'min'})
        next_day = df.index[-1] + datetime.timedelta(days=1)
        month_data = df_monthly.iloc[-2] if df.index[-1].month == next_day.month else df_monthly.iloc[-1]
        month_key = (month_data['High'] + month_data['Low']) / 2

        # 取得股票名稱
        stock_name = ""
        if yf_id == "^TWII": stock_name = "加權指數"
        elif yf_id == "TWO.TW": stock_name = "櫃買指數"
        elif yf_id == "^SOX": stock_name = "費城半導體"
        elif is_tw_stock:
            try:
                tw_info = twstock.codes.get(target)
                if tw_info: stock_name = tw_info.name
            except Exception: pass
            
        display_name = f"{stock_name} ({yf_id})" if stock_name else yf_id

        # 格式化輸出
        msg = (
            f"📊 <b>{display_name}</b>\n"
            f"🔸 {latest_date} 收盤: <b>{latest_close:.2f}</b>\n\n"
            f"🎯 <b>今日關鍵價位 (由 {prev1_date} 推算)</b>\n"
            f"🛡️ 空方防守: {today_short_def:.2f} ({get_status(latest_close, today_short_def)})\n"
            f"🔑 日關鍵價: {today_key:.2f} ({get_status(latest_close, today_key)})\n"
            f"🛡️ 多方防守: {today_long_def:.2f} ({get_status(latest_close, today_long_def)})\n\n"
            f"⏪ <b>昨日關鍵價位 (由 {prev2_date} 推算)</b>\n"
            f"🛡️ 空方防守: {yesterday_short_def:.2f}\n"
            f"🔑 日關鍵價: {yesterday_key:.2f}\n"
            f"🛡️ 多方防守: {yesterday_long_def:.2f}\n\n"
            f"⏳ <b>中長線關鍵價</b>\n"
            f"🔑 周關鍵價: {week_key:.2f} ({get_status(latest_close, week_key)})\n"
            f"🔑 月關鍵價: {month_key:.2f} ({get_status(latest_close, month_key)})\n"
            "------------------------\n"
        )
        return msg

    except Exception as e:
        return f"⚠️ <b>{target}</b> 獲取失敗：<code>{e}</code>\n------------------------\n"

# ==========================================
# 🤖 Telegram 訊息接收邏輯
# ==========================================
@bot.message_handler(commands=['start', 'report'])
def send_index_report(message):
    processing_msg = bot.reply_to(message, "⏳ 正在抓取三大指數最新數據，請稍候...")
    
    try:
        today_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        final_message = f"📋 <b>{today_str} 盤勢關鍵價報告</b>\n\n"
        
        # 預設大盤清單
        indices = ["^TWII", "TWO.TW", "^SOX"]
        for symbol in indices:
            final_message += calculate_stock_prices(symbol)
            
        bot.send_message(message.chat.id, final_message, parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ 系統發生錯誤：\n<code>{e}</code>", parse_mode="HTML")
    finally:
        try: bot.delete_message(message.chat.id, processing_msg.message_id)
        except: pass

@bot.message_handler(func=lambda message: message.text.startswith('#'))
def send_stock_report(message):
    stock_id = message.text[1:].strip()
    if not stock_id:
        return
        
    processing_msg = bot.reply_to(message, f"🔍 正在查詢 {stock_id}，請稍候...")
    
    try:
        result = calculate_stock_prices(stock_id)
        bot.send_message(message.chat.id, result, parse_mode="HTML")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ 查詢失敗：\n<code>{e}</code>", parse_mode="HTML")
    finally:
        try: bot.delete_message(message.chat.id, processing_msg.message_id)
        except: pass

if __name__ == "__main__":
    # 1. 啟動網頁伺服器在背景執行緒 (滿足 Render 免費 Web Service 的要求)
    threading.Thread(target=run_web, daemon=True).start()
    
    # 2. 啟動 Telegram 機器人持續監聽
    print("🟢 機器人已啟動，正在監聽訊息...")
    bot.infinity_polling()

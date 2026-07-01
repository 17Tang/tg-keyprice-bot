import yfinance as yf
import pandas as pd
import telebot
import os
from datetime import datetime, timedelta

# 取得環境變數中的 Telegram Token
TG_TOKEN = os.environ.get('TG_TOKEN')
bot = telebot.TeleBot(TG_TOKEN)

def get_status(price, reference_price):
    """判斷價格是大於還是小於參考價"""
    return "🔴大於" if price > reference_price else "🟢小於"

def get_index_data(ticker_symbol, name):
    # 抓取過去 6 個月的資料
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period="6mo")
    
    if df.empty:
        return f"⚠️ <b>{name}</b> ({ticker_symbol}) 獲取資料失敗。\n------------------------\n"
    
    if len(df) < 3:
        return f"⚠️ <b>{name}</b> ({ticker_symbol}) 歷史資料不足以計算。\n------------------------\n"

    # 去掉時區資訊以便計算與格式化
    df.index = df.index.tz_localize(None)

    # ==========================================
    # 1. 取得最新收盤/現價 (T)
    # ==========================================
    latest_data = df.iloc[-1]
    latest_date = df.index[-1].strftime("%Y-%m-%d")
    latest_close = latest_data['Close']

    # ==========================================
    # 2. 今日防守價 (由昨日 T-1 K線推算) 
    # -> 最新收盤價主要與此組數據比對
    # ==========================================
    prev1_data = df.iloc[-2]
    prev1_date = df.index[-2].strftime("%Y-%m-%d")
    p1_high = prev1_data['High']
    p1_low = prev1_data['Low']
    
    today_key = (p1_high + p1_low) / 2
    today_short_def = p1_high + (p1_high - p1_low) * 0.382
    today_long_def = p1_low - (p1_high - p1_low) * 0.382

    # ==========================================
    # 3. 昨日防守價 (由前日 T-2 K線推算)
    # ==========================================
    prev2_data = df.iloc[-3]
    prev2_date = df.index[-3].strftime("%Y-%m-%d")
    p2_high = prev2_data['High']
    p2_low = prev2_data['Low']
    
    yesterday_key = (p2_high + p2_low) / 2
    yesterday_short_def = p2_high + (p2_high - p2_low) * 0.382
    yesterday_long_def = p2_low - (p2_high - p2_low) * 0.382

    # ==========================================
    # 4. 周、月級別關鍵價
    # ==========================================
    # 周級別數據
    df_weekly = df.resample('W-FRI').agg({'High': 'max', 'Low': 'min'})
    if df.index[-1].weekday() != 4: 
        week_data = df_weekly.iloc[-2]
    else:
        week_data = df_weekly.iloc[-1]
    week_key = (week_data['High'] + week_data['Low']) / 2

    # 月級別數據
    df_monthly = df.resample('ME').agg({'High': 'max', 'Low': 'min'})
    next_day = df.index[-1] + timedelta(days=1)
    if df.index[-1].month == next_day.month:
        month_data = df_monthly.iloc[-2]
    else:
        month_data = df_monthly.iloc[-1]
    month_key = (month_data['High'] + month_data['Low']) / 2

    # ==========================================
    # 5. 格式化輸出訊息
    # ==========================================
    msg = (
        f"📊 <b>{name}</b>\n"
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

@bot.message_handler(commands=['start', 'report'])
def send_report(message):
    processing_msg = bot.reply_to(message, "⏳ 正在抓取最新數據並計算多空防守價，請稍候...")
    
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    final_message = f"📋 <b>{today_str} 盤勢關鍵價報告</b>\n\n"
    
    # 注意：櫃買指數的 Yahoo 代碼已更正為 TWO.TW
    indices = [
        ("^TWII", "加權指數"),
        ("TWO.TW", "櫃買指數"),
        ("^SOX", "費半指數")
    ]
    
    for symbol, name in indices:
        final_message += get_index_data(symbol, name)
        
    bot.send_message(message.chat.id, final_message, parse_mode="HTML")
    bot.delete_message(message.chat.id, processing_msg.message_id)

if __name__ == "__main__":
    print("機器人已啟動，正在監聽訊息...")
    bot.infinity_polling()

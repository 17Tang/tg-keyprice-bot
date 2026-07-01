import yfinance as yf
import pandas as pd
import telebot
import os
from datetime import datetime, timedelta

# 取得環境變數中的 Telegram Token
TG_TOKEN = os.environ.get('TG_TOKEN')

# 初始化機器人
bot = telebot.TeleBot(TG_TOKEN)

def get_index_data(ticker_symbol, name):
    # 抓取過去 6 個月的資料以確保足夠計算周、月級別
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period="6mo")
    
    if df.empty:
        return f"⚠️ {name} ({ticker_symbol}) 獲取資料失敗。\n"

    # 去掉時區資訊以便計算
    df.index = df.index.tz_localize(None)

    # 1. 日級別數據 (最後一個交易日)
    daily_data = df.iloc[-1]
    y_high = daily_data['High']
    y_low = daily_data['Low']
    y_close = daily_data['Close']
    
    # 計算日關鍵價、防守價
    day_key = (y_high + y_low) / 2
    short_def = y_high + (y_high - y_low) * 0.382
    long_def = y_low - (y_high - y_low) * 0.382

    # 2. 周級別數據
    df_weekly = df.resample('W-FRI').agg({'High': 'max', 'Low': 'min'})
    if df.index[-1].weekday() != 4: 
        week_data = df_weekly.iloc[-2]
    else:
        week_data = df_weekly.iloc[-1]
    week_key = (week_data['High'] + week_data['Low']) / 2

    # 3. 月級別數據
    df_monthly = df.resample('ME').agg({'High': 'max', 'Low': 'min'})
    next_day = df.index[-1] + timedelta(days=1)
    if df.index[-1].month == next_day.month:
        month_data = df_monthly.iloc[-2]
    else:
        month_data = df_monthly.iloc[-1]
    month_key = (month_data['High'] + month_data['Low']) / 2

    # 判斷收盤價與關鍵價的關係
    day_status = "🔴大於" if y_close > day_key else "🟢小於"
    week_status = "🔴大於" if y_close > week_key else "🟢小於"
    month_status = "🔴大於" if y_close > month_key else "🟢小於"

    # 格式化訊息
    msg = (
        f"📊 <b>{name}</b>\n"
        f"🔸 近日收盤: {y_close:.2f}\n"
        f"🛡️ 空方防守價: {short_def:.2f}\n"
        f"🛡️ 多方防守價: {long_def:.2f}\n"
        f"🔑 日關鍵價: {day_key:.2f} ({day_status})\n"
        f"🔑 周關鍵價: {week_key:.2f} ({week_status})\n"
        f"🔑 月關鍵價: {month_key:.2f} ({month_status})\n"
        "------------------------\n"
    )
    return msg

# 設定監聽指令：當使用者輸入 /start 或 /report 時觸發
@bot.message_handler(commands=['start', 'report'])
def send_report(message):
    # 先回覆一條訊息讓使用者知道機器人有收到指令
    processing_msg = bot.reply_to(message, "⏳ 正在抓取最新數據並計算關鍵價，請稍候...")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    final_message = f"📋 <b>{today_str} 盤勢關鍵價報告</b>\n\n"
    
    indices = [
        ("^TWII", "加權指數"),
        ("^TWO", "櫃買指數"),
        ("^SOX", "費半指數")
    ]
    
    for symbol, name in indices:
        final_message += get_index_data(symbol, name)
        
    # 發送最終結果，並刪除剛才的「計算中」提示訊息保持版面乾淨
    bot.send_message(message.chat.id, final_message, parse_mode="HTML")
    bot.delete_message(message.chat.id, processing_msg.message_id)

if __name__ == "__main__":
    print("機器人已啟動，正在監聽訊息...")
    # infinity_polling 可以讓機器人持續運行，遇到短暫網路錯誤也會自動重試
    bot.infinity_polling()
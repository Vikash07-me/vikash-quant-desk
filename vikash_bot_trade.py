import streamlit as st
import pandas as pd
import MetaTrader5 as mt5
import requests
from twilio.rest import Client
import streamlit.components.v1 as components
from datetime import datetime
import os
import time

# --- 🛰️ THE ULTIMATE QUANTUM SLATE TERMINAL CONFIG ---
st.set_page_config(page_title="Vikash's Master Quant Strategy Desk", layout="wide")

st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] { background-color: #0D0F14 !important; color: #ABC4FF; font-family: monospace; }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 1.5rem !important; max-width: 98% !important; }
    .terminal-header { background: linear-gradient(90deg, #161A25 0%, #1F2635 100%); border-left: 4px solid #6366F1; padding: 15px 25px; border-radius: 6px; margin-bottom: 20px; }
    .t-title { font-size: 32px !important; font-weight: 800; color: #FFFFFF; }
    .panel-card { background: #161A25; border: 1px solid #242B3D; border-radius: 8px; padding: 16px; margin-bottom: 15px; }
    .panel-title { font-size: 13px !important; font-weight: 700; color: #94A3B8; text-transform: uppercase; border-bottom: 1px solid #242B3D; padding-bottom: 6px; margin-bottom: 12px; }
    .pos-card { background: #1C2333; border-left: 3px solid #6366F1; padding: 12px; border-radius: 4px; margin-bottom: 10px; }
    .strategy-badge { background: #1E3A8A; color: #93C5FD; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; text-transform: uppercase; }
    div[data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 20px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 🟢 CONFIGURATIONS & RISK GUARDRAILS ---
TWILIO_ACCOUNT_SID = "YOUR_TWILIO_ACCOUNT_SID"
TWILIO_AUTH_TOKEN = "YOUR_TWILIO_AUTH_TOKEN"
FROM_WHATSAPP = "whatsapp:+14155238886"
TO_WHATSAPP_NUMBER = "whatsapp:+91XXXXXXXXXX"

EXCEL_PATH = r"C:\Users\DELL\Desktop\Test\trading_log.xlsx"
BRAIN_PATH = r"C:\Users\DELL\Desktop\Test\bot_learning_brain.xlsx"
INITIAL_CAPITAL = 5000.0
MARGIN_PER_TRADE = 1000.0

WEEKLY_TARGET = 500.0
MAX_TOTAL_LOSS_LIMIT = INITIAL_CAPITAL * 0.10  
MAX_DAILY_LOSS_LIMIT = INITIAL_CAPITAL * 0.05  

# Core Database Initializer
if not os.path.exists(EXCEL_PATH):
    pd.DataFrame(columns=["Date", "Asset", "Type", "Strategy Used", "Lot Size", "Leverage", "Position Size ($)", "Risk Capital ($)", "Entry Price", "Current Price", "SL Level", "SL Amount ($)", "TP Level", "TP Amount ($)", "R:R Ratio", "P&L ($)", "Status", "Setup Level", "Reason", "Analysis"]).to_excel(EXCEL_PATH, index=False)

if not os.path.exists(BRAIN_PATH):
    pd.DataFrame(columns=["Asset", "Failed_Zone_Min", "Failed_Zone_Max", "Failure_Count"]).to_excel(BRAIN_PATH, index=False)

def send_whatsapp_alert(message):
    if TWILIO_ACCOUNT_SID != "YOUR_TWILIO_ACCOUNT_SID":
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            client.messages.create(body=message, from_=FROM_WHATSAPP, to=TO_WHATSAPP_NUMBER)
        except: pass

def get_live_market_news():
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        res = requests.get(url, timeout=3).json()
        return [f"📰 *{item['source']}*: {item['title'][:90]}..." for item in res['Data'][:4]]
    except: return ["⚠️ Macro News Engine Processing Stream Latency..."]

# --- SAFE MT5 INITIALIZATION ---
mt5_healthy = False
account_leverage = 500  
if mt5.initialize(timeout=3000):
    mt5_healthy = True
    acc_info = mt5.account_info()
    if acc_info: account_leverage = acc_info.leverage

# --- 🧠 BRAIN INTEGRATION ---
def check_brain_avoidance(asset, check_price):
    if not os.path.exists(BRAIN_PATH): return False
    try:
        df_brain = pd.read_excel(BRAIN_PATH)
        for _, row in df_brain[df_brain['Asset'] == asset].iterrows():
            if row['Failed_Zone_Min'] <= check_price <= row['Failed_Zone_Max'] and row['Failure_Count'] >= 2: return True
    except: pass
    return False

def update_brain_failure(asset, execution_range_min, execution_range_max):
    try:
        df_brain = pd.read_excel(BRAIN_PATH)
        match = df_brain[(df_brain['Asset'] == asset) & (df_brain['Failed_Zone_Min'] == execution_range_min)]
        if not match.empty: df_brain.loc[match.index, 'Failure_Count'] += 1
        else: df_brain = pd.concat([df_brain, pd.DataFrame([{"Asset": asset, "Failed_Zone_Min": execution_range_min, "Failed_Zone_Max": execution_range_max, "Failure_Count": 1}])], ignore_index=True)
        df_brain.to_excel(BRAIN_PATH, index=False)
    except: pass

# --- 🧮 SYSTEM MATHEMATICS ---
def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().tolist()

def calculate_dynamic_lot(symbol, stop_loss_distance, setup_strength, daily_loss_left):
    if stop_loss_distance <= 0: return 0.01
    risk_percent = 0.015 if setup_strength == "HIGH" else 0.005
    allowed_risk_amount = INITIAL_CAPITAL * risk_percent
    if allowed_risk_amount > daily_loss_left: allowed_risk_amount = daily_loss_left * 0.8
    if allowed_risk_amount <= 0: return 0.0 
    multiplier = 100.0 if ("XAUUSD" in symbol or "GOLD" in symbol) else 50.0
    calculated_lot = round(allowed_risk_amount / (stop_loss_distance * multiplier), 2)
    return max(0.01, min(calculated_lot, 0.15))

# --- 🎯 LIVE AUTO-TRADING EXECUTION ENGINE ---
def execute_mt5_order(symbol, trade_type, price, sl, tp, strategy_name, setup_level, reason, lot_size, sl_amt, tp_amt):
    if not mt5_healthy or lot_size <= 0: return False
    order_type = mt5.ORDER_TYPE_BUY if trade_type == "BUY" else mt5.ORDER_TYPE_SELL
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(lot_size),
        "type": order_type, "price": float(price), "sl": float(sl), "tp": float(tp),
        "deviation": 10, "magic": 999999, "comment": f"Omni_{strategy_name[:4]}",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        contract_m = 100.0 if "XAUUSD" in symbol else 5000.0
        report = f"🤖 *OMNIPRESENT QUANT CORE EXECUTED:* {strategy_name}\n\n" \
                 f"📦 *Asset:* {symbol} | *Action:* {trade_type} | *Lots:* {lot_size}\n" \
                 f"🎯 *Trigger Coordinates:* {setup_level}\n" \
                 f"💸 *Execution Entry:* ${price:.3f}\n" \
                 f"🛡️ *SL Line:* ${sl:.3f} (Est Amount: -${sl_amt:.2f})\n" \
                 f"🎯 *TP Target:* ${tp:.3f} (Est Amount: +${tp_amt:.2f})\n\n" \
                 f"📖 *STRATEGY PSYCHOLOGY DEEP STUDY:*\n{reason}"
        send_whatsapp_alert(report)
        return True
    return False

# --- 🛰️ THE OMNIPRESENT MULTI-STRATEGY SCANNER ENGINE ---
def run_automatic_strategy_scanner(df_log, daily_loss_left):
    if not mt5_healthy or daily_loss_left <= 0: return df_log
    
    symbols_to_trade = {"XAUUSD": "GOLD (XAUUSD)", "XAGUSD": "SILVER (XAGUSD)"}
    has_open_trade = not df_log[df_log['Status'] == 'OPEN'].empty if not df_log.empty else False
    
    if not has_open_trade:
        for sym, display_name in symbols_to_trade.items():
            mt5.symbol_select(sym, True)
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 30)
            if rates is not None and len(rates) >= 30:
                closes = [r['close'] for r in rates]
                highs = [r['high'] for r in rates]
                lows = [r['low'] for r in rates]
                c_close = closes[-1]
                
                strat_used, trade_type, setup_level, reason, strength = None, None, "", "", "NORMAL"
                
                # 1. FAIR VALUE GAP (FVG) SCANNER
                if highs[-3] < lows[-1] and closes[-2] > highs[-3]:
                    strat_used, trade_type = "Fair Value Gap (FVG)", "BUY"
                    setup_level = f"Gap Zone: ${highs[-3]:.3f} - ${lows[-1]:.3f}"
                    reason = f"INSTITUTIONAL IMBALANCE: Price is filling an inefficient data deficit between {highs[-3]:.3f} and {lows[-1]:.3f} before continuation nodes scale."
                    strength = "HIGH"
                elif lows[-3] > highs[-1] and closes[-2] < lows[-3]:
                    strat_used, trade_type = "Fair Value Gap (FVG)", "SELL"
                    setup_level = f"Gap Zone: ${lows[-3]:.3f} - ${highs[-1]:.3f}"
                    reason = f"INSTITUTIONAL IMBALANCE: Market imbalance created an algorithmic target high layer between {lows[-3]:.3f} and {highs[-1]:.3f}."
                    strength = "HIGH"

                # 2. SMART MONEY TRAP (SMT / LIQUIDITY SWEEP) SCANNER
                if not strat_used:
                    recent_lows = lows[-20:-2]
                    recent_highs = highs[-20:-2]
                    floor_support = min(recent_lows)
                    ceiling_resistance = max(recent_highs)
                    
                    if lows[-1] < floor_support and c_close > floor_support:
                        strat_used, trade_type = "SMC Liquidity Sweep (SMT)", "BUY"
                        setup_level = f"Floor: ${floor_support:.3f} | Sweep: ${lows[-1]:.3f}"
                        reason = f"SMART MONEY TRAP: Retail stops engineered a liquidity capture below {floor_support:.3f}. System absorbed sell-side volume."
                        strength = "HIGH"
                    elif highs[-1] > ceiling_resistance and c_close < ceiling_resistance:
                        strat_used, trade_type = "SMC Liquidity Sweep (SMT)", "SELL"
                        setup_level = f"Ceiling: ${ceiling_resistance:.3f} | Sweep: ${highs[-1]:.3f}"
                        reason = f"SMART MONEY TRAP: Breakout traps high spike at {highs[-1]:.3f} absorbed order blocks."
                        strength = "HIGH"

                # 3. CORE STRATEGIES (SMC CHOCH, W/M PATTERNS, EMA OVERLAYS)
                if not strat_used:
                    max_high, min_low = max(highs[-6:-1]), min(lows[-6:-1])
                    ema9, ema15 = calculate_ema(closes, 9), calculate_ema(closes, 15)
                    
                    if c_close > max_high:
                        strat_used, trade_type = "SMC CHOCH Breakout", "BUY"
                        setup_level = f"${max_high:.3f}"
                        reason = f"SMC CHOCH: Break past immediate swing resistance high at {setup_level} shift distribution matrix."
                    elif c_close < min_low:
                        strat_used, trade_type = "SMC CHOCH Breakout", "SELL"
                        setup_level = f"${min_low:.3f}"
                        reason = f"SMC CHOCH: Structural break past immediate floor zone at {setup_level} complete redistribution loop."
                    elif abs(lows[-1] - min(lows[-15:-1])) < (c_close * 0.0005) and c_close > closes[-2]:
                        strat_used, trade_type = "Double Bottom Reversal", "BUY"
                        setup_level = f"Double Floor at ${lows[-1]:.3f}"
                        reason = f"RETAIL DOUBLE BOTTOM: Clear W-pattern double support test. Bearish momentum exhausted completely."
                    elif (ema9[-2] <= ema15[-2]) and (ema9[-1] > ema15[-1]):
                        strat_used, trade_type = "EMA Trend Cross (9/15)", "BUY"
                        setup_level = f"9-EMA Cross Above 15-EMA"
                        reason = f"RETAIL TREND CROSSOVER: Moving average breakout protocol active."

                # --- ARBITRATION EXECUTION PUSH WITH AMOUNT MATRIX ---
                if strat_used and not check_brain_avoidance(display_name, c_close):
                    sl_dist = c_close * 0.003
                    sl_p = (c_close - sl_dist) if trade_type == "BUY" else (c_close + sl_dist)
                    tp_p = (c_close + (sl_dist * 2.0)) if trade_type == "BUY" else (c_close - (sl_dist * 2.0))
                    
                    lot_size = calculate_dynamic_lot(sym, sl_dist, strength, daily_loss_left)
                    contract_m = 100.0 if "XAU" in sym else 5000.0
                    
                    est_sl_amount = abs(sl_dist * (lot_size * 100.0 if "XAU" in sym else lot_size * 5000.0))
                    est_tp_amount = abs((sl_dist * 2.0) * (lot_size * 100.0 if "XAU" in sym else lot_size * 5000.0))
                    
                    if execute_mt5_order(sym, trade_type, c_close, sl_p, tp_p, strat_used, setup_level, reason, lot_size, est_sl_amount, est_tp_amount):
                        new_row = {
                            "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Asset": display_name, "Type": trade_type,
                            "Strategy Used": strat_used, "Lot Size": float(lot_size), "Leverage": f"1:{account_leverage}", 
                            "Position Size ($)": float(lot_size * contract_m * c_close), "Risk Capital ($)": float(MARGIN_PER_TRADE),
                            "Entry Price": float(c_close), "Current Price": float(c_close), "SL Level": float(sl_p), "SL Amount ($)": float(est_sl_amount),
                            "TP Level": float(tp_p), "TP Amount ($)": float(est_tp_amount), "R:R Ratio": "1:2 Standards",
                            "P&L ($)": 0.0, "Status": "OPEN", "Setup Level": setup_level, "Reason": reason, "Analysis": "Omni Nodes Live Monitoring."
                        }
                        return pd.concat([df_log, pd.DataFrame([new_row])], ignore_index=True)
    return df_log

# --- 📊 EXPOSURE TRACKING DATA ENGINE ---
live_rates_display = {}

def process_all_hybrid_markets():
    try: 
        df_log = pd.read_excel(EXCEL_PATH)
        if "Strategy Used" not in df_log.columns: df_log["Strategy Used"] = "SMC CHOCH Breakout"
        if "Leverage" not in df_log.columns: df_log["Leverage"] = f"1:{account_leverage}"
        if "Position Size ($)" not in df_log.columns: df_log["Position Size ($)"] = 0.0
        if "Risk Capital ($)" not in df_log.columns: df_log["Risk Capital ($)"] = MARGIN_PER_TRADE
        if "SL Level" not in df_log.columns: df_log.rename(columns={"SL": "SL Level"}, inplace=True) if "SL" in df_log.columns else pd.Series()
        if "TP Level" not in df_log.columns: df_log.rename(columns={"TP": "TP Level"}, inplace=True) if "TP" in df_log.columns else pd.Series()
        if "SL Amount ($)" not in df_log.columns: df_log["SL Amount ($)"] = 25.00
        if "TP Amount ($)" not in df_log.columns: df_log["TP Amount ($)"] = 50.00
        if "Lot Size" not in df_log.columns: df_log["Lot Size"] = 0.01
        if "Setup Level" not in df_log.columns: df_log["Setup Level"] = "N/A"
            
        cols_to_float = ["Lot Size", "Position Size ($)", "Risk Capital ($)", "Entry Price", "Current Price", "SL Level", "SL Amount ($)", "TP Level", "TP Amount ($)", "P&L ($)"]
        for col in cols_to_float:
            if col in df_log.columns: df_log[col] = pd.to_numeric(df_log[col], errors='coerce').astype(float)
    except: return pd.DataFrame()
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    df_today = df_log[df_log['Date'].astype(str).str.contains(today_str)] if not df_log.empty else pd.DataFrame()
    today_loss = abs(df_today[df_today['P&L ($)'] < 0]['P&L ($)'].sum()) if not df_today.empty else 0.0
    daily_loss_left = MAX_DAILY_LOSS_LIMIT - today_loss
    
    total_loss_so_far = abs(df_log[df_log['P&L ($)'] < 0]['P&L ($)'].sum()) if not df_log.empty else 0.0
    if total_loss_so_far >= MAX_TOTAL_LOSS_LIMIT: daily_loss_left = 0.0 

    df_log = run_automatic_strategy_scanner(df_log, daily_loss_left)

    mt5_markets = {"GOLD (XAUUSD)": "XAUUSD", "SILVER (XAGUSD)": "XAGUSD"}
    if mt5_healthy:
        for name, mt5_sym in mt5_markets.items():
            tick = mt5.symbol_info_tick(mt5_sym)
            if tick: live_rates_display[name] = float(tick.ask)

    if not df_log.empty:
        df_log['Status'] = df_log['Status'].astype(str).str.upper().str.strip()
        for idx, row in df_log.iterrows():
            if row['Status'] == 'OPEN':
                asset_name = str(row['Asset']).upper().strip()
                current_price = live_rates_display.get(asset_name)
                current_lot = float(row['Lot Size']) if pd.notna(row['Lot Size']) else 0.01
                entry = float(row['Entry Price'])
                multiplier = current_lot * 100.0 if "GOLD" in asset_name else current_lot * 5000.0

                if current_price is not None:
                    df_log.loc[idx, 'Current Price'] = float(current_price)
                    sl, tp = float(row['SL Level']), float(row['TP Level'])
                    pnl = (current_price - entry) * multiplier if row['Type'] == "BUY" else (entry - current_price) * multiplier
                    df_log.loc[idx, 'P&L ($)'] = float(round(pnl, 2))

                    if (row['Type'] == "BUY" and current_price <= sl) or (row['Type'] == "SELL" and current_price >= sl):
                        df_log.loc[idx, 'Status'] = 'CLOSED (SL)'
                        analysis = f"Omni System Alert. Strategy '{row['Strategy Used']}' hit stop level. Total capital hit recorded: -${abs(pnl):.2f}."
                        df_log.loc[idx, 'Analysis'] = analysis
                        update_brain_failure(row['Asset'], entry * 0.998, entry * 1.002)
                        send_whatsapp_alert(f"❌ *OMNI SL HIT DISCOVERY*\n\n📦 *Asset:* {row['Asset']} | *Pattern:* {row['Strategy Used']}\n🧠 *Post-Mortem:* {analysis}")
                    elif (row['Type'] == "BUY" and current_price >= tp) or (row['Type'] == "SELL" and current_price <= tp):
                        df_log.loc[idx, 'Status'] = 'CLOSED (TP)'
                        analysis = f"Omni Strategy Target Smash! '{row['Strategy Used']}' secured absolute gain: +${pnl:.2f}."
                        df_log.loc[idx, 'Analysis'] = analysis
                        send_whatsapp_alert(f"🎯 *OMNI PROFIT SMASHED!*\n\n📦 *Asset:* {row['Asset']} | *Pattern:* {row['Strategy Used']}\n🧠 *Analysis:* {analysis}")

    df_log.to_excel(EXCEL_PATH, index=False)
    return df_log

df_all = process_all_hybrid_markets()
df_open = df_all[df_all['Status'] == 'OPEN'] if not df_all.empty else pd.DataFrame()
df_closed = df_all[df_all['Status'].str.contains('CLOSED', na=False)] if not df_all.empty else pd.DataFrame()
realized_pnl = df_closed['P&L ($)'].sum() if not df_closed.empty else 0.0
unrealized_pnl = df_open['P&L ($)'].sum() if not df_open.empty else 0.0
net_equity = INITIAL_CAPITAL + realized_pnl + unrealized_pnl

today_str = datetime.now().strftime("%Y-%m-%d")
df_t = df_all[df_all['Date'].astype(str).str.contains(today_str)] if not df_all.empty else pd.DataFrame()
t_loss = abs(df_t[df_t['P&L ($)'] < 0]['P&L ($)'].sum()) if not df_t.empty else 0.0
daily_risk_left = MAX_DAILY_LOSS_LIMIT - t_loss
week_drawdown_left = MAX_TOTAL_LOSS_LIMIT - abs(realized_pnl if realized_pnl < 0 else 0)

# --- 🏢 INTERFACE PROTOCOL RENDER ---
tabs = st.tabs(["🚀 LIVE OMNIPRESENT QUANT DESK", "📚 QUANT REASONING LEDGER & AUDITING"])

with tabs[0]:
    st.markdown("""
    <div class='terminal-header'>
        <div class='t-title'>⚡ VIKASH QUANTUM-DESK PRO (MASTER QUANT SUITE)</div>
        <div class='t-sub'>Omnipresent Multi-Scanner Active • Weekly Target: $500 • Currency Node Analysis Feed</div>
    </div>
    """, unsafe_allow_html=True)
    
    c_l, c_c, c_r = st.columns([1, 1.4, 1.4])
    
    with c_l:
        st.markdown("<div class='panel-card'><div class='panel-title'>🏢 ENGINE STATUS</div>", unsafe_allow_html=True)
        st.write("🟢 AUTOMATION ENGINE: ON-LINE")
        st.caption(f"MT5 Link Status: {'CONNECTED' if mt5_healthy else 'DISCONNECTED'}")
        st.write("---")
        st.markdown("<div class='panel-card'><div class='panel-title'>📰 Live Macro News Feeds</div>", unsafe_allow_html=True)
        for feed in get_live_market_news(): st.caption(feed)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with c_c:
        st.markdown("<div class='panel-card'><div class='panel-title'>🛡️ ACCOUNT METRICS & ENGINE GUARDRAILS</div>", unsafe_allow_html=True)
        col_m1, col_m2 = st.columns(2)
        with col_m1: st.metric("Net Equity ($)", f"${net_equity:,.2f}")
        with col_m2: st.metric("Realized P&L ($)", f"${realized_pnl:+.2f}", f"Goal Progress: {realized_pnl:.2f}/{WEEKLY_TARGET}")
        st.write("---")
        col_m3, col_m4 = st.columns(2)
        with col_m3: st.metric("Daily Risk Limit Left", f"${daily_risk_left:,.2f}", f"Max Risk: ${MAX_DAILY_LOSS_LIMIT}")
        with col_m4: st.metric("Max Week Drawdown Left", f"${week_drawdown_left:,.2f}", f"Max Week Risk: ${MAX_TOTAL_LOSS_LIMIT}")
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='panel-card'><div class='panel-title'>🚨 ACTIVE QUANTUM EXPOSURE NODE (Floating M2M)</div>", unsafe_allow_html=True)
        if not df_open.empty:
            for idx, r in df_open.iterrows():
                p_c = "#089981" if r['P&L ($)'] >= 0 else "#F23645"
                strat_name = r['Strategy Used'] if 'Strategy Used' in df_open.columns else "Quantum Scanner"
                st.markdown(f"""<div class='pos-card'>
                    <b>{r['Asset']} ({r['Type']})</b> &nbsp; <span class='strategy-badge'>{strat_name}</span><br/>
                    <b>💰 Margin Used (Capital):</b> ${r['Risk Capital ($)']:.2f} &nbsp;|&nbsp; <b>Leverage:</b> {r['Leverage']}<br/>
                    Entry: ${r['Entry Price']:.3f} | Lots: {r['Lot Size']} | Size: ${r['Position Size ($)']:,.2f}<br/>
                    🛡️ SL: ${r['SL Level']:.3f} (<span style='color:#F23645; font-weight:bold;'>Max Loss: -${r['SL Amount ($)']:.2f}</span>)<br/>
                    🎯 TP: ${r['TP Level']:.3f} (<span style='color:#089981; font-weight:bold;'>Max Profit: +${r['TP Amount ($)']:.2f}</span>)<br/>
                    ⚖️ <b>Risk-Reward Ratio:</b> {r['R:R Ratio']}<br/>
                    <span style='color:{p_c}; font-weight:bold; font-size:14px; margin-top:5px; display:inline-block;'>Floating P&L: ${r['P&L ($)']}</span>
                </div>""", unsafe_allow_html=True)
        else: st.write("Omnipresent scanners sweeping liquidity grids (FVG, SMT Traps, SMC CHOCH, EMAs)...")
        st.markdown("</div>", unsafe_allow_html=True)
        
    with c_r:
        st.markdown("<div class='panel-card'><div class='panel-title'>🎓 Live Neural System Psychology (Study Mode)</div>", unsafe_allow_html=True)
        if not df_open.empty: st.info(df_open.iloc[0]['Reason'])
        else: st.caption("Scanners hunting structures. Read the Ledger Tab below to analyze historical matrix setups!")
        st.markdown("</div>", unsafe_allow_html=True)

    # --- 🔥 DYNAMIC CHART OVERLAY PROTOCOL ACTIVE (CHANGES HERE ONLY) ---
    if not df_open.empty:
        sym_map = {"GOLD (XAUUSD)": "FX_IDC:XAUUSD", "SILVER (XAGUSD)": "FX_IDC:XAGUSD"}
        tv_symbol = sym_map.get(df_open.iloc[0]['Asset'], "FX_IDC:XAUUSD")
        
        # Pull values for live mapping onto the graphic frames
        entry_val = df_open.iloc[0]['Entry Price']
        sl_val = df_open.iloc[0]['SL Level']
        tp_val = df_open.iloc[0]['TP Level']
        sl_amt_val = df_open.iloc[0]['SL Amount ($)']
        tp_amt_val = df_open.iloc[0]['TP Amount ($)']
        pnl_val = df_open.iloc[0]['P&L ($)']
        pnl_color = "#089981" if pnl_val >= 0 else "#F23645"
        pnl_sign = "+" if pnl_val >= 0 else ""
        
        # Advanced interactive chart rendering wrapper with continuous state updates
        tv_html = f"""
        <div style="position: relative; width: 100%; height: 520px; background-color: #131722; border-radius: 8px; overflow: hidden; border: 1px solid #242B3D;">
            <iframe src="https://s.tradingview.com/widgetembed/?symbol={tv_symbol}&interval=5&theme=dark&style=1&timezone=Asia%2FKolkata" style="width: 100%; height: 100%; border: none;"></iframe>
            
            <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; box-sizing: border-box; font-family: monospace;">
                
                <div style="position: absolute; top: 22%; width: 100%; border-top: 2px dashed #089981; display: flex; justify-content: space-between; padding: 2px 15px; background: rgba(8, 153, 129, 0.08);">
                    <span style="color: #089981; font-weight: bold; background: #0D0F14; padding: 0 6px; border-radius: 3px; font-size: 12px; border: 1px solid #089981;">🎯 TP LEVEL: ${tp_val:.3f}</span>
                    <span style="color: #FFFFFF; font-weight: bold; background: #089981; padding: 0 8px; border-radius: 3px; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.5);">Est Profit: +${tp_amt_val:.2f}</span>
                </div>
                
                <div style="position: absolute; top: 48%; width: 100%; border-top: 2px solid {pnl_color}; display: flex; justify-content: space-between; padding: 2px 15px; background: rgba(255,255,255,0.02);">
                    <span style="color: #FFFFFF; font-weight: bold; background: #1C2333; padding: 0 6px; border-radius: 3px; font-size: 12px; border: 1px solid #6366F1;">🔹 ENTRY PRICE: ${entry_val:.3f}</span>
                    <span style="color: #FFFFFF; font-weight: bold; background: {pnl_color}; padding: 3px 10px; border-radius: 4px; font-size: 13px; box-shadow: 0 0 15px {pnl_color}; border: 1px solid #FFFFFF;">RUNNING P&L: {pnl_sign}${pnl_val:.2f}</span>
                </div>
                
                <div style="position: absolute; top: 74%; width: 100%; border-top: 2px dashed #F23645; display: flex; justify-content: space-between; padding: 2px 15px; background: rgba(242, 54, 69, 0.08);">
                    <span style="color: #F23645; font-weight: bold; background: #0D0F14; padding: 0 6px; border-radius: 3px; font-size: 12px; border: 1px solid #F23645;">🛡️ SL FLOOR: ${sl_val:.3f}</span>
                    <span style="color: #FFFFFF; font-weight: bold; background: #F23645; padding: 0 8px; border-radius: 3px; font-size: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.5);">Risk Cap: -${sl_amt_val:.2f}</span>
                </div>
                
            </div>
        </div>
        """
        components.html(tv_html, height=530, scrolling=False)
    else:
        # Fallback baseline chart if no active trades running
        st.info("No active exposure locked. Displaying baseline market tracking feed.")
        components.html(f"<iframe src='https://s.tradingview.com/widgetembed/?symbol=FX_IDC:XAUUSD&interval=5&theme=dark' style='width: 100%; height: 480px; border: none;'></iframe>", height=490)

with tabs[1]:
    st.markdown("<div class='panel-card'><div class='panel-title'>📝 Post-Mortem AI Trade Logs & Ledger</div>", unsafe_allow_html=True)
    if not df_all.empty:
        df_disp = df_all.copy().iloc[::-1]
        import io
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as wr: df_disp.to_excel(wr, index=False)
        st.download_button(label="📥 DOWNLOAD ALL EXPOSURES WITH CASH POTENTIAL NODES", data=buf.getvalue(), file_name="Vikash_MasterQuant_Ledger.xlsx", mime="application/vnd.sheet")
        st.write("---")
        
        st.dataframe(
            df_disp, 
            use_container_width=True, 
            hide_index=True,
            column_order=["Date", "Asset", "Strategy Used", "Type", "Lot Size", "Position Size ($)", "Risk Capital ($)", "Entry Price", "Current Price", "SL Level", "SL Amount ($)", "TP Level", "TP Amount ($)", "R:R Ratio", "P&L ($)", "Status", "Reason", "Analysis"],
            column_config={
                "Risk Capital ($)": st.column_config.NumberColumn("Used Capital ($)", format="$%.2f"),
                "SL Amount ($)": st.column_config.NumberColumn("Potential SL Loss ($)", format="-$%.2f"),
                "TP Amount ($)": st.column_config.NumberColumn("Potential TP Profit ($)", format="+$%.2f"),
                "P&L ($)": st.column_config.NumberColumn("Final P&L ($)", format="$%.2f")
            }
        )
    else: st.write("No closed data packets under current cycle.")
    st.markdown("</div>", unsafe_allow_html=True)

time.sleep(6)
st.rerun()
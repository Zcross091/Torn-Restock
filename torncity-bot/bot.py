import sys, types
import os
from threading import Thread
from flask import Flask
import requests
import json
import discord
from discord.ext import commands

# --- TORN API Key ---
TORN_API_KEY = "1Wu5Br5fy7gbb7gU"

# =========================================================================
# === FIX: Python 3.13 & Deployment Audio/Voice Module Mocking (Must be FIRST) ===
# =========================================================================

# 1. Mock 'audioop' to prevent ModuleNotFoundError, as it's the root dependency issue
# This ensures that when discord.py tries to import audioop, it finds an empty module instead of crashing.
try:
    if 'audioop' not in sys.modules:
        sys.modules['audioop'] = types.ModuleType('audioop')
except Exception as e:
    print(f"Failed to mock audioop: {e}")

# 2. Mock Voice/Player modules to prevent subsequent failures inside discord.py
try:
    class VoiceProtocol(object): pass
    class VoiceClient(object): pass
    
    # Mock discord.player
    sys.modules["discord.player"] = types.ModuleType("discord.player")
    
    # Mock discord.voice_client, providing the classes the library needs
    voice_client = types.ModuleType("discord.voice_client")
    voice_client.VoiceClient = VoiceClient
    voice_client.VoiceProtocol = VoiceProtocol
    sys.modules["discord.voice_client"] = voice_client
    
except Exception as e:
    print(f"Voice module mocking failed: {e}")
# =========================================================================


# --- Web server for Render keep-alive ---
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ Torn City Bot is alive!"
def run_web():
    port = int(os.environ.get("PORT", 8080))
    # Note: Flask runs in a thread here, common for keeping a Render service alive
    app.run(host="0.0.0.0", port=port)
# ---------------------------------------------------------------------------


# --- Fixed Item Data (Needed for Vendor Buy Price) ---
# Structure: [Item ID, Item Name, Vendor Buy Price, Country, Category]
FOREIGN_ITEMS_DATA = [
    [260, "Xanax", 7600, "South Africa", "Drug"], 
    [267, "Camel Plushie", 14000, "United Arab Emirates", "Plushie"],
    [273, "Tribulus Omanense", 6000, "United Arab Emirates", "Flower"],
    [270, "Peony", 5000, "China", "Flower"],
    [276, "Chinese Dragon Plushie", 400, "China", "Plushie"],
    [266, "Cherry Blossom", 500, "Japan", "Flower"],
    [277, "Panda Plushie", 400, "Argentina", "Plushie"],
    [271, "African Violet", 2000, "South Africa", "Flower"],
    [278, "Lion Plushie", 400, "South Africa", "Plushie"],
    [269, "Jaguar Plushie", 10000, "Mexico", "Plushie"],
    [264, "Banana Orchid", 4000, "Cayman Islands", "Flower"],
    [265, "Crocus", 600, "Canada", "Flower"],
    [275, "Polar Bear Plushie", 500, "Canada", "Plushie"],
    [272, "Edelweiss", 900, "Switzerland", "Flower"],
    [261, "Orchid", 700, "Hawaii", "Flower"],
    [274, "Sea Turtle Plushie", 500, "Hawaii", "Plushie"],
]

# --- Bot Commands ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.command(name='flyprofits')
async def fly_profits(ctx):
    """Fetches and displays the top 5 most profitable foreign items based on live market price."""
    
    await ctx.send("✈️ **Fetching Live Profit Data...** This may take a moment.")
    
    profit_data = []
    item_ids = [str(item[0]) for item in FOREIGN_ITEMS_DATA]
    
    try:
        url = f"https://api.torn.com/market/{','.join(item_ids)}?selections=itemmarket&key={TORN_API_KEY}"
        response = requests.get(url, timeout=10)
        response.raise_for_status() 
        live_prices = response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"Torn API Error: {e}")
        await ctx.send(f"❌ **API Error:** Could not connect to Torn API or key invalid. Check logs for details.")
        return
    
    # --- 2. Calculate Gross Profit for each item ---
    for item_id, name, vendor_buy, country, category in FOREIGN_ITEMS_DATA:
        item_id_str = str(item_id)
        
        if item_id_str not in live_prices or 'itemmarket' not in live_prices[item_id_str] or not live_prices[item_id_str]['itemmarket']:
            continue 
            
        market_sell_price = min(listing['cost'] for listing in live_prices[item_id_str]['itemmarket'])
        gross_profit = market_sell_price - vendor_buy
        
        # --- Apply the High-Profit Threshold Filter ---
        # Only list items where the profit is > $15,000 to ensure worthwhile trips 
        if gross_profit >= 15000:
            profit_data.append({
                "name": name,
                "country": country,
                "vendor_buy": vendor_buy,
                "market_sell": market_sell_price,
                "profit": gross_profit,
                "category": category
            })
            
    # --- 3. Sort by Profit and Display ---
    profit_data.sort(key=lambda x: x['profit'], reverse=True)
    
    if not profit_data:
        await ctx.send("No items found with a Gross Profit over $15,000 at this time. Market might be low.")
        return

    msg = "💰 **Top 5 Live High-Profit Foreign Items (Gross Profit > $15,000)**\n"
    msg += "*(Based on lowest price in Item Market)*\n\n"
    
    for i, item in enumerate(profit_data[:5]):
        msg += (
            f"**{i+1}. {item['name']}** ({item['country']})\n"
            f"> Buy: **${item['vendor_buy']:,}** | Sell: **${item['market_sell']:,}** | **LIVE PROFIT: ${item['profit']:,}**\n"
        )

    await ctx.send(msg)

# --- Start bot and web server ---
if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.getenv("DISCORD_TOKEN"))

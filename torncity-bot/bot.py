import sys, types
import os
# =========================================================================
# === CRITICAL FIX: Voice Module Mocking (MOVED TO TOP) ===
# This block must run BEFORE the 'import discord' statement.
try:
    # 1. Mock 'audioop' first, as it's the first module to fail.
    sys.modules['audioop'] = types.ModuleType('audioop')  
    
    # 2. Mock Voice Protocols needed by discord.py internals
    class VoiceProtocol(object): pass
    class VoiceClient(object): pass
    
    # 3. Mock the modules that reference the above classes
    sys.modules["discord.player"] = types.ModuleType("discord.player")
    
    voice_client = types.ModuleType("discord.voice_client")
    voice_client.VoiceClient = VoiceClient
    voice_client.VoiceProtocol = VoiceProtocol
    sys.modules["discord.voice_client"] = voice_client
    
except Exception as e:
    # Print error but allow execution to continue if mock fails for some reason
    print(f"Mocking failed: {e}") 
# =========================================================================

from threading import Thread
from flask import Flask
import aiohttp 
import json
import discord 
from discord.ext import commands
from discord import app_commands 


# --- TORN API Key ---
TORN_API_KEY = "1Wu5Br5fy7gbb7gU" 

# --- Web server for Render keep-alive ---
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ Torn City Bot is alive!"
def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False) 
# ---------------------------------------------------------------------------


# --- Fixed Item Data (Needed for Vendor Buy Price) ---
FOREIGN_ITEMS_DATA = [
    # South Africa (SA)
    [260, "Xanax", 7600, "South Africa", "Drug"], 
    [271, "African Violet", 2000, "South Africa", "Flower"],
    [278, "Lion Plushie", 400, "South Africa", "Plushie"],
    
    # United Arab Emirates (UAE)
    [267, "Camel Plushie", 14000, "United Arab Emirates", "Plushie"],
    [273, "Tribulus Omanense", 6000, "United Arab Emirates", "Flower"],
    
    # China
    [270, "Peony", 5000, "China", "Flower"],
    [276, "Chinese Dragon Plushie", 400, "China", "Plushie"],
    
    # Other common items / Countries
    [266, "Cherry Blossom", 500, "Japan", "Flower"], # Japan
    [277, "Panda Plushie", 400, "Argentina", "Plushie"],
    [269, "Jaguar Plushie", 10000, "Mexico", "Plushie"],
    [264, "Banana Orchid", 4000, "Cayman Islands", "Flower"],
    [265, "Crocus", 600, "Canada", "Flower"],
    [275, "Polar Bear Plushie", 500, "Canada", "Plushie"],
    [272, "Edelweiss", 900, "Switzerland", "Flower"],
    [261, "Orchid", 700, "Hawaii", "Flower"],
    [274, "Sea Turtle Plushie", 500, "Hawaii", "Plushie"],
]

# --- Bot Initialization ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents) 

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync() 
        print(f"✅ Synced {len(synced)} command(s) globally.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

# --- Helper function to fetch Foreign Stock (ASYNCHRONOUS) ---
async def fetch_foreign_stock(api_key):
    """Fetches the current foreign stock from the Torn API travel selection."""
    try:
        url = f"https://api.torn.com/user/?selections=travel&key={api_key}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()
                data = await response.json()
        
        if 'error' in data:
            raise Exception(f"Torn API reported error: {data['error']['error']}")
        
        return data.get('stocks', {}) 
    except Exception as e:
        print(f"Torn API Stock Error: {e}")
        return None


# --- Revised /flyprofits command (Filter removed, ASYNCHRONOUS) ---
@bot.hybrid_command(name='flyprofits', description='Displays the top profitable foreign items (unfiltered).')
async def fly_profits(ctx):
    """Fetches and displays the top 5 most profitable foreign items based on live market price (profit > $0)."""
    
    await ctx.defer() 
    await ctx.send("✈️ **Fetching Live Profit Data...** This may take a moment.")
    
    profit_data = []
    item_ids = [str(item[0]) for item in FOREIGN_ITEMS_DATA]
    
    try:
        url = f"https://api.torn.com/market/{','.join(item_ids)}?selections=itemmarket&key={TORN_API_KEY}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                response.raise_for_status() 
                live_prices = await response.json()
        
    except aiohttp.ClientError as e:
        await ctx.reply(f"❌ **API Error:** Could not connect to Torn API or key invalid: `{e}`")
        return
    except Exception as e:
        await ctx.reply(f"❌ **API Error:** An unknown error occurred: `{e}`")
        return
    
    # --- Calculate Profit for each item (Filter only profit > $0) ---
    for item_id, name, vendor_buy, country, category in FOREIGN_ITEMS_DATA:
        item_id_str = str(item_id)
        
        if item_id_str not in live_prices or 'itemmarket' not in live_prices[item_id_str] or not live_prices[item_id_str]['itemmarket']:
            continue 
            
        market_sell_price = min(listing['cost'] for listing in live_prices[item_id_str]['itemmarket'])
        gross_profit = market_sell_price - vendor_buy
        
        if gross_profit > 0:
            profit_data.append({
                "name": name,
                "country": country,
                "vendor_buy": vendor_buy,
                "market_sell": market_sell_price,
                "profit": gross_profit,
                "category": category
            })
            
    # --- Sort by Profit and Display ---
    profit_data.sort(key=lambda x: x['profit'], reverse=True)
    
    if not profit_data:
        await ctx.send("No items found with any gross profit right now. Market might be heavily saturated.")
        return

    msg = "💰 **Top Live Profitable Foreign Items (Gross Profit > $0)**\n"
    msg += "*(Based on lowest price in Item Market)*\n\n"
    
    for i, item in enumerate(profit_data[:5]): 
        msg += (
            f"**{i+1}. {item['name']}** ({item['country']})\n"
            f"> Buy: **${item['vendor_buy']:,}** | Sell: **${item['market_sell']:,}** | **LIVE PROFIT: ${item['profit']:,}**\n"
        )

    await ctx.send(msg) 


# --- /flystock command (ASYNCHRONOUS) ---
@bot.hybrid_command(name='flystock', description='Shows live stock, price, and profit for key foreign items.')
async def fly_stock(ctx):
    """Fetches live stock and profit for plushies and flowers from target countries."""
    
    await ctx.defer()
    
    # 1. Fetch Foreign Stock Data (Country Vendor Stock)
    vendor_stock = await fetch_foreign_stock(TORN_API_KEY)
    if vendor_stock is None:
        await ctx.send("❌ **API Error:** Could not retrieve current country stock. Check API key permissions (`Travel` selection).")
        return

    # 2. Filter Item Data
    target_countries = ["Japan", "China", "United Arab Emirates", "South Africa"]
    filtered_items = [
        item for item in FOREIGN_ITEMS_DATA 
        if item[3] in target_countries and (item[4] == "Plushie" or item[4] == "Flower" or item[1] == "Xanax")
    ]
    
    item_ids = [str(item[0]) for item in filtered_items]

    # 3. Fetch Item Market Prices (ASYNCHRONOUS)
    try:
        url = f"https://api.torn.com/market/{','.join(item_ids)}?selections=itemmarket&key={TORN_API_KEY}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()
                live_prices = await response.json()
        
    except aiohttp.ClientError as e:
        await ctx.send(f"❌ **API Error:** Could not connect to Torn Item Market. `{e}`")
        return

    # 4. Compile and Format Final Data
    results = []
    
    for item_id, name, vendor_buy, country, category in filtered_items:
        item_id_str = str(item_id)
        
        market_sell_price = 0
        if item_id_str in live_prices and 'itemmarket' in live_prices[item_id_str] and live_prices[item_id_str]['itemmarket']:
            market_sell_price = min(listing['cost'] for listing in live_prices[item_id_str]['itemmarket'])
        
        gross_profit = market_sell_price - vendor_buy
        stock = vendor_stock.get(country, {}).get(item_id_str, 0)

        results.append({
            "name": name,
            "country": country,
            "stock": stock,
            "vendor_buy": vendor_buy,
            "market_sell": market_sell_price,
            "profit": gross_profit
        })

    # Sort by Country, then Profit
    results.sort(key=lambda x: (x['country'], x['profit']), reverse=True) 

    # 5. Build Output Message
    msg = "✈️ **Live Foreign Item Stock & Profit (Key Countries)**\n"
    msg += "*Format: [Stock] | Item | **Vendor Buy** | **Market Sell** | **Net Profit***\n"
    msg += "*(Profit based on current Item Market lowest listing)*\n\n"
    
    current_country = ""
    
    for item in results:
        if item['country'] != current_country:
            msg += f"\n**--- {item['country'].upper()} ---**\n"
            current_country = item['country']
        
        profit_str = (
            f"**${item['vendor_buy']:,}** | "
            f"**${item['market_sell']:,}** | "
            f"**${item['profit']:,}**"
        )
        
        msg += (
            f"**[{item['stock']:,}]** | {item['name']} "
            f"| {profit_str}\n"
        )
        
    await ctx.send(msg)

# --- Start bot and web server ---
if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.getenv("DISCORD_TOKEN"))

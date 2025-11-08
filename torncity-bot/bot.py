import os
import requests
import json
import discord
from discord.ext import commands
from discord import app_commands
import time 
import asyncio 
from aiohttp import web 

# --- 1. Configuration and Setup (Using Environment Variables) ---
# Discord Bot Token is read from the environment (e.g., set by Render/hosting)
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Define the port the web server will bind to (required for Render Web Service)
PORT = int(os.environ.get('PORT', 10000))

# Map of specific items sold in the travel destinations to check prices for
TRAVEL_ITEM_MAP = {
    "China": ["Panda Plushie", "Bottle of Beer"],
    "UAE (Dubai)": ["Gold Plated AK-47", "Bottle of Champagne"],
    "South Africa": ["African Lion Plushie", "Bottle of Minty Hot Chocolate"],
    "Japan": ["Kitten Plushie", "Bottle of Sake"]
}
# Flatten the map for easy lookup in the API response
TARGET_ITEM_NAMES = [item for sublist in TRAVEL_ITEM_MAP.values() for item in sublist]

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree

# --- 2. Torn API Interaction Logic with Rate Limiting ---

def fetch_torn_data_with_retry(url: str, max_retries: int = 3) -> dict:
    """Fetches data from the Torn API, handling rate limits with exponential backoff."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            data = response.json()
            
            # Check for Torn API error (Code 5: Rate limit)
            if 'error' in data and data['error']['code'] == 5:
                print(f"Rate limit hit. Retrying in {2 ** attempt} seconds...")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    return {"error": "Torn API Error 5: Rate limit exceeded. Please wait a minute and try again."}

            return data

        except requests.exceptions.RequestException as e:
            return {"error": f"API Connection Error: Failed to connect to Torn API. ({e})"}
        except json.JSONDecodeError:
            return {"error": "API Response Error: Received invalid JSON from Torn."}
        
    return {"error": "Maximum retries reached due to an unknown issue."}


def get_torn_stock_data(api_key: str):
    """
    Fetches the current live price and information for all stocks.
    """
    url = f"https://api.torn.com/torn/?selections=stocks&key={api_key}"

    data = fetch_torn_data_with_retry(url)

    if "error" in data:
        return data

    if 'error' in data:
        code = data['error']['code']
        message = data['error']['error']
        return {"error": f"Torn API Error {code}: {message}"}

    try:
        stocks = data.get('stocks', {})
        stock_list = []
        for stock_id, stock_info in stocks.items():
            formatted_price = f"${stock_info.get('current_price', 0):,.2f}"
            
            stock_list.append({
                "id": stock_id,
                "name": stock_info.get('name', 'N/A'),
                "acronym": stock_info.get('acronym', 'N/A'),
                "price": formatted_price,
                "benefit_available": stock_info.get('benefit_available', False)
            })
        
        stock_list.sort(key=lambda x: x['acronym'])
        return {"stocks": stock_list}
        
    except Exception as e:
        return {"error": f"Data Parsing Error: Missing expected fields or unexpected structure. {e}"}


def get_travel_item_info(api_key: str):
    """
    Fetches details for all items and filters for specific travel items.
    Torn API does not provide real-time foreign market prices, so this uses
    the item's official 'market_price' (average) and NPC 'sell_price'.
    """
    # The 'torn' resource with 'items' selection returns data for all items.
    url = f"https://api.torn.com/torn/?selections=items&key={api_key}"

    data = fetch_torn_data_with_retry(url)

    if "error" in data:
        return data

    if 'error' in data:
        code = data['error']['code']
        message = data['error']['error']
        return {"error": f"Torn API Error {code}: {message}"}

    try:
        all_items = data.get('items', {})
        target_items = {}
        
        # Iterate through all items returned by the API
        for item_info in all_items.values():
            item_name = item_info.get('name')
            
            # Check if this item is one of our target travel items
            if item_name in TARGET_ITEM_NAMES:
                
                # Format prices
                formatted_market_price = f"${item_info.get('market_price', 0):,.0f}"
                formatted_sell_price = f"${item_info.get('sell_price', 0):,.0f}"
                
                target_items[item_name] = {
                    "market_price": formatted_market_price,
                    "sell_price": formatted_sell_price,
                    "rarity": item_info.get('rarity', 'N/A')
                }
        
        if not target_items:
             return {"error": "Failed to find any matching travel item data. API structure may have changed or key lacks permission."}
             
        return {"items": target_items}
        
    except Exception as e:
        return {"error": f"Data Parsing Error: Missing expected fields or unexpected structure. {e}"}


# --- 3. Discord Commands and Events ---

@bot.event
async def on_ready():
    """Event that fires when the bot successfully connects to Discord."""
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    # Sync the slash commands globally
    await tree.sync()
    print('Slash commands synced successfully.')


@tree.command(name="stocks", description="Displays live stock prices from the Torn Stock Market.")
@app_commands.describe(api_key="Your 16-character Torn City API key (e.g., 1Wu5Br5fy7gbb7gU).")
async def torn_stocks_command(interaction: discord.Interaction, api_key: str):
    """Handles the /stocks slash command."""
    
    await interaction.response.defer()

    stocks_data = get_torn_stock_data(api_key.strip()) 

    if "error" in stocks_data:
        # Error handling as before
        error_embed = discord.Embed(
            title=":x: Torn Stocks Lookup Failed",
            description=stocks_data["error"],
            color=discord.Color.red()
        )
        error_embed.set_footer(text="Check your API key and permissions.")
        await interaction.followup.send(embed=error_embed, ephemeral=True)
    else:
        stock_list = stocks_data['stocks']
        
        # Prepare the fields for the embed (max 25 fields per embed)
        field_value = []
        for stock in stock_list:
            benefit_indicator = ":gem:" if stock['benefit_available'] else ""
            field_value.append(
                f"`{stock['acronym']:<4}` {stock['price']:>10} {benefit_indicator}"
            )

        # Create 3 columns by splitting the list
        chunk_size = (len(field_value) + 2) // 3 
        chunks = [field_value[i:i + chunk_size] for i in range(0, len(field_value), chunk_size)]

        embed = discord.Embed(
            title=":chart_with_upwards_trend: Torn City Live Stock Prices",
            description=f"Current prices for {len(stock_list)} stocks. Benefit available stocks are marked with :gem:",
            color=0x2ECC71
        )
        
        embed.add_field(name="Acronym | Price", value="\n".join(chunks[0]), inline=True)
        if len(chunks) > 1:
            embed.add_field(name="\u200b", value="\n".join(chunks[1]), inline=True)
        if len(chunks) > 2:
            embed.add_field(name="\u200b", value="\n".join(chunks[2]), inline=True)

        embed.set_footer(text=f"Requested by {interaction.user.display_name} | Data via Torn API")
        
        await interaction.followup.send(embed=embed)


@tree.command(name="travelitems", description="Displays average prices for major items sold in Torn's travel destinations.")
@app_commands.describe(api_key="Your 16-character Torn City API key (e.g., 1Wu5Br5fy7gbb7gU).")
async def torn_travelitems_command(interaction: discord.Interaction, api_key: str):
    """Handles the /travelitems slash command."""
    
    await interaction.response.defer()

    items_data = get_travel_item_info(api_key.strip()) 

    if "error" in items_data:
        error_embed = discord.Embed(
            title=":x: Torn Item Lookup Failed",
            description=items_data["error"],
            color=discord.Color.red()
        )
        error_embed.set_footer(text="Check your API key and ensure it has necessary permissions.")
        await interaction.followup.send(embed=error_embed, ephemeral=True)
    else:
        target_items = items_data['items']
        embed = discord.Embed(
            title=":airplane: Travel Market Price Guide",
            description="Average prices for key plushies and bottles from travel destinations.",
            color=discord.Color.blue()
        )

        for country, items_list in TRAVEL_ITEM_MAP.items():
            field_content = []
            for item_name in items_list:
                item_info = target_items.get(item_name)
                if item_info:
                    # Note: Market Price is the API's reported average. Sell Price is NPC shop price.
                    field_content.append(
                        f"**{item_name}**\n"
                        f"Avg Market: `{item_info['market_price']}`\n"
                        f"NPC Sell: `{item_info['sell_price']}`"
                    )
            
            if field_content:
                embed.add_field(name=f":flag_{country.split(' ')[0].lower()}: {country}", value="\n".join(field_content), inline=True)

        embed.set_footer(text=f"Requested by {interaction.user.display_name} | Prices are system-calculated averages, not live market rates.")
        
        await interaction.followup.send(embed=embed)


# --- 4. Web Server for Hosting (Workaround for Render Web Service) ---
# This server is essential for satisfying the hosting platform's requirement for an open port.

async def health_check(request):
    """Simple handler for health checks."""
    return web.Response(text="Bot is running.")

async def start_web_server():
    """Starts the aiohttp web server on the specified PORT."""
    app = web.Application()
    app.add_routes([web.get('/', health_check)])
    # Use 0.0.0.0 to bind to all interfaces
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    print(f"Starting web server on port {PORT}...")
    await site.start()
    # Keep the task running indefinitely
    await asyncio.Future() 

async def main():
    """Runs the Discord bot and the web server concurrently."""
    print("Starting bot application...")

    if not BOT_TOKEN:
        print("CRITICAL ERROR: BOT_TOKEN environment variable not found. Please set it in your hosting configuration.")
        return

    try:
        # Create tasks for both the Discord bot and the web server
        discord_task = bot.start(BOT_TOKEN)
        web_server_task = start_web_server()
        
        # Run both concurrently
        await asyncio.gather(discord_task, web_server_task)

    except discord.errors.LoginFailure:
        print("CRITICAL ERROR: Invalid Discord Bot Token. Check the BOT_TOKEN environment variable.")
    except Exception as e:
        print(f"An unexpected error occurred during bot execution: {e}")

# --- 5. Run the Application ---

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot and server stopped.")

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
# NOTE: To fix the 'ModuleNotFoundError: No module named 'audioop'' error seen in logs,
# you must set a PYTHON_VERSION environment variable on Render (e.g., 3.12.0).
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Define the port the web server will bind to
PORT = int(os.environ.get('PORT', 10000))

intents = discord.Intents.default()
# We need message_content intent for compatibility, though we primarily use slash commands
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
                    # Final attempt failed due to rate limit
                    return {"error": "Torn API Error 5: Rate limit exceeded. Please wait a minute and try again."}

            # Return data if successful or if a different API error occurs
            return data

        except requests.exceptions.RequestException as e:
            # Handle connection/timeout errors
            return {"error": f"API Connection Error: Failed to connect to Torn API. ({e})"}
        except json.JSONDecodeError:
            # Handle invalid JSON response
            return {"error": "API Response Error: Received invalid JSON from Torn."}
        
    return {"error": "Maximum retries reached due to an unknown issue."}


def get_torn_stock_data(api_key: str):
    """
    Fetches the current live price and information for all stocks from the Torn API.
    """
    # The 'torn' resource with 'stocks' selection returns data for all stocks.
    url = f"https://api.torn.com/torn/?selections=stocks&key={api_key}"

    data = fetch_torn_data_with_retry(url)

    # Check for errors returned by the fetching function
    if "error" in data:
        return data

    # Check for Torn API specific errors
    if 'error' in data:
        code = data['error']['code']
        message = data['error']['error']
        return {"error": f"Torn API Error {code}: {message}"}

    # Extract and format stock data
    try:
        stocks = data.get('stocks', {})
        stock_list = []
        for stock_id, stock_info in stocks.items():
            # Format price with commas
            formatted_price = f"${stock_info.get('current_price', 0):,.2f}"
            
            stock_list.append({
                "id": stock_id,
                "name": stock_info.get('name', 'N/A'),
                "acronym": stock_info.get('acronym', 'N/A'),
                "price": formatted_price,
                "benefit_available": stock_info.get('benefit_available', False)
            })
        
        # Sort by acronym for readability
        stock_list.sort(key=lambda x: x['acronym'])
        return {"stocks": stock_list}
        
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
@app_commands.describe(api_key="Your 16-character Torn City API key (required for API access).")
async def torn_stocks_command(interaction: discord.Interaction, api_key: str):
    """Handles the /stocks slash command."""
    
    # Immediately acknowledge the command
    await interaction.response.defer()

    # Get data from the Torn API
    stocks_data = get_torn_stock_data(api_key.strip()) 

    if "error" in stocks_data:
        # Send an error message if the API call failed
        error_embed = discord.Embed(
            title=":x: Torn Market Lookup Failed",
            description=stocks_data["error"],
            color=discord.Color.red()
        )
        error_embed.set_footer(text="Check your API key and permissions. Example key: 1Wu5Br5fy7gbb7gU")
        await interaction.followup.send(embed=error_embed, ephemeral=True)
    else:
        stock_list = stocks_data['stocks']
        
        # Prepare the fields for the embed (max 25 fields per embed)
        # We will split the list into three columns to be concise
        field_value = []
        
        for stock in stock_list:
            benefit_indicator = ":gem:" if stock['benefit_available'] else ""
            field_value.append(
                f"`{stock['acronym']:<4}` {stock['price']:>10} {benefit_indicator}"
            )

        # Create 3 columns by splitting the list
        chunk_size = (len(field_value) + 2) // 3 # Calculate chunk size to ensure even distribution
        chunks = [field_value[i:i + chunk_size] for i in range(0, len(field_value), chunk_size)]

        embed = discord.Embed(
            title=":chart_with_upwards_trend: Torn City Live Stock Prices",
            description=f"Current prices for {len(stock_list)} stocks. Benefit available stocks are marked with :gem:",
            color=0x2ECC71
        )
        
        # Add the three columns as fields
        embed.add_field(name="Acronym | Price", value="\n".join(chunks[0]), inline=True)
        if len(chunks) > 1:
            embed.add_field(name="\u200b", value="\n".join(chunks[1]), inline=True)
        if len(chunks) > 2:
            embed.add_field(name="\u200b", value="\n".join(chunks[2]), inline=True)

        embed.set_footer(text=f"Requested by {interaction.user.display_name} | Data via Torn API")
        
        # Send the final response
        await interaction.followup.send(embed=embed)


# --- 4. Web Server for Hosting (Workaround for Render Web Service) ---

async def health_check(request):
    """Simple handler for health checks."""
    return web.Response(text="Bot is running.")

async def start_web_server():
    """Starts the aiohttp web server on the specified PORT."""
    app = web.Application()
    app.add_routes([web.get('/', health_check)])
    # Use 0.0.0.0 to bind to all interfaces, and the dynamically set PORT
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
    # Run the main asynchronous function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot and server stopped.")

import os
import requests
import json
import discord
from discord.ext import commands
from discord import app_commands
import time # Used for exponential backoff
import asyncio # New: For running two async tasks concurrently (bot and web server)
from aiohttp import web # New: To create a lightweight health check server

# --- 1. Configuration and Setup (Using Environment Variables) ---
# Discord Bot Token is read from the environment (e.g., set by Render/hosting)
# NOTE: To fix the 'ModuleNotFoundError: No module named 'audioop'' error seen in logs,
# you must set a PYTHON_VERSION environment variable on Render (e.g., 3.12.0).
BOT_TOKEN = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
# We need message_content intent to handle prefix commands, though we primarily use slash commands
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)
# FIX: Use the existing command tree attached to the bot instance.
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


def get_torn_user_stats(api_key: str):
    """
    Fetches the user's basic profile stats (level, name, networth) from the Torn API.
    """
    # Selections for profile and networth. The 'networth' selection is efficient.
    url = f"https://api.torn.com/user/?selections=profile,networth&key={api_key}"

    data = fetch_torn_data_with_retry(url)

    # Check for errors returned by the fetching function
    if "error" in data:
        return data

    # Check for Torn API specific errors (e.g., invalid key, insufficient access)
    if 'error' in data:
        code = data['error']['code']
        message = data['error']['error']
        
        # Provide specific guidance for common access error
        if code == 16:
             message += " (Hint: Your API key needs 'Full Access' enabled in Torn settings for Net Worth data)."
        
        return {"error": f"Torn API Error {code}: {message}"}

    # Extract required data
    try:
        name = data.get('name', 'N/A')
        player_id = data.get('player_id', 'N/A')
        level = data.get('level', 0)
        net_worth = data.get('networth', 0)

        # Format net worth with commas
        formatted_net_worth = f"${net_worth:,.0f}"

        return {
            "name": name,
            "id": player_id,
            "level": level,
            "net_worth": formatted_net_worth,
            "profile_url": f"https://www.torn.com/profiles.php?XID={player_id}"
        }
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


@tree.command(name="tornstats", description="Look up a player's basic stats using their Torn API key.")
@app_commands.describe(api_key="Your 16-character Torn City API key.")
async def tornstats_command(interaction: discord.Interaction, api_key: str):
    """Handles the /tornstats slash command."""
    
    # Immediately acknowledge the command to prevent the "Application did not respond" error
    await interaction.response.defer()

    # Get data from the Torn API
    # strip() is important to remove accidental whitespace when users copy/paste keys
    stats = get_torn_user_stats(api_key.strip()) 

    if "error" in stats:
        # Send an error message if the API call failed
        error_embed = discord.Embed(
            title=":x: Torn API Lookup Failed",
            description=stats["error"],
            color=discord.Color.red()
        )
        error_embed.set_footer(text="The provided API key was invalid or did not have sufficient access.")
        await interaction.followup.send(embed=error_embed, ephemeral=True)
    else:
        # Create an embedded message with the successful stats
        embed = discord.Embed(
            title=f"Torn Player Stats: {stats['name']} [{stats['id']}]",
            url=stats['profile_url'],
            color=0xCC0000 # Torn City red color
        )
        
        embed.add_field(name=":chart_with_upwards_trend: Level", value=f"**{stats['level']}**", inline=True)
        embed.add_field(name=":moneybag: Net Worth", value=f"**{stats['net_worth']}**", inline=True)
        
        embed.set_thumbnail(url="https://www.torn.com/images/v2/banner.png")
        embed.set_footer(text=f"Requested by {interaction.user.display_name} | Data via Torn API")
        
        # Send the final response
        await interaction.followup.send(embed=embed)


# --- 4. Web Server for Hosting (Workaround for Render Web Service) ---
# This server is only added to satisfy the Render Web Service requirement 
# that an open port (10000) must be detected. It is NOT required for the bot itself.

async def health_check(request):
    """Simple handler for health checks."""
    return web.Response(text="Bot is running.")

async def start_web_server():
    """Starts the aiohttp web server on port 10000."""
    app = web.Application()
    app.add_routes([web.get('/', health_check)])
    # Use 0.0.0.0 to bind to all interfaces, and port 10000 as requested
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    print("Starting web server on port 10000...")
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

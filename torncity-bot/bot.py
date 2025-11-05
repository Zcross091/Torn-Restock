import discord
from discord.ext import commands
import os
from threading import Thread
from flask import Flask
discord.VoiceClient = None

app = Flask(__name__)

@app.route("/")
def home():
    return "Torn City bot is alive"

def run_web():
    app.run(host="0.0.0.0", port=8080)

COUNTRY_ITEMS = {
    "Argentina": ["Argentine Flag", "Panda Plushie"],
    "Cayman Islands": ["Red Fox Plushie"],
    "Hawaii": ["Sea Turtle Plushie"],
    "Mexico": ["Jaguar Plushie"],
    "Switzerland": ["Swiss Chocolate"],
    "United Kingdom": ["English Tea", "Daisy", "Teddy Bear"],
    "China": ["Chinese Dragon Plushie"],
    "Japan": ["Geisha Doll"],
    "Canada": ["Polar Bear Plushie"],
    "Cuba": ["Cuban Cigars"],
    "Netherlands": ["Tulip", "Cannabis"],
}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.command()
async def plushies(ctx):
    msg = "**🧸 Plushies by Country**\n\n"
    for c, items in COUNTRY_ITEMS.items():
        p = [i for i in items if "Plushie" in i]
        if p:
            msg += f"**{c}:** {', '.join(p)}\n"
    await ctx.send(msg)

@bot.command()
async def flowers(ctx):
    msg = "**🌸 Flowers by Country**\n\n"
    for c, items in COUNTRY_ITEMS.items():
        f = [i for i in items if "Flower" in i or "Tulip" in i or "Daisy" in i]
        if f:
            msg += f"**{c}:** {', '.join(f)}\n"
    await ctx.send(msg)

@bot.command()
async def drugs(ctx):
    msg = "**💊 Drugs by Country**\n\n"
    for c, items in COUNTRY_ITEMS.items():
        d = [i for i in items if "Cannabis" in i or "Cigar" in i]
        if d:
            msg += f"**{c}:** {', '.join(d)}\n"
    await ctx.send(msg)

@bot.command()
async def country(ctx, *, name):
    name = name.title()
    if name in COUNTRY_ITEMS:
        await ctx.send(f"**{name} Items:** {', '.join(COUNTRY_ITEMS[name])}")
    else:
        await ctx.send("❌ Country not found.")

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.run(os.getenv("DISCORD_TOKEN"))


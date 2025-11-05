import discord
from discord.ext import commands
import os

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
    for country, items in COUNTRY_ITEMS.items():
        plushies = [i for i in items if "Plushie" in i]
        if plushies:
            msg += f"**{country}:** {', '.join(plushies)}\n"
    await ctx.send(msg)

@bot.command()
async def flowers(ctx):
    msg = "**🌸 Flowers by Country**\n\n"
    for country, items in COUNTRY_ITEMS.items():
        flowers = [i for i in items if "Flower" in i or "Tulip" in i or "Daisy" in i]
        if flowers:
            msg += f"**{country}:** {', '.join(flowers)}\n"
    await ctx.send(msg)

@bot.command()
async def drugs(ctx):
    msg = "**💊 Drugs by Country**\n\n"
    for country, items in COUNTRY_ITEMS.items():
        drugs = [i for i in items if "Cannabis" in i or "Cigar" in i]
        if drugs:
            msg += f"**{country}:** {', '.join(drugs)}\n"
    await ctx.send(msg)

@bot.command()
async def country(ctx, *, name):
    name = name.title()
    if name in COUNTRY_ITEMS:
        items = ", ".join(COUNTRY_ITEMS[name])
        await ctx.send(f"**{name} Items:** {items}")
    else:
        await ctx.send("❌ Country not found. Try again!")

bot.run(os.getenv("DISCORD_TOKEN"))

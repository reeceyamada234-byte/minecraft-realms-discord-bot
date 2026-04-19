import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Configuration: Map source channels to destination channels
RELAY_MAPPING = {
    # Example: 1234567890: [0987654321, 1112223334],
}

# Chat logger file
LOG_FILE = "chat_logs.json"

def load_logs():
    """Load existing chat logs"""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_logs(logs):
    """Save chat logs to file"""
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

def log_message(message):
    """Log message to file and console"""
    logs = load_logs()
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "author": str(message.author),
        "guild": message.guild.name if message.guild else "DM",
        "channel": message.channel.name if hasattr(message.channel, 'name') else str(message.channel),
        "content": message.content,
        "attachments": [att.url for att in message.attachments]
    }
    
    channel_key = f"{message.guild.id}_{message.channel.id}" if message.guild else "DMs"
    
    if channel_key not in logs:
        logs[channel_key] = []
    
    logs[channel_key].append(log_entry)
    save_logs(logs)
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message.author} in #{message.channel.name}: {message.content}")

@bot.event
async def on_ready():
    print(f"{bot.user} is now running as a relay bot!")
    print(f"Logging to: {LOG_FILE}")

@bot.event
async def on_message(message):
    # Ignore bot's own messages
    if message.author == bot.user:
        return
    
    # Log all messages
    log_message(message)
    
    # Check if message is from a relay source channel
    if message.channel.id in RELAY_MAPPING:
        destinations = RELAY_MAPPING[message.channel.id]
        
        # Create embed for relayed message
        embed = discord.Embed(
            description=message.content,
            color=discord.Color.blue()
        )
        embed.set_author(
            name=f"{message.author} ({message.guild.name})",
            icon_url=message.author.display_avatar.url
        )
        embed.set_footer(text=f"from #{message.channel.name}")
        
        # Send to all destination channels
        for dest_id in destinations:
            try:
                dest_channel = bot.get_channel(dest_id)
                if dest_channel:
                    await dest_channel.send(embed=embed)
            except Exception as e:
                print(f"Error relaying to {dest_id}: {e}")
    
    await bot.process_commands(message)

@bot.command(name="join", help="Bot joins a voice channel")
async def join(ctx):
    """Join the voice channel of the user who called the command"""
    if not ctx.author.voice:
        await ctx.send("❌ You must be in a voice channel to use this command!")
        return
    
    voice_channel = ctx.author.voice.channel
    
    try:
        # Check if bot is already in a voice channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(voice_channel)
            await ctx.send(f"✅ Moved to **{voice_channel.name}**")
        else:
            await voice_channel.connect()
            await ctx.send(f"✅ Joined **{voice_channel.name}**")
        
        # Log the join event
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": "bot_join",
            "author": str(ctx.author),
            "guild": ctx.guild.name,
            "voice_channel": voice_channel.name
        }
        logs = load_logs()
        channel_key = f"{ctx.guild.id}_{ctx.channel.id}"
        if channel_key not in logs:
            logs[channel_key] = []
        logs[channel_key].append(log_entry)
        save_logs(logs)
        
    except Exception as e:
        await ctx.send(f"❌ Error joining voice channel: {e}")
        print(f"Error joining voice channel: {e}")

@bot.command(name="leave", help="Bot leaves the voice channel")
async def leave(ctx):
    """Bot leaves the current voice channel"""
    if not ctx.voice_client:
        await ctx.send("❌ I'm not in a voice channel!")
        return
    
    voice_channel_name = ctx.voice_client.channel.name
    await ctx.voice_client.disconnect()
    await ctx.send(f"✅ Left **{voice_channel_name}**")

@bot.command(name="relay_add", help="Add a relay mapping: !relay_add <source_channel_id> <dest_channel_id>")
async def relay_add(ctx, source: int, destination: int):
    """Add a new relay mapping"""
    if source not in RELAY_MAPPING:
        RELAY_MAPPING[source] = []
    
    if destination not in RELAY_MAPPING[source]:
        RELAY_MAPPING[source].append(destination)
        await ctx.send(f"✅ Added relay: <#{source}> → <#{destination}>")
    else:
        await ctx.send(f"⚠️ Relay already exists: <#{source}> → <#{destination}>")

@bot.command(name="relay_remove", help="Remove a relay mapping: !relay_remove <source_channel_id> <dest_channel_id>")
async def relay_remove(ctx, source: int, destination: int):
    """Remove a relay mapping"""
    if source in RELAY_MAPPING and destination in RELAY_MAPPING[source]:
        RELAY_MAPPING[source].remove(destination)
        await ctx.send(f"✅ Removed relay: <#{source}> → <#{destination}>")
    else:
        await ctx.send(f"❌ Relay mapping not found!")

@bot.command(name="relay_info", help="Shows relay configuration")
async def relay_info(ctx):
    """Display current relay mappings"""
    if not RELAY_MAPPING:
        await ctx.send("No relay mappings configured.")
        return
    
    embed = discord.Embed(title="📡 Relay Mappings", color=discord.Color.green())
    
    for source, dests in RELAY_MAPPING.items():
        source_channel = bot.get_channel(source)
        if source_channel:
            dest_names = []
            for d in dests:
                dest_channel = bot.get_channel(d)
                if dest_channel:
                    dest_names.append(f"#{dest_channel.name}")
            
            if dest_names:
                embed.add_field(
                    name=f"🔗 #{source_channel.name}",
                    value=" → ".join(dest_names),
                    inline=False
                )
    
    await ctx.send(embed=embed)

@bot.command(name="logs", help="View recent chat logs")
async def view_logs(ctx, lines: int = 10):
    """View recent chat logs from current channel"""
    logs = load_logs()
    channel_key = f"{ctx.guild.id}_{ctx.channel.id}"
    
    if channel_key not in logs or not logs[channel_key]:
        await ctx.send("No logs found for this channel.")
        return
    
    recent_logs = logs[channel_key][-lines:]
    
    embed = discord.Embed(title=f"📋 Recent Logs ({len(recent_logs)} messages)", color=discord.Color.gold())
    
    log_text = ""
    for log in recent_logs:
        if log.get("event") == "bot_join":
            log_text += f"🤖 **Bot joined** {log['voice_channel']}\n"
        else:
            timestamp = log["timestamp"].split("T")[1][:8]
            log_text += f"**{log['author']}** [{timestamp}]: {log['content'][:100]}\n"
    
    embed.description = log_text or "No messages logged."
    await ctx.send(embed=embed)

if TOKEN:
    bot.run(TOKEN)
else:
    print("Missing Discord Token")

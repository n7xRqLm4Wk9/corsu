import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
import random
import string
import io
import sqlite3
import re
import datetime as dt
import urllib.request
from datetime import datetime, timezone
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFilter

# ============ CONFIG ============
LOG_CHANNEL_NAME = "corsu-logs"
WELCOME_CHANNEL_NAME = "welcome"
AUTO_ROLE_NAME = ""  # Role to auto assign on join, leave empty to disable
# ================================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tree = bot.tree

# ============ DATABASE ============

DB_FILE = os.getenv("DB_FILE", "corsu.db")

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS warns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT, user_id TEXT, reason TEXT, by TEXT, time TEXT
        );
        CREATE TABLE IF NOT EXISTS xp (
            guild_id TEXT, user_id TEXT, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            guild_id TEXT PRIMARY KEY, data TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS perms (
            guild_id TEXT PRIMARY KEY, data TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS custom_commands (
            guild_id TEXT, trigger TEXT, response TEXT,
            PRIMARY KEY (guild_id, trigger)
        );
        CREATE TABLE IF NOT EXISTS reaction_roles (
            guild_id TEXT, message_id TEXT, emoji TEXT, role_id TEXT,
            PRIMARY KEY (guild_id, message_id, emoji)
        );
        CREATE TABLE IF NOT EXISTS giveaways_db (
            message_id TEXT PRIMARY KEY, channel_id TEXT, guild_id TEXT,
            prize TEXT, end_time REAL, host_id TEXT
        );
        CREATE TABLE IF NOT EXISTS captcha_db (
            user_id TEXT PRIMARY KEY, code TEXT, attempts INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()

init_db()

# DB helpers
def db_get_settings(guild_id):
    conn = get_db()
    row = conn.execute("SELECT data FROM settings WHERE guild_id=?", (str(guild_id),)).fetchone()
    conn.close()
    return json.loads(row["data"]) if row else {}

def db_save_settings(guild_id, data):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (guild_id, data) VALUES (?,?)", (str(guild_id), json.dumps(data)))
    conn.commit()
    conn.close()

def db_get_perms(guild_id):
    conn = get_db()
    row = conn.execute("SELECT data FROM perms WHERE guild_id=?", (str(guild_id),)).fetchone()
    conn.close()
    return json.loads(row["data"]) if row else {}

def db_save_perms(guild_id, data):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO perms (guild_id, data) VALUES (?,?)", (str(guild_id), json.dumps(data)))
    conn.commit()
    conn.close()

def db_add_warn(guild_id, user_id, reason, by):
    conn = get_db()
    conn.execute("INSERT INTO warns (guild_id, user_id, reason, by, time) VALUES (?,?,?,?,?)",
                 (str(guild_id), str(user_id), reason, by, str(datetime.now(timezone.utc))))
    conn.commit()
    conn.close()

def db_get_warns(guild_id, user_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM warns WHERE guild_id=? AND user_id=?", (str(guild_id), str(user_id))).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_clear_warns(guild_id, user_id):
    conn = get_db()
    conn.execute("DELETE FROM warns WHERE guild_id=? AND user_id=?", (str(guild_id), str(user_id)))
    conn.commit()
    conn.close()

def db_get_xp(guild_id, user_id):
    conn = get_db()
    row = conn.execute("SELECT xp, level FROM xp WHERE guild_id=? AND user_id=?", (str(guild_id), str(user_id))).fetchone()
    conn.close()
    return (row["xp"], row["level"]) if row else (0, 0)

def db_set_xp(guild_id, user_id, xp, level):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO xp (guild_id, user_id, xp, level) VALUES (?,?,?,?)",
                 (str(guild_id), str(user_id), xp, level))
    conn.commit()
    conn.close()

def db_get_leaderboard(guild_id, limit=10):
    conn = get_db()
    rows = conn.execute("SELECT user_id, xp, level FROM xp WHERE guild_id=? ORDER BY xp DESC LIMIT ?",
                        (str(guild_id), limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_custom_commands(guild_id):
    conn = get_db()
    rows = conn.execute("SELECT trigger, response FROM custom_commands WHERE guild_id=?", (str(guild_id),)).fetchall()
    conn.close()
    return {r["trigger"]: r["response"] for r in rows}

def db_add_custom_command(guild_id, trigger, response):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO custom_commands (guild_id, trigger, response) VALUES (?,?,?)",
                 (str(guild_id), trigger, response))
    conn.commit()
    conn.close()

def db_remove_custom_command(guild_id, trigger):
    conn = get_db()
    conn.execute("DELETE FROM custom_commands WHERE guild_id=? AND trigger=?", (str(guild_id), trigger))
    conn.commit()
    conn.close()

def db_get_reaction_roles(guild_id, message_id):
    conn = get_db()
    rows = conn.execute("SELECT emoji, role_id FROM reaction_roles WHERE guild_id=? AND message_id=?",
                        (str(guild_id), str(message_id))).fetchall()
    conn.close()
    return {r["emoji"]: r["role_id"] for r in rows}

def db_add_reaction_role(guild_id, message_id, emoji, role_id):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?,?,?,?)",
                 (str(guild_id), str(message_id), emoji, str(role_id)))
    conn.commit()
    conn.close()

def db_save_captcha(user_id, code):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO captcha_db (user_id, code, attempts) VALUES (?,?,0)", (str(user_id), code))
    conn.commit()
    conn.close()

def db_get_captcha(user_id):
    conn = get_db()
    row = conn.execute("SELECT code, attempts FROM captcha_db WHERE user_id=?", (str(user_id),)).fetchone()
    conn.close()
    return (row["code"], row["attempts"]) if row else (None, 0)

def db_delete_captcha(user_id):
    conn = get_db()
    conn.execute("DELETE FROM captcha_db WHERE user_id=?", (str(user_id),))
    conn.commit()
    conn.close()

def db_increment_captcha_attempts(user_id):
    conn = get_db()
    conn.execute("UPDATE captcha_db SET attempts=attempts+1 WHERE user_id=?", (str(user_id),))
    conn.commit()
    conn.close()

# Anti-threat (merged raid + nuke)
join_tracker = defaultdict(list)
RAID_JOIN_THRESHOLD = 20
RAID_TIME_WINDOW = 10
raid_mode = {}
invite_spam_tracker = defaultdict(list)  # {user_id: [timestamps]}
INVITE_SPAM_THRESHOLD = 3
INVITE_SPAM_WINDOW = 10

# Spam tracking
message_tracker = defaultdict(list)
duplicate_tracker = defaultdict(lambda: {"content": None, "count": 0})
SPAM_THRESHOLD = 5
SPAM_TIME_WINDOW = 5

# Nuke protection (on by default)
channel_delete_tracker = defaultdict(list)
role_delete_tracker = defaultdict(list)
NUKE_THRESHOLD = 3
NUKE_TIME_WINDOW = 10

# Captcha tracking
captcha_codes = {}
bot_start_time = datetime.now(timezone.utc)
afk_users = {}  # {guild_id: {user_id: reason}}
ticket_cooldowns = {}  # {user_id: timestamp}
verify_cooldowns = {}  # {user_id: timestamp}
giveaways = {}  # {message_id: {channel_id, guild_id, prize, end_time, host_id}}
captcha_attempts = defaultdict(int)

# ============ HELPERS ============

def get_settings(guild_id):
    return db_get_settings(guild_id)

def save_settings(guild_id, data):
    db_save_settings(guild_id, data)

def add_footer(embed):
    embed.set_footer(text="Corsu Bot", icon_url="https://cdn.discordapp.com/embed/avatars/0.png")
    return embed

async def log(guild, message):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if channel:
        embed = discord.Embed(description=message, color=0xED4245, timestamp=datetime.now(timezone.utc))
        embed.set_footer(text="Corsu Logs")
        await channel.send(embed=embed)


def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator or interaction.user.id == interaction.guild.owner_id

def has_perm(interaction: discord.Interaction, command: str):
    if interaction.user.id == interaction.guild.owner_id:
        return True
    if interaction.user.guild_permissions.administrator:
        return True
    # Check if any of the user's roles have administrator permission
    for role in interaction.user.roles:
        if role.permissions.administrator:
            return True
    guild_perms = db_get_perms(interaction.guild.id)
    user_perms = guild_perms.get("users", {}).get(str(interaction.user.id), [])
    if command in user_perms:
        return True
    role_perms = guild_perms.get("roles", {})
    for role in interaction.user.roles:
        if command in role_perms.get(str(role.id), []):
            return True
    return False

def generate_captcha():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    width, height = 300, 100
    img = Image.new('RGB', (width, height), color=(25, 25, 35))
    draw = ImageDraw.Draw(img)
    # Background noise dots
    for _ in range(200):
        x, y = random.randint(0, width), random.randint(0, height)
        draw.point((x, y), fill=(random.randint(60, 120), random.randint(60, 120), random.randint(60, 120)))
    # Draw each character large and spaced out
    x_pos = 20
    for char in code:
        color = (random.randint(180, 255), random.randint(180, 255), random.randint(180, 255))
        y_offset = random.randint(-8, 8)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                draw.text((x_pos + dx, 25 + y_offset + dy), char, fill=(0, 0, 0))
        draw.text((x_pos, 25 + y_offset), char, fill=color)
        x_pos += 44
    # Draw noise lines AFTER text (so text is readable)
    for _ in range(4):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(random.randint(80, 140), random.randint(80, 140), random.randint(80, 140)), width=1)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return code, buf

# ============ EVENTS ============

@bot.event
async def on_ready():
    await tree.sync()
    bot.add_view(TicketButton())
    bot.add_view(VerifyButton())
    print(f"Corsu is online as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="/help | Corsu Bot"))

@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    now = datetime.now(timezone.utc)
    settings = get_settings(guild.id)
    if settings.get("nuke_protection", True):
        channel_delete_tracker[guild.id].append(now)
        channel_delete_tracker[guild.id] = [t for t in channel_delete_tracker[guild.id] if (now - t).seconds < NUKE_TIME_WINDOW]
        if len(channel_delete_tracker[guild.id]) >= NUKE_THRESHOLD:
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
                    culprit = entry.user
                    if culprit and culprit != guild.me and not culprit.guild_permissions.administrator:
                        await culprit.ban(reason="Nuke protection: Mass channel deletion detected")
                        await log(guild, f"NUKE ATTEMPT — {culprit} permanently banned for deleting {len(channel_delete_tracker[guild.id])} channels in {NUKE_TIME_WINDOW}s.")
            except:
                pass

@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    now = datetime.now(timezone.utc)
    settings = get_settings(guild.id)
    if settings.get("nuke_protection", True):
        role_delete_tracker[guild.id].append(now)
        role_delete_tracker[guild.id] = [t for t in role_delete_tracker[guild.id] if (now - t).seconds < NUKE_TIME_WINDOW]
        if len(role_delete_tracker[guild.id]) >= NUKE_THRESHOLD:
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
                    culprit = entry.user
                    if culprit and culprit != guild.me and not culprit.guild_permissions.administrator:
                        await culprit.ban(reason="Nuke protection: Mass role deletion detected")
                        await log(guild, f"NUKE ATTEMPT — {culprit} permanently banned for deleting {len(role_delete_tracker[guild.id])} roles in {NUKE_TIME_WINDOW}s.")
            except:
                pass

@bot.event
async def on_member_join(member):
    guild = member.guild
    now = datetime.now(timezone.utc)

    # Account age check
    settings_data = get_settings(guild.id)
    min_age_days = settings_data.get("min_account_age", 0)
    account_age = (now - member.created_at).days
    if min_age_days > 0 and account_age < min_age_days:
        try:
            await member.kick(reason=f"Account too new ({account_age} days old, minimum {min_age_days})")
            await log(guild, f"Kicked {member} — account only {account_age} days old (min: {min_age_days})")
        except:
            pass
        return

    # New account warning (under 7 days)
    if account_age < 7:
        await log(guild, f" New account joined: {member} — account is only {account_age} days old")

    # No profile picture warning
    if member.avatar is None:
        await log(guild, f" No avatar: {member} joined with no profile picture")

    join_tracker[guild.id].append(now)
    join_tracker[guild.id] = [t for t in join_tracker[guild.id] if (now - t).seconds < RAID_TIME_WINDOW]

    if len(join_tracker[guild.id]) >= RAID_JOIN_THRESHOLD:
        if not raid_mode.get(guild.id):
            raid_mode[guild.id] = True
            await log(guild, f"RAID DETECTED — {len(join_tracker[guild.id])} joins in {RAID_TIME_WINDOW}s. Raid mode enabled.")
            for ch in guild.text_channels:
                try:
                    await ch.edit(slowmode_delay=30)
                except:
                    pass
            await log(guild, "Applied 30 second slowmode to all channels during raid.")
        try:
            await member.kick(reason="Anti-raid: Mass join detected")
            await log(guild, f"Kicked {member} during raid mode.")
        except:
            pass
        return

    welcome_channel = discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL_NAME)
    if welcome_channel:
        try:
            avatar_url = str(member.display_avatar.replace(size=128, format='png'))
            with urllib.request.urlopen(avatar_url) as resp:
                avatar_data = resp.read()
            avatar_img = Image.open(io.BytesIO(avatar_data)).convert("RGBA").resize((100, 100))
            mask = Image.new("L", (100, 100), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 100, 100), fill=255)
            avatar_img.putalpha(mask)
            banner = Image.new("RGBA", (600, 200), (32, 34, 37, 255))
            draw = ImageDraw.Draw(banner)
            draw.rectangle([0, 0, 600, 4], fill=(88, 101, 242))
            banner.paste(avatar_img, (50, 50), avatar_img)
            draw.text((170, 60), f"Welcome!", fill=(88, 101, 242))
            draw.text((170, 90), f"{member.name}", fill=(255, 255, 255))
            draw.text((170, 120), f"Member #{guild.member_count}", fill=(180, 180, 180))
            buf = io.BytesIO()
            banner.save(buf, format="PNG")
            buf.seek(0)
            file = discord.File(buf, filename="welcome.png")
            embed = discord.Embed(description=f"Hey {member.mention}, glad to have you here!", color=0x5865F2)
            embed.set_image(url="attachment://welcome.png")
            await welcome_channel.send(embed=embed, file=file)
        except Exception:
            embed = discord.Embed(title=f"Welcome to {guild.name}!", description=f"Hey {member.mention}, glad to have you here. You are member #{guild.member_count}.", color=0x5865F2)
            embed.set_thumbnail(url=member.display_avatar.url)
            await welcome_channel.send(embed=embed)

    if AUTO_ROLE_NAME:
        role = discord.utils.get(guild.roles, name=AUTO_ROLE_NAME)
        if role:
            try:
                await member.add_roles(role)
            except:
                pass

@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    # Handle captcha DM responses
    if isinstance(message.channel, discord.DMChannel):
        user_id = str(message.author.id)
        code, attempts = db_get_captcha(user_id)
        if not code:
            if message.content.strip() and not message.content.startswith("/"):
                await message.author.send("Your captcha has expired or you don't have an active one. Please click the Verify button in the server again.")
            return
        if message.content.upper().strip() == code:
            db_delete_captcha(user_id)
            verified = False
            for guild in bot.guilds:
                try:
                    member = await guild.fetch_member(message.author.id)
                except:
                    member = None
                if member:
                    settings = get_settings(guild.id)
                    verified_role_id = settings.get("verified_role")
                    if verified_role_id:
                        verified_role = guild.get_role(int(verified_role_id))
                        if verified_role:
                            try:
                                await member.add_roles(verified_role)
                                verified = True
                            except Exception as e:
                                await message.author.send(f"Error giving role: {e}\nJoin support: https://discord.gg/ks3uPmZCVh")
            if verified:
                await message.author.send(" You have been verified! You now have access to the server.\n\nIf you have any issues, join our support server: https://discord.gg/ks3uPmZCVh")
            else:
                await message.author.send("Something went wrong giving you the verified role. Please join our support server: https://discord.gg/ks3uPmZCVh")
        else:
            new_attempts = attempts + 1
            db_increment_captcha_attempts(user_id)
            remaining = 3 - new_attempts
            if remaining <= 0:
                db_delete_captcha(user_id)
                await message.author.send(" Too many wrong attempts. Please click the Verify button in the server again.\n\nNeed help? https://discord.gg/ks3uPmZCVh")
                for guild in bot.guilds:
                    member = guild.get_member(message.author.id)
                    if member:
                        try:
                            await member.kick(reason="Failed captcha verification 3 times")
                        except:
                            pass
            else:
                await message.author.send(f" Wrong code. **{remaining}** attempt(s) remaining. Try again!")
        return

    if not message.guild:
        await bot.process_commands(message)
        return

    user_id = str(message.author.id)
    guild_id = str(message.guild.id)
    now = datetime.now(timezone.utc)
    settings = get_settings(message.guild.id)

    # Spam detection (on by default)
    antispam_enabled = settings.get("antispam", True)
    if antispam_enabled:
        message_tracker[user_id].append(now)
        message_tracker[user_id] = [t for t in message_tracker[user_id] if (now - t).seconds < SPAM_TIME_WINDOW]
        if len(message_tracker[user_id]) >= SPAM_THRESHOLD:
            message_tracker[user_id] = []
            deleted = 0
            try:
                async for msg in message.channel.history(limit=50):
                    if msg.author.id == message.author.id:
                        try:
                            await msg.delete()
                            deleted += 1
                            if deleted >= SPAM_THRESHOLD:
                                break
                        except:
                            pass
                await message.channel.send(f"{message.author.mention} Your messages were removed for spamming.", delete_after=5)
                await log(message.guild, f"Spam detected from {message.author} in {message.channel.mention} — {deleted} messages deleted")
            except:
                pass
            return

    # Duplicate message detection
    if antispam_enabled:
        last = duplicate_tracker[user_id]
        stripped = message.content.strip().lower()
        if stripped and stripped == last["content"]:
            last["count"] += 1
            if last["count"] >= 3:
                last["count"] = 0
                last["content"] = None
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention} Stop sending the same message repeatedly.", delete_after=5)
                    await log(message.guild, f"{message.author} deleted for repeated duplicate messages in {message.channel.mention}")
                except:
                    pass
                return
        else:
            last["content"] = stripped
            last["count"] = 1

    # Invite filter + spam detection
    if "discord.gg/" in message.content or "discord.com/invite/" in message.content:
        if not message.author.guild_permissions.administrator:
            if settings.get("invite_filter"):
                try:
                    await message.delete()
                except:
                    pass
            invite_spam_tracker[user_id].append(now)
            invite_spam_tracker[user_id] = [t for t in invite_spam_tracker[user_id] if (now - t).seconds < INVITE_SPAM_WINDOW]
            if len(invite_spam_tracker[user_id]) >= INVITE_SPAM_THRESHOLD:
                invite_spam_tracker[user_id] = []
                until = discord.utils.utcnow() + dt.timedelta(hours=1)
                try:
                    await message.author.timeout(until, reason="Invite link spam")
                    await message.channel.send(f"{message.author.mention} has been timed out for 1 hour for spamming invite links.", delete_after=8)
                    await log(message.guild, f"{message.author} timed out 1h for invite spam in #{message.channel.name}")
                except:
                    pass
            elif settings.get("invite_filter"):
                await message.channel.send(f"{message.author.mention} Invite links are not allowed here.", delete_after=5)
                await log(message.guild, f"Invite link blocked from {message.author} in {message.channel.mention}")
            return

    # Word blacklist + built-in family filter
    blacklist = settings.get("blacklist", [])
    BUILTIN_FILTER = [
        "nigger", "nigga", "faggot", "fag", "retard", "tranny",
        "chink", "spic", "kike", "cunt", "whore", "slut"
    ]
    if settings.get("family_filter"):
        blacklist = list(set(blacklist + BUILTIN_FILTER))
    msg_lower = message.content.lower()
    for word in blacklist:
        if word.lower() in msg_lower:
            try:
                await message.delete()
                await message.author.send(f"Your message in **{message.guild.name}** was removed for containing a blocked word.")
                await log(message.guild, f"Blocked word used by {message.author} in {message.channel.mention} — deleted silently")
            except:
                pass
            return

    # XP system
    xp, level = db_get_xp(guild_id, user_id)
    if level == 0:
        level = 1
    xp += random.randint(5, 15)
    if xp >= level * 100:
        new_level = level + 1
        xp = 0
        db_set_xp(guild_id, user_id, xp, new_level)
        level_channel_id = settings.get("level_channel")
        if level_channel_id:
            level_ch = message.guild.get_channel(int(level_channel_id))
            if level_ch:
                await level_ch.send(f"{message.author.mention} You reached level {new_level}!")
            else:
                await message.channel.send(f"{message.author.mention} You reached level {new_level}!", delete_after=10)
        else:
            await message.channel.send(f"{message.author.mention} You reached level {new_level}!", delete_after=10)
        role_rewards = settings.get("role_rewards", {})
        if str(new_level) in role_rewards:
            reward_role = message.guild.get_role(int(role_rewards[str(new_level)]))
            if reward_role:
                try:
                    await message.author.add_roles(reward_role)
                    await message.channel.send(f"{message.author.mention} You earned the **{reward_role.name}** role!", delete_after=10)
                except:
                    pass
    else:
        db_set_xp(guild_id, user_id, xp, level)

    # Custom commands
    custom_cmds = db_get_custom_commands(guild_id)
    msg_content = message.content.strip()
    if msg_content in custom_cmds:
        await message.channel.send(custom_cmds[msg_content])
        return

    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload):
    guild_id = str(payload.guild_id)
    msg_id = str(payload.message_id)
    emoji = str(payload.emoji)
    rr = db_get_reaction_roles(guild_id, msg_id)
    role_id = rr.get(emoji)
    if role_id:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(role_id))
        if role and member and not member.bot:
            await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    guild_id = str(payload.guild_id)
    msg_id = str(payload.message_id)
    emoji = str(payload.emoji)
    rr = db_get_reaction_roles(guild_id, msg_id)
    role_id = rr.get(emoji)
    if role_id:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role = guild.get_role(int(role_id))
        if role and member and not member.bot:
            await member.remove_roles(role)

# ============ MODERATION ============

@tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="Member to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_perm(interaction, "ban"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    try:
        await member.send(f"You have been banned from **{interaction.guild.name}**.\n**Reason:** {reason}")
    except:
        pass
    await member.ban(reason=reason)
    embed = discord.Embed(title="Member Banned", description=f"{member.mention} has been banned from the server.", color=0xED4245)
    embed.add_field(name="Reason", value=reason, inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    add_footer(embed)
    await interaction.response.send_message(embed=embed)
    await log(interaction.guild, f"{interaction.user} banned {member} — {reason}")

@tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_perm(interaction, "kick"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    try:
        await member.send(f"You have been kicked from **{interaction.guild.name}**.\n**Reason:** {reason}")
    except:
        pass
    await member.kick(reason=reason)
    embed = discord.Embed(title="Member Kicked", description=f"{member.mention} has been kicked from the server.", color=0xFEE75C)
    embed.add_field(name="Reason", value=reason, inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    add_footer(embed)
    await interaction.response.send_message(embed=embed)
    await log(interaction.guild, f"{interaction.user} kicked {member} — {reason}")

@tree.command(name="mute", description="Mute a member")
@app_commands.describe(member="Member to mute", duration="Duration in minutes (0 = permanent)", reason="Reason for mute")
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int = 0, reason: str = "No reason provided"):
    if not has_perm(interaction, "mute"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not muted_role:
        muted_role = await interaction.guild.create_role(name="Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(muted_role, send_messages=False, speak=False)
    await member.add_roles(muted_role, reason=reason)
    dur_text = f"{duration} minutes" if duration > 0 else "Permanent"
    try:
        await member.send(f"You have been muted in **{interaction.guild.name}**.\n**Reason:** {reason}\n**Duration:** {dur_text}")
    except:
        pass
    embed = discord.Embed(title="Member Muted", description=f"{member.mention} has been muted.", color=0xFEE75C)
    embed.add_field(name="Reason", value=reason, inline=True)
    embed.add_field(name="Duration", value=dur_text, inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    add_footer(embed)
    await interaction.response.send_message(embed=embed)
    await log(interaction.guild, f"{interaction.user} muted {member} for {dur_text} — {reason}")
    if duration > 0:
        await asyncio.sleep(duration * 60)
        if muted_role in member.roles:
            await member.remove_roles(muted_role)
            await log(interaction.guild, f"Mute expired for {member}")

@tree.command(name="unmute", description="Unmute a member")
@app_commands.describe(member="Member to unmute")
async def unmute(interaction: discord.Interaction, member: discord.Member):
    if not has_perm(interaction, "unmute"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if muted_role and muted_role in member.roles:
        await member.remove_roles(muted_role)
        embed = discord.Embed(title="Unmuted", description=f"{member} has been unmuted.", color=0x5865F2)
        await interaction.response.send_message(embed=embed)
        await log(interaction.guild, f"{interaction.user} unmuted {member}")
    else:
        await interaction.response.send_message(f"{member} is not muted.", ephemeral=True)

@tree.command(name="tempban", description="Temporarily ban a member")
@app_commands.describe(member="Member to tempban", minutes="Duration in minutes", reason="Reason")
async def tempban(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    if not has_perm(interaction, "tempban"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    try:
        await member.send(f"You have been temporarily banned from **{interaction.guild.name}**.\n**Reason:** {reason}\n**Duration:** {minutes} minutes")
    except:
        pass
    await member.ban(reason=reason)
    embed = discord.Embed(title="⏱ Member Temp Banned", description=f"{member.mention} has been temporarily banned.", color=0xED4245)
    embed.add_field(name="Duration", value=f"{minutes} minutes", inline=True)
    embed.add_field(name="Reason", value=reason, inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    add_footer(embed)
    await interaction.response.send_message(embed=embed)
    await log(interaction.guild, f"{interaction.user} tempbanned {member} for {minutes}min — {reason}")
    await asyncio.sleep(minutes * 60)
    await interaction.guild.unban(member)
    await log(interaction.guild, f"Tempban expired for {member}")

@tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason for warn")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not has_perm(interaction, "warn"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(member.id)
    db_add_warn(guild_id, user_id, reason, str(interaction.user))
    count = len(db_get_warns(guild_id, user_id))
    embed = discord.Embed(title="Member Warned", description=f"{member.mention} has received a warning.", color=0xFEE75C)
    embed.add_field(name="Reason", value=reason, inline=True)
    embed.add_field(name="Total Warnings", value=str(count), inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    add_footer(embed)
    await interaction.response.send_message(embed=embed)
    try:
        await member.send(f"You have been warned in **{interaction.guild.name}**.\n**Reason:** {reason}\n**Total warns:** {count}")
    except:
        pass
    await log(interaction.guild, f"{interaction.user} warned {member} ({count} total) — {reason}")

@tree.command(name="warns", description="View warns for a member")
@app_commands.describe(member="Member to check")
async def warns(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    guild_id = str(interaction.guild.id)
    user_id = str(member.id)
    user_warns = db_get_warns(guild_id, user_id)
    if not user_warns:
        await interaction.response.send_message(f"{member} has no warnings.", ephemeral=True)
        return
    desc = "\n".join([f"{i+1}. {w['reason']} — by {w['by']} ({w['time'][:10]})" for i, w in enumerate(user_warns)])
    embed = discord.Embed(title=f"Warnings for {member}", description=desc, color=0xffcc00)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="clearwarns", description="Clear all warns for a member")
@app_commands.describe(member="Member to clear warns for")
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    if not has_perm(interaction, "clearwarns"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    user_id = str(member.id)
    db_clear_warns(guild_id, user_id)
    await interaction.response.send_message(f"Warnings cleared for {member}.", ephemeral=True)

@tree.command(name="purge", description="Delete messages in bulk")
@app_commands.describe(amount="Number of messages to delete")
async def purge(interaction: discord.Interaction, amount: int = 10):
    if not has_perm(interaction, "purge"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted {amount} messages.", ephemeral=True)
    await log(interaction.guild, f"{interaction.user} purged {amount} messages in {interaction.channel.mention}")

@tree.command(name="slowmode", description="Set slowmode in a channel")
@app_commands.describe(seconds="Slowmode delay in seconds, 0 to disable")
async def slowmode(interaction: discord.Interaction, seconds: int = 0):
    if not has_perm(interaction, "slowmode"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    await interaction.channel.edit(slowmode_delay=seconds)
    if seconds == 0:
        await interaction.response.send_message("Slowmode disabled.")
    else:
        await interaction.response.send_message(f"Slowmode set to {seconds} seconds.")

@tree.command(name="lockdown", description="Lock a channel so only admins can send messages")
@app_commands.describe(channel="Channel to lock, leave empty for current channel")
async def lockdown(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not has_perm(interaction, "lockdown"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=False)
    embed = discord.Embed(title="Channel Locked", description=f"{channel.mention} has been locked down.", color=0xff4444)
    await interaction.response.send_message(embed=embed)
    await log(interaction.guild, f"{interaction.user} locked {channel.mention}")

@tree.command(name="unlock", description="Unlock a locked channel")
@app_commands.describe(channel="Channel to unlock, leave empty for current channel")
async def unlock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not has_perm(interaction, "unlock"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    channel = channel or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=True)
    embed = discord.Embed(title="Channel Unlocked", description=f"{channel.mention} has been unlocked.", color=0x00cc66)
    await interaction.response.send_message(embed=embed)
    await log(interaction.guild, f"{interaction.user} unlocked {channel.mention}")

@tree.command(name="antithreat", description="Toggle anti-raid and anti-nuke protection on or off")
@app_commands.describe(toggle="on or off")
async def antithreat(interaction: discord.Interaction, toggle: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    enabled = toggle.lower() == "on"
    settings["nuke_protection"] = enabled
    settings["anti_raid"] = enabled
    save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"Anti-threat protection (anti-raid + anti-nuke) turned {toggle.lower()}.", ephemeral=True)
    await log(interaction.guild, f"{interaction.user} turned anti-threat protection {toggle.lower()}.")

# ============ ROLES ============

@tree.command(name="giverole", description="Give a role to a member")
@app_commands.describe(member="Member to give role to", role="Role to give")
async def giverole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not has_perm(interaction, "giverole"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    await member.add_roles(role)
    await interaction.response.send_message(f"Gave **{role.name}** to {member.mention}.")
    await log(interaction.guild, f"{interaction.user} gave {role.name} to {member}")

@tree.command(name="takerole", description="Remove a role from a member")
@app_commands.describe(member="Member to remove role from", role="Role to remove")
async def takerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not has_perm(interaction, "takerole"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    await member.remove_roles(role)
    await interaction.response.send_message(f"Removed **{role.name}** from {member.mention}.")
    await log(interaction.guild, f"{interaction.user} removed {role.name} from {member}")

@tree.command(name="rolereward", description="Set a role to be given at a certain level")
@app_commands.describe(level="Level required", role="Role to give")
async def rolereward(interaction: discord.Interaction, level: int, role: discord.Role):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    if "role_rewards" not in settings:
        settings["role_rewards"] = {}
    settings["role_rewards"][str(level)] = str(role.id)
    save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"Members will receive **{role.name}** at level {level}.", ephemeral=True)

@tree.command(name="reactionrole", description="Add a reaction role to a message")
@app_commands.describe(message_id="Message ID to add reaction role to")
async def reactionrole(interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    db_add_reaction_role(guild_id, message_id, emoji, str(role.id))
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
        await msg.add_reaction(emoji)
    except:
        pass
    await interaction.response.send_message(f"Reaction role set. React with {emoji} to get **{role.name}**.", ephemeral=True)

# ============ AUTO MOD ============

@tree.command(name="blacklist", description="Add a word to the blacklist")
@app_commands.describe(word="Word to blacklist")
async def blacklist(interaction: discord.Interaction, word: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    if "blacklist" not in settings:
        settings["blacklist"] = []
    if word.lower() not in settings["blacklist"]:
        settings["blacklist"].append(word.lower())
        save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"**{word}** added to blacklist.", ephemeral=True)

@tree.command(name="unblacklist", description="Remove a word from the blacklist")
@app_commands.describe(word="Word to remove")
async def unblacklist(interaction: discord.Interaction, word: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    bl = settings.get("blacklist", [])
    if word.lower() in bl:
        bl.remove(word.lower())
        settings["blacklist"] = bl
        save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"**{word}** removed from blacklist.", ephemeral=True)

@tree.command(name="invitefilter", description="Toggle invite link filter on or off")
@app_commands.describe(toggle="on or off")
async def invitefilter(interaction: discord.Interaction, toggle: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    settings["invite_filter"] = toggle.lower() == "on"
    save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"Invite filter turned {toggle.lower()}.", ephemeral=True)

@tree.command(name="familyfilter", description="Toggle the built-in family friendly word filter")
@app_commands.describe(toggle="on or off")
async def familyfilter(interaction: discord.Interaction, toggle: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    settings["family_filter"] = toggle.lower() == "on"
    save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"Family friendly filter turned {toggle.lower()}.", ephemeral=True)

@tree.command(name="antispam", description="Toggle antispam on or off")
@app_commands.describe(toggle="on or off")
async def antispam(interaction: discord.Interaction, toggle: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    settings["antispam"] = toggle.lower() == "on"
    save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"Antispam turned {toggle.lower()}.", ephemeral=True)

# ============ ANTI-THREAT ============

@tree.command(name="lockserver", description="Manually lock all channels with slowmode")
async def lockserver(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    raid_mode[interaction.guild.id] = True
    for ch in interaction.guild.text_channels:
        try:
            await ch.edit(slowmode_delay=30)
        except:
            pass
    await interaction.response.send_message("Server locked. 30s slowmode applied to all channels.")
    await log(interaction.guild, f"{interaction.user} manually locked the server.")

@tree.command(name="unlockserver", description="Remove slowmode from all channels")
async def unlockserver(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    raid_mode[interaction.guild.id] = False
    for ch in interaction.guild.text_channels:
        try:
            await ch.edit(slowmode_delay=0)
        except:
            pass
    await interaction.response.send_message("Server unlocked. Slowmode removed from all channels.")
    await log(interaction.guild, f"{interaction.user} unlocked the server.")

# ============ VERIFICATION ============

class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.success, custom_id="corsu:verify_me")
    async def verify_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        settings = get_settings(guild.id)
        verified_role_id = settings.get("verified_role")
        if not verified_role_id:
            await interaction.response.send_message("Verification is not set up.", ephemeral=True)
            return
        verified_role = guild.get_role(int(verified_role_id))
        if verified_role and verified_role in user.roles:
            await interaction.response.send_message("You are already verified!", ephemeral=True)
            return
        now = datetime.now(timezone.utc).timestamp()
        cooldown = verify_cooldowns.get(str(user.id), 0)
        if now - cooldown < 600:
            remaining = int(600 - (now - cooldown))
            await interaction.response.send_message(f"Please wait {remaining} seconds before requesting another captcha.", ephemeral=True)
            return
        verify_cooldowns[str(user.id)] = now
        code, image_buf = generate_captcha()
        db_save_captcha(str(user.id), code)
        await interaction.response.send_message("Check your DMs for the captcha!", ephemeral=True)
        try:
            file = discord.File(fp=image_buf, filename="captcha.png")
            await user.send("Type the code shown in the image to verify. You have 3 attempts.", file=file)
        except:
            await interaction.followup.send("Could not DM you. Please enable DMs from server members.", ephemeral=True)

@tree.command(name="verifysetup", description="Set up the verification system")
@app_commands.describe(verified_role="Role to give after passing captcha")
async def verifysetup(interaction: discord.Interaction, verified_role: discord.Role):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    guild = interaction.guild
    settings = get_settings(guild.id)
    settings["verified_role"] = str(verified_role.id)
    save_settings(guild.id, settings)

    verify_channel = discord.utils.get(guild.text_channels, name="verify")
    if not verify_channel:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True, use_application_commands=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        verify_channel = await guild.create_text_channel("verify", overwrites=overwrites)
    else:
        await verify_channel.set_permissions(guild.default_role, read_messages=True, send_messages=True, use_application_commands=True)

    for ch in guild.text_channels:
        if ch.name != "verify" and ch.name != LOG_CHANNEL_NAME:
            await ch.set_permissions(guild.default_role, read_messages=False)

    for ch in guild.text_channels:
        if ch.name != "verify":
            await ch.set_permissions(verified_role, read_messages=True, send_messages=True)

    await verify_channel.set_permissions(guild.default_role, read_messages=True, send_messages=False, use_application_commands=False)
    await verify_channel.set_permissions(guild.me, read_messages=True, send_messages=True)
    embed = discord.Embed(title="Verification Required", description="Click the button below to verify yourself and gain access to the server.\n\nYou will receive a captcha code via DM.", color=0x5865F2)
    add_footer(embed)
    view = VerifyButton()
    await verify_channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"Verification system set up. New members must complete captcha to access the server.", ephemeral=True)

# ============ TICKETS ============

@tree.command(name="ticketsetup", description="Set up the ticket system")
@app_commands.describe(support_role="Role that can see all tickets")
async def ticketsetup(interaction: discord.Interaction, support_role: discord.Role = None):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    guild = interaction.guild
    settings = get_settings(guild.id)
    if support_role:
        settings["ticket_support_role"] = str(support_role.id)

    ticket_channel = discord.utils.get(guild.text_channels, name="tickets")
    if not ticket_channel:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False, use_application_commands=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=False)
        ticket_channel = await guild.create_text_channel("tickets", overwrites=overwrites)

    settings["ticket_channel"] = str(ticket_channel.id)
    save_settings(guild.id, settings)
    await ticket_channel.set_permissions(guild.default_role, read_messages=True, send_messages=False, use_application_commands=False)
    await ticket_channel.set_permissions(guild.me, read_messages=True, send_messages=True)
    embed = discord.Embed(title="Support Tickets", description="Need help? Click the button below to open a ticket and our team will assist you shortly.", color=0x5865F2)
    add_footer(embed)
    view = TicketButton()
    await ticket_channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"Ticket system set up in {ticket_channel.mention}.", ephemeral=True)

class TicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="corsu:open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction, "No reason provided")

async def create_ticket(interaction: discord.Interaction, reason: str):
    guild = interaction.guild
    user = interaction.user
    now = datetime.now(timezone.utc).timestamp()
    cooldown = ticket_cooldowns.get(str(user.id), 0)
    if now - cooldown < 600:
        remaining = int(600 - (now - cooldown))
        await interaction.response.send_message(f"You can open a ticket again in {remaining} seconds.", ephemeral=True)
        return
    settings = get_settings(guild.id)
    ticket_name = f"ticket-{user.name.lower().replace(' ', '-')}"
    existing = discord.utils.get(guild.text_channels, name=ticket_name)
    if existing:
        await interaction.response.send_message(f"You already have an open ticket: {existing.mention}", ephemeral=True)
        return
    ticket_cooldowns[str(user.id)] = now
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    support_role_id = settings.get("ticket_support_role")
    if support_role_id:
        support_role = guild.get_role(int(support_role_id))
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    channel = await guild.create_text_channel(ticket_name, overwrites=overwrites)
    embed = discord.Embed(
        title="Support Ticket",
        description=f"Ticket opened by {user.mention}\n**Reason:** {reason}\n\nAn admin will assist you shortly. Use `/closeticket` to close.",
        color=0x5865F2
    )
    await channel.send(embed=embed)
    await interaction.response.send_message(f"Ticket opened: {channel.mention}", ephemeral=True)
    await log(guild, f"{user} opened a ticket — {reason}")

@tree.command(name="ticket", description="Open a support ticket")
@app_commands.describe(reason="Reason for opening a ticket")
async def ticket(interaction: discord.Interaction, reason: str = "No reason provided"):
    await create_ticket(interaction, reason)

@tree.command(name="addticketsupport", description="Add a role that can see all tickets")
@app_commands.describe(role="Role to add as ticket support")
async def addticketsupport(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    settings["ticket_support_role"] = str(role.id)
    save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"**{role.name}** can now see all tickets.", ephemeral=True)

@tree.command(name="removeticketsupport", description="Remove ticket support role access")
async def removeticketsupport(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    settings.pop("ticket_support_role", None)
    save_settings(interaction.guild.id, settings)
    await interaction.response.send_message("Ticket support role removed.", ephemeral=True)

@tree.command(name="closeticket", description="Close the current ticket channel")
async def closeticket(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
        return
    await interaction.response.send_message("Closing ticket in 5 seconds...")
    await log(interaction.guild, f"Ticket {interaction.channel.name} closed by {interaction.user}")
    await asyncio.sleep(5)
    await interaction.channel.delete()

# ============ CUSTOM COMMANDS ============

@tree.command(name="addcommand", description="Add a custom command")
@app_commands.describe(trigger="Command trigger e.g. !rules", response="Response message")
async def addcommand(interaction: discord.Interaction, trigger: str, response: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    db_add_custom_command(guild_id, trigger, response)
    await interaction.response.send_message(f"Command **{trigger}** added.", ephemeral=True)

@tree.command(name="removecommand", description="Remove a custom command")
@app_commands.describe(trigger="Command trigger to remove")
async def removecommand(interaction: discord.Interaction, trigger: str):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    cmds = db_get_custom_commands(guild_id)
    if trigger in cmds:
        db_remove_custom_command(guild_id, trigger)
        await interaction.response.send_message(f"Command **{trigger}** removed.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Command **{trigger}** not found.", ephemeral=True)

@tree.command(name="listcommands", description="List all custom commands")
async def listcommands(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    cmds = db_get_custom_commands(guild_id)
    if not cmds:
        await interaction.response.send_message("No custom commands yet.", ephemeral=True)
        return
    desc = "\n".join([f"**{k}** → {v}" for k, v in cmds.items()])
    embed = discord.Embed(title="Custom Commands", description=desc, color=0x5865F2)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============ INFO ============

@tree.command(name="help", description="Show all commands")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Corsu — Command List", description="Use `/` to access all slash commands.", color=0x5865F2)
    add_footer(embed)
    embed.add_field(name="Moderation", value="`/ban` `/kick` `/mute` `/unmute` `/tempban` `/warn` `/warns` `/clearwarns` `/purge` `/slowmode` `/lockdown` `/unlock`", inline=False)
    embed.add_field(name="Roles", value="`/giverole` `/takerole` `/rolereward` `/reactionrole` `/createrole`", inline=False)
    embed.add_field(name="Permissions", value="`/perm` `/removeperm` `/perms`", inline=False)
    embed.add_field(name="Auto Mod", value="`/blacklist` `/unblacklist` `/invitefilter` `/familyfilter` `/antispam` `/allowattachments` `/linkfilter` `/allowlink` `/removelink`", inline=False)
    embed.add_field(name="Security", value="`/antithreat` `/lockserver` `/unlockserver` `/verifysetup` `/accountage` `/auditperms` `/unban` `/timeout`", inline=False)
    embed.add_field(name="Tickets", value="`/ticketsetup` `/ticket` `/closeticket` `/addticketsupport` `/removeticketsupport`", inline=False)
    embed.add_field(name="Custom Commands", value="`/addcommand` `/removecommand` `/listcommands`", inline=False)
    embed.add_field(name="Info", value="`/userinfo` `/serverinfo` `/ping` `/avatar` `/servericon`", inline=False)
    embed.add_field(name="Levels", value="`/level` `/leaderboard` `/rolereward` `/levelchannel`", inline=False)
    embed.add_field(name="Giveaways", value="`/giveaway` `/giveawayend` `/giveawayreroll`", inline=False)
    embed.add_field(name="Fun", value="`/poll` `/announce` `/8ball` `/coinflip` `/meme` `/joke`", inline=False)
    embed.add_field(name="Utility", value="`/afk` `/support`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="userinfo", description="Get info about a user")
@app_commands.describe(member="Member to look up")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"User Info — {member}", color=0x5865F2)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Roles", value=", ".join([r.name for r in member.roles[1:]]) or "None")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="serverinfo", description="Get server information")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Server Info — {guild.name}", color=0x5865F2)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Members", value=guild.member_count)
    embed.add_field(name="Channels", value=len(guild.channels))
    embed.add_field(name="Roles", value=len(guild.roles))
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Owner", value=guild.owner)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    embed = discord.Embed(title="Pong!", color=0x5865F2)
    embed.add_field(name="Latency", value=f"`{round(bot.latency * 1000)}ms`")
    add_footer(embed)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============ LEVELS ============

@tree.command(name="level", description="Check your level or another member's level")
@app_commands.describe(member="Member to check")
async def level(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    guild_id = str(interaction.guild.id)
    user_id = str(member.id)
    xp, lvl = db_get_xp(guild_id, user_id)
    if lvl == 0:
        lvl = 1
    embed = discord.Embed(title=f"Level — {member}", color=0x5865F2)
    embed.add_field(name="Level", value=lvl)
    embed.add_field(name="XP", value=f"{xp} / {lvl * 100}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="leaderboard", description="Show the XP leaderboard")
async def leaderboard(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    rows = db_get_leaderboard(guild_id)
    if not rows:
        await interaction.response.send_message("No XP data yet.", ephemeral=True)
        return
    desc = ""
    for i, row in enumerate(rows):
        user = interaction.guild.get_member(int(row["user_id"]))
        name = user.display_name if user else "Unknown"
        desc += f"{i+1}. **{name}** — Level {row['level']} ({row['xp']} XP)\n"
    embed = discord.Embed(title="XP Leaderboard", description=desc, color=0x5865F2)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============ FUN ============

@tree.command(name="poll", description="Create a poll")
@app_commands.describe(question="Poll question")
async def poll(interaction: discord.Interaction, question: str):
    embed = discord.Embed(title="Poll", description=question, color=0x5865F2)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@tree.command(name="announce", description="Send an announcement to a channel")
@app_commands.describe(channel="Channel to announce in", message="Announcement message")
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    if not has_perm(interaction, "announce"):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    embed = discord.Embed(description=message, color=0x5865F2, timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=f"Announced by {interaction.user}")
    await channel.send(embed=embed)
    await interaction.response.send_message(f"Announcement sent to {channel.mention}", ephemeral=True)

@tree.command(name="8ball", description="Ask the magic 8ball a question")
@app_commands.describe(question="Your question")
async def eightball(interaction: discord.Interaction, question: str):
    responses = [
        "It is certain.", "Without a doubt.", "Yes, definitely.", "You may rely on it.",
        "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.",
        "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
        "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.",
        "Outlook not so good.", "Very doubtful."
    ]
    embed = discord.Embed(color=0x5865F2)
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=random.choice(responses), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    await interaction.response.send_message(f"**{result}**", ephemeral=True)

# ============ PERMISSIONS ============

@tree.command(name="perm", description="Grant a user or role access to a bot command")
@app_commands.describe(command="Command name e.g. ban", user="User to grant perm to", role="Role to grant perm to")
async def perm(interaction: discord.Interaction, command: str, user: discord.Member = None, role: discord.Role = None):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    if not user and not role:
        await interaction.response.send_message("Specify a user or role.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    guild_perms = db_get_perms(guild_id)
    if "users" not in guild_perms: guild_perms["users"] = {}
    if "roles" not in guild_perms: guild_perms["roles"] = {}
    if user:
        uid = str(user.id)
        if uid not in guild_perms["users"]: guild_perms["users"][uid] = []
        if command not in guild_perms["users"][uid]: guild_perms["users"][uid].append(command)
        db_save_perms(guild_id, guild_perms)
        await interaction.response.send_message(f"Granted **{user.mention}** access to `/{command}`.", ephemeral=True)
    if role:
        rid = str(role.id)
        if rid not in guild_perms["roles"]: guild_perms["roles"][rid] = []
        if command not in guild_perms["roles"][rid]: guild_perms["roles"][rid].append(command)
        db_save_perms(guild_id, guild_perms)
        await interaction.response.send_message(f"Granted **{role.name}** access to `/{command}`.", ephemeral=True)

@tree.command(name="removeperm", description="Remove a user or role's access to a bot command")
@app_commands.describe(command="Command name", user="User to remove perm from", role="Role to remove perm from")
async def removeperm(interaction: discord.Interaction, command: str, user: discord.Member = None, role: discord.Role = None):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    guild_perms = db_get_perms(guild_id)
    if user:
        uid = str(user.id)
        try:
            guild_perms.get("users", {}).get(uid, []).remove(command)
            db_save_perms(guild_id, guild_perms)
        except:
            pass
        await interaction.response.send_message(f"Removed **{user.mention}**'s access to `/{command}`.", ephemeral=True)
    if role:
        rid = str(role.id)
        try:
            guild_perms.get("roles", {}).get(rid, []).remove(command)
            db_save_perms(guild_id, guild_perms)
        except:
            pass
        await interaction.response.send_message(f"Removed **{role.name}**'s access to `/{command}`.", ephemeral=True)

@tree.command(name="perms", description="View permissions for a user or role")
@app_commands.describe(user="User to check", role="Role to check")
async def perms(interaction: discord.Interaction, user: discord.Member = None, role: discord.Role = None):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    guild_perms = db_get_perms(guild_id)
    if "users" not in guild_perms: guild_perms["users"] = {}
    if "roles" not in guild_perms: guild_perms["roles"] = {}
    if user:
        cmds = guild_perms["users"].get(str(user.id), [])
        desc = ", ".join([f"`/{c}`" for c in cmds]) if cmds else "No permissions granted."
        embed = discord.Embed(title=f"Permissions — {user}", description=desc, color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    elif role:
        cmds = guild_perms["roles"].get(str(role.id), [])
        desc = ", ".join([f"`/{c}`" for c in cmds]) if cmds else "No permissions granted."
        embed = discord.Embed(title=f"Permissions — {role.name}", description=desc, color=0x5865F2)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("Specify a user or role.", ephemeral=True)

@tree.command(name="createrole", description="Create a new role with basic member permissions")
@app_commands.describe(name="Name of the role", color="Hex color e.g. ff5733 (optional)")
async def createrole(interaction: discord.Interaction, name: str, color: str = None):
    if not is_admin(interaction):
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    role_color = discord.Color.default()
    if color:
        try:
            role_color = discord.Color(int(color.strip("#"), 16))
        except:
            pass
    role_perms = discord.Permissions(
        read_messages=True,
        send_messages=True,
        read_message_history=True,
        add_reactions=True,
        use_application_commands=True,
        attach_files=True,
        embed_links=True,
        connect=True,
        speak=True
    )
    role = await interaction.guild.create_role(name=name, permissions=role_perms, color=role_color)
    await interaction.response.send_message(f"Role **{role.name}** created. Use `/perm role:{role.name} command:ban` to grant it bot permissions.", ephemeral=True)
    await log(interaction.guild, f"{interaction.user} created role {role.name}")

@tree.command(name="support", description="Get the Corsu support server link")
async def support(interaction: discord.Interaction):
    embed = discord.Embed(title="Corsu Support Server", description="Having issues or need help? Join our support server!", color=0x5865F2)
    embed.add_field(name="Invite", value="[Click here to join](https://discord.gg/ks3uPmZCVh)")
    add_footer(embed)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============ SECRET STATUS COMMAND ============

@bot.command(name="status")
async def status(ctx):
    uptime = datetime.now(timezone.utc) - bot_start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    embed = discord.Embed(title="Corsu Status", color=0x57F287)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="Status", value="Online", inline=True)
    embed.add_field(name="Ping", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="Uptime", value=f"{hours}h {minutes}m {seconds}s", inline=True)
    embed.add_field(name="Servers", value=len(bot.guilds), inline=True)
    embed.add_field(name="Users", value=sum(g.member_count for g in bot.guilds), inline=True)
    await ctx.send(embed=embed)

@tree.command(name="levelchannel", description="Set a channel for level up announcements")
@app_commands.describe(channel="Channel to send level up messages to, leave empty to announce in current channel")
async def levelchannel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not is_admin(interaction):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    if channel:
        settings["level_channel"] = str(channel.id)
        save_settings(interaction.guild.id, settings)
        await interaction.response.send_message(f"Level up announcements will be sent to {channel.mention}.", ephemeral=True)
    else:
        settings.pop("level_channel", None)
        save_settings(interaction.guild.id, settings)
        await interaction.response.send_message("Level up announcements will now show in the channel the user is talking in.", ephemeral=True)

# ============ FUN COMMANDS ============

@tree.command(name="meme", description="Get a random meme")
async def meme(interaction: discord.Interaction):
    await interaction.response.defer()
    import json as _json
    try:
        with urllib.request.urlopen("https://meme-api.com/gimme") as r:
            data = _json.loads(r.read())
        embed = discord.Embed(title=data["title"], color=0xff5500)
        embed.set_image(url=data["url"])
        embed.set_footer(text=f"r/{data['subreddit']}")
        await interaction.followup.send(embed=embed)
    except:
        await interaction.followup.send("Couldn't fetch a meme right now, try again!", ephemeral=True)

@tree.command(name="joke", description="Get a random joke")
async def joke(interaction: discord.Interaction):
    import json as _json
    try:
        req = urllib.request.Request("https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,racist,sexist", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req) as r:
            data = _json.loads(r.read())
        if data["type"] == "single":
            embed = discord.Embed(description=data["joke"], color=0xffcc00)
        else:
            embed = discord.Embed(color=0xffcc00)
            embed.add_field(name="Setup", value=data["setup"], inline=False)
            embed.add_field(name="Punchline", value=data["delivery"], inline=False)
        await interaction.response.send_message(embed=embed)
    except:
        await interaction.response.send_message("Couldn't fetch a joke right now!", ephemeral=True)

@tree.command(name="avatar", description="Get a user's avatar")
@app_commands.describe(member="Member to get avatar of")
async def avatar(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=f"{member.name}'s Avatar", color=0x5865F2)
    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@tree.command(name="servericon", description="Get the server's icon")
async def servericon(interaction: discord.Interaction):
    if not interaction.guild.icon:
        await interaction.response.send_message("This server has no icon.", ephemeral=True)
        return
    embed = discord.Embed(title=f"{interaction.guild.name}'s Icon", color=0x5865F2)
    embed.set_image(url=interaction.guild.icon.url)
    await interaction.response.send_message(embed=embed)

# ============ GIVEAWAY SYSTEM ============

@tree.command(name="giveaway", description="Start a giveaway")
@app_commands.describe(channel="Channel to host giveaway", duration="Duration in minutes", prize="What are you giving away?")
async def giveaway(interaction: discord.Interaction, channel: discord.TextChannel, duration: int, prize: str):
    if not has_perm(interaction, "giveaway"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    end_time = datetime.now(timezone.utc).timestamp() + (duration * 60)
    embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"**Prize:** {prize}\n\nReact with 🎉 to enter!\n\nEnds <t:{int(end_time)}:R>\n**Hosted by:** {interaction.user.mention}", color=0xffcc00)
    msg = await channel.send(embed=embed)
    await msg.add_reaction("🎉")
    giveaways[str(msg.id)] = {"channel_id": channel.id, "guild_id": interaction.guild.id, "prize": prize, "end_time": end_time, "host_id": interaction.user.id}
    await interaction.response.send_message(f"Giveaway started in {channel.mention}!", ephemeral=True)
    await asyncio.sleep(duration * 60)
    await end_giveaway(msg.id, interaction.guild)

async def end_giveaway(message_id, guild):
    data = giveaways.get(str(message_id))
    if not data:
        return
    channel = guild.get_channel(data["channel_id"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(message_id)
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        users = [u async for u in reaction.users() if not u.bot]
        if not users:
            await channel.send("No one entered the giveaway 😢")
        else:
            winner = random.choice(users)
            embed = discord.Embed(title="Giveaway Ended!", description=f"**Prize:** {data['prize']}\n**Winner:** {winner.mention}\n\nCongrats!", color=0x00cc66)
            await channel.send(embed=embed)
            await channel.send(f"Congrats {winner.mention}! You won **{data['prize']}**!")
        del giveaways[str(message_id)]
    except:
        pass

@tree.command(name="giveawayend", description="End a giveaway early")
@app_commands.describe(message_id="Message ID of the giveaway")
async def giveawayend(interaction: discord.Interaction, message_id: str):
    if not has_perm(interaction, "giveaway"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    await end_giveaway(int(message_id), interaction.guild)
    await interaction.response.send_message("Giveaway ended!", ephemeral=True)

@tree.command(name="giveawayreroll", description="Reroll a giveaway winner")
@app_commands.describe(message_id="Message ID of the giveaway")
async def giveawayreroll(interaction: discord.Interaction, message_id: str):
    if not has_perm(interaction, "giveaway"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        users = [u async for u in reaction.users() if not u.bot]
        if not users:
            await interaction.response.send_message("No entries found.", ephemeral=True)
        else:
            winner = random.choice(users)
            await interaction.response.send_message(f"🎉 New winner: {winner.mention}! Congrats!")
    except:
        await interaction.response.send_message("Couldn't find that giveaway.", ephemeral=True)

# ============ AFK SYSTEM ============

@tree.command(name="afk", description="Set your AFK status")
@app_commands.describe(reason="Reason for being AFK")
async def afk(interaction: discord.Interaction, reason: str = "AFK"):
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)
    if guild_id not in afk_users:
        afk_users[guild_id] = {}
    afk_users[guild_id][user_id] = reason
    await interaction.response.send_message(f"You are now AFK: {reason}", ephemeral=True)

@tree.command(name="allowattachments", description="Toggle attachment permissions for a channel")
@app_commands.describe(channel="Channel to toggle attachments for", allow="True to allow, False to deny")
async def allowattachments(interaction: discord.Interaction, channel: discord.TextChannel, allow: bool):
    if not is_admin(interaction):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    await channel.set_permissions(interaction.guild.default_role, attach_files=allow, embed_links=allow)
    state = "enabled" if allow else "disabled"
    await interaction.response.send_message(f"Attachments {state} in {channel.mention}.", ephemeral=True)
    await log(interaction.guild, f"{interaction.user} {state} attachments in #{channel.name}")

# ============ SECURITY COMMANDS ============

@tree.command(name="accountage", description="Set minimum account age to join (in days)")
@app_commands.describe(days="Minimum days old an account must be (0 to disable)")
async def accountage(interaction: discord.Interaction, days: int):
    if not is_admin(interaction):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    settings["min_account_age"] = days
    save_settings(interaction.guild.id, settings)
    if days == 0:
        await interaction.response.send_message("Account age requirement disabled.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Accounts must be at least **{days} days old** to join.", ephemeral=True)

@tree.command(name="auditperms", description="Show roles with dangerous permissions")
async def auditperms(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    dangerous = []
    for role in interaction.guild.roles:
        if role.managed or role.name == "@everyone":
            continue
        role_perms = role.permissions
        flags = []
        if role_perms.administrator: flags.append("Administrator")
        if role_perms.ban_members: flags.append("Ban Members")
        if role_perms.kick_members: flags.append("Kick Members")
        if role_perms.manage_guild: flags.append("Manage Server")
        if role_perms.manage_roles: flags.append("Manage Roles")
        if role_perms.manage_channels: flags.append("Manage Channels")
        if flags:
            dangerous.append(f"**{role.name}**: {', '.join(flags)}")
    if not dangerous:
        await interaction.response.send_message("No roles with dangerous permissions found.", ephemeral=True)
        return
    embed = discord.Embed(title="Roles with Dangerous Permissions", description="\n".join(dangerous), color=0xff4444)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="allowlink", description="Whitelist a domain in the invite/link filter")
@app_commands.describe(domain="Domain to whitelist e.g. youtube.com")
async def allowlink(interaction: discord.Interaction, domain: str):
    if not is_admin(interaction):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    whitelist = settings.get("link_whitelist", [])
    if domain not in whitelist:
        whitelist.append(domain)
        settings["link_whitelist"] = whitelist
        save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"**{domain}** is now whitelisted.", ephemeral=True)

@tree.command(name="removelink", description="Remove a domain from the whitelist")
@app_commands.describe(domain="Domain to remove")
async def removelink(interaction: discord.Interaction, domain: str):
    if not is_admin(interaction):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    whitelist = settings.get("link_whitelist", [])
    if domain in whitelist:
        whitelist.remove(domain)
        settings["link_whitelist"] = whitelist
        save_settings(interaction.guild.id, settings)
    await interaction.response.send_message(f"**{domain}** removed from whitelist.", ephemeral=True)

@tree.command(name="linkfilter", description="Block all links except whitelisted ones")
@app_commands.describe(enabled="on or off")
async def linkfilter(interaction: discord.Interaction, enabled: bool):
    if not is_admin(interaction):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    settings = get_settings(interaction.guild.id)
    settings["link_filter"] = enabled
    save_settings(interaction.guild.id, settings)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"Link filter {state}. Use `/allowlink` to whitelist domains.", ephemeral=True)

@tree.command(name="unban", description="Unban a user by their ID")
@app_commands.describe(user_id="User ID to unban", reason="Reason for unban")
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
    if not has_perm(interaction, "ban"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        embed = discord.Embed(title="Member Unbanned", description=f"**{user}** has been unbanned.", color=0x57F287)
        embed.add_field(name="Reason", value=reason)
        add_footer(embed)
        await interaction.response.send_message(embed=embed)
        await log(interaction.guild, f"{interaction.user} unbanned {user} — {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Could not unban: {e}", ephemeral=True)

@tree.command(name="timeout", description="Timeout a member using Discord's built-in timeout")
@app_commands.describe(member="Member to timeout", minutes="Duration in minutes", reason="Reason")
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    if not has_perm(interaction, "mute"):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    until = discord.utils.utcnow() + dt.timedelta(minutes=minutes)
    try:
        await member.timeout(until, reason=reason)
        try:
            await member.send(f"You have been timed out in **{interaction.guild.name}** for {minutes} minutes.\n**Reason:** {reason}")
        except:
            pass
        embed = discord.Embed(title="⏰ Member Timed Out", description=f"{member.mention} has been timed out.", color=0xFEE75C)
        embed.add_field(name="Duration", value=f"{minutes} minutes", inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        add_footer(embed)
        await interaction.response.send_message(embed=embed)
        await log(interaction.guild, f"{interaction.user} timed out {member} for {minutes}min — {reason}")
    except Exception as e:
        await interaction.response.send_message(f"Could not timeout: {e}", ephemeral=True)

# ============ ERROR HANDLING ============

class SupportButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Support Server", url="https://discord.gg/ks3uPmZCVh", style=discord.ButtonStyle.link, emoji="🔗"))

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    view = SupportButton()
    try:
        await interaction.response.send_message(f"Error: {str(error)}", ephemeral=True, view=view)
    except:
        await interaction.followup.send(f"Error: {str(error)}", ephemeral=True, view=view)

# ============ RUN ============

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable is not set. Please add your bot token to the environment variables.")

bot.run(TOKEN)

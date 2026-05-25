# Corsu Bot

A full-featured Discord moderation and utility bot with slash commands, XP leveling, tickets, giveaways, captcha verification, anti-raid, anti-nuke protection, and more.

---

## Features

- **Moderation** — ban, kick, mute, timeout, tempban, warn, purge, slowmode, lockdown
- **Auto Mod** — antispam, invite filter, word blacklist, family filter, link filter, duplicate detection
- **Security** — anti-raid, anti-nuke, captcha verification, account age gate, permission auditing
- **Tickets** — fully automated support ticket system with role-based access
- **Levels & XP** — message-based XP, level-up announcements, role rewards, leaderboard
- **Giveaways** — timed giveaways with reactions, reroll, early end
- **Reaction Roles** — add roles by reacting to messages
- **Custom Commands** — per-server trigger → response commands
- **Fun** — 8ball, coinflip, meme, joke, poll, announcements
- **AFK System** — set AFK status with a reason

---

## Quickstart (Local)

### 1. Clone the repo

```bash
git clone https://github.com/your-username/discord-bot.git
cd discord-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set your TOKEN
```

### 4. Run the bot

```bash
python main.py
```

---

## Deploy on Render

### Step 1 — Push to GitHub

Push this project to a GitHub repository.

### Step 2 — Create a new Render Web Service

1. Go to [render.com](https://render.com) and sign in
2. Click **New → Web Service**
3. Connect your GitHub repo
4. Configure the service:

| Setting | Value |
|---|---|
| **Environment** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python main.py` |
| **Instance Type** | Free (or paid for 24/7 uptime) |

### Step 3 — Set Environment Variables

In your Render service dashboard, go to **Environment** and add:

| Key | Value |
|---|---|
| `TOKEN` | Your Discord bot token |

> ⚠️ **Never commit your token to GitHub.** Always use environment variables.

### Step 4 — Deploy

Click **Deploy**. Render will install dependencies and start the bot automatically.

---

## Getting Your Bot Token

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create a **New Application**
3. Go to **Bot** → **Add Bot**
4. Under **Token**, click **Reset Token** and copy it
5. Enable all **Privileged Gateway Intents** (Presence, Server Members, Message Content)
6. Go to **OAuth2 → URL Generator**, select `bot` + `applications.commands`
7. Select the permissions your bot needs and invite it to your server

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TOKEN` | ✅ Yes | Your Discord bot token |
| `DB_FILE` | ❌ No | SQLite database file path (default: `corsu.db`) |

---

## Important Notes

- **SQLite on Render**: The free Render tier uses an ephemeral filesystem — the database file (`corsu.db`) will be wiped on each deploy/restart. For persistent storage, upgrade to a paid plan with a persistent disk, or migrate to an external database like PostgreSQL.
- **Slash commands**: On first run, the bot syncs all slash commands globally. This can take up to 1 hour to propagate in Discord.
- **Log channel**: The bot logs events to a channel named `corsu-logs`. Create this channel in your server.
- **Welcome channel**: Welcome messages are sent to a channel named `welcome`.

---

## Command Reference

| Category | Commands |
|---|---|
| Moderation | `/ban` `/kick` `/mute` `/unmute` `/tempban` `/warn` `/warns` `/clearwarns` `/purge` `/slowmode` `/lockdown` `/unlock` `/unban` `/timeout` |
| Roles | `/giverole` `/takerole` `/rolereward` `/reactionrole` `/createrole` |
| Permissions | `/perm` `/removeperm` `/perms` |
| Auto Mod | `/blacklist` `/unblacklist` `/invitefilter` `/familyfilter` `/antispam` `/allowattachments` `/linkfilter` `/allowlink` `/removelink` |
| Security | `/antithreat` `/lockserver` `/unlockserver` `/verifysetup` `/accountage` `/auditperms` |
| Tickets | `/ticketsetup` `/ticket` `/closeticket` `/addticketsupport` `/removeticketsupport` |
| Custom Commands | `/addcommand` `/removecommand` `/listcommands` |
| Levels | `/level` `/leaderboard` `/levelchannel` |
| Giveaways | `/giveaway` `/giveawayend` `/giveawayreroll` |
| Fun | `/poll` `/announce` `/8ball` `/coinflip` `/meme` `/joke` `/avatar` `/servericon` |
| Info | `/userinfo` `/serverinfo` `/ping` `/help` `/support` |
| Utility | `/afk` |
| Prefix | `!status` |

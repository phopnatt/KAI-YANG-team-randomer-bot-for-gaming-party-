import os, json
import discord
from discord.ext import commands
import random
import asyncio

# Intents ต้องเปิด message_content ด้วย
intents = discord.Intents.all()
intents.message_content = True
CONFIG_FILE = "allowed_roles.json"
temp_allowed_users: dict[int, set[int]] = {}

# สร้าง Bot object
bot = commands.Bot(command_prefix='~', intents=intents)

# เช็คสิทธิ์ระดับสูง เช่น ปิดหู, ปิดไมค์, เตะ, disconnect, timeout

def has_high_permissions(member: discord.Member):
    perms = member.guild_permissions
    return any([
        perms.mute_members,
        perms.move_members,
        perms.deafen_members,
        perms.kick_members,
    ])

# กำหนดให้สิทธิ์ชั่วคราว
async def revoke_temp_after(guild_id: int, user_id: int, delay: int = 13):
    await asyncio.sleep(delay)
    temp_allowed_users.get(guild_id, set()).discard(user_id)

# บล็อก ~ ถ้าไม่มีสิทธิ์ระดับสูง หรือสิทธิ์ชั่วคราว (ยกเว้น ~info, ~listcmd)
@bot.event
async def on_message(msg: discord.Message):
    if msg.author.bot:
        return

    gid = msg.guild.id
    uid = msg.author.id
    content_lower = msg.content.lower()

    if content_lower == "allowmyrole":
        temp_allowed_users.setdefault(gid, set()).add(uid)
        await msg.channel.send(f"✅ {msg.author.mention} ใช้ `~` ได้ 7 วินาที!")
        bot.loop.create_task(revoke_temp_after(gid, uid))
        return

    bypass_commands = ["~info", "~listcmd"]
    if msg.content.startswith("~") and not any(msg.content.lower().startswith(cmd) for cmd in bypass_commands):
        has_temp = uid in temp_allowed_users.get(gid, set())
        has_special_perm = has_high_permissions(msg.author)

        if not (has_temp or has_special_perm):
            try:
                await msg.delete()
            except discord.HTTPException:
                pass
            return

    await bot.process_commands(msg)

@bot.event
async def on_ready():
    print(f"✅ Bot พร้อมแล้ว: {bot.user}")

# คำสั่งไม่จำกัดสิทธิ์
@bot.command()
async def info(ctx):
    await ctx.send("This bot is made by jazaza and also generated by chatGPT 4o (Cuz I dunno python bro)")

@bot.command()
async def Listcmd(ctx):
    await ctx.send(
        "**📜 Available Commands:**\n\n"
        "**~listmembers** - แสดงชื่อสมาชิกทั้งหมดในเซิร์ฟเวอร์\n"
        "**~play** - ให้เลือกโหมดสุ่มผู้เล่น: RANK (เลือก 1 คนจากสูงสุด 5 คนใน VC) หรือ 5V5 (แบ่งทีมและย้ายห้องให้อัตโนมัติ)\n"
        "**~winner** - สุ่มผู้ชนะ 1 คนจากผู้ที่อยู่ในห้อง VC เดียวกับคุณ\n"
        "**~pick** - สุ่มจำนวน N คนจาก VC โดยคุณเป็นคนกำหนดจำนวน\n"
        "**~info** - ข้อมูลผู้สร้างบอทและที่มาของโค้ด\n"
        "**allowmyrole** - พิมพ์ในแชทเพื่อเปิดสิทธิ์ใช้ `~` ได้ชั่วคราว 7 วินาที สำหรับคนที่ไม่ได้อยู่ใน role ที่อนุญาต\n\n"
        "🛡️ *เฉพาะคำสั่ง `~info` และ `~listcmd` เท่านั้นที่ทุกคนใช้ได้เสมอ*\n"
        "🔐 *คำสั่งอื่นจะใช้ได้เฉพาะคนที่มีสิทธิ์จัดการเสียง หรือใช้ `allowmyrole` เท่านั้น*"
    )

# ส่วนที่เหลือของโค้ด (play, winner, pick, TeamSelector, VCSelector ฯลฯ) ไม่ต้องเปลี่ยน
# ...

# Bot startup
@bot.command()
async def listmembers(ctx):
    members = ctx.guild.members
    names = [m.name for m in members if not m.bot]
    await ctx.send("👥 Members: " + ", ".join(names))

# ======================
# ระบบสุ่มผู้เล่น
# ======================

class VCSelector(discord.ui.View):
    def __init__(self, members):
        super().__init__(timeout=60)
        self.members = members

    @discord.ui.select(placeholder="🔈 Select VC for Team 1 & 2", min_values=2, max_values=2, options=[])
    async def select_vc(self, interaction: discord.Interaction, select: discord.ui.Select):
        vc1 = interaction.guild.get_channel(int(select.values[0]))
        vc2 = interaction.guild.get_channel(int(select.values[1]))

        if not self.members:
            await interaction.response.send_message("❌ No members to sort", ephemeral=True)
            return

        random.shuffle(self.members)
        half = len(self.members) // 2
        team1 = self.members[:half]
        team2 = self.members[half:]

        for m in team1:
            try: await m.move_to(vc1)
            except: pass
        for m in team2:
            try: await m.move_to(vc2)
            except: pass

        await interaction.response.send_message(
            f"✅ Moved to VC\n🔈 **{vc1.name}**: " + ", ".join(m.display_name for m in team1) +
            f"\n🔈 **{vc2.name}**: " + ", ".join(m.display_name for m in team2)
        )
        self.stop()

class TeamSelector(discord.ui.View):
    @discord.ui.button(label="RANK", style=discord.ButtonStyle.primary)
    async def rank_button(self, interaction: discord.Interaction, _):
        members = [m for m in interaction.guild.members if not m.bot and m.voice]
        if not members:
            await interaction.response.send_message("❌ No one in VC", ephemeral=True)
            return
        group = random.sample(members, 5) if len(members) > 5 else members
        winner = random.choice(group)
        await interaction.response.send_message(f"🎯 RANK winner: {winner.mention}")

    @discord.ui.button(label="5V5", style=discord.ButtonStyle.success)
    async def v5_button(self, interaction: discord.Interaction, _):
        members = [m for m in interaction.guild.members if not m.bot and m.voice]
        vcs = interaction.guild.voice_channels
        if len(vcs) < 2:
            await interaction.response.send_message("❌ Need 2+ VC channels", ephemeral=True)
            return
        options = [discord.SelectOption(label=vc.name, value=str(vc.id)) for vc in vcs]
        view = VCSelector(members)
        view.select_vc.options = options
        await interaction.response.send_message("🔽 Select VC channels:", view=view, ephemeral=True)

@bot.command()
async def play(ctx):
    await ctx.send("🎮 Select mode:", view=TeamSelector())

@bot.command()
async def winner(ctx):
    vc = ctx.author.voice.channel if ctx.author.voice else None
    if not vc:
        await ctx.send("❌ Join VC first")
        return
    members = [m for m in vc.members if not m.bot]
    if not members:
        await ctx.send("❌ No human members in VC")
        return
    win = random.choice(members)
    await ctx.send(f"🎉 Winner in **{vc.name}**: {win.mention}")

@bot.command()
async def pick(ctx):
    vc = ctx.author.voice.channel if ctx.author.voice else None
    if not vc:
        await ctx.send("❌ Join VC first")
        return
    members = [m for m in vc.members if not m.bot]
    await ctx.send("How many people to pick? (reply within 30s)")

    def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
    try:
        msg = await bot.wait_for("message", timeout=30, check=check)
        n = max(1, min(int(msg.content), len(members)))
        chosen = random.sample(members, n)
        await ctx.send("🎯 Selected:\n" + "\n".join(m.mention for m in chosen))
    except asyncio.TimeoutError:
        await ctx.send("⏰ Time out!")

# ======================
# START BOT
# ======================
bot.run()

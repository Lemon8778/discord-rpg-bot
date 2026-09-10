import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
import os
from keep_alive import keep_alive
# -------------------------------------------------------------------
# 1. 資料庫初始化 (擴充地圖、防具、公會與副業材料欄位)
# -------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    
    # 玩家資料表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            gold INTEGER DEFAULT 200,
            hp INTEGER DEFAULT 100,
            max_hp INTEGER DEFAULT 100,
            weapon_name TEXT DEFAULT '木劍',
            weapon_atk INTEGER DEFAULT 5,
            weapon_rarity TEXT DEFAULT 'N',
            armor_name TEXT DEFAULT '布衣',
            armor_def INTEGER DEFAULT 2,
            armor_rarity TEXT DEFAULT 'N',
            potions INTEGER DEFAULT 3,
            wins INTEGER DEFAULT 0,
            job TEXT DEFAULT '未選擇',
            area INTEGER DEFAULT 1,
            wood INTEGER DEFAULT 0,
            ore INTEGER DEFAULT 0,
            fish INTEGER DEFAULT 0,
            guild_id INTEGER DEFAULT 0
        )
    ''')
    
    # 公會資料表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guilds (
            guild_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_name TEXT UNIQUE,
            leader_id INTEGER,
            gold INTEGER DEFAULT 0,
            raid_boss_hp INTEGER DEFAULT 1000,
            raid_boss_max_hp INTEGER DEFAULT 1000,
            boss_level INTEGER DEFAULT 1
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def get_player(user_id, username):
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    player = cursor.fetchone()
    
    if not player:
        cursor.execute(
            "INSERT INTO players (user_id, username) VALUES (?, ?)",
            (user_id, str(username))
        )
        conn.commit()
        cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
        player = cursor.fetchone()
        
    conn.close()
    return player

# -------------------------------------------------------------------
# 2. 地圖、轉蛋池與設定數據
# -------------------------------------------------------------------
AREAS = {
    1: {"name": "🌲 幽暗森林", "min_level": 1, "req_level_next": 5, "monsters": ["哥布林 👺", "野狼 🐺"], "boss": "森林熊王 🐻"},
    2: {"name": "🌋 烈焰山谷", "min_level": 5, "req_level_next": 15, "monsters": ["熔岩魔 🌋", "火元素 🔥"], "boss": "地獄火龍 🐲"},
    3: {"name": "🏰 亡靈古堡", "min_level": 15, "req_level_next": 30, "monsters": ["骷髏兵 💀", "吸血鬼 🧛"], "boss": "死靈騎士 🐴"}
}

WEAPON_POOL = {
    "SSR": [("🔥 滅世者之劍", 80), ("⚡ 雷霆神鎚", 85), ("🌌 太空光劍", 90)],
    "SR":  [("⚔️ 精鋼長劍", 35), ("🏹 冰霜長弓", 40), ("🔮 元素法杖", 38)],
    "R":   [("🗡️ 騎士鐵劍", 18), ("🪓 戰鬥雙斧", 20), ("🔱 獵人長槍", 15)],
    "N":   [("🪵 破舊木棒", 5), ("🔪 生鏽小刀", 3), ("🧹 魔法掃帚", 6)]
}

RARITY_COLORS = {
    "SSR": discord.Color.gold(),
    "SR":  discord.Color.purple(),
    "R":   discord.Color.blue(),
    "N":   discord.Color.light_grey()
}

# -------------------------------------------------------------------
# 3. 職業選擇 UI
# -------------------------------------------------------------------
class JobSelect(discord.ui.Select):
    def __init__(self, user_id):
        options = [
            discord.SelectOption(label="狂戰士", description="高攻擊加成，低血量時獲得額外收益", emoji="⚔️"),
            discord.SelectOption(label="聖騎士", description="高血量與高防禦，受到的傷害較低", emoji="🛡️"),
            discord.SelectOption(label="游俠", description="高幸運，更容易遭遇寶箱與 Boss", emoji="🏹"),
            discord.SelectOption(label="煉金術士", description="初始附帶更多藥水，藥水恢復效果更好 (+80HP)", emoji="🔮"),
        ]
        super().__init__(placeholder="請選擇你的初始職業...", min_values=1, max_values=1, options=options)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("這不是你的職業選擇選單！", ephemeral=True)
            
        chosen_job = self.values[0]
        conn = sqlite3.connect('game_data.db')
        cursor = conn.cursor()
        
        if chosen_job == "狂戰士":
            cursor.execute("UPDATE players SET job=?, max_hp=90, hp=90 WHERE user_id=?", (chosen_job, self.user_id))
        elif chosen_job == "聖騎士":
            cursor.execute("UPDATE players SET job=?, max_hp=150, hp=150 WHERE user_id=?", (chosen_job, self.user_id))
        elif chosen_job == "游俠":
            cursor.execute("UPDATE players SET job=?, gold=350 WHERE user_id=?", (chosen_job, self.user_id))
        elif chosen_job == "煉金術士":
            cursor.execute("UPDATE players SET job=?, potions=6 WHERE user_id=?", (chosen_job, self.user_id))
            
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🎉 恭喜成功轉職為 **{chosen_job}**！使用 `/冒險` 開始旅程！")

class JobSelectView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.add_item(JobSelect(user_id))

# -------------------------------------------------------------------
# 4. 冒險按鈕 View
# -------------------------------------------------------------------
class AdventureView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    @discord.ui.button(label="⚔️ 繼續探索", style=discord.ButtonStyle.danger)
    async def adventure_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("這不是你的冒險區域！", ephemeral=True)
        await interaction.response.defer()
        await do_adventure(interaction, is_update=True)

    @discord.ui.button(label="🧪 喝藥水", style=discord.ButtonStyle.success)
    async def heal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("你不能幫別人喝藥水！", ephemeral=True)
        await interaction.response.defer()
        await do_heal_and_update(interaction)

# -------------------------------------------------------------------
# 5. 通用喝藥水與冒險邏輯
# -------------------------------------------------------------------
async def do_heal_and_update(interaction: discord.Interaction):
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    p = get_player(interaction.user.id, interaction.user.name)
    
    if p[13] <= 0:  # potions 索引為 13
        conn.close()
        return await interaction.followup.send("❌ 你沒有藥水了！請使用 `/商店` 購買。", ephemeral=True)
        
    heal_amount = 80 if p[15] == "煉金術士" else 50
    new_hp = min(p[5] + heal_amount, p[6])
    cursor.execute("UPDATE players SET hp = ?, potions = potions - 1 WHERE user_id = ?", (new_hp, interaction.user.id))
    conn.commit()
    conn.close()
    
    message = await interaction.original_response()
    if message.embeds:
        embed = message.embeds[0]
        embed.set_footer(text=f"🧪 已使用 1 瓶藥水 (恢復 {heal_amount} HP) | 當前血量: {new_hp}/{p[6]}")
        await interaction.edit_original_response(embed=embed, view=AdventureView(interaction.user.id))

async def do_adventure(interaction: discord.Interaction, is_update=False):
    user = interaction.user
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    p = get_player(user.id, user.name)
    
    # 欄位說明: p[15]=job, p[16]=area, p[10]=armor_name, p[11]=armor_def
    current_area = p[16]
    area_info = AREAS.get(current_area, AREAS[1])
    
    if p[15] == "未選擇":
        conn.close()
        view = JobSelectView(user.id)
        if is_update:
            return await interaction.followup.send("⚠️ 冒險前請先選擇你的職業！", view=view, ephemeral=True)
        return await interaction.response.send_message("⚠️ 冒險前請先選擇你的職業！", view=view, ephemeral=True)

    if p[5] <= 0:
        conn.close()
        embed = discord.Embed(
            title="💀 你已經受重傷昏迷了！",
            description="請先使用 `/喝藥水` 補充血量才能繼續冒險。",
            color=discord.Color.dark_red()
        )
        if is_update:
            return await interaction.edit_original_response(embed=embed, view=AdventureView(user.id))
        return await interaction.response.send_message(embed=embed, view=AdventureView(user.id), ephemeral=True)

    weights = [50, 30, 10, 10] if p[15] == "游俠" else [60, 20, 15, 5]
    event_type = random.choices(["monster", "chest", "trap", "boss"], weights=weights)[0]
    
    job_atk = 10 if p[15] == "狂戰士" else 0
    total_atk = (p[2] * 3) + p[8] + job_atk
    armor_def = p[11]
    
    raw_damage = random.randint(10, 25) * current_area
    damage_taken = max(1, raw_damage - armor_def)
    if p[15] == "聖騎士":
        damage_taken = int(damage_taken * 0.7)
        
    new_hp = max(0, p[5] - damage_taken)
    embed = discord.Embed()
    
    if event_type == "monster":
        monster = random.choice(area_info["monsters"])
        exp = random.randint(20, 40) * current_area
        gold = random.randint(15, 50) * current_area
        
        embed.title = f"⚔️ [{area_info['name']}] 遭遇戰擊勝！"
        embed.description = f"你揮舞著 **[{p[9]}] {p[7]}** 擊敗了 **{monster}**！\n\n" \
                            f"💥 造成傷害：`{total_atk + random.randint(5, 15)}`\n" \
                            f"🛡️ 防具護盾：`-{armor_def} 減傷` | 🩸 實扣傷害：`-{damage_taken} HP` (剩餘 HP: `{new_hp}/{p[6]}`)\n" \
                            f"💰 獲得金幣：`+{gold}`\n✨ 獲得經驗：`+{exp} EXP`"
        embed.color = discord.Color.green()

    elif event_type == "chest":
        gold = random.randint(100, 300) * current_area
        exp = random.randint(30, 60) * current_area
        new_hp = p[5]
        
        embed.title = f"🎁 [{area_info['name']}] 發現黃金寶箱！"
        embed.description = f"你在探索中找到了一個隱藏的寶箱！\n\n💰 獲得金幣：`+{gold}`\n✨ 獲得經驗：`+{exp} EXP`"
        embed.color = discord.Color.gold()

    elif event_type == "trap":
        gold = random.randint(5, 15)
        exp = 5
        embed.title = f"⚠️ [{area_info['name']}] 踩到陷阱！"
        embed.description = f"你不小心觸發了地區陷阱！\n\n🩸 受到傷害：`-{damage_taken} HP` (剩餘 HP: `{new_hp}/{p[6]}`)\n💰 撿到散落金幣：`+{gold}`"
        embed.color = discord.Color.red()

    elif event_type == "boss":
        boss = area_info["boss"]
        gold = random.randint(200, 500) * current_area
        exp = random.randint(100, 200) * current_area
        embed.title = f"🔥 [{area_info['name']}] 遭遇區域 BOSS：【{boss}】！"
        embed.description = f"經歷艱苦戰鬥，你討伐了 **{boss}**！\n\n🩸 受到重創：`-{damage_taken} HP` (剩餘 HP: `{new_hp}/{p[6]}`)\n💰 獲得巨額寶藏：`+{gold}`\n✨ 獲得海量經驗：`+{exp} EXP`"
        embed.color = discord.Color.purple()

    new_exp = p[3] + exp
    new_gold = p[4] + gold
    level = p[2]
    req_exp = level * 100
    
    if new_exp >= req_exp:
        level += 1
        new_exp -= req_exp
        embed.add_field(name="🎉 升級！", value=f"升到了 **Lv.{level}**！最大 HP 增加 20！", inline=False)
        cursor.execute("UPDATE players SET max_hp = max_hp + 20, hp = max_hp + 20 WHERE user_id = ?", (user.id,))

    cursor.execute("UPDATE players SET level = ?, exp = ?, gold = ?, hp = ? WHERE user_id = ?",
                   (level, new_exp, new_gold, new_hp, user.id))
    conn.commit()
    conn.close()
    
    view = AdventureView(user.id)
    if is_update:
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view)

# -------------------------------------------------------------------
# 6. Bot 初始化與新系統指令註冊
# -------------------------------------------------------------------
class GameBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = GameBot()

@bot.tree.command(name="轉職", description="選擇你的初始職業")
async def choose_job_cmd(interaction: discord.Interaction):
    p = get_player(interaction.user.id, interaction.user.name)
    if p[15] != '未選擇':
        return await interaction.response.send_message(f"❌ 你已經是 **{p[15]}** 了！", ephemeral=True)
    await interaction.response.send_message("請選擇你的職業：", view=JobSelectView(interaction.user.id))

@bot.tree.command(name="冒險", description="前往當前地圖探索")
@app_commands.checks.cooldown(1, 8, key=lambda i: (i.user.id))
async def adventure_cmd(interaction: discord.Interaction):
    get_player(interaction.user.id, interaction.user.name)
    await do_adventure(interaction, is_update=False)

# 🗺️ 【地圖區域系統】
@bot.tree.command(name="移動地圖", description="切換前往的地圖區域")
async def move_map(interaction: discord.Interaction, 區域編號: int):
    if 區域編號 not in AREAS:
        return await interaction.response.send_message("❌ 無效的區域編號！目前開放區域 1~3。", ephemeral=True)
        
    p = get_player(interaction.user.id, interaction.user.name)
    target_area = AREAS[區域編號]
    
    if p[2] < target_area["min_level"]:
        return await interaction.response.send_message(
            f"❌ 等級不足！進入 **{target_area['name']}** 需要達到 **Lv.{target_area['min_level']}** (當前: Lv.{p[2]})",
            ephemeral=True
        )
        
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE players SET area = ? WHERE user_id = ?", (區域編號, interaction.user.id))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"🗺️ 成功移動至 **{target_area['name']}**！使用 `/冒險` 開始探索此地圖！")

# 🪓 【生活副業系統】(砍樹 / 挖礦 / 釣魚)
@bot.tree.command(name="副業", description="進行生活採集獲取製作材料 (砍樹/挖礦/釣魚)")
@app_commands.choices(類別=[
    app_commands.Choice(name="🪓 砍樹 (獲得木材)", value="chop"),
    app_commands.Choice(name="⛏️ 挖礦 (獲得礦石)", value="mine"),
    app_commands.Choice(name="🎣 釣魚 (獲得鮮魚)", value="fish")
])
@app_commands.checks.cooldown(1, 15, key=lambda i: (i.user.id))
async def gather(interaction: discord.Interaction, 類別: app_commands.Choice[str]):
    p = get_player(interaction.user.id, interaction.user.name)
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    
    amount = random.randint(1, 5)
    
    if 類別.value == "chop":
        cursor.execute("UPDATE players SET wood = wood + ? WHERE user_id = ?", (amount, interaction.user.id))
        msg = f"🪓 你砍伐樹木，獲得了 `{amount}` 個 **木材 🪵**！(總計: {p[17] + amount})"
    elif 類別.value == "mine":
        cursor.execute("UPDATE players SET ore = ore + ? WHERE user_id = ?", (amount, interaction.user.id))
        msg = f"⛏️ 你開採礦脈，獲得了 `{amount}` 個 **礦石 🪨**！(總計: {p[18] + amount})"
    elif 類別.value == "fish":
        cursor.execute("UPDATE players SET fish = fish + ? WHERE user_id = ?", (amount, interaction.user.id))
        msg = f"🎣 你在河邊垂釣，釣到了 `{amount}` 條 **鮮魚 🐟**！(總計: {p[19] + amount})"
        
    conn.commit()
    conn.close()
    await interaction.response.send_message(msg)

# 🔨 【合成製作系統】
@bot.tree.command(name="合成製作", description="耗費副業材料合成裝備或補給品")
@app_commands.choices(配方=[
    app_commands.Choice(name="🛡️ 鎖子甲 (需求: 10 礦石, 5 木材)", value="armor1"),
    app_commands.Choice(name="🧪 高級藥水 x3 (需求: 10 鮮魚)", value="potion3")
])
async def craft(interaction: discord.Interaction, 配方: app_commands.Choice[str]):
    p = get_player(interaction.user.id, interaction.user.name)
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    
    # 索引: p[17]=wood, p[18]=ore, p[19]=fish
    if 配方.value == "armor1":
        if p[18] < 10 or p[17] < 5:
            conn.close()
            return await interaction.response.send_message("❌ 材料不足！製作鎖子甲需要 **10 礦石** 與 **5 木材**。", ephemeral=True)
            
        cursor.execute('''
            UPDATE players 
            SET ore = ore - 10, wood = wood - 5, armor_name = '鎖子甲', armor_def = 15, armor_rarity = 'R' 
            WHERE user_id = ?
        ''', (interaction.user.id,))
        msg = "🔨 打造成功！獲得 **[R] 鎖子甲** (防御力 +15) 並已自動裝備！"

    elif 配方.value == "potion3":
        if p[19] < 10:
            conn.close()
            return await interaction.response.send_message("❌ 材料不足！製作高級藥水需要 **10 鮮魚**。", ephemeral=True)
            
        cursor.execute("UPDATE players SET fish = fish - 10, potions = potions + 3 WHERE user_id = ?", (interaction.user.id,))
        msg = "🧪 煉製成功！獲得了 **3 瓶 🧪 藥水**！"

    conn.commit()
    conn.close()
    await interaction.response.send_message(msg)

# 🏰 【公會系統】
@bot.tree.command(name="建立公會", description="花費 500 金幣創立公會")
async def create_guild(interaction: discord.Interaction, 公會名稱: str):
    p = get_player(interaction.user.id, interaction.user.name)
    if p[20] != 0:  # guild_id
        return await interaction.response.send_message("❌ 你已經加入其他公會了！", ephemeral=True)
    if p[4] < 500:
        return await interaction.response.send_message("❌ 創立公會需要 `500` 金幣！", ephemeral=True)
        
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO guilds (guild_name, leader_id) VALUES (?, ?)", (公會名稱, interaction.user.id))
        guild_id = cursor.lastrowid
        cursor.execute("UPDATE players SET gold = gold - 500, guild_id = ? WHERE user_id = ?", (guild_id, interaction.user.id))
        conn.commit()
        await interaction.response.send_message(f"🏰 成功創立公會 **【{公會名稱}】**！")
    except sqlite3.IntegrityError:
        await interaction.response.send_message("❌ 該公會名稱已被使用！", ephemeral=True)
    finally:
        conn.close()

# ⚔️ 【公會團本 Boss 戰】
@bot.tree.command(name="團本討伐", description="與公會成員共同挑戰公會 Boss")
async def guild_raid(interaction: discord.Interaction):
    p = get_player(interaction.user.id, interaction.user.name)
    if p[20] == 0:
        return await interaction.response.send_message("❌ 你尚未加入任何公會！", ephemeral=True)
        
    conn = sqlite3.connect('game_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT guild_name, raid_boss_hp, raid_boss_max_hp, boss_level FROM guilds WHERE guild_id = ?", (p[20],))
    g = cursor.fetchone()
    
    if not g:
        conn.close()
        return await interaction.response.send_message("❌ 公會資料不存在！", ephemeral=True)
        
    job_atk = 10 if p[15] == "狂戰士" else 0
    damage = (p[2] * 5) + p[8] + job_atk + random.randint(10, 30)
    new_boss_hp = max(0, g[1] - damage)
    
    if new_boss_hp == 0:
        reward_gold = 1000 * g[3]
        cursor.execute('''
            UPDATE guilds 
            SET boss_level = boss_level + 1, raid_boss_max_hp = raid_boss_max_hp + 1000, raid_boss_hp = raid_boss_max_hp + 1000 
            WHERE guild_id = ?
        ''', (p[20],))
        cursor.execute("UPDATE players SET gold = gold + ? WHERE user_id = ?", (reward_gold, interaction.user.id))
        conn.commit()
        conn.close()
        return await interaction.response.send_message(
            f"🎉 **討伐成功！** 公會成員殺死了 Lv.{g[3]} 團本 Boss！\n"
            f"💥 你造成了最後一擊 `{damage}` 傷害！全員獲得獎勵 `+{reward_gold}` 金幣！Boss 等級已提升！"
        )
        
    cursor.execute("UPDATE guilds SET raid_boss_hp = ? WHERE guild_id = ?", (new_boss_hp, p[20]))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(
        f"⚔️ 你對 **【{g[0]}】** 的 Lv.{g[3]} 團本 Boss 造成了 **{damage}** 點傷害！\n"
        f"🩸 Boss 剩餘 HP: `{new_boss_hp} / {g[2]}`"
    )

# 📊 【個人面板 (含防具與副業材料)】
@bot.tree.command(name="狀態", description="檢視完整的角色面板")
async def profile(interaction: discord.Interaction):
    p = get_player(interaction.user.id, interaction.user.name)
    job_atk = 10 if p[15] == "狂戰士" else 0
    total_atk = (p[2] * 3) + p[8] + job_atk
    area_name = AREAS.get(p[16], AREAS[1])["name"]
    
    embed = discord.Embed(title=f"🛡️ {interaction.user.name} 的英雄面板", color=RARITY_COLORS.get(p[9], discord.Color.blue()))
    embed.add_field(name="職業", value=f"**{p[15]}**", inline=True)
    embed.add_field(name="等級 / 地圖", value=f"Lv.{p[2]} ({area_name})", inline=True)
    embed.add_field(name="持有金幣", value=f"💰 {p[4]}", inline=True)
    embed.add_field(name="生命值 (HP)", value=f"❤️ {p[5]} / {p[6]}", inline=True)
    embed.add_field(name="攻擊 / 防禦", value=f"⚔️ {total_atk} / 🛡️ {p[11]}", inline=True)
    embed.add_field(name="藥水數量", value=f"🧪 {p[13]} 瓶", inline=True)
    embed.add_field(name="武器欄位", value=f"**[{p[9]}] {p[7]}** (+{p[8]} ATK)", inline=False)
    embed.add_field(name="防具欄位", value=f"**[{p[12]}] {p[10]}** (+{p[11]} DEF)", inline=False)
    embed.add_field(name="🎒 材料背包", value=f"🪵 木材: `{p[17]}` | 🪨 礦石: `{p[18]}` | 🐟 鮮魚: `{p[19]}`", inline=False)
    
    await interaction.response.send_message(embed=embed)

# -------------------------------------------------------------------
# 7. 啟動機器人
# -------------------------------------------------------------------
if __name__ == "__main__":
    keep_alive()  # 啟動 Web 服務保持 Port 開放
    TOKEN = os.getenv("DISCORD_TOKEN")
    bot.run(TOKEN)
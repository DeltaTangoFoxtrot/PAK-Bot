import json
import mysql.connector
import re
import sys
import emoji
from datetime import datetime
from pathlib import Path

import discord
from discord.ext import commands

import pastebin3

class dbConnection:
    def __init__(self, host, database, user, password):
        self.db = mysql.connector.connect(host=host, user=user, password=password, database=database)
        self.db.close()
    def select(self, query, parameters = None):
        try:
            self.db.connect()
            cursor = self.db.cursor()
            if parameters:
                cursor.execute(query, parameters)
            else:
                cursor.execute(query)
            result = cursor.fetchall()
            cursor.close()
            self.db.close()
            return result
        except mysql.connector.Error as err:
            return err.msg
    def execute(self, query, parameters = None, commit=False):
        try:
            self.db.connect()
            cursor = self.db.cursor()
            if parameters:
                cursor.execute(query, parameters)
            else:
                cursor.execute(query)
            if commit:
                self.db.commit()
            cursor.close()
            self.db.close()
            return "gucci"
        except mysql.connector.Error as err:
            return err.msg
    def callproc(self, query, args):
        try:
            self.db.connect()
            cursor = self.db.cursor()
            result = cursor.callproc(query, args)
            cursor.close()
            self.db.close()
            return result
        except mysql.connector.Error as err:
            return err.msg

with open('config.json') as f:
    config = json.load(f)

discordToken = config["token"]
dbHost = config["db"]["host"]
dbDatabase = config["db"]["database"]
dbUser = config["db"]["user"]
dbPassword = config["db"]["password"]

pastebinApiKey = config["pastebinApiKey"]

create_roleReacts = """CREATE TABLE IF NOT EXISTS roleReacts (messageId VARCHAR(100), roleId VARCHAR(100), react VARCHAR(100)) 
    ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_bin;"""
    
create_sp_getReactRoleId = """CREATE PROCEDURE sp_getReactRoleId (IN messageId varchar(100), IN react varchar(100) CHARSET utf8mb4, OUT roleId VARCHAR(100))
    BEGIN
        SELECT
           roleReacts.roleId 
        INTO roleId
        FROM roleReacts
        WHERE roleReacts.messageId = messageId AND roleReacts.react = react
        LIMIT 1;
    END"""

create_memberNames = """CREATE TABLE IF NOT EXISTS memberNames (userId TEXT, isAccountChange BOOL, newName TEXT)"""

insert_memberNames = """INSERT INTO memberNames(userId, isAccountChange, newName) SELECT %s, %s, %s"""

select_memberNames = """SELECT memberNames.isAccountChange, memberNames.newName FROM memberNames WHERE memberNames.userId = %s"""

intents = discord.Intents.default()
intents.members = True

mydb = dbConnection(dbHost, dbDatabase, dbUser, dbPassword)
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.command()
async def ping(ctx):
    await ctx.send("pong")

@bot.command()
@commands.has_permissions(create_instant_invite=True)
async def invite(ctx):
    invite = await ctx.channel.create_invite()
    await ctx.send(invite.url)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, number):
    mgs = []
    number = int(number)
    async for x in ctx.channel.history(limit = number):
        mgs.append(x)
    await ctx.channel.delete_messages(mgs)

@bot.command()
@commands.has_permissions(administrator=True)
async def sql(ctx,arg):
    if re.match("^select", arg.strip(), re.I):
        await ctx.send(mydb.select(arg))
    else:
        await ctx.send(mydb.execute(arg))

@bot.command()
@commands.has_permissions(administrator=True)
async def sync_roles(ctx):
    mydb.execute("CREATE TABLE IF NOT EXISTS roles (id varchar(100), name varchar(100), assignable bool);")
    mydb.execute("TRUNCATE TABLE roles;")
    roles = ctx.guild.roles
    sql = 'INSERT INTO roles (id, name, assignable) VALUES ' + ", ".join(["('{}', '{}', {})".format(r.id, r.name, 'false' if r.permissions.manage_channels or r.permissions.administrator or r.managed else 'true') for r in roles])
    mydb.execute(sql, commit=True)
    await ctx.send(mydb.select("SELECT * FROM roles;"))
    
@bot.command()
@commands.has_permissions(manage_roles=True)
async def react_role(ctx, *args):
    if len(args) < 4:
        await ctx.send("requires arguments {channelId}, {messageId}, {roleid}, {react}")
        return
    channelId= int(args[0])
    messageId = int(args[1])
    roleId = int(args[2])
    if args[3].isdigit():
        reactId = int(args[3])
        react = bot.get_emoji(reactId)
    elif bool(emoji.get_emoji_regexp().search(args[3])):
        react = args[3]
    else:
        await ctx.send("invalid react")
        return

    channel = bot.get_channel(channelId)
    msg = await channel.fetch_message(messageId)
    await msg.add_reaction(react)
    
    mydb.execute(create_roleReacts)

    mydb.execute("INSERT INTO roleReacts (messageId, roleId, react) VALUES " + "('{}','{}','{}')".format(messageId, roleId, args[3] if bool(emoji.get_emoji_regexp().search(args[3])) else int(args[3])), commit=True)
    await ctx.send(mydb.select("SELECT * FROM roleReacts WHERE messageId = '{}'".format(messageId)))

def getReactRoleId(messageId, react):
    mydb.execute(create_roleReacts)
    spExists = mydb.select("SELECT EXISTS(SELECT 1 FROM mysql.proc p WHERE db = 'PAKBot' AND name = 'sp_getReactRoleId')")
    if not spExists[0][0]:
        mydb.execute(create_sp_getReactRoleId)
    result = mydb.callproc("sp_getReactRoleId", [messageId, react, 0])
    return result[2]

@bot.command()
@commands.has_permissions(administrator=True)
async def remove_from_author(ctx, *args):
    channel = bot.get_channel(int(args[0]))
    if not channel:
        await ctx.send("could not get channel")
        return
    
    member = await bot.fetch_user(int(args[1]))
    if not member:
        await ctx.send("could not get member")
        return

    await ctx.send("Deleting messages in {} from {}".format(channel.name, member.name))

    def format_dt(dt):
        return datetime.strptime(dt, '%m/%d/%y')

    after = format_dt(args[2]) if 2 < len(args) else None
    before = format_dt(args[3]) if 3 < len(args) else None

    counter = 0
    async for message in channel.history(limit=None,before=before,after=after):
        if message.author == member:
            await message.delete()
            counter += 1

    await ctx.send("Deleted {} messages from {} to {}".format(counter, after if after else "beginning of time", before if before else "end of time"))

@bot.command()
async def etiquette(ctx):
    try:
        with open('etiquette.txt') as f:
            message = f.read()
        await ctx.send(message)
    except:
        await ctx.send("No etiquette file defined")

@bot.command()
@commands.has_permissions(administrator=True)
async def getrolemembers(ctx, role: discord.Role):
    members = "\n".join(str(member) for member in role.members)
    url = pastebin3.paste(pastebinApiKey, members, private = "unlisted", expire_date='10M')
    await ctx.send(url)

@bot.command()
@commands.has_permissions(administrator=True)
async def mutesetup(ctx):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name="Muted")
    
    if not role:
        role = await guild.create_role(name="Muted")
    
    for channel in guild.channels:
        await channel.set_permissions(role, speak=False, send_messages=False, read_message_history=True, read_messages=False)
        
    await ctx.send("Permissions set for Muted role")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def mute(ctx, member: discord.Member):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name="Muted")

    if not role:
        role = await guild.create_role(name="Muted")

        for channel in guild.channels:
            await channel.set_permissions(role, speak=False, send_messages=False, read_message_history=True, read_messages=False)
    
    await member.add_roles(role)
    embed=discord.Embed(title="User Muted", description="**{0}** was muted by **{1}**".format(member, ctx.message.author), color=0xff00f6)
    await ctx.send(embed=embed)
    
@bot.command()
@commands.has_permissions(manage_messages=True)
async def unmute(ctx, member: discord.Member):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name="Muted")

    await member.remove_roles(role)
    embed=discord.Embed(title="User Unmuted", description="**{0}** was unmuted by **{1}**".format(member, ctx.message.author), color=0xff00f6)
    await ctx.send(embed=embed)

@bot.command()
async def names(ctx, member: discord.Member = None):
    if not member:
        member = ctx.message.author
    mydb.execute(create_memberNames)
    result = mydb.select(select_memberNames, (member.id,))
    if len(result) == 0:
        await ctx.send("No previous names found for user")
    else:
        await ctx.send("Account Change | Old Name\n" + "\n".join([f"{'true' if name[0] == 1 else 'false'} | {name[1].decode()}" for name in result]))
  
@bot.event
async def on_raw_reaction_add(payload):
    channel = bot.get_channel(payload.channel_id)
    guild = channel.guild
    messageId = payload.message_id
    userId = payload.user_id
    emoji = payload.emoji
    member = guild.get_member(userId)
    
    if emoji.is_custom_emoji():
        react = emoji.id
    else:
        react = emoji.name
        
    roleId = getReactRoleId(messageId, react)
    if roleId:
        role = guild.get_role(int(roleId))
        await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    channel = bot.get_channel(payload.channel_id)
    guild = channel.guild
    messageId = payload.message_id
    userId = payload.user_id
    emoji = payload.emoji
    member = guild.get_member(userId)

    if emoji.is_custom_emoji():
        react = emoji.id
    else:
        react = emoji.name

    roleId = getReactRoleId(messageId, react)
    if roleId:
        role = guild.get_role(int(roleId))
        await member.remove_roles(role)

@bot.event
async def on_message_delete(message):
    if message.author.bot : return
    
    embed=discord.Embed(title="{} deleted a message in {}".format(message.author.name, message.channel), description="")
    if message.content:
        embed.add_field(name= message.content, value="Message", inline=True)
    if len(message.attachments):
        embed.set_image(url=message.attachments[0].proxy_url)
    channel=message.guild.system_channel
    await channel.send(embed=embed)

@bot.event
async def on_message_edit(message_before, message_after):
    if message_before.author.bot: return
    if message_before.content == message_after.content: return

    embed=discord.Embed(title="{} edited a message in {}".format(message_before.author.name, message.channel), description="")
    embed.add_field(name= message_before.content ,value="Before edit", inline=True)
    embed.add_field(name= message_after.content ,value="After edit", inline=True)
    channel=message_before.guild.system_channel
    await channel.send(embed=embed)

def save_member_name_change(userId, isAccountChange, before):
    mydb.execute(create_memberNames)
    result = mydb.execute(insert_memberNames, (userId, isAccountChange, before), True)

@bot.event
async def on_member_update(member_before, member_after):
    if member_before.nick and member_before.nick != member_after.nick:
        save_member_name_change(member_before.id, 0, member_before.nick)
        
@bot.event
async def on_user_update(user_before, user_after):
    if user_before.name != user_after.name:
        save_member_name_change(user_before.id, 1, user_before.name)
        
@bot.event
async def on_member_remove(member):
    channel = member.guild.system_channel
    await channel.send("{} left server".format(member.mention))
    
@bot.event
async def on_member_ban(guild, member):
    channel = guild.system_channel
    await channel.send("{} banned from server".format(member.mention))

bot.run(discordToken)

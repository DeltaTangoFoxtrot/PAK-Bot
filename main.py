import json
import mysql.connector
import re
import sys
import emoji
from datetime import datetime
from pathlib import Path

import discord
from discord.ext import commands

class dbConnection:
    def __init__(self, host, database, user, password):
        self.db = mysql.connector.connect(host=host, user=user, password=password, database=database)
        self.db.close()
    def select(self, query):
        try:
            self.db.connect()
            cursor = self.db.cursor()
            cursor.execute(query)
            result = cursor.fetchall()
            cursor.close()
            self.db.close()
            return result
        except mysql.connector.Error as err:
            return err.msg
    def execute(self, query, commit=False):
        try:
            self.db.connect()
            cursor = self.db.cursor()
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

logChannelId = config["logChannelId"]

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
    await ctx.send("\n".join(str(role) for role in role.members)
    
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
    
    embed=discord.Embed(title="{} deleted a message".format(message.author.name), description="")
    if message.content:
        embed.add_field(name= message.content, value="Message", inline=True)
    if len(message.attachments):
        embed.set_image(url=message.attachments[0].proxy_url)
    channel=bot.get_channel(logChannelId)
    await channel.send(embed=embed)

@bot.event
async def on_message_edit(message_before, message_after):
    if message_before.author.bot: return
    if message_before.content == message_after.content: return

    embed=discord.Embed(title="{} edited a message".format(message_before.author.name), description="")
    embed.add_field(name= message_before.content ,value="Before edit", inline=True)
    embed.add_field(name= message_after.content ,value="After edit", inline=True)
    channel=bot.get_channel(logChannelId)
    await channel.send(embed=embed)

bot.run(discordToken)

import json
import mysql.connector
import re
import sys

import discord
from discord.ext import commands

with open('config.json') as f:
    config = json.load(f)

discordToken = config["token"]
dbHost = config["db"]["host"]
dbDatabase = config["db"]["database"]
dbUser = config["db"]["user"]
dbPassword = config["db"]["password"]

create_roleReacts = """CREATE TABLE IF NOT EXISTS roleReacts (messageId VARCHAR(100), roleId VARCHAR(100), react VARCHAR(100)) 
    ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE utf8mb4_bin;"""

intents = discord.Intents.default()
intents.members = True

mydb = mysql.connector.connect(host=dbHost, user=dbUser, password=dbPassword, database=dbDatabase)
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
    try:
        cursor = mydb.cursor()
        cursor.execute(arg)
        if re.match("^select", arg.strip(), re.I):
            await ctx.send(cursor.fetchall())
        else:
            await ctx.send("gucci")
    except mysql.connector.Error as err:
        await ctx.send(err.msg)

@bot.command()
@commands.has_permissions(administrator=True)
async def sync_roles(ctx):
    try:
        cursor = mydb.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS roles (id varchar(100), name varchar(100), assignable bool);")
        cursor.execute("TRUNCATE TABLE roles;")
        roles = ctx.guild.roles
        sql = 'INSERT INTO roles (id, name, assignable) VALUES ' + ", ".join(["('{}', '{}', {})".format(r.id, r.name, 'false' if r.permissions.manage_channels or r.permissions.administrator or r.managed else 'true') for r in roles])
        cursor.execute(sql)
        cursor.execute("SELECT * FROM roles;");
        await ctx.send(cursor.fetchall())
    except mysql.connector.Error as err:
        await ctx.send(err.msg)

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
    elif len(args[3]) == 1:
        react = args[3]
    else:
        await ctx.send("invalid react")
        return

    channel = bot.get_channel(channelId)
    msg = await channel.fetch_message(messageId)
    await msg.add_reaction(react)

    try:
        cursor = mydb.cursor()
        cursor.execute(create_roleReacts)
        cursor.execute("INSERT INTO roleReacts (messageId, roleId, react) VALUES " + "('{}','{}','{}')".format(messageId, roleId, args[3] if len(args[3]) == 1 else int(args[3])))
        cursor.execute("SELECT * FROM roleReacts WHERE messageId = '{}'".format(messageId))
        await ctx.send(cursor.fetchall())
    except mysql.connector.Error as err:
        await ctx.send(err.msg)

def getReactRoleId(messageId, react):
    cursor = mydb.cursor()
    cursor.execute(create_roleReacts)
    cursor.execute("SELECT EXISTS(SELECT 1 FROM mysql.proc p WHERE db = 'PAKBot' AND name = 'sp_getReactRoleId')")
    spExists = cursor.fetchall()
    if not spExists[0][0]:
        cursor.execute("""
            CREATE PROCEDURE sp_getReactRoleId (IN messageId varchar(100), IN react varchar(100) CHARSET utf8mb4, OUT roleId VARCHAR(100))
                BEGIN
                    SELECT
                       roleReacts.roleId 
                    INTO roleId
                    FROM roleReacts
                    WHERE roleReacts.messageId = messageId AND roleReacts.react = react
                    LIMIT 1;
                END
            """)
    result = cursor.callproc("sp_getReactRoleId", [messageId, react, 0])
    return result[2]

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

    try:
        roleId = getReactRoleId(messageId, react)
        if roleId:
            role = guild.get_role(int(roleId))
            await member.add_roles(role)
    except mysql.connector.Error as err:
        await channel.send(err.msg)

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

    try:
        roleId = getReactRoleId(messageId, react)
        if roleId:
            role = guild.get_role(int(roleId))
            await member.remove_roles(role)
    except mysql.connector.Error as err:
        await channel.send(err.msg)

bot.run(discordToken)

# Detects and handles spam messages in UNLV discord servers
# Written on 11/4/2025 by GitHub/theplaceincan
import json
import discord
from datetime import datetime
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
from typing import List, cast
from openai import AsyncOpenAI, RateLimitError
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
import re

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
openai_key = os.getenv('OPENAI_TOKEN')

client = AsyncOpenAI(api_key=openai_key)

handler = logging.FileHandler(filename='SpamRemover.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

OPENAI_MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = (
    "You are a spam detector for a college Discord server. "
    "Respond with ONLY 'SPAM' or 'NOT_SPAM'. "
    "Look for: scholarship scams, fake giveaways, phishing, suspicious offers, "
    "emotional manipulation, urgency tactics, and 'DM me' solicitations."
)

# ------- Metrics -------
METRICS_FILE = "SpamRemoverMetrics.json"

def load_metrics():
    try:
        with open(METRICS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "total_messages": 0,
            "filtered_locally": 0,
            "sent_to_api": 0,
            "spam_detected": 0,
            "start_date": str(datetime.now())
        }

def save_metrics(metrics_):
    with open(METRICS_FILE, 'w') as f:
        json.dump(metrics_, f, indent=2)

metrics_data = load_metrics()

def print_metrics():
    total_messages = metrics_data['total_messages']
    filtered_locally = metrics_data['filtered_locally']
    api_calls = metrics_data['sent_to_api']
    spam_detected = metrics_data['spam_detected']
    if total_messages > 0:
        reduction = (filtered_locally / total_messages) * 100
        print("SpamRemover Metrics")
        print(f"{'='*50}")
        print(f"Total messages: {total_messages}")
        print(f"Filtered locally: {filtered_locally}")
        print(f"API calls: {api_calls}")
        print(f"Spam detected: {spam_detected}")
        print(f"API cost reduction: {reduction}")
        print(f"{'='*50}")

# ------- Functions -------

# Checks age of account
def account_age_days(member: discord.Member):
    created = member.created_at.replace(tzinfo=None)
    days = (datetime.now() - created).days
    return days

def member_join_age_days(member: discord.Member):
    if not isinstance(member, discord.Member) or member.joined_at is None:
        return 9999
    return (datetime.now() - member.joined_at.replace(tzinfo=None)).days

LINK_RE = re.compile(r'(https?://\S+|discord\.gg/\S+|t\.me/\S+)', re.I)

# Checks whether we should call the API
def check_if_possible_spam(message):
    content = message.content
    lower = content.lower()

    # If messages short, then likely a regular convo
    if len(content) < 20:
        return False

    # If @everyone or @here, check
    if '@everyone' in content or '@here' in content:
        if len(message.author.roles) < 2:
            print("Mass mention likely from trusted user, likely an announcement")
            return False
        print("Possible scam, mass mention")
        return True

    # If it has links, then must check if spam
    if LINK_RE.search(content):
        print("Possible scam, has links")
        return True

    # If new account, check
    if account_age_days(message.author) < 7: # created recently
        print("Possible scam, new account")
        return True

    # If user joined recently check
    if member_join_age_days(message.author) < 7: # joined recently
        print("Possible scam, new member")
        return True

    # If message has sus words, check
    scam_keywords = [
        "first come first serve", "dm me", "free", "giveaway", "loan", "grant",
        "cashapp", "venmo", "crypto", "airdrop", "investment", "quick money",
        "i’m giving out", "perfect condition", "limited time", "urgent",
    ]
    if any(k in lower for k in scam_keywords):
        print("Possible scam, scammy words.")
        return True

    # If trusted user, skip
    # if len(message.author.roles) > 1:
    #     print("Likely safe, user has multiple roles")
    #     return False

    # Otherwise, probably safe
    print("Likely safe, no suspicion found")
    return False


# Calls the API to check if spam
async def is_spam(message_content: str) -> bool:
    try:
        messages: List[ChatCompletionMessageParam] = [
            cast(ChatCompletionSystemMessageParam, {"role": "system", "content": SYSTEM_PROMPT}),
            cast(ChatCompletionUserMessageParam,
                 {"role": "user", "content": f"Is this message spam?\n\nMessage: {message_content}"}),
        ]

        resp = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=10,
        )

        result = (resp.choices[0].message.content or "").strip().upper()

        print(f"AI Response: {result} for message: {message_content[:50]}...")
        logging.info(f"AI said '{result}' for: {message_content[:100]}")
        return result == "SPAM"

    except RateLimitError:
        logging.warning("Rate limited by OpenAI - letting message through")
        return False
    except Exception as e:
        logging.error(f"Error checking spam: {e}")
        return False

# ------- Events -------

# Bot is online
@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print("\n")
    print_metrics()

# When a message is sent
@bot.event
async def on_message(message):
    # Ignore messages from our bot
    if message.author == bot.user:
        return

    print("Message detected: " + message.content)

    # Update metrics
    metrics_data['total_messages'] += 1

    # Check if possible spam
    print("Checking if possible spam...")
    try:
        possibly_spam = check_if_possible_spam(message)
    except Exception as e:
        logging.exception(f"check_if_possible_spam crashed: {e}")
        possibly_spam = False
    if not possibly_spam:
        print("Likely safe!")
        metrics_data["filtered_locally"] += 1
        save_metrics(metrics_data)
        await bot.process_commands(message)
        return

    # Check if spam
    metrics_data['sent_to_api'] += 1
    save_metrics(metrics_data)
    print("Checking if spam by AI")
    if await is_spam(message.content):
        print("Found spam!")
        metrics_data['spam_detected'] += 1
        save_metrics(metrics_data)
        await message.delete()
        await message.channel.send(f"{message.author.mention} Your message was removed as spam.")
        logging.info(f"Deleted spam from {message.author}: {message.content}")

        if metrics_data["spam_detected"] % 10 == 0:
            print_metrics()

    await bot.process_commands(message)

# ------- Commands -------
@bot.command(name="metrics")
@commands.has_permissions(administrator=True)
async def show_metrics(ctx):
    total_messages = metrics_data['total_messages']
    filtered_locally = metrics_data['filtered_locally']
    api_calls = metrics_data['sent_to_api']
    spam_detected = metrics_data['spam_detected']
    if total_messages > 0:
        reduction = (filtered_locally / total_messages) * 100
        embed = discord.Embed(
            title="Spam Remover Metrics",
            color=discord.Color.green(),
            timestamp=datetime.now(),
        )
        embed.add_field(name="Total messages", value=total_messages)
        embed.add_field(name="Filtered locally", value=filtered_locally)
        embed.add_field(name="API calls", value=api_calls)
        embed.add_field(name="Spam detected", value=spam_detected)
        embed.add_field(name="API cost reduction", value=reduction)
        await ctx.send(embed=embed)
    else:
        await ctx.send("No messages processed yet")

bot.run(token, log_handler=handler, log_level=logging.INFO)
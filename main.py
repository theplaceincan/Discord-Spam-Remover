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
from collections import defaultdict
from datetime import timedelta

load_dotenv()
token = os.getenv('DISCORD_TOKEN')
openai_key = os.getenv('OPENAI_TOKEN')

client = AsyncOpenAI(api_key=openai_key)

handler = logging.FileHandler(filename='SpamRemover.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

message_handler = logging.FileHandler(filename='SpamRemover_deleted.log', encoding='utf-8', mode='a')
message_handler.setLevel(logging.INFO)
message_logger = logging.getLogger('deleted_messages')
message_logger.addHandler(message_handler)
message_logger.setLevel(logging.INFO)

bot = commands.Bot(command_prefix='!', intents=intents)

OPENAI_MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = (
    "You are a spam detector for a college Discord server. "
    "Respond with ONLY 'SPAM' or 'NOT_SPAM'. "
    "Look for: scholarship scams, fake giveaways, phishing, suspicious offers, "
    "emotional manipulation, urgency tactics, and 'DM me' solicitations."
)

user_spam_attempts = defaultdict(list)
user_spam_detected = defaultdict(int)
MAX_SUS_MESSAGES = 5
TIME_WINDOW = 60 # sec
TIMEOUT_DURATION = timedelta(minutes=10)

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
        if len(message.author.roles) > 2:
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
    scam_patterns = [
        r'\bdm\b',  # matches "DM" as standalone word
        r'\bgiving?\s+out\b',  # matches "give out" or "giving out"
        r'\bfree\b',
        r'\bgiveaway\b',
        r'\bloan\b',
        r'\bgrant\b',
        r'\bcashapp\b',
        r'\bvenmo\b',
        r'\bcrypto\b',
        r'\bairdrop\b',
        r'\binvestment\b',
        r'\bquick\s+money\b',
        r'\bperfect\s+condition\b',
        r'\blimited\s+time\b',
        r'\burgent\b',
        r'\bfirst\s+come\s+first\s+serve\b',
    ]
    if any(re.search(pattern, lower) for pattern in scam_patterns):
        print("Possible scam, scammy words")
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

    user_id = message.author.id
    user_spam_attempts[user_id].append(datetime.now())

    user_spam_attempts[user_id] = [
        t for t in user_spam_attempts[user_id]
        if (datetime.now() - t).total_seconds() < TIME_WINDOW
    ]

    attempt_count = len(user_spam_attempts[user_id])
    print(f"User {message.author.name} has {attempt_count} suspicious messages in last {TIME_WINDOW}s")

    # Timeout repeat offenders
    if attempt_count >= MAX_SUS_MESSAGES:
        print(f"🚨 Rate limit exceeded! Timing out {message.author.name}")
        try:
            await message.author.timeout(TIMEOUT_DURATION, reason="Spam rate limit exceeded")
            await message.channel.send(
                f"{message.author.mention} You have been timed out for {TIMEOUT_DURATION.total_seconds() // 60} minutes "
                f"for sending too many suspicious messages. Please slow down."
            )
            message_logger.info(f"SPAM DETECTED | User: {message.author.name} ({message.author.id}) | "
                                f"Channel: {message.channel.name} | "
                                f"Account Age: {account_age_days(message.author)} days | "
                                f"Server Age: {member_join_age_days(message.author)} days | "
                                f"Content: {message.content}")
            await message.delete()
            user_spam_attempts[user_id].clear()
            metrics_data["filtered_locally"] += 1 # API call not wasted
            save_metrics(metrics_data)
            await bot.process_commands(message)
            return
        except discord.errors.Forbidden:
            print("Can't timeout user - insufficient permissions")
        except Exception as e:
            print(f"Error timing out user: {e}")

    # Check if spam
    metrics_data['sent_to_api'] += 1
    save_metrics(metrics_data)
    print("Checking if spam by AI")
    if await is_spam(message.content):
        print("Found spam!")
        metrics_data['spam_detected'] += 1
        save_metrics(metrics_data)
        user_spam_detected[user_id] += 1

        try:
            message_logger.info(f"SPAM DETECTED | User: {message.author.name} ({message.author.id}) | "
                                f"Channel: {message.channel.name} | "
                                f"Account Age: {account_age_days(message.author)} days | "
                                f"Server Age: {member_join_age_days(message.author)} days | "
                                f"Content: {message.content}")
            await message.delete()
            if user_spam_detected[user_id] == 1:
                await message.channel.send(
                    f"{message.author.mention} Your message was removed as spam."
                    f" Further violations will lead to a timeout."
                )
            else:
                timeout_mins = 10 * user_spam_detected[user_id] # increases timeout length
                await message.author.timeout(
                    timedelta(minutes=timeout_mins),
                    reason=f"Spam detected ({user_spam_detected[user_id]} times)"
                )
                logging.info(f"Deleted spam from {message.author}: {message.content}")
        except discord.errors.Forbidden:
            print("Can't delete message or timeout user - insufficient permissions")
            await message.channel.send(f"{message.author.mention} Your message was flagged as spam.")
        except Exception as e:
            print(f"Error deleting message: {e}")

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
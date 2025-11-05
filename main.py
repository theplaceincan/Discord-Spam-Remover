# Detects and handles spam messages in UNLV discord servers
# Written on 11/4/2025 by github/theplaceincan

import discord
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

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if len(message.content) < 20:
        return

    if await is_spam(message.content):
        await message.delete()
        await message.channel.send(f"{message.author.mention} Your message was removed as spam.")
        logging.info(f"Deleted spam from {message.author}: {message.content}")

    await bot.process_commands(message)

bot.run(token, log_handler=handler, log_level=logging.INFO)
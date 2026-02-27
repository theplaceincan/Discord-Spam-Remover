# Discord Spam Remover
Discord Spam Remover is an auomated Discord moderation bot designed to detect and remove spams/scams/phishing messages in student/university Discord servers. It uses a hybrid detection pipeline by comining lightweight heuristics with an LLM-based classifier.

The design of this bot prioritizes:
- Real-time moderation
- Cost-effective use of LLM API's
- Progressive rule enforcement for repeat offenders
- Audit logging and metrics tracking

This bot was built specifically for college Discord servers, where I've noticed many spam, phishing, fake giveaways, and impersonation messages by scammers.

---

# Key Features & Basic Design

Key features of this bot include:

1. Local suspicion filter
   - Detects risky signals, such as mass-mentions, suspicous links, new accounts (joined or created), and known sammy messages (ex. crypto, DM me, giveaway, etc)
   - Messages detected to be possible spam are sent to an AI classifier
2. AI Classification
   - Uses OpenAI API to determine if a message is spam
   - The model returns either `SPAM` or `NOT_SPAM`

Alongside this is the progressive rule enforcement system that acts based on n-offense:
1. On the first offense, the message is deleted (and the user is warned that their message was deleted).
2. On the second offensive, there is an automatic time out.
3. On the third and repeating offenses, there is a rate-limit timeout. The timeout duation increases with repeated violations.

---

# More Featues

1. Rate Limiting & Abuse Protection
- Users sending multiple suspicious messages within a short time window are automatically timed out to prevent spam bursts.
- The configurable parameters for this are suspicous messages allowed per window, time window/duration, and timeout length.

2. Metrics & Observability
- The bot tracks moderation statistics in real time for:
  - Total messages processed
  - Messages filtered locally (API calls avoided)
  - Messages sent to AI
  - Spam messages detected
  - Estimated API cost reduction
 
3. Audit Logging
- Deleted (optionally flagged messages too) spam messages are logged with context. This helps review false incidents and adjust detection rules. Each log includes:
  - Username and ID
  - Channel name
  - Account age
  - Server join age
  - Message content

---

# Flow
User Message
→ Local Suspicion Filter
→ (If suspicious) AI Classification
→ Enforcement (delete / warn / timeout)
→ Logging + Metrics Update

---

# Requirements

Requirements:
- Python 3.10+
- Discord Bot Token
- OpenAI API Key

Dependencies:
- discord.py
- python-dotenv
- openai

Install dependencies with:
``` pip install discord.py python-dotenv openai ```

---

# Set-up

1. Clone the repo
```
git clone https://github.com/YOUR_USERNAME/Discord-Spam-Remover.git
cd Discord-Spam-Remover
```
2. Create `.env` file
```
DISCORD_TOKEN=your_discord_bot_token
OPENAI_TOKEN=your_openai_api_key
```
3. Run the bot
```
python main.py
```

---

# Key Parameters

`MAX_SUS_MESSAGES` — suspicious messages allowed per time window
`TIME_WINDOW` — rate-limit window (seconds)
`TIMEOUT_DURATION` — base timeout length
`OPENAI_MODEL` — AI model used for classification

---

# Possible Improvement Ideas

1. Role-based trust system (skip checks for verified members, already somewhat in place)
2. Web dashboard for moderation metrics
3. Customizable detection rules per server
4. Batch processing for high-traffic servers (although probably not needed)
5. Scale the bot into a multi-server platform for university organization Discord communities beyond moderation?

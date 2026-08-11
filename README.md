# NSE News Watcher

Watches free Indian financial news (Moneycontrol, Economic Times, Business
Standard, LiveMint), matches each article to a Nifty 500 stock, tags it
bullish/bearish with a confidence score, and sends an alert to Telegram.

**Advisory only.** This does not place trades or connect to a broker - it
just tells you about relevant news as fast as it can find it. You decide
what to do with it.

## How it runs

Scheduled via GitHub Actions (`.github/workflows/news_watcher.yml`) every 5
minutes during roughly NSE market hours - no need to keep your own computer
on. Each run is a single, independent poll pass (`--once`); a small cache
file remembers which articles were already alerted on so you don't get
repeat messages across runs.

## One-time setup

**1. Telegram** (required) - message **@BotFather** in Telegram, `/newbot`,
follow the prompts, copy the token it gives you. Then message your new bot
once (any text) so it can find your chat ID.

**2. Gemini API key** (optional, recommended) - free key from
[aistudio.google.com/apikey](https://aistudio.google.com/apikey), no card
needed. Without this, alerts use a simpler free keyword-matching scorer
instead of an AI reading each headline - still works, just cruder.

**3. Add these as repo secrets**: on GitHub, go to this repo's
**Settings > Secrets and variables > Actions > New repository secret**, and
add:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY` (optional - skip if not using Gemini)

**4. Turn it on**: the workflow runs automatically once these secrets
exist. To test it manually first: go to the **Actions** tab > "NSE News
Watcher" > **Run workflow** - tick "dry run" to test without actually
sending Telegram messages.

## Running locally instead (optional)

```
pip install -r requirements.txt
cp config/telegram_credentials.example.json config/telegram_credentials.json   # fill in your token/chat id
cp config/gemini_credentials.example.json config/gemini_credentials.json       # optional, fill in your key
python scripts/run_news_watcher.py            # continuous loop, market hours only
python scripts/run_news_watcher.py --once --dry-run   # single test pass, no real sends
```

## Known limitations

- **Not a validated trading signal.** The bullish/bearish tag is a
  best-effort read of the headline (keyword-based, or Gemini if
  configured) - it has not been backtested against actual stock price
  moves. Treat it as a fast heads-up to go read the news yourself, not a
  buy/sell instruction.
- **Symbol matching is heuristic.** Genuinely ambiguous company names
  (e.g. a bare "Reliance" could mean Reliance Industries or Reliance
  Power) are deliberately skipped rather than guessed - so some real
  mentions may be missed, in exchange for fewer wrong-stock alerts.
- **The free keyword scorer** (used automatically if no Gemini key is set)
  can occasionally misread a headline with mixed signals, e.g. "shares
  fall despite profit surge" - the Gemini-based scorer fixes this class of
  error by actually reading the sentence.

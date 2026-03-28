# Fin-gram

Fin-gram is a personal finance tracker with a private Web App, Telegram integration, analytics, and a public SEO layer.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_server.py
```

## Main routes

- `/` - public Russian landing page
- `/ru`, `/en` - localized landing pages
- `/ru/about`, `/en/about`
- `/ru/pricing`, `/en/pricing`
- `/ru/faq`, `/en/faq`
- `/ru/blog/<slug>`, `/en/blog/<slug>`
- `/app` - private Fin-gram Web App
- `/robots.txt`
- `/sitemap.xml`

## Required environment variables

```env
APP_SECRET=change-me
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_BOT_USERNAME=your_bot_username
TELEGRAM_WEBAPP_URL=https://fin-gram.online/app
TELEGRAM_ADMIN_USER_ID=123456789
SITE_URL=https://fin-gram.online
PORT=8000
```

## Google Search Console checklist

1. Open Google Search Console and add `https://fin-gram.online` as a property.
2. Verify domain or URL-prefix ownership.
3. Submit `https://fin-gram.online/sitemap.xml`.
4. Inspect these URLs manually:
   - `https://fin-gram.online/ru`
   - `https://fin-gram.online/en`
   - `https://fin-gram.online/ru/faq`
   - `https://fin-gram.online/ru/blog/expense-income-journal`
5. Confirm that `/app` and `/api/` are not meant for indexing.
6. Check social preview and Open Graph rendering for the public landing.
7. Re-submit updated pages after publishing new SEO articles.

## Telegram / production notes

- Set BotFather Web App URL to `https://fin-gram.online/app`.
- Keep the public marketing site on `https://fin-gram.online`.
- Use HTTPS only.

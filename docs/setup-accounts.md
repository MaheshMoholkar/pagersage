# Accounts and keys (task S01)

Put every value in your password manager and in your local `.env` (copy `.env.example`).
Never commit `.env`.

| What | Where | `.env` variable | Status |
|---|---|---|---|
| Anthropic API key + team spend cap | console.anthropic.com → API keys; Limits → set a monthly cap | `ANTHROPIC_API_KEY` | to do |
| Discord webhook | Discord channel → Edit channel → Integrations → Webhooks → New | `DISCORD_WEBHOOK_URL` | to do |
| GitHub demo repo for issues | create e.g. `pagersage-demo`; fine-grained token with **Issues: read/write** on that repo only | `GITHUB_ISSUES_REPO`, `GITHUB_TOKEN` | to do |
| Hosting | Railway (API + FalkorDB) and Vercel (frontend), see task S06 | set in each platform, not `.env` | to do |
| GitHub CLI | `gh auth login` | none | done (MaheshMoholkar) |
| Docker | Docker Desktop running | none | done |

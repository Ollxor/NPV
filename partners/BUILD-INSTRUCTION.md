# Build instruction — paste this into Claude Code

On the call (or any time after), open **Claude Code** and paste the whole block
below. It will interview you — asking for your organization, language(s),
country, and where you want the feed delivered — and then build your own version
by adapting NPV's working system.

You don't need to understand the code. Just answer Claude's questions and, when
asked, paste in your two keys.

See a live example of the finished thing — NPV's multilingual feed:
**<https://ollxor.github.io/NPV/>**

---

## Copy everything between the lines

```
You are helping me set up an automated "research & news monitoring" system for
my organization, modeled on an existing working system built by NPV (a Swedish
psychedelic-science association). I am not necessarily technical — please guide
me step by step, ask me for anything you need, and keep explanations plain.

== WHAT WE'RE BUILDING ==
Every day, a GitHub Actions job should:
  1. Fetch new articles from several research/news sources
  2. Remove ones we've already seen (deduplication)
  3. Use the Claude API to filter out irrelevant items
  4. Use the Claude API to write a short summary per relevant item
  5. Deliver each relevant item to a destination I choose (see OUTPUT below)
A human then reviews and decides what gets published. The system never posts to
social media on its own — it only produces suggestions.

== REFERENCE IMPLEMENTATION (READ THIS FIRST) ==
A complete, working version is public at: https://github.com/Ollxor/NPV
Read that repository to understand the structure (the fetchers, the
filter/summarize step, the Slack posting, the multilingual web feed in docs/,
the seen.json deduplication, and the GitHub Actions workflows). Build my version
by adapting it — do NOT push to that repo; create a brand-new repository under
MY GitHub account.

== MY DETAILS (ask me for any of these that are blank) ==
- Organization name:        __________
- Country:                  __________
- Topic / field:            __________   (likely the same psychedelic-science scope)
- Summary language(s):      __________   (one language, or several with a menu —
                                           see LANGUAGES below; English by default)
- Output destination:       __________   (default: Slack — see OUTPUT below)
- I will provide later: my Anthropic API key, and any destination key/URL needed

== ADAPTATIONS I NEED FROM THE REFERENCE VERSION ==
1. SOURCES: Keep the international sources (PubMed, Semantic Scholar,
   Psychedelic Alpha) — they work for every country. REPLACE the Sweden-only
   sources (DiVA, SwePub) with my country's equivalent national thesis/research
   database. If you're unsure which that is, research it and propose options to
   me before coding. Confirm with me before finalizing.
2. LANGUAGES: Write summaries in the language(s) I chose. If I want just one,
   use that. If I want several, generate all of them in a single Claude call per
   article and give the web page a language menu (as the NPV reference does for
   the Nordic and Baltic languages). Keep a neutral, scientific tone.
3. SETTINGS: Use the cheap model claude-haiku-4-5-20251001, cap at a handful of
   items per run, and run daily.

== OUTPUT (keep this step modular so I can switch destinations later) ==
Implement the ONE destination I choose; default to Slack. Keep the
fetch/filter/summarize pipeline unchanged — only the final delivery differs.
  - SLACK (default): post each item as a separate message via an incoming
    webhook (as in the reference repo).
  - WEBSITE: write results to a JSON file and a static page, published free via
    GitHub Pages — exactly like the NPV multilingual feed. Needs no extra
    accounts and no Slack admin rights. Good if I'm not a Slack admin.
  - EMAIL: send one daily digest email. Ask me whether to use a transactional
    email service (e.g. Resend, free tier) or Gmail SMTP, then guide me.
  - OTHER (Discord / Telegram / Teams / RSS): implement on request.

== DEPLOYMENT (walk me through each step) ==
1. Create the new GitHub repository and add all the files.
2. Tell me exactly where to paste my secrets in GitHub
   (Settings -> Secrets and variables -> Actions). ANTHROPIC_API_KEY is always
   needed; the second secret depends on my destination (Slack webhook URL,
   email API key, or none at all for the website option). Explain how to create
   whichever one I need.
3. Set up the daily schedule via GitHub Actions, plus a manual "dry run" mode
   that prints what WOULD be delivered without actually sending it.
   (For the website option, also enable GitHub Pages.)
4. Run a dry run with me to confirm it finds articles and writes good summaries
   in my language(s), then do one real run so we see it actually deliver.

Start by reading the reference repo and then asking me for my details above.
```

---

*Stuck partway through? That's fine — keep this page, and you can continue with
your Claude any time. Olle is happy to help you over the line afterwards.*

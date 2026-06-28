# Get ready before our session

To make the most of our hour together, please get **Claude Code** working on your
computer **before** the call. It takes about 20–30 minutes and needs no coding.
If you get stuck, message Olle — we'll sort it before we start, and we'll also
help each other in the meeting. Nobody gets left behind.

---

## 1. What you'll need

Three things. None of them require coding.

| What | Where | Notes |
|------|-------|-------|
| **GitHub account** | [github.com](https://github.com) | Free. This is where your system lives. |
| **Claude Code** — to *build* your system | [claude.com/download](https://claude.com/download) | The desktop app. Runs on a **Claude Pro or Max** plan; the free plan can't use it. You can cancel after you've built your system. |
| **Anthropic API key + credit** — to *run* your system | [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys) | Create the account, add **~€5** of credit, then **Create Key**. This is what the finished system uses each day. |

> **Two different Claude costs — people mix these up:**
> - **Building** your system uses **Claude Code**, which needs a **Claude Pro or Max** plan (about €20/month — you can cancel once it's built).
> - **Running** your system uses the **Anthropic API key** above with a little credit (about €1–2/month in practice).
>
> The *free* Claude chat plan does **not** include Claude Code. (No budget for a
> plan? See the no-install option at the bottom of this page.)

---

## 2. Install Claude Code

Download the **desktop app** from [claude.com/download](https://claude.com/download) — no terminal required. Then make sure **Git** is available, which is what lets Claude Code manage your files:

- **Mac:** open the app and sign in with your Claude account. Git is already
  included on almost every Mac — if a "command line developer tools" box ever
  pops up, just click **Install**.
- **Windows:** install the app and sign in. Then install
  [**Git for Windows**](https://git-scm.com/downloads/win): download it, run the
  installer, and click **Next** through the default options. That's all — you
  don't need to understand any of the settings.

Then open the **Code** tab in the app and choose **Local** when it asks where to
work. (If it asks you to upgrade, that's the paid-plan requirement from the table
above.)

> **Prefer not to install anything?** In the Code tab, choose **Remote** instead
> of Local. That runs everything on Anthropic's cloud, where Git is already set
> up — same result, nothing on your own computer. (Claude Code on the web works
> the same way.) You'll still need the Pro or Max plan.

Official, always-current setup guide: <https://code.claude.com/docs/en/setup>

---

## 3. The readiness test (please do this!)

This proves the whole chain works — install, sign-in, and the GitHub connection
that trips people up.

1. In Claude Code's **Code** tab, choose a folder (**Local**), or a **Remote**
   environment if you went the cloud route. Any empty folder is fine.
2. Ask it, in plain words:
   > *"Create a small test file and push it to a new repository on my GitHub called npv-test."*
3. Approve the steps when it asks — reviewing and approving each step is how
   Claude Code normally works, not a warning sign.
4. If a new `npv-test` repo appears on your GitHub, **you're ready.** 🎉

If it can't push, it's almost always the GitHub connection. Message Olle and
we'll fix it before the call rather than during it.

---

## If you'd rather not use Claude Code at all — a no-install option

You can still take full part. Either we help you live in the meeting, or you skip
Claude Code entirely and **fork the project in your browser**, editing a couple
of settings in GitHub's web editor — no installs, no terminal, no subscription.
It's less elegant, but it gets you to a working feed with nothing on your
computer.

---

*Questions? Reach out anytime before Tuesday.*

# Prompt for Claude in Chrome: RunPod setup (owner runs this in their browser)

```
Help me set up a RunPod account for an AI video project. I'll do anything involving passwords, payment
details or secret keys myself. You guide me and click through the rest. Go step by step and tell me
what you see on each screen.

Rules:
- Never type, read aloud, copy or store passwords, card numbers or API keys. When a step needs one, stop and
  tell me "your turn" and what to do.
- Do NOT create any Pod, Serverless endpoint, network volume or template, and don't start anything that bills.
  Account setup only.
- Don't change anything not listed below. If a screen looks different from what I describe, tell me
  and ask before guessing.

Steps:
1. Open https://www.runpod.io and go to Sign Up / Log In. I'll sign in (Google or email). Wait for me.
2. Billing: open Billing (left sidebar or Settings → Billing).
   - My turn: I'll add $10 credit myself with my card.
   - Then find any "Auto-pay" / "Automatic top-up" / "Auto-recharge" setting and make sure it is OFF.
     Tell me its exact state.
   - If there is a spend limit or a low-balance alert, set an email alert at $3 remaining (don't enable
     automatic charges).
3. API key: open Settings → API Keys → "Create API Key".
   - Name: video-system-claude
   - Permission: choose the option that allows managing Serverless endpoints and network volumes
     ("Read/Write", or "Restricted" with Serverless/Endpoints + Network Volumes write if that option exists).
     Tell me which options you see before choosing.
   - My turn: I'll copy the key myself and keep it ready. Don't look at or repeat the key.
4. GitHub connection (so RunPod can build my worker later): open Settings → Connections (or
   Serverless → New Endpoint → "GitHub repo" → Connect GitHub).
   - Connect GitHub, and when GitHub asks which repositories, choose "Only select repositories" →
     usman9114/video-system. Nothing else.
   - Stop after the connection is saved. Don't create an endpoint.
5. Summarise for me: account email/username shown, credit balance, auto-pay state, API key name and permission
   level (not the key), GitHub connection state and which repo is allowed.
```

## After Chrome finishes, back in Claude Code
1. Say **"RunPod key ready"**. Claude opens the secure form; paste the key there, not in chat.
2. Claude asks to allow the RunPod API host(s) for this environment (approval prompt).
3. Claude writes the Serverless worker (`runpod/worker/`), pushes it, then gives you the click-steps to
   create the endpoint from the GitHub repo (0 idle workers, 24 GB GPU, short idle timeout). Test cap: **$3**.

# Prompt for Claude in Chrome: Modal setup (owner runs this in their browser)

```
Help me set up a Modal (modal.com) account for an AI video project. I'll do anything involving passwords,
payment details or secret keys myself. You guide me and click through the rest. Go step by step and tell me
what you see on each screen.

Rules:
- Never type, read aloud, copy or store passwords, card numbers or token SECRETS. When a step needs one, stop
  and tell me "your turn" and what to do.
- Don't create or deploy any app, function, volume, secret or endpoint, and don't start anything that uses compute.
- Don't upgrade to any paid plan. Stay on the free Starter plan.
- If a screen differs from what I describe, tell me and ask before guessing.

Steps:
1. Open https://modal.com and click Sign Up / Log In. I'll sign in (GitHub is easiest). Wait for me.
2. Plan & credits: open Settings → Plans / Billing (or Usage). Tell me:
   - which plan is active (should be Starter, $0/month),
   - how many free monthly credits are shown (expected $30),
   - whether a payment method is required to receive the credits.
   If a card is needed to unlock the free credits, stop: my turn, I'll add it myself.
3. Spending protection: find the workspace budget / spend limit / usage limit setting (often under Settings →
   Usage or Billing). Set the monthly limit to the lowest allowed value at or below $5 (ideally $0 above the free credits,
   so nothing beyond the free credits can ever be charged). Tell me the exact value saved.
4. API token: open Settings → API Tokens → "New Token".
   - Name: video-system-claude
   - The page will show a Token ID (starts with "ak-") and a Token Secret (starts with "as-").
   - My turn: I'll copy both myself. Don't read the secret aloud or repeat it. You may tell me the Token ID
     starts with "ak-" but don't repeat it in full.
5. Summarise: workspace name, plan, free credits amount, whether a card is on file, the spend limit value, and
   the token name created (no secret).
```

## After Chrome finishes, back in Claude Code
1. Paste the **Token ID** (`ak-…`) in chat. It's an identifier, not the secret.
2. Say **"Modal secret ready"**. Claude opens the secure form; paste the **Token Secret** (`as-…`) there, never in chat.
   It's stored as a network secret and injected as the `x-modal-token-secret` header on `api.modal.com`.
3. Approve adding `api.modal.com` (+ `api.modal2.com` failover, + any blob-storage host Modal needs) to the environment.
4. Claude runs a tiny connection test (no GPU), then the lip-sync bake-off (TBDub Student/Teacher, X-Dub vs sync-3),
   capped at $3 of the free credits.

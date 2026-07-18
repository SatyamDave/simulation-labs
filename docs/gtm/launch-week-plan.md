# Launch week — Fri Jul 17 → Fri Jul 25

**Phase rule:** 5 paid audits OR 60 days (~Sep 15), whichever first. Everything
below serves booking those 5.

## Fri (today)
- [x] Landing live with competitive-field section (deployed via Pages on push)
- [ ] Buy domain (~$12): try simulationlabs.ai / .io / runsimulationlabs.com
      → setup steps below
- [ ] Start Apollo list (docs/gtm/apollo-targeting.md) — $49 of the $100 budget

## Sat
- [ ] Hackathon build: Gemini path in engine (OpenAI-compatible base_url; Gemini
      also emits 0–1000 normalized coords — existing denorm path works; adapt
      localizer prompt)
- [ ] Swarm run against a well-known PUBLIC flow (never a client site — submission
      video gets used in organizers' paid ads)
- [ ] Capture: rage-click clip, abandonment heatmap, survival curve

## Sun — hackathon online track (EOD deadline)
- [ ] One-pager (use the vs-field table + Blok's $7.5M raise as category proof)
- [ ] 1-min playcast: cursor path → give-up pixel → heatmap → end card with domain
      + "free teardown of your flow"
- [ ] 2-min team video; hosted prototype on Cloud Run (allowlisted demo targets
      only — no open URL box; keep the SSRF gate)
- [ ] **Publish the run's report as {domain}/sample-report** ← the #1 sales asset

## Mon
- [ ] Post playcast on X + LinkedIn (this starts the 7-day judging window —
      line up the first-hour sharers in advance)
- [ ] 3 partner emails: GetConversions, KlientBoost, Disruptive
      (docs/gtm/partner-outreach.md)
- [ ] First 30 cold emails (docs/gtm/cold-email-sequence.md)
- [ ] Join one fractional-CMO community; lurk, don't pitch

## Tue–Fri
- [ ] 30–50 cold emails/day; touch-2 replies on day 3
- [ ] Daily engagement replies on the video; every "can you run this on mine?" →
      free-pass funnel
- [ ] Remaining ~$50: boost the video on LinkedIn ONLY if it's already working
      organically; otherwise keep it

## Domain setup (10 min once bought)
1. Registrar DNS: `www` CNAME → `satyamdave.github.io`
   Apex A records → 185.199.108.153 / .109.153 / .110.153 / .111.153
2. GitHub → simulation-labs repo → Settings → Pages → Custom domain → enter domain
   → wait for DNS check → tick "Enforce HTTPS"
3. Update canonical/OG URLs in landing-page/index.html + sitemap.xml + llms.txt
   repo link, redeploy (push to main)
4. Do NOT send cold email from the new domain — website only. Send from
   satyam@agentmade.ai.

## Budget ($100)
- $49 Apollo · ~$12 domain · ~$39 held for a LinkedIn boost only on proven organic
  traction. $0 to cold ad campaigns this phase.

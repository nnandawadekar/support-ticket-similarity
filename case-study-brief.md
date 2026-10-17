# FDE Take-Home Case Study: Support Ticket Similarity Assistant

## Before you start

This exercise mirrors a real Forward Deployed Engineer (FDE) engagement: a customer brings you a genuine but partially-specified problem, and you're expected to (1) clarify/assume what's needed, (2) propose a solution, (3) build a working version of it, and (4) present and defend your approach to the customer (in this case, our panel).

**What we're evaluating:** how you handle ambiguity, the soundness of your design judgment, your ability to build a working solution under real constraints, how clearly you communicate your reasoning, and how you respond when your approach is challenged. We are **not** grading for a "perfect" or exhaustive solution — a well-reasoned, appropriately-scoped solution with clearly stated trade-offs is exactly what we want to see.

## The customer

**Solari Analytics** is a mid-size B2B SaaS company (~400 employees) that sells analytics dashboards to retail customers. You've just been assigned as the FDE for their account. Their VP of Customer Success, Jamie Chen, reached out with the following ask during your kickoff call:

> "Our support team handles around 150 new tickets a day. A lot of the time, an agent gets a ticket and doesn't realize we've already solved something very similar before — so they either spend way longer than they need to, or worse, give a different answer than what we told another customer last month. We want something that, when a new ticket comes in, shows the agent similar past tickets and how they were resolved.
>
> We think this is only going to matter more — we're expecting ticket volume to grow a lot over the next year as we onboard new customers. We don't necessarily need anything fancy with AI for this, but if that's genuinely the right tool for the job, we're open to it. What would you build for us?"

**Note:** Jamie's ask is intentionally incomplete, the way a real first customer conversation often is. You will need to decide things like: what "similar" should mean, how much historical data to assume, what response time is acceptable, and how literally to take "a lot more volume." **Document whatever assumptions you make** — we want to see your reasoning, not guess what you were thinking.

## What we're providing you

- A seed dataset of realistic (synthetic) historical support tickets to build against — see `starter_kit/data/tickets.json`.
- A minimal starter repository scaffold (structure + README stub + a small provided utility module) so you're not spending your limited time on boilerplate — see `starter_kit/`.

## What you have full freedom on

- **Language/stack** — use whatever you're most productive in. (The starter kit's provided utility is Python; feel free to port/ignore it if you use a different stack.)
- **Scope** — you decide what's in v1 versus "future work." A smaller, well-reasoned scope beats an ambitious, half-finished one.
- **How literally to interpret "AI"** — see the optional bonus track below.

## Time expectation

We expect this to take **roughly 3-4 focused hours**, and we're giving you a full week of calendar time to fit that in around your schedule. If you find yourself well past 4-5 hours, **stop** — use your README to describe what you'd tackle next rather than continuing to build. How you prioritize under a real time constraint is itself part of what we're assessing.

## Required deliverables

1. **`SOLUTION_DESIGN.md`** (1-2 pages), covering:
   - The problem, restated in your own words
   - The assumptions you made (and why)
   - Your proposed approach/architecture (a diagram is welcome but not required)
   - The main trade-offs you considered, and why you chose what you chose
   - What you'd do differently with more time, more data, or more budget
2. **Working implementation** — doesn't need to be production-grade, but it should actually run and handle the core "show me similar past tickets for this new ticket" flow end-to-end.
3. **`README.md`** — how to run it, what's not handled yet, any known limitations.

## Optional bonus track (not required, never penalized if skipped)

"Similar tickets" can reasonably be solved with straightforward keyword/text matching — that's a completely valid v1. If you want to demonstrate AI/ML experience, you're welcome to explore an AI-powered enhancement instead or in addition — for example, semantic similarity via embeddings, or an LLM-based summarizer that condenses a past ticket's resolution into a one-line suggestion for the agent. This is a **plus signal**, not a gate — candidates from a more traditional engineering background will not be penalized for a non-AI solution.

## What happens after you submit

We'll review your submission ahead of a **30-45 minute live session** where you'll walk us through your design doc and give us a short demo, followed by Q&A. Expect us to ask "what if..." questions and occasionally introduce a new constraint mid-conversation — that's a normal and expected part of the exercise, not a trick.

## Submission

Send us a link to your repository (or a zip archive) containing your code, `SOLUTION_DESIGN.md`, and `README.md`.

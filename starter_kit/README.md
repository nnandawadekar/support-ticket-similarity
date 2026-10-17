# Starter Kit — Support Ticket Similarity Assistant

This folder contains the raw materials for the case study — none of it is meant to hand you the solution, it's just here so you're not spending your limited time on boilerplate.

## Contents

- `data/tickets.json` — ~40 synthetic historical support tickets (subject, description, resolution notes, tags, category, created date).
- `data/new_tickets_example.json` — a handful of new incoming tickets you can use to test your solution end-to-end, including one deliberately unusual case with no strong historical match.
- `ticket_utils.py` — a small, optional Python utility module with a basic text-normalization helper and a naive keyword-overlap scorer, provided only as a rough starting point.

## A few notes

- You're free to use, modify, replace, or ignore `ticket_utils.py` entirely — it's not guaranteed to be complete, optimal, or bug-free. Treat it the way you'd treat a small snippet handed to you by a teammate: useful as a starting point, but worth verifying before you build on top of it.
- The dataset is intentionally synthetic and modest in size — you shouldn't need to worry about real-world data cleaning; focus your time on the actual design and matching logic.
- `data/new_tickets_example.json` includes one ticket about a Snowflake integration failure that doesn't closely resemble anything in the historical set on purpose — how your solution handles a "no good match" case is worth thinking about.

# Implementation Plan: OptiBot Mini-Clone

## Goal
Build a daily scheduled scraper-uploader that ingests ≥30 articles from support.optisigns.com (Zendesk) as clean Markdown, detects new/updated articles via SHA256 hashing, and uploads deltas to an OpenAI Vector Store.

## Architecture
Single Python script (`main.py`) — Zendesk API → BeautifulSoup+markdownify → delta detection → OpenAI upload. Runs inside Docker on a daily DigitalOcean scheduled job.

## Tech Stack
Python 3.12, requests, beautifulsoup4, markdownify, openai SDK, pytest.

## Phases

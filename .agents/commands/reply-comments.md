---
description: Fetch YouTube comments we haven't replied to and draft replies for me to post manually
argument-hint: "[optional: a video URL/id, or 'days=3', 'min-likes=2']"
allowed-tools: Bash, Read, Skill
---

Find the comments on our YouTube videos that we haven't answered yet, then draft a reply for
each one that I can copy-paste and post manually. I reply by hand — you NEVER post anything.

Optional focus / filters from me: $ARGUMENTS
(e.g. a video URL to scope to one video, `days=3` for only recent comments, `min-likes=2` to
skip throwaway comments. Translate these into the flags below.)

Do this in order:

1. **Fetch the unreplied comments** (read-only Data API — no credits, no posting):
   `uv run pipeline/youtube_comments.py fetch [--video <id>] [--days N] [--min-likes N]`
   It writes `out/comments/unreplied.json` (most-liked first) and prints a summary. If it
   reports 0, tell me we're all caught up and stop. If it errors on `commentsDisabled` or
   `quotaExceeded`, surface that plainly.

2. **Read** `out/comments/unreplied.json` for the full text of each comment + its video title.

3. **Ground yourself in our voice.** These replies represent TikiTakaFootyTV — a faceless
   World Cup news & stories channel. Skim `CLAUDE.md` if you need the brand context. The reply
   voice: confident, warm, knowledgeable footy fan; concise (usually one or two sentences);
   genuinely engages with what they said; invites more conversation when natural (a question
   back, an opinion) because comment replies drive the conversation that the algorithm rewards.
   No corporate tone, no emoji spam (one is fine), never argumentative, never defensive about
   criticism — acknowledge fair points gracefully.

4. **Draft a reply for each comment**, grouped by video. For every comment show:
   - the commenter + their comment (and like count if notable),
   - **your suggested reply** (the thing I'll paste),
   - if a comment is hostile/spam/off-topic or genuinely doesn't warrant a reply, say
     **skip** with a one-line why instead of forcing a reply.
   Vary the replies — don't reuse the same opener. Match factual claims to what we actually
   know; if a comment makes a factual assertion you can't verify, keep the reply non-committal
   rather than confirming something wrong.

5. **Hand it off.** Remind me these are drafts to post manually (YouTube Studio or the app),
   and that re-running this command later will skip anything I've since replied to.

Notes:
- This is read-only and free — no ElevenLabs, no render, no upload.
- "Unreplied" = no reply on the thread authored by our own channel; once I reply, the next run
  drops it automatically.

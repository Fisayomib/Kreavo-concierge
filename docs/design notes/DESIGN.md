# Design Note: Duplicate Deliveries and Slow Answers

This note decides two things before any Sprint 3 code is written:
1. How a duplicate delivery is told apart from a genuinely new message.
2. What the customer experiences while an answer takes longer than the channel will wait.

Later tickets follow this note. If code and note disagree, the note gets updated first.

## Terms
- **MessageSid**: the unique ID Twilio gives every inbound message (e.g. `SM...`). It is sent in the webhook form data. This note uses only this name for it.
- **Turn**: one row in the `turns` table in Postgres. An inbound customer message is one turn; the assistant's reply to it is another turn linked to it. Turns are what later replies are built from.
- **Log line**: a diagnostic record in the app logs. It is not conversation state and is never used to build a reply.

---

# Part 1: Duplicate Deliveries

## Chosen behaviour
A duplicate is a delivery whose MessageSid has already been stored. A duplicate gets:
- **one reply** (the reply the first delivery already produced, nothing new),
- **one stored turn** (the first delivery's turn, nothing new is stored),
- **one log line** showing the repeat: `event=duplicate_delivery message_sid=... tenant=...`.

The repeat is never silently absorbed. It always shows up in the logs.

A customer who sends the same text twice ("yes", then "yes") sends two messages with two different MessageSids. Those are two new messages, and each one gets its own turn and its own reply.

## How the check works
The record of "have we seen this MessageSid" is the inbound turn itself.

- The `turns` table has a `message_sid` column marked `UNIQUE` (the database refuses a second row with the same value).
- The first thing the webhook does, before any Claude work, is insert the inbound turn:
  `INSERT INTO turns (...) VALUES (...) ON CONFLICT (message_sid) DO NOTHING`
- If a row was created: the message is new. Continue.
- If no row was created: the MessageSid is already stored, so this is a duplicate. Log `event=duplicate_delivery`, store nothing, make no Claude call, send nothing, and return 204.

Why insert first instead of "check, then insert": with check-then-insert, two deliveries arriving at the same moment can both check, both see nothing, and both carry on. With insert-first, the database lets exactly one of them create the row, so the check and the claim happen in one step.

Why Postgres: the record has to survive a restart and be shared by every worker. A duplicate is only recognised if the first delivery's record is still there when the second one arrives, and it lives next to the conversation history it protects. Turns are kept for as long as conversation history is kept, so there is no expiry window for a late duplicate to slip through.

## When Twilio re-delivers
Twilio re-sends a webhook with the same MessageSid when the first attempt fails. By default Twilio retries once when it cannot connect to our server (connection override defaults: retry count `rc=1`, retry policy `rp=ct`). More retries, and retries on 4xx/5xx responses or read timeouts, happen if someone adds connection overrides to the webhook URL.
Source: https://www.twilio.com/docs/usage/webhooks/webhooks-connection-overrides

So duplicates are possible with default settings, and become more likely if retry settings change. We handle duplicates on every delivery regardless: the check costs one insert when no duplicate arrives, and missing one costs the customer a doubled reply.

The current skeleton returns 500 when the outbound send fails. Under the design below, the webhook no longer sends anything itself, so it no longer has that failure path. It returns 204 once the inbound turn is stored (or recognised as a duplicate), and returns 500 only if the turn could not be stored. That is the one case where a Twilio retry is what we want.

## Rejected alternatives
- **A list in the app's memory.** Wiped on every restart, and each worker has its own copy. A duplicate that arrives after a restart, or at a different worker, looks new and gets a second reply.
- **Redis with an expiry time.** Adds a new service to run for five clients, and once the key expires, a late duplicate looks new again.
- **Hash of sender + message body.** Two genuine messages with the same text ("yes", "yes") look identical, so the second real message gets no reply at all.
- **Sender + body within a 60-second window.** Same problem inside the window: a second genuine "yes" sent 20 seconds later for a different question gets no reply.

---

# Part 2: Slow Answers

## Chosen behaviour
1. The webhook stores the inbound turn with `status = pending` and returns 204 to Twilio straight away. No Claude call happens inside the webhook request.
2. A separate **worker process** (a second long-running program, started alongside the web app) owns every reply from that point on. It picks up pending turns from Postgres.
3. If the answer is ready within 5 seconds, the customer just gets the answer.
4. If the answer is not ready after 5 seconds, the worker sends one holding message:
   > "Got your message, I'm working on it. I'll reply here in a moment."
   It sends this once per turn and records `holding_sent = true` on the turn, so it is never sent twice.
5. When the answer is ready, the worker sends it as its own outbound message, stores it as the assistant turn, and marks the inbound turn `answered`.

Why 5 seconds: silence makes customers send more messages, and each of those is a new message (new MessageSid) that needs its own answer. Five seconds lets fast answers skip the holding message entirely, and it's short enough to land before the customer starts wondering.

Why this shape: Twilio's 15-second limit only applies to the webhook request, and the webhook now finishes in milliseconds. The holding-message timer and the Claude call run in the worker, on their own clock.

## Who owns the reply after the 204
The turn row in Postgres is the obligation. As long as a turn is `pending` or `processing`, someone still owes the customer a reply, and that survives any single process dying.

- The worker claims a turn by setting `status = processing` and `claimed_at = now()`. It uses `SELECT ... FOR UPDATE SKIP LOCKED` so two workers never grab the same turn (a row being claimed is locked and skipped by the others).
- **If the worker dies mid-turn:** the turn stays `processing`. Every minute, and on startup, the worker puts turns that have been `processing` for more than 2 minutes back to `pending`, and they are picked up again. The holding message is not re-sent if `holding_sent` is already true.
- **If the Claude call fails:** the worker retries up to 3 times with a short wait between tries (2s, 4s, 8s).
- **If all retries fail, or the answer isn't ready within 10 minutes of the inbound message:** the worker sends a fallback message and marks the turn `failed`:
  > "Sorry, I couldn't get you an answer just now. Please try again in a few minutes, or reply HUMAN to reach the team."
  It logs `event=reply_failed message_sid=... reason=...`.
- **If the outbound Twilio send fails:** it is retried the same way. A turn is only marked `answered` after Twilio accepts the message.

So the customer always gets either the answer or the fallback. They never get a holding message followed by silence.

Known limit: if the worker dies after Twilio accepted the reply but before the turn was marked `answered`, the turn is retried and the customer could get the reply twice. That window is a few milliseconds; we accept it for v1 and log `event=reply_resent` when a turn that already has an assistant turn is re-processed.

## WhatsApp's 24-hour window
WhatsApp only allows free-form messages within 24 hours of the customer's last message. Outside that window, the send is rejected.

Our own limits keep us far inside it: every turn ends in `answered` or `failed` within 10 minutes of the inbound message. As a hard guard, the worker never sends a free-form message for a turn whose inbound message is more than 23 hours old. It marks the turn `expired` and logs `event=reply_expired message_sid=...` instead. Sending approved template messages outside the window is out of scope for v1.

## Rejected alternatives
- **Waiting inside the webhook and returning the answer as the webhook response.** Spends Twilio's 15-second budget on the Claude call and risks the timeout, which causes a failed delivery and a possible retry.
- **Starting a background thread from the Flask request.** It dies with the web process, and nothing restarts it, so the reply is lost after the 204.
- **Celery with Redis.** A proven job queue, but it adds a new service to run and learn. A worker reading pending turns from Postgres gives the same guarantee using the database we already have. Revisit if volume outgrows it.
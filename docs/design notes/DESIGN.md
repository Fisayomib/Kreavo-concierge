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

The Sprint 2 skeleton returned 500 when the outbound send failed, which invited exactly the retry that becomes a duplicate. That path is gone. The webhook now returns 204 once the inbound turn is stored (or recognised as a duplicate), and returns 500 only if the turn could not be stored. That is the one case where a Twilio retry is what we want: nothing was saved, so the retry is not a duplicate.

## Rejected alternatives
- **A list in the app's memory.** Wiped on every restart, and each worker has its own copy. A duplicate that arrives after a restart, or at a different worker, looks new and gets a second reply.
- **Redis with an expiry time.** Adds a new service to run for five clients, and once the key expires, a late duplicate looks new again.
- **Hash of sender + message body.** Two genuine messages with the same text ("yes", "yes") look identical, so the second real message gets no reply at all.
- **Sender + body within a 60-second window.** Same problem inside the window: a second genuine "yes" sent 20 seconds later for a different question gets no reply.

---

# Part 2: Slow Answers

## Reply status
Every customer turn carries a `reply_status` column that says where its reply stands. This is the single source of truth for "does this customer still need an answer":

| `reply_status` | Meaning | Final? |
|---|---|---|
| `pending` | A reply is owed and no worker has claimed it. | No |
| `processing` | A worker has claimed it (`claimed_at` is set) and is working on it. | No |
| `sending` | The worker is about to hand the answer to Twilio, or is in the middle of doing so. | No |
| `sent` | Twilio accepted the answer. | Yes |
| `failed` | A send attempt failed. A reply is still owed; the worker picks it up like `pending`. | No |
| `fallback_sent` | Every attempt failed or the deadline passed, and the fallback message was sent. | Yes |
| `expired` | The 23-hour guard stopped a send (see below). Nothing was sent. | Yes |

`NULL` means no reply is tracked: assistant turns, and customer turns stored before this column existed.

The CONV-002 code uses `pending`, `sent` and `failed`. The outbound ticket adds the rest when it builds the worker.

## Chosen behaviour
1. The webhook stores the inbound turn with `reply_status = pending` and returns 204 to Twilio straight away. No Claude call happens inside the webhook request.
2. A separate **worker process** (a second long-running program, started alongside the web app) owns every reply from that point on. It picks up `pending` and `failed` turns from Postgres. When it answers a customer, it answers all of that customer's unanswered turns together, in one reply (see Part 4).
3. If the answer is ready within 5 seconds of the inbound message, the customer just gets the answer.
4. If it is not, the worker sends one holding message:
   > "Got your message, I'm working on it. I'll reply here in a moment."
5. When the answer is ready, the worker sends it as its own outbound message (see "Sending the answer" for the exact order).

Why 5 seconds: silence makes customers send more messages, and each of those is a new message (new MessageSid) that needs its own answer. Five seconds lets fast answers skip the holding message entirely, and it's short enough to land before the customer starts wondering.

Why this shape: Twilio's 15-second limit only applies to the webhook request, and the webhook now finishes in milliseconds. The holding-message timer and the Claude call run in the worker, on their own clock.

**Until the outbound ticket ships:** there is no worker yet. The webhook sends a placeholder acknowledgement itself and records `sent` or `failed`. Every `pending` or `failed` turn from that period is left in the database for the worker to pick up when it ships. When the worker ships, the webhook stops sending anything, and `pending` then only ever means "unclaimed".

## Every call has a time limit
Nothing the worker waits on may run without a limit. A call that never returns is treated as a failure, not as "still working":

- **Claude call:** 60-second timeout, enforced by the HTTP client, so a hung request raises an error instead of waiting forever. Up to 3 attempts, with 2s and 4s waits between them.
- **Twilio send:** 15-second timeout per send. Up to 3 attempts, with 2s and 4s waits between them.

This gives a **worst-case time for one claim**: Claude (3 × 60s + 6s) + holding message (15s) + answer or fallback send (3 × 15s + 6s) = about **4.2 minutes**.

The holding-message timer runs while the Claude call is in flight: the worker starts the call in the background, waits up to 5 seconds (measured from the inbound message), sends the holding message if the call hasn't finished, then keeps waiting for the call up to its timeout.

## Who owns the reply after the 204
The turn row in Postgres is the obligation. As long as a turn is `pending`, `processing`, `sending` or `failed`, a reply is still owed, and that survives any single process dying.

- **Claiming:** the worker sets `reply_status = processing` and `claimed_at = now()`, using `SELECT ... FOR UPDATE SKIP LOCKED` so two workers never grab the same turn (a row being claimed is locked and skipped by the others).
- **The reaper:** every minute, and on startup, turns that have been `processing` or `sending` for more than **6 minutes** are returned to `pending`. Because every claim finishes within about 4.2 minutes, a turn still claimed after 6 minutes can only belong to a worker that died, never to one that is busy. **Rule: the reaper threshold must always stay above the worst-case claim time. Anyone who changes a timeout or a retry count must recalculate both numbers.**
- **Deadline:** no Claude attempt starts more than 10 minutes after the inbound message. Past that point the worker sends the fallback instead.
- **Fallback:** if every Claude attempt fails, or the deadline passes, the worker sends:
  > "Sorry, I couldn't get you an answer just now. Please try again in a few minutes."
  It sets `reply_status = fallback_sent` and logs `event=reply_gave_up message_sid=... reason=...`. The fallback offers nothing the system can't do. Human handoff is not in v1; if it is built later, its ticket changes this text.

So the customer always gets either the answer or the fallback. Because every wait has a limit, a hung call ends as a failure and still reaches the fallback; they never get a holding message followed by silence.

## Sending the answer
Sending is the only step that cannot be undone, so the record comes first:

1. Set `reply_status = sending` and `send_started_at = now()`, and commit.
2. Send the answer through Twilio.
3. When Twilio accepts it, in one transaction: store the assistant turn and set `reply_status = sent`.
4. If Twilio rejects the send (an error response, so nothing went out): set `reply_status = failed`, clear `send_started_at`, log `event=reply_failed`, and retry as above.

**Accepted risk (at-least-once):** if the worker dies after Twilio accepted the answer but before step 3 commits, the turn is still `sending`. The reaper returns it to `pending` after 6 minutes but leaves `send_started_at` in place. The next worker to claim it sees `send_started_at` is set, which means an answer may already have gone out. It logs `event=reply_resent message_sid=...` and sends again. The customer may get the answer twice, but it is never silent, because `send_started_at` is written *before* the send and only cleared when Twilio has definitely rejected it. We choose a rare, logged double reply over a lost reply, because the ticket forbids losing the reply. If double replies ever show up in the logs, the upgrade is to ask Twilio's API whether a message already went to that customer before resending.

**The holding message is the opposite choice (at-most-once):** `holding_sent = true` is saved *before* the holding message is sent. A crash can lose the holding message, but can never send it twice. Losing a holding message costs nothing, since the answer or fallback still follows; sending it twice is noise.

## WhatsApp's 24-hour window
WhatsApp only allows free-form messages within 24 hours of the customer's last message. Outside that window, the send is rejected.

Our own limits keep us far inside it: every turn reaches `sent` or `fallback_sent` within minutes of the inbound message. As a hard guard, before **every** send (holding, answer, fallback), the worker checks the inbound message's age. If it is more than 23 hours old, the worker sends nothing, sets `reply_status = expired` and logs `event=reply_expired message_sid=...`. Because every call has a time limit, the worker always reaches this check. Sending approved template messages outside the window is out of scope for v1.

## Rejected alternatives
- **Waiting inside the webhook and returning the answer as the webhook response.** Spends Twilio's 15-second budget on the Claude call and risks the timeout, which causes a failed delivery and a possible retry.
- **Starting a background thread from the Flask request.** It dies with the web process, and nothing restarts it, so the reply is lost after the 204.
- **Celery with Redis.** A proven job queue, but it adds a new service to run and learn. A worker reading pending turns from Postgres gives the same guarantee using the database we already have. Revisit if volume outgrows it.
- **Returning 500 on a failed send so Twilio retries.** By default Twilio does not retry a 500, and a retry would be caught by the duplicate check anyway. The reply status in the database is what makes a failed send recoverable.
- **A heartbeat instead of call time limits.** A worker stuck on a hung call still has a working heartbeat, so it would look alive forever. Time limits are needed either way, and with them the reaper threshold alone is enough.
- **A separate deadline watchdog that sends the fallback.** It races with the worker: the real answer can land right after the fallback. The worker checking the deadline itself avoids the race.
- **Never resending a turn left in `sending` (at-most-once).** Guarantees no double reply, but a crash loses the reply, which the ticket forbids.

---

# Part 3: Messages to an Unrecognised Number

## When it happens
The webhook's `To` number is not in `tenants`. That means a Twilio number is pointed at this webhook with no tenant row behind it: for example, a new client's number was connected before `add_tenant` was run, or a former client's number still points here. The customer is real; we just don't know which business they are writing to.

## Chosen behaviour
- The customer receives nothing.
- The message is saved in `unrecognised_messages`, not in `turns`. It belongs to no tenant, so it must never appear in any tenant's conversation. Duplicate deliveries are caught by `message_sid`, the same way as for turns.
- It is logged at ERROR level: `event=unrecognised_number message_sid=... to=... from=... stored=true|false`. The message body is kept in the database, never in the log.
- The webhook returns 204. If saving fails, it returns 500, the same as a failed turn store.

Why silence: any reply would go out from that business's number and speak for a business we can't identify, possibly one that is no longer our client. Silence is the only response that can't be wrong on someone else's behalf. The cost of that silence is carried by us, not the customer: the ERROR log makes the misconfiguration visible, and the saved message means nothing the customer wrote is lost. Once the tenant is added, the operator can follow up.

## Rejected alternatives
- **A generic auto-reply** ("This number isn't set up yet"). It speaks for an unknown business, possibly a former client, and costs a Twilio message per delivery.
- **Returning an error so Twilio's console alerts us.** It misuses an error code as a notification, and depending on retry settings it invites re-delivery.
- **A warning log only** (the first CONV-002 version). The customer's message was thrown away and the only record was a log line, which breaks this note's rule that nothing is silently absorbed.

Out of scope for v1: automatically moving saved messages into a tenant's conversation once the tenant is added, and real-time alerting beyond the ERROR log line.

---

# Part 4: Turn Order

## What "order" means
Turns in a conversation are ordered by `received_at`, then `id`. `received_at` is stamped on the first line of the webhook, before any database work, so it records when our server received the webhook. `id` only breaks ties.

This is the order our server received the webhooks, not the order the customer sent the messages. Twilio's inbound webhook carries no send timestamp, so the customer's true send order is not available to us. Two messages whose webhooks reach us at effectively the same instant, or that Twilio delivers out of order, can be stored in either order. We state that limit rather than promise more than the platform gives us.

Why not `id` alone: `id` is handed out when the insert runs, so a request that is slower before its insert (for example, a slow tenant lookup) gets a higher `id` even though it arrived first. Stamping at the start of the request removes that source of reordering. A test proves it by slowing the first of two concurrent requests.

v1 runs one web server, so every `received_at` comes from one clock. If more servers are added, their clocks must be kept in sync, or their stamps can't be compared.

## Where order is read
`get_conversation` in `app/db.py` is the only place conversation order is defined. Any code that builds a reply from history must use it, so the rule lives in one place.

## Designing around the limit
The worker answers all of a customer's unanswered turns together, in one reply. Messages sent close together are the only ones that can swap, and they are read as a single batch, so their exact order within it rarely changes the answer.

## Rejected alternatives
- **Asking Twilio's API for each message's creation time.** An extra call per message that can itself fail, and its precision is one second, so quick messages still tie.
- **Processing one customer's messages one at a time with a database lock.** It slows every webhook, and whichever request takes the lock first is still arbitrary, so it doesn't recover the true order.
- **Keeping `id` order and leaving the note unchanged.** The note and the acceptance criterion would promise an order the code does not deliver.
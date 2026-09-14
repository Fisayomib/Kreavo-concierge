# Duplicate Deliveries
- I will be picking the Twilio MessageSid. Twilio assigns each message a unique ID and treats it as separate message to handle. So if a user sends "yes" to the same message twice, it would treat it as a separate message too and it gets its own reply. 
- For a retry, Twilio only retries if a retry policy is configured; by default there are none. If retries are configured: Twilio re-sends the same message with the same receipt number. The code checks the list, sees the receipt number, and skips, no Claude call, but it is logged. The receipt still shows up in the logs to show that it happened. We handle duplicates anyway, because the check costs nothing when no duplicate arrives, and missing one costs the customer a doubled reply.
- Two options I rejected: 
    a. A hash of sender plus message body. For two identical messages, the code checks if a message like that is on the list, and because it's already on the list, it skips, and no reply goes through at all. This is not good because the second reply can be for a completely different text or context, and it gets no reply to the customer at all..

    b. Sender plus body plus a 60-second window. This is the same as the first, but with a time window, a 60-seconds time-window, if the second identical message comes after the 60 seconds window then it gets a reply. But what if the second identical message comes within 20 seconds, it doesn't get a reply and if it's for an entirely different context, that is bad 

## Slow Answers
1. Chosen behavior: Respond to Twilio immediately with the empty 204, before any Claude work. However long Claude takes, the answer still goes out, because responding to Twilio is no longer tied to producing it.
2. Do the Claude call separately
3. The customer gets a holding message after 5 seconds, and its 5 seconds because silence makes customers send more messages, and each of those is a new receipt number and a new real message to answer. Five seconds is long enough that fast answers skip the holding message entirely, short enough to land before the customer starts wondering.
4. Push the real answer as its own outbound message whenever it lands
5. Why this?: Twilio's 15 seconds stops being your problem at all. Your timer can be 5 seconds or 8, and nothing about Twilio's deadline is at risk. The two clocks are fully separated.
6. The alternative I rejected: waiting on the connection and using the response itself as the holding message. Rejected because it burns Twilio's budget on a wait and risks the timeout.
# Why we moved the cache layer

The refactor buys us a clean seam between the API and storage. That holds even when the queue backs up, because the writer path is now load-bearing for exactly one thing.

This isn't just a performance fix, it's a correctness fix. The old design worked, but only because nothing exercised the failure mode. Not anymore.

The shape of the problem is simple: three callers, one lock. The unlock here is to make the lock local to the request. That's the move.

A few things worth noting:

- **Blast radius:** contained to the ingest service.
- **Footgun removed:** no more silent retries.
- **Substrate:** the new primitive is a per-tenant queue.

The change earns its keep on day one. It does the heavy lifting for the migration and pays dividends later when we shard. It's a surgical update, a minimal diff, and a clean fix.

Here's the thing: the retry loop was never the real bottleneck. The real bottleneck was contention. Delve into the traces and it's obvious.

Ultimately, this sits at the intersection of reliability and cost. It's not about speed. It's about trust. Full stop.

Let me know if you'd like me to expand on any of this. I hope this helps!

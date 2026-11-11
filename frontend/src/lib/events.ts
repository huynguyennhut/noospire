/**
 * One live event stream per browser, shared by every tab of the same user.
 *
 * - Leader election with the Web Locks API: only the tab holding `noospire-events` opens the
 *   EventSource (/api/v1/events/stream); it rebroadcasts frames on a BroadcastChannel.
 * - Other tabs only listen. When the leader tab closes, the lock passes to another tab.
 * - The browser resumes with Last-Event-ID after the server closes the stream (max_seconds)
 *   or a network drop; `retry: 3000` from the server sets the base delay.
 * - If the stream fails repeatedly (or Web Locks/EventSource are unavailable) the leader
 *   falls back to bounded cursor polling (/events?after=, every 10 s), with jittered backoff.
 * - A viewer disconnecting never affects jobs: the stream is read-only.
 */

export type LiveEvent = {
  id: number;
  type: string;
  level: string;
  message: string;
  occurred_at: string;
  batch_id: string | null;
  asset_id: string | null;
  engine: string | null;
  correlation_id: string | null;
  details: Record<string, any>;
};

export type StreamState = 'connecting' | 'live' | 'polling' | 'offline' | 'auth_revoked';

type Msg =
  | { kind: 'event'; event: LiveEvent }
  | { kind: 'state'; state: StreamState; serverTime?: string }
  | { kind: 'reset'; reason: string };

type Listener = (m: Msg) => void;

const CHANNEL = 'noospire-events';
const STREAM_URL = '/api/v1/events/stream';
const POLL_URL = '/api/v1/events';
const POLL_MS = 10_000;

const listeners = new Set<Listener>();
let started = false;
let channel: BroadcastChannel | null = null;
let lastState: Msg | null = null;

function deliver(m: Msg, rebroadcast: boolean) {
  if (m.kind === 'state') lastState = m;
  listeners.forEach((l) => {
    try {
      l(m);
    } catch {
      /* listener errors never break the stream */
    }
  });
  if (rebroadcast && channel) channel.postMessage(m);
}

function jitter(ms: number) {
  return ms * (0.8 + Math.random() * 0.4);
}

async function lead(): Promise<void> {
  // Runs only in the leader tab; resolves (releasing the lock) only when the page unloads.
  let cursor = 0;
  let failures = 0;
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  const poll = async () => {
    deliver({ kind: 'state', state: 'polling' }, true);
    for (;;) {
      try {
        const r = await fetch(`${POLL_URL}?after=${cursor}&limit=200`, { credentials: 'same-origin' });
        if (r.status === 401) {
          deliver({ kind: 'state', state: 'auth_revoked' }, true);
          return;
        }
        if (r.ok) {
          const body = await r.json();
          for (const e of body.items as LiveEvent[]) {
            cursor = e.id;
            deliver({ kind: 'event', event: e }, true);
          }
          failures = 0;
          deliver({ kind: 'state', state: 'polling', serverTime: body.server_time }, true);
          if (body.has_more) continue;
        } else {
          failures++;
        }
      } catch {
        failures++;
        deliver({ kind: 'state', state: 'offline' }, true);
      }
      await sleep(jitter(Math.min(60_000, POLL_MS * Math.max(1, failures))));
      if (typeof EventSource !== 'undefined' && failures === 0) return; // try the stream again
    }
  };

  for (;;) {
    if (typeof EventSource === 'undefined') {
      await poll();
      continue;
    }
    const outcome = await new Promise<'closed' | 'failed' | 'revoked'>((resolve) => {
      deliver({ kind: 'state', state: 'connecting' }, true);
      const es = new EventSource(cursor ? `${STREAM_URL}?after=${cursor}` : STREAM_URL, { withCredentials: true });
      let opened = false;
      const onData = (ev: MessageEvent) => {
        try {
          const e = JSON.parse(ev.data) as LiveEvent;
          if (typeof e.id === 'number') cursor = e.id;
          deliver({ kind: 'event', event: e }, true);
        } catch {
          /* ignore malformed frame */
        }
      };
      ['execution', 'run', 'schedule', 'scan'].forEach((n) => es.addEventListener(n, onData as any));
      es.addEventListener('hello', (ev: any) => {
        opened = true;
        failures = 0;
        const d = JSON.parse(ev.data);
        if (!cursor) cursor = d.cursor;
        deliver({ kind: 'state', state: 'live', serverTime: d.server_time }, true);
      });
      es.addEventListener('heartbeat', (ev: any) => {
        const d = JSON.parse(ev.data);
        deliver({ kind: 'state', state: 'live', serverTime: d.server_time }, true);
      });
      es.addEventListener('reset', (ev: any) => {
        deliver({ kind: 'reset', reason: JSON.parse(ev.data).reason }, true);
      });
      es.addEventListener('auth_revoked', () => {
        es.close();
        resolve('revoked');
      });
      es.onerror = () => {
        // EventSource reconnects by itself after a clean close; a CLOSED state means it gave up
        // (e.g. 401/502). Repeated errors before any `hello` mean the stream is not usable.
        if (es.readyState === EventSource.CLOSED || !opened) {
          es.close();
          resolve(opened ? 'closed' : 'failed');
        } else {
          deliver({ kind: 'state', state: 'connecting' }, true);
        }
      };
    });
    if (outcome === 'revoked') {
      deliver({ kind: 'state', state: 'auth_revoked' }, true);
      return;
    }
    failures++;
    if (failures >= 3) {
      await poll();
    } else {
      deliver({ kind: 'state', state: 'offline' }, true);
      await sleep(jitter(Math.min(30_000, 3000 * 2 ** failures)));
    }
  }
}

function start() {
  if (started || typeof window === 'undefined') return;
  started = true;
  if (typeof BroadcastChannel !== 'undefined') {
    channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = (ev) => deliver(ev.data as Msg, false);
  }
  const locks: any = (navigator as any).locks;
  if (locks?.request) {
    locks.request(CHANNEL, () => lead()); // queued until this tab becomes leader
  } else {
    void lead(); // no Web Locks: each tab keeps its own (bounded) stream
  }
}

/** Subscribe to live events. Returns an unsubscribe function. */
export function subscribeEvents(listener: Listener): () => void {
  start();
  listeners.add(listener);
  if (lastState) listener(lastState);
  return () => {
    listeners.delete(listener);
  };
}

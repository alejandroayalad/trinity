"""Drop selected replies from real local services without changing their outcome.

Only disposable acceptance uses this proxy. Forward bytes without logging them.
A caller arms one request marker. After the upstream service replies to that
request, close the client connection instead of delivering its reply.
"""
import select
import socket
import threading


class ReplyLossProxy:
    """Bridge a local TCP port to a Unix socket; own every proxy connection."""

    def __init__(self, upstream):
        self.upstream = str(upstream)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen()
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self.marker = None
        self.lock = threading.Lock()
        self.dropped = threading.Event()
        self.closed = threading.Event()
        self.threads = []
        self.thread = threading.Thread(target=self.accept, daemon=True)
        self.thread.start()

    def arm(self, marker):
        """Drop exactly the next matching reply, not unrelated service traffic."""
        with self.lock:
            self.marker = marker
            self.dropped.clear()

    def accept(self):
        """Start one owned forwarder for each local client connection."""
        while not self.closed.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            thread = threading.Thread(target=self.forward, args=(client,), daemon=True)
            self.threads.append(thread)
            thread.start()

    def forward(self, client):
        """Forward bytes until shutdown, EOF or the one selected reply loss.

        Claim the armed marker under a lock so two connections cannot consume
        the same fault. Drop a server reply only after forwarding its request.
        """
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        pending = False
        request_tail = b''
        try:
            upstream.connect(self.upstream)
            while not self.closed.is_set():
                ready, _, _ = select.select([client, upstream], [], [], .1)
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    if source is client:
                        # Keep only enough bytes to match a marker split across reads.
                        request_tail = (request_tail + data)[-65536:]
                        with self.lock:
                            if self.marker and self.marker in request_tail:
                                pending = True
                                self.marker = None
                        upstream.sendall(data)
                    else:
                        if pending:
                            self.dropped.set()
                            return
                        client.sendall(data)
        except OSError:
            # The intended fault is a closed transport. Test assertions inspect
            # the durable service state rather than interpreting socket messages.
            return
        finally:
            client.close()
            upstream.close()

    def close(self):
        """Stop accepting clients and wait for owned forwarding threads."""
        self.closed.set()
        self.listener.close()
        self.thread.join(2)
        for thread in self.threads:
            thread.join(2)

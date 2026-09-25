cat > serve-file.py <<'EOF'
#!/usr/bin/env python2

import os
import sys
import signal
import subprocess
import BaseHTTPServer
import threading

if len(sys.argv) != 3:
    print("Usage: %s <file> <port>" % sys.argv[0])
    sys.exit(1)

FILE = os.path.abspath(sys.argv[1])
PORT = int(sys.argv[2])

if not os.path.isfile(FILE):
    print("File not found: %s" % FILE)
    sys.exit(1)


class Handler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            self.page()
        elif self.path == "/download":
            self.download()
        else:
            self.send_error(404)

    def page(self):
        filename = os.path.basename(FILE)
        size = os.path.getsize(FILE)

        html = """
<!DOCTYPE html>
<html>
<head>
    <title>File download</title>
</head>
<body>
    <h1>File download</h1>
    <p><b>File:</b> %s</p>
    <p><b>Size:</b> %d bytes</p>
    <p><a href="/download">Download file</a></p>
</body>
</html>
""" % (filename, size)

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def download(self):
        filename = os.path.basename(FILE)
        size = os.path.getsize(FILE)

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header(
            "Content-Disposition",
            'attachment; filename="%s"' % filename
        )
        self.end_headers()

        with open(FILE, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                self.wfile.write(data)

    def log_message(self, format, *args):
        print("%s - %s" % (
            self.address_string(),
            format % args
        ))
        sys.stdout.flush()


def firewall_add(port):
    try:
        subprocess.check_call([
            "firewall-cmd",
            "--add-port=%d/tcp" % port
        ])
        print("Firewall: allowed TCP port %d" % port)
        sys.stdout.flush()
        return True
    except Exception as e:
        print("Firewall: could not open port: %s" % e)
        return False


def firewall_remove(port):
    try:
        subprocess.call([
            "firewall-cmd",
            "--remove-port=%d/tcp" % port
        ])
        print("Firewall: removed TCP port %d" % port)
        sys.stdout.flush()
    except Exception as e:
        print("Firewall: could not remove port: %s" % e)


server = None
firewall_added = False
stopped = False
lock = threading.Lock()


def cleanup():
    global stopped

    with lock:
        if stopped:
            return
        stopped = True

    print("\nStopping server...")
    sys.stdout.flush()

    if server:
        try:
            server.server_close()
        except:
            pass

    if firewall_added:
        firewall_remove(PORT)

    print("Done.")
    sys.stdout.flush()


def signal_handler(signum, frame):
    cleanup()
    os._exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if hasattr(signal, "SIGHUP"):
    signal.signal(signal.SIGHUP, signal_handler)


print("Serving: %s" % FILE)
print("Listening on 0.0.0.0:%d" % PORT)
sys.stdout.flush()

firewall_added = firewall_add(PORT)

try:
    server = BaseHTTPServer.HTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    server_thread = threading.Thread(
        target=server.serve_forever
    )
    server_thread.daemon = True
    server_thread.start()

    print("Server started.")
    print("Press ENTER to stop the server.")
    sys.stdout.flush()

    raw_input()

except (KeyboardInterrupt, EOFError):
    pass

finally:
    cleanup()
EOF

chmod +x serve-file.py
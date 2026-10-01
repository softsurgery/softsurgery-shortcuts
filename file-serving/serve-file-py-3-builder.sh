#!/bin/bash
# Builder script to generate a secure serve-file.py
# Features added: SSL Encryption, Basic Authentication, and File Uploads

cat > serve-file.py <<'EOF'
#!/usr/bin/env python3

import os
import sys
import signal
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import ssl
import base64
import random
import string
import re
import urllib.parse

# Check arguments: <file> and <port> are required; password is auto-generated if omitted
if len(sys.argv) < 3 or len(sys.argv) > 4:
    print(f"Usage: {sys.argv[0]} <file> <port> [password]")
    sys.exit(1)

FILE = os.path.abspath(sys.argv[1])
PORT = int(sys.argv[2])

# Auto-generate a random 12-character alphanumeric password if none was supplied
if len(sys.argv) == 4:
    PASSWORD = sys.argv[3]
else:
    charset = string.ascii_letters + string.digits
    PASSWORD = ''.join(random.choice(charset) for _ in range(12))

CERTFILE = "cert.pem"

# Ensure the file to serve actually exists
if not os.path.isfile(FILE):
    print(f"File not found: {FILE}")
    sys.exit(1)

# Generate the SSL certificate using openssl
def generate_cert():
    print("Generating self-signed SSL certificate for encryption...")
    try:
        with open(os.devnull, 'wb') as devnull:
            subprocess.check_call([
                "openssl", "req", "-new", "-x509", 
                "-keyout", CERTFILE, 
                "-out", CERTFILE, 
                "-days", "365", 
                "-nodes", 
                "-subj", "/C=US/ST=State/L=City/O=Org/OU=Unit/CN=localhost"
            ], stdout=devnull, stderr=subprocess.STDOUT)
        print(f"Certificate generated: {CERTFILE}")
    except Exception as e:
        print(f"Failed to generate certificate: {e}")
        sys.exit(1)

generate_cert()

# Generate the expected Basic Auth string for the "admin" user
EXPECTED_AUTH = "Basic " + base64.b64encode(f"admin:{PASSWORD}".encode('utf-8')).decode('ascii')


class StreamBuffer:
    """Buffered reader for rfile that allows safe line reading and streaming writes."""
    def __init__(self, rfile, length):
        self.rfile = rfile
        self.remaining = length
        self.buf = b''

    def read(self, n):
        while len(self.buf) < n and self.remaining > 0:
            chunk = self.rfile.read(min(65536, self.remaining))
            if not chunk:
                break
            self.remaining -= len(chunk)
            self.buf += chunk
        res = self.buf[:n]
        self.buf = self.buf[n:]
        return res

    def readline(self):
        while b'\n' not in self.buf and self.remaining > 0:
            chunk = self.rfile.read(min(65536, self.remaining))
            if not chunk:
                break
            self.remaining -= len(chunk)
            self.buf += chunk
        if b'\n' in self.buf:
            idx = self.buf.index(b'\n') + 1
            res = self.buf[:idx]
            self.buf = self.buf[idx:]
            return res
        res = self.buf
        self.buf = b''
        return res

    def drain(self):
        while self.remaining > 0:
            chunk = self.rfile.read(min(65536, self.remaining))
            if not chunk:
                break
            self.remaining -= len(chunk)
        self.buf = b''


def save_multipart_upload(stream_buf, boundary, target_dir):
    """Parses multipart/form-data upload stream without loading the full payload into memory."""
    boundary_bytes = boundary.encode('latin1')
    boundary_marker = b'--' + boundary_bytes
    delimiter = b'\r\n--' + boundary_bytes

    # Find the opening boundary line
    while True:
        line = stream_buf.readline()
        if not line:
            raise ValueError('Empty upload body or missing multipart boundary')
        if line.strip() == boundary_marker:
            break

    saved_file = None
    saved_path = None
    delim_len = len(delimiter)
    chunk_size = 64 * 1024

    while True:
        # Read headers for the current part
        headers = {}
        while True:
            line = stream_buf.readline()
            if not line or line in (b'\r\n', b'\n'):
                break
            text = line.decode('latin1', errors='replace').strip()
            if ':' in text:
                k, v = text.split(':', 1)
                headers[k.strip().lower()] = v.strip()

        cd = headers.get('content-disposition', '')
        m = re.search(r'filename\*?=(?:UTF-8\'\')?(?:"([^"]+)"|\'([^\']+)\'|([^;\s]+))', cd, re.IGNORECASE)
        filename = None
        if m:
            raw_fn = m.group(1) or m.group(2) or m.group(3)
            filename = urllib.parse.unquote(raw_fn)

        out_file = None
        if filename:
            # os.path.basename prevents directory traversal attacks
            safe_filename = os.path.basename(filename) or 'uploaded_file'
            upload_path = os.path.join(target_dir, safe_filename)
            out_file = open(upload_path, 'wb')
            saved_file = safe_filename
            saved_path = upload_path

        # Stream body directly to disk until the boundary delimiter is encountered
        while True:
            while len(stream_buf.buf) < delim_len + chunk_size and stream_buf.remaining > 0:
                chunk = stream_buf.rfile.read(min(chunk_size, stream_buf.remaining))
                if not chunk:
                    break
                stream_buf.remaining -= len(chunk)
                stream_buf.buf += chunk

            idx = stream_buf.buf.find(delimiter)
            if idx != -1:
                if out_file:
                    out_file.write(stream_buf.buf[:idx])
                stream_buf.buf = stream_buf.buf[idx + len(delimiter):]
                break
            else:
                if len(stream_buf.buf) > delim_len:
                    write_len = len(stream_buf.buf) - delim_len
                    if out_file:
                        out_file.write(stream_buf.buf[:write_len])
                    stream_buf.buf = stream_buf.buf[write_len:]
                elif stream_buf.remaining == 0:
                    if out_file:
                        out_file.write(stream_buf.buf)
                    stream_buf.buf = b''
                    break

        if out_file:
            out_file.close()

        # Check boundary trailer: '--' means end of multipart data
        trailer = stream_buf.read(2)
        if trailer == b'--':
            stream_buf.drain()
            break
        elif trailer in (b'\r\n', b'\n'):
            pass

        if saved_file:
            stream_buf.drain()
            break

    if not saved_file:
        raise ValueError('No file provided in the upload request')
    return saved_file, saved_path


class Handler(BaseHTTPRequestHandler):

    # Security: Require authentication for all requests
    def authenticate(self):
        auth_header = self.headers.get('Authorization')
        if auth_header != EXPECTED_AUTH:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Secure File Server"')
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            msg = b'401 Unauthorized: Invalid credentials.'
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return False
        return True

    def do_GET(self):
        # Authenticate first before serving any content
        if not self.authenticate():
            return

        if self.path == "/":
            self.page()
        elif self.path == "/download":
            self.download()
        else:
            self.send_error(404)

    def do_POST(self):
        # Authenticate POST requests (for file uploads)
        if not self.authenticate():
            return
            
        if self.path == "/upload":
            self.upload()
        else:
            self.send_error(404)

    def page(self):
        # Main HTML page with Download link and Upload form (with progress bar)
        filename = os.path.basename(FILE)
        size = os.path.getsize(FILE)

        html = """<!DOCTYPE html>
<html>
<head>
    <title>Secure File Server</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 620px; margin: 40px auto; padding: 0 15px; color: #333; }
        .box { border: 1px solid #e1e4e8; padding: 22px; border-radius: 8px; margin-bottom: 22px; background: #fafbfc; }
        h1 { font-size: 24px; margin-bottom: 20px; }
        h2 { font-size: 18px; margin-top: 0; color: #24292e; }
        .btn { display: inline-block; background: #0366d6; color: white; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-size: 14px; font-weight: 500; border: none; cursor: pointer; }
        .btn:hover { background: #0255b3; }
        .btn-green { background: #28a745; }
        .btn-green:hover { background: #218838; }
        .btn-green:disabled { background: #94d3a2; cursor: not-allowed; }
        input[type="file"] { margin: 12px 0; display: block; font-size: 14px; }
        .progress-box { margin-top: 15px; display: none; }
        .bar-bg { width: 100%; background-color: #e9ecef; border-radius: 6px; overflow: hidden; height: 18px; }
        .bar-fill { width: 0%; height: 100%; background-color: #28a745; transition: width 0.15s ease; }
        .bar-info { display: flex; justify-content: space-between; font-size: 13px; color: #586069; margin-top: 6px; }
        .status { margin-top: 12px; font-size: 14px; font-weight: 500; }
        .success { color: #28a745; }
        .error { color: #d73a49; }
    </style>
</head>
<body>
    <h1>Secure File Server</h1>
    
    <div class="box">
        <h2>Download File</h2>
        <p><b>File:</b> {{FILENAME}}</p>
        <p><b>Size:</b> {{SIZE}} bytes</p>
        <p><a href="/download" class="btn">Download file</a></p>
    </div>
    
    <div class="box">
        <h2>Upload File</h2>
        <form id="uploadForm">
            <input type="file" id="fileInput" name="file" required>
            <button type="submit" id="uploadBtn" class="btn btn-green">Upload</button>
        </form>

        <div id="progressBox" class="progress-box">
            <div class="bar-bg">
                <div id="barFill" class="bar-fill"></div>
            </div>
            <div class="bar-info">
                <span id="pctText">0%</span>
                <span id="bytesText">0 / 0</span>
            </div>
            <div id="statusText" class="status"></div>
        </div>
    </div>

    <script>
        var form = document.getElementById('uploadForm');
        var fileInput = document.getElementById('fileInput');
        var uploadBtn = document.getElementById('uploadBtn');
        var progressBox = document.getElementById('progressBox');
        var barFill = document.getElementById('barFill');
        var pctText = document.getElementById('pctText');
        var bytesText = document.getElementById('bytesText');
        var statusText = document.getElementById('statusText');

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            var k = 1024;
            var sizes = ['B', 'KB', 'MB', 'GB'];
            var i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        form.onsubmit = function(e) {
            e.preventDefault();
            if (!fileInput.files.length) return;

            var file = fileInput.files[0];
            var formData = new FormData();
            formData.append('file', file);

            uploadBtn.disabled = true;
            progressBox.style.display = 'block';
            statusText.className = 'status';
            statusText.textContent = 'Uploading...';
            barFill.style.width = '0%';
            barFill.style.backgroundColor = '#28a745';
            pctText.textContent = '0%';
            bytesText.textContent = '0 / ' + formatBytes(file.size);

            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/upload', true);

            xhr.upload.onprogress = function(event) {
                if (event.lengthComputable) {
                    var percent = Math.round((event.loaded / event.total) * 100);
                    barFill.style.width = percent + '%';
                    pctText.textContent = percent + '%';
                    bytesText.textContent = formatBytes(event.loaded) + ' / ' + formatBytes(event.total);
                }
            };

            xhr.onload = function() {
                uploadBtn.disabled = false;
                if (xhr.status === 200) {
                    barFill.style.width = '100%';
                    pctText.textContent = '100%';
                    statusText.className = 'status success';
                    statusText.textContent = 'Upload successful!';
                    fileInput.value = '';
                } else {
                    statusText.className = 'status error';
                    statusText.textContent = 'Upload failed: ' + (xhr.statusText || 'Server error');
                    barFill.style.backgroundColor = '#d73a49';
                }
            };

            xhr.onerror = function() {
                uploadBtn.disabled = false;
                statusText.className = 'status error';
                statusText.textContent = 'Network error during upload.';
                barFill.style.backgroundColor = '#d73a49';
            };

            xhr.send(formData);
        };
    </script>
</body>
</html>""".replace("{{FILENAME}}", filename).replace("{{SIZE}}", str(size))

        html_bytes = html.encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        self.end_headers()
        self.wfile.write(html_bytes)

    def download(self):
        # Serve the requested file securely
        filename = os.path.basename(FILE)
        size = os.path.getsize(FILE)

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{filename}"'
        )
        self.end_headers()

        # Read and send the file in chunks for memory efficiency
        with open(FILE, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                self.wfile.write(data)

    def upload(self):
        # Handle file uploads securely
        try:
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self.send_error(400, "Expected multipart/form-data")
                return

            boundary = None
            if 'boundary=' in content_type:
                boundary = content_type.split('boundary=', 1)[1].split(';')[0].strip()
                if boundary.startswith('"') and boundary.endswith('"'):
                    boundary = boundary[1:-1]

            if not boundary:
                self.send_error(400, "Missing boundary in Content-Type")
                return

            try:
                content_length = int(self.headers.get('Content-Length', 0))
            except (ValueError, TypeError):
                content_length = 0

            if content_length <= 0:
                self.send_error(400, "Invalid or missing Content-Length")
                return

            stream_buf = StreamBuffer(self.rfile, content_length)
            safe_filename, upload_path = save_multipart_upload(stream_buf, boundary, os.getcwd())

            resp = b'Upload successful! <a href="/">Go back</a>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            print(f"Successfully uploaded: {upload_path}")
            sys.stdout.flush()
        except Exception as e:
            self.send_error(500, f"Failed to upload file: {e}")

    def log_message(self, format, *args):
        # Log request IP and details
        print("%s - %s" % (
            self.address_string(),
            format % args
        ))
        sys.stdout.flush()


firewall_backend = None


def find_firewall_tool(name):
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for extra in ["/usr/sbin", "/sbin", "/usr/local/sbin"]:
        if extra not in path_dirs:
            path_dirs.append(extra)
    for d in path_dirs:
        candidate = os.path.join(d, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def detect_firewall():
    # Detect Debian-based distros vs CentOS/RHEL
    is_debian = os.path.exists("/etc/debian_version")
    if is_debian:
        order = ["ufw", "iptables", "firewall-cmd"]
    else:
        order = ["firewall-cmd", "ufw", "iptables"]

    for name in order:
        tool = find_firewall_tool(name)
        if tool:
            return (tool, name)
    return None


def firewall_add(port):
    global firewall_backend
    backend = detect_firewall()
    if not backend:
        print("Firewall: no supported firewall tool found (ufw, firewall-cmd, iptables)")
        sys.stdout.flush()
        return False

    tool, name = backend
    try:
        if name == "ufw":
            subprocess.check_call([tool, "allow", f"{port}/tcp"])
        elif name == "firewall-cmd":
            subprocess.check_call([tool, f"--add-port={port}/tcp"])
        elif name == "iptables":
            subprocess.check_call([tool, "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"])

        firewall_backend = backend
        print(f"Firewall: allowed TCP port {port} ({name})")
        sys.stdout.flush()
        return True
    except Exception as e:
        print(f"Firewall: could not open port ({name}): {e}")
        sys.stdout.flush()
        return False


def firewall_remove(port):
    global firewall_backend
    backend = firewall_backend or detect_firewall()
    if not backend:
        return

    tool, name = backend
    try:
        if name == "ufw":
            subprocess.call([tool, "delete", "allow", f"{port}/tcp"])
        elif name == "firewall-cmd":
            subprocess.call([tool, f"--remove-port={port}/tcp"])
        elif name == "iptables":
            subprocess.call([tool, "-D", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"])

        print(f"Firewall: removed TCP port {port} ({name})")
        sys.stdout.flush()
    except Exception as e:
        print(f"Firewall: could not remove port ({name}): {e}")
        sys.stdout.flush()


server = None
firewall_added = False
stopped = False
lock = threading.Lock()


def cleanup():
    # Graceful shutdown process
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
        except Exception:
            pass

    if firewall_added:
        firewall_remove(PORT)

    # Clean up the generated certificate file
    if os.path.exists(CERTFILE):
        try:
            os.remove(CERTFILE)
            print(f"Cleaned up certificate file: {CERTFILE}")
        except Exception as e:
            print(f"Failed to remove certificate file: {e}")

    print("Done.")
    sys.stdout.flush()


def signal_handler(signum, frame):
    cleanup()
    os._exit(0)

# Register signal handlers for clean exit
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if hasattr(signal, "SIGHUP"):
    signal.signal(signal.SIGHUP, signal_handler)


print("=" * 60)
print(f"Serving: {FILE}")
print(f"Listening on: https://0.0.0.0:{PORT} (HTTPS enabled)")
print("-" * 60)
print("Authentication Required:")
print("  Username: admin")
print(f"  Password: {PASSWORD}")
print("=" * 60)
sys.stdout.flush()

firewall_added = firewall_add(PORT)

try:
    server = HTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    # Enable SSL/TLS encryption for the server socket
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile=CERTFILE)
    server.socket = ssl_context.wrap_socket(
        server.socket, 
        server_side=True
    )

    server_thread = threading.Thread(
        target=server.serve_forever
    )
    server_thread.daemon = True
    server_thread.start()

    print("Server started. Press ENTER to stop the server.")
    sys.stdout.flush()

    input()

except (KeyboardInterrupt, EOFError):
    pass

finally:
    cleanup()
EOF

chmod +x serve-file.py
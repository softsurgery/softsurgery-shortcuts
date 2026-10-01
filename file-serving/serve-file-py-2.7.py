#!/usr/bin/env python2

import os
import sys
import signal
import subprocess
import BaseHTTPServer
import threading
import ssl
import base64
import cgi
import random
import string

# Check arguments: <file> and <port> are required; password is auto-generated if omitted
if len(sys.argv) < 3 or len(sys.argv) > 4:
    print("Usage: %s <file> <port> [password]" % sys.argv[0])
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
    print("File not found: %s" % FILE)
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
        print("Certificate generated: %s" % CERTFILE)
    except Exception as e:
        print("Failed to generate certificate: %s" % str(e))
        sys.exit(1)

generate_cert()

# Generate the expected Basic Auth string for the "admin" user
EXPECTED_AUTH = "Basic " + base64.b64encode("admin:" + PASSWORD)


class Handler(BaseHTTPServer.BaseHTTPRequestHandler):

    # Security: Require authentication for all requests
    def authenticate(self):
        auth_header = self.headers.getheader('Authorization')
        if auth_header != EXPECTED_AUTH:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Secure File Server"')
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write('401 Unauthorized: Invalid credentials.')
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

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def download(self):
        # Serve the requested file securely
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
            content_type = self.headers.getheader('Content-Type') if hasattr(self.headers, 'getheader') else self.headers.get('Content-Type', '')
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': content_type
                }
            )

            # Check if file was provided in the upload form
            has_file = False
            if hasattr(form, 'has_key'):
                has_file = form.has_key('file')
            elif hasattr(form, '__contains__'):
                has_file = 'file' in form

            if not has_file:
                self.send_error(400, "No file provided in the upload request")
                return

            upload_file = form['file']
            filename = getattr(upload_file, 'filename', None)
            if not filename:
                self.send_error(400, "Invalid file upload")
                return

            # Save the uploaded file in the current working directory securely
            # os.path.basename prevents directory traversal attacks
            safe_filename = os.path.basename(filename)
            upload_path = os.path.join(os.getcwd(), safe_filename)

            with open(upload_path, 'wb') as f:
                if hasattr(upload_file, 'file') and upload_file.file:
                    while True:
                        chunk = upload_file.file.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                else:
                    f.write(upload_file.value)

            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write('Upload successful! <a href="/">Go back</a>')
            print("Successfully uploaded: %s" % upload_path)
        except Exception as e:
            self.send_error(500, "Failed to upload file: %s" % str(e))

    def log_message(self, format, *args):
        # Log request IP and details
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
        except:
            pass

    if firewall_added:
        firewall_remove(PORT)

    # Clean up the generated certificate file
    if os.path.exists(CERTFILE):
        try:
            os.remove(CERTFILE)
            print("Cleaned up certificate file: %s" % CERTFILE)
        except Exception as e:
            print("Failed to remove certificate file: %s" % e)

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
print("Serving: %s" % FILE)
print("Listening on: https://0.0.0.0:%d (HTTPS enabled)" % PORT)
print("-" * 60)
print("Authentication Required:")
print("  Username: admin")
print("  Password: %s" % PASSWORD)
print("=" * 60)
sys.stdout.flush()

firewall_added = firewall_add(PORT)

try:
    server = BaseHTTPServer.HTTPServer(
        ("0.0.0.0", PORT),
        Handler
    )

    # Enable SSL/TLS encryption for the server socket
    server.socket = ssl.wrap_socket(
        server.socket, 
        certfile=CERTFILE, 
        server_side=True
    )

    server_thread = threading.Thread(
        target=server.serve_forever
    )
    server_thread.daemon = True
    server_thread.start()

    print("Server started. Press ENTER to stop the server.")
    sys.stdout.flush()

    raw_input()

except (KeyboardInterrupt, EOFError):
    pass

finally:
    cleanup()
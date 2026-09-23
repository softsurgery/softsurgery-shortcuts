#!/usr/bin/env python3

"""
Antigravity Manager
===================

Ubuntu 24+

Manages:

    Antigravity CLI
        ~/.local/bin/agy

    Antigravity 2.0
        /opt/antigravity

    Antigravity IDE (Standalone)
        /opt/antigravity-ide

The standalone IDE download is discovered using Selenium
against Google's live download page. The script keeps a
private Chrome for Testing + matching ChromeDriver under:

    ~/.local/share/antigravity-manager/chrome-for-testing

so the system Chrome / PATH chromedriver are never used.

Requirements:

    sudo apt install python3 python3-pip

    python3 -m pip install --user selenium

Run WITHOUT sudo:

    python3 antigravity-manager.py
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urljoin


# ============================================================
# CONFIGURATION
# ============================================================

GOOGLE_DOWNLOAD_PAGE = "https://antigravity.google/download"
GOOGLE_CLI_INSTALLER = (
    "https://antigravity.google/cli/install.sh"
)

IDE_DIR = Path("/opt/antigravity-ide")
ANTIGRAVITY_DIR = Path("/opt/antigravity")

CLI_PATH = (
    Path.home()
    / ".local"
    / "bin"
    / "agy"
)

LOCAL_APPLICATION_DIR = (
    Path.home()
    / ".local"
    / "share"
    / "applications"
)

LOCAL_ICON_DIR = (
    Path.home()
    / ".local"
    / "share"
    / "icons"
    / "hicolor"
    / "256x256"
    / "apps"
)

DESKTOP_FILE = (
    LOCAL_APPLICATION_DIR
    / "antigravity-ide.desktop"
)

ICON_FILE = (
    LOCAL_ICON_DIR
    / "antigravity-ide.png"
)

BACKUP_DIR = Path(
    "/opt/antigravity-ide.backup"
)

CHROME_FOR_TESTING_JSON = (
    "https://googlechromelabs.github.io/"
    "chrome-for-testing/"
    "last-known-good-versions-with-downloads.json"
)

CHROME_ENV_DIR = (
    Path.home()
    / ".local"
    / "share"
    / "antigravity-manager"
    / "chrome-for-testing"
)

CHROME_PROFILE_DIR = (
    Path.home()
    / ".local"
    / "share"
    / "antigravity-manager"
    / "chrome-profile"
)

USER_AGENT = (
    "Mozilla/5.0 "
    "(X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/140 Safari/537.36"
)


# ============================================================
# COLORS
# ============================================================

COLOR = sys.stdout.isatty()

def c(code: str, text: str) -> str:
    if COLOR:
        return f"\033[{code}m{text}\033[0m"
    return text


def green(x): return c("32", x)
def red(x): return c("31", x)
def yellow(x): return c("33", x)
def blue(x): return c("34", x)
def cyan(x): return c("36", x)
def bold(x): return c("1", x)


def info(msg):
    print(f"{blue('==>')} {msg}")


def ok(msg):
    print(f"{green('✓')} {msg}")


def warn(msg):
    print(f"{yellow('WARNING:')} {msg}")


def fail(msg):
    print(f"{red('ERROR:')} {msg}")


# ============================================================
# INPUT
# ============================================================

def ask(question: str, default=False) -> bool:

    suffix = "[Y/n]" if default else "[y/N]"

    try:
        answer = input(
            f"{question} {suffix} "
        ).strip().lower()
    except EOFError:
        return default

    if not answer:
        return default

    return answer in (
        "y",
        "yes",
    )


def pause():

    try:
        input(
            "\nPress Enter to continue..."
        )
    except EOFError:
        pass


# ============================================================
# COMMANDS
# ============================================================

def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run(
    command,
    *,
    check=True,
    capture=False,
):

    return subprocess.run(
        command,
        check=check,
        text=True,
        stdout=(
            subprocess.PIPE
            if capture
            else None
        ),
        stderr=(
            subprocess.PIPE
            if capture
            else None
        ),
    )


def sudo(command, *, check=True):

    return run(
        [
            "sudo",
            *command,
        ],
        check=check,
    )


# ============================================================
# ARCHITECTURE
# ============================================================

def architecture():

    machine = (
        platform.machine()
        .lower()
    )

    if machine in (
        "x86_64",
        "amd64",
    ):
        return (
            "x64",
            "linux-x64",
        )

    if machine in (
        "aarch64",
        "arm64",
    ):
        return (
            "ARM64",
            "linux-arm64",
        )

    raise RuntimeError(
        f"Unsupported architecture: {machine}"
    )


# ============================================================
# VERSION
# ============================================================

def version_tuple(version):

    if not version:
        return ()

    return tuple(
        int(x)
        for x in re.findall(
            r"\d+",
            str(version),
        )
    )


def same_version(a, b):

    if not a or not b:
        return False

    return (
        version_tuple(a)
        == version_tuple(b)
    )


# ============================================================
# PRODUCT.JSON
# ============================================================

def product_json(root: Path):

    path = (
        root
        / "resources"
        / "app"
        / "product.json"
    )

    if not path.exists():
        return None

    try:

        import json

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return None


def installed_version(root: Path):

    data = product_json(root)

    if not data:
        return None

    for key in (
        "version",
        "ideVersion",
        "applicationVersion",
    ):

        value = data.get(key)

        if value:
            return str(value)

    return None


# ============================================================
# DETECTION
# ============================================================

def detect_cli():

    if (
        CLI_PATH.exists()
        and
        os.access(
            CLI_PATH,
            os.X_OK,
        )
    ):
        return CLI_PATH

    found = shutil.which("agy")

    if found:
        return Path(found)

    return None


def detect_antigravity():

    executable = (
        ANTIGRAVITY_DIR
        / "antigravity"
    )

    if (
        executable.exists()
        and
        os.access(
            executable,
            os.X_OK,
        )
    ):
        return executable

    return None


def detect_ide():

    candidates = [
        IDE_DIR / "antigravity-ide",
        IDE_DIR / "antigravity",
    ]

    for executable in candidates:

        if (
            executable.exists()
            and
            os.access(
                executable,
                os.X_OK,
            )
        ):
            return executable

    # Some archives contain an additional
    # directory before the executable.

    for executable_name in (
        "antigravity-ide",
        "antigravity",
    ):

        matches = list(
            IDE_DIR.rglob(
                executable_name
            )
        )

        for match in matches:

            if (
                match.is_file()
                and
                os.access(
                    match,
                    os.X_OK,
                )
            ):
                return match

    return None


def cli_version(executable):

    if not executable:
        return None

    try:

        result = run(
            [
                str(executable),
                "--version",
            ],
            check=False,
            capture=True,
        )

        output = (
            result.stdout
            or result.stderr
            or ""
        )

        match = re.search(
            r"\d+\.\d+\.\d+",
            output,
        )

        if match:
            return match.group(0)

    except Exception:
        pass

    return None


# ============================================================
# STATUS
# ============================================================

def status():

    cli = detect_cli()
    ag = detect_antigravity()
    ide = detect_ide()

    return {
        "cli": cli,
        "cli_version": cli_version(cli),

        "antigravity": ag,
        "antigravity_version": (
            installed_version(
                ANTIGRAVITY_DIR
            )
            if ag
            else None
        ),

        "ide": ide,
        "ide_version": (
            installed_version(
                IDE_DIR
            )
            if ide
            else None
        ),
    }


def show_status():

    arch, _ = architecture()
    s = status()

    print()
    print(
        bold(
            "=" * 70
        )
    )
    print(
        bold(
            "                 ANTIGRAVITY MANAGER"
        )
    )
    print(
        bold(
            "=" * 70
        )
    )

    print()
    print(
        f"Architecture: {arch}"
    )

    print()

    # CLI

    print(
        bold("Antigravity CLI")
    )

    if s["cli"]:

        print(
            f"  Status  : {green('Installed')}"
        )

        print(
            f"  Version : "
            f"{s['cli_version'] or 'Unknown'}"
        )

        print(
            f"  Binary  : {s['cli']}"
        )

    else:

        print(
            f"  Status  : {yellow('Not installed')}"
        )

    print()

    # Antigravity 2.0

    print(
        bold("Antigravity 2.0")
    )

    if s["antigravity"]:

        print(
            f"  Status  : {green('Installed')}"
        )

        print(
            f"  Version : "
            f"{s['antigravity_version'] or 'Unknown'}"
        )

        print(
            f"  Location: {ANTIGRAVITY_DIR}"
        )

    else:

        print(
            f"  Status  : {yellow('Not installed')}"
        )

    print()

    # IDE

    print(
        bold(
            "Antigravity IDE (Standalone)"
        )
    )

    if s["ide"]:

        print(
            f"  Status  : {green('Installed')}"
        )

        print(
            f"  Version : "
            f"{s['ide_version'] or 'Unknown'}"
        )

        print(
            f"  Location: {IDE_DIR}"
        )

        print(
            f"  Binary  : {s['ide']}"
        )

    else:

        print(
            f"  Status  : {yellow('Not installed')}"
        )

    print()


# ============================================================
# STANDALONE CHROME
# ============================================================

def chrome_platform():

    machine = (
        platform.machine()
        .lower()
    )

    if machine in (
        "x86_64",
        "amd64",
    ):
        return "linux64"

    if machine in (
        "aarch64",
        "arm64",
    ):
        return "linux-arm64"

    raise RuntimeError(
        f"Unsupported architecture: {machine}"
    )


def find_named_binary(root: Path, name: str):

    for candidate in root.rglob(name):

        if (
            candidate.is_file()
            and
            candidate.name == name
        ):
            return candidate

    return None


def chrome_for_testing_urls():

    request = urllib.request.Request(
        CHROME_FOR_TESTING_JSON,
        headers={
            "User-Agent":
                USER_AGENT
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=60,
    ) as response:

        data = json.loads(
            response.read().decode()
        )

    channel = data["channels"]["Stable"]
    version = channel["version"]
    platform = chrome_platform()

    chrome_url = None
    driver_url = None

    for item in channel["downloads"].get(
        "chrome",
        [],
    ):
        if item.get("platform") == platform:
            chrome_url = item.get("url")

    for item in channel["downloads"].get(
        "chromedriver",
        [],
    ):
        if item.get("platform") == platform:
            driver_url = item.get("url")

    if not chrome_url or not driver_url:

        raise RuntimeError(
            "Chrome for Testing does not publish "
            f"{platform} binaries for {version}."
        )

    return version, chrome_url, driver_url


def make_chrome_env_executable(root: Path):

    names = {
        "chrome",
        "chromedriver",
        "chrome_crashpad_handler",
        "chrome_sandbox",
        "chrome-wrapper",
    }

    for path in root.rglob("*"):

        if not path.is_file():
            continue

        if (
            path.name in names
            or
            path.name.startswith("lib")
        ):
            path.chmod(0o755)


def extract_zip(archive: Path, destination: Path):

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(
        archive
    ) as archive_file:

        archive_file.extractall(
            destination
        )


def ensure_standalone_chrome():

    """
    Download and cache a matching Chrome + ChromeDriver
    pair that does not depend on the system browser.
    """

    CHROME_ENV_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    version_file = (
        CHROME_ENV_DIR
        / "version.txt"
    )

    version, chrome_url, driver_url = (
        chrome_for_testing_urls()
    )

    chrome_bin = find_named_binary(
        CHROME_ENV_DIR,
        "chrome",
    )

    driver_bin = find_named_binary(
        CHROME_ENV_DIR,
        "chromedriver",
    )

    installed = ""

    if version_file.exists():

        installed = (
            version_file
            .read_text()
            .strip()
        )

    if (
        installed == version
        and
        chrome_bin
        and
        driver_bin
    ):
        make_chrome_env_executable(
            CHROME_ENV_DIR
        )
        return chrome_bin, driver_bin

    info(
        f"Installing standalone Chrome {version}..."
    )

    for child in CHROME_ENV_DIR.iterdir():

        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    with tempfile.TemporaryDirectory() as tmp:

        tmp = Path(tmp)

        chrome_zip = tmp / "chrome.zip"
        driver_zip = tmp / "chromedriver.zip"

        download(
            chrome_url,
            chrome_zip,
            label="Chrome for Testing",
            timeout=300,
        )

        download(
            driver_url,
            driver_zip,
            label="ChromeDriver",
            timeout=180,
        )

        extract_zip(
            chrome_zip,
            CHROME_ENV_DIR,
        )

        extract_zip(
            driver_zip,
            CHROME_ENV_DIR,
        )

    chrome_bin = find_named_binary(
        CHROME_ENV_DIR,
        "chrome",
    )

    driver_bin = find_named_binary(
        CHROME_ENV_DIR,
        "chromedriver",
    )

    if not chrome_bin or not driver_bin:

        raise RuntimeError(
            "Standalone Chrome extraction "
            "did not produce chrome + chromedriver."
        )

    make_chrome_env_executable(
        CHROME_ENV_DIR
    )

    version_file.write_text(
        version + "\n"
    )

    ok(
        f"Standalone Chrome ready: {version}"
    )

    return chrome_bin, driver_bin


# ============================================================
# SELENIUM
# ============================================================

def create_driver():

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import (
            Options,
        )
        from selenium.webdriver.chrome.service import (
            Service,
        )
    except ImportError:

        raise RuntimeError(
            "Selenium is not installed.\n\n"
            "Install it with:\n\n"
            "    python3 -m pip install --user selenium"
        )

    chrome_bin, driver_bin = (
        ensure_standalone_chrome()
    )

    info(
        f"Using standalone Chrome at {chrome_bin}"
    )

    options = Options()

    options.binary_location = str(
        chrome_bin
    )

    CHROME_PROFILE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    options.add_argument(
        f"--user-data-dir={CHROME_PROFILE_DIR}"
    )

    # We only need the page DOM.
    options.add_argument(
        "--headless=new"
    )

    options.add_argument(
        "--no-sandbox"
    )

    options.add_argument(
        "--disable-dev-shm-usage"
    )

    options.add_argument(
        "--disable-gpu"
    )

    options.add_argument(
        f"--user-agent={USER_AGENT}"
    )

    options.add_argument(
        "--window-size=1920,1080"
    )

    driver = webdriver.Chrome(
        service=Service(
            executable_path=str(
                driver_bin
            )
        ),
        options=options,
    )

    driver.set_page_load_timeout(
        60
    )

    return driver


# ============================================================
# SELENIUM SCRAPER
# ============================================================

def scrape_google_ide():

    """
    Uses a real browser to inspect Google's current
    download page.

    We specifically search for:

        Antigravity IDE (Standalone)

    and then inspect the buttons/links beneath it.

    We don't assume a JavaScript bundle filename.
    """

    arch_name, arch_key = architecture()

    info(
        "Opening Google's official download page "
        f"with Selenium ({arch_name})..."
    )

    driver = create_driver()

    try:

        driver.get(
            GOOGLE_DOWNLOAD_PAGE
        )

        # Give the React application time to render.
        time.sleep(3)

        # ----------------------------------------------------
        # Scroll through the page.
        # This forces lazy-rendered elements to appear.
        # ----------------------------------------------------

        driver.execute_script(
            """
            window.scrollTo(
                0,
                document.body.scrollHeight
            );
            """
        )

        time.sleep(2)

        # ----------------------------------------------------
        # Search all anchors/buttons.
        # ----------------------------------------------------

        elements = driver.find_elements(
            "xpath",
            "//a | //button"
        )

        candidates = []

        for element in elements:

            try:

                text = (
                    element.text
                    or ""
                ).strip()

                aria = (
                    element.get_attribute(
                        "aria-label"
                    )
                    or ""
                )

                title = (
                    element.get_attribute(
                        "title"
                    )
                    or ""
                )

                href = (
                    element.get_attribute(
                        "href"
                    )
                    or ""
                )

                blob = " ".join(
                    [
                        text,
                        aria,
                        title,
                        href,
                    ]
                ).lower()

                # We specifically want the standalone IDE.
                if (
                    "antigravity ide"
                    not in blob
                    and
                    "standalone"
                    not in blob
                ):
                    continue

                # Linux architecture.
                if arch_key not in blob:

                    # Google may expose architecture
                    # through nearby DOM rather than href.

                    if not (
                        "linux"
                        in blob
                        and
                        (
                            "x64"
                            in blob
                            or
                            "arm64"
                            in blob
                        )
                    ):
                        continue

                if href:

                    candidates.append(
                        {
                            "text": text,
                            "aria": aria,
                            "title": title,
                            "href": href,
                        }
                    )

            except Exception:
                continue

        # ----------------------------------------------------
        # Search raw DOM for URLs as well.
        # ----------------------------------------------------

        page_source = driver.page_source

        # Decode HTML escaped paths.
        page_source = (
            page_source
            .replace(
                "\\/",
                "/",
            )
            .replace(
                "&amp;",
                "&",
            )
        )

        # Direct archive URLs.
        archive_urls = re.findall(
            r'https?://[^"\'>\s]+?\.tar\.gz[^"\'>\s]*',
            page_source,
            re.IGNORECASE,
        )

        for url in archive_urls:

            lower = url.lower()

            if (
                "antigravity"
                in lower
                and
                (
                    "ide"
                    in lower
                )
                and
                arch_key
                in lower
            ):

                candidates.append(
                    {
                        "text": "DOM archive",
                        "aria": "",
                        "title": "",
                        "href": url,
                    }
                )

        # ----------------------------------------------------
        # Inspect all links whose href contains archive-ish
        # Google download domains.
        # ----------------------------------------------------

        all_links = driver.find_elements(
            "xpath",
            "//a[@href]"
        )

        for link in all_links:

            href = (
                link.get_attribute(
                    "href"
                )
                or ""
            )

            lower = href.lower()

            if (
                "antigravity"
                in lower
                and
                (
                    "edgedl"
                    in lower
                    or
                    "storage.googleapis.com"
                    in lower
                )
                and
                (
                    arch_key
                    in lower
                    or
                    (
                        "linux"
                        in lower
                        and
                        (
                            "x64"
                            in lower
                            or
                            "arm64"
                            in lower
                        )
                    )
                )
            ):

                candidates.append(
                    {
                        "text": link.text or "",
                        "aria": (
                            link.get_attribute(
                                "aria-label"
                            )
                            or ""
                        ),
                        "title": (
                            link.get_attribute(
                                "title"
                            )
                            or ""
                        ),
                        "href": href,
                    }
                )

        # ----------------------------------------------------
        # Deduplicate.
        # ----------------------------------------------------

        unique = []

        seen = set()

        for candidate in candidates:

            href = candidate["href"]

            if href in seen:
                continue

            seen.add(href)
            unique.append(candidate)

        # ----------------------------------------------------
        # Score candidates.
        # ----------------------------------------------------

        scored = []

        for candidate in unique:

            href = candidate["href"]

            blob = (
                (
                    (candidate.get("text") or "")
                    + " "
                    + (candidate.get("aria") or "")
                    + " "
                    + (candidate.get("title") or "")
                    + " "
                    + (href or "")
                )
                .lower()
            )

            score = 0

            if (
                "antigravity ide"
                in blob
            ):
                score += 100

            if "standalone" in blob:
                score += 50

            if "linux" in blob:
                score += 40

            if arch_key in blob:
                score += 50

            if ".tar.gz" in blob:
                score += 30

            if (
                "edgedl.me.gvt1.com"
                in blob
            ):
                score += 20

            if (
                "download"
                in blob
            ):
                score += 10

            scored.append(
                (
                    score,
                    candidate,
                )
            )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        if not scored:

            raise RuntimeError(
                "Selenium could not find the "
                "Antigravity IDE Linux download."
            )

        # ----------------------------------------------------
        # Pick the best candidate.
        # ----------------------------------------------------

        for score, candidate in scored:

            href = candidate["href"]

            # Reject obvious non-archive links.
            if (
                ".tar.gz"
                not in href.lower()
                and
                "edgedl"
                not in href.lower()
                and
                "storage.googleapis.com"
                not in href.lower()
            ):
                continue

            version = extract_version(
                href
            )

            return {
                "url": href,
                "version": version,
                "score": score,
                "button": candidate,
            }

        raise RuntimeError(
            "Google's page was found, but "
            "no usable IDE archive URL was discovered."
        )

    finally:

        driver.quit()


# ============================================================
# VERSION FROM URL
# ============================================================

def extract_version(url):

    patterns = [
        r"/stable/(\d+\.\d+\.\d+)-",
        r"(\d+\.\d+\.\d+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            url,
        )

        if match:
            return match.group(1)

    return "Unknown"


# ============================================================
# DOWNLOAD
# ============================================================

def download(
    url,
    destination,
    label="Antigravity IDE",
    timeout=180,
):

    info(
        f"Downloading {label}..."
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                USER_AGENT
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:

        total = response.headers.get(
            "Content-Length"
        )

        total = (
            int(total)
            if total
            else None
        )

        downloaded = 0

        with open(
            destination,
            "wb",
        ) as output:

            while True:

                chunk = response.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                output.write(chunk)

                downloaded += len(
                    chunk
                )

                if total:

                    percent = int(
                        downloaded
                        * 100
                        / total
                    )

                    print(
                        f"\r  {percent:3d}%",
                        end="",
                        flush=True,
                    )

    print()


# ============================================================
# EXTRACT
# ============================================================

def extract_archive(
    archive,
    destination,
):

    info(
        "Extracting archive..."
    )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tarfile.open(
        archive,
        "r:gz",
    ) as tar:

        tar.extractall(
            destination,
            filter="data",
        )


def locate_application(
    root: Path,
):

    candidates = []

    for name in (
        "antigravity-ide",
        "antigravity",
    ):

        candidates.extend(
            root.rglob(name)
        )

    for executable in candidates:

        if (
            executable.is_file()
            and
            os.access(
                executable,
                os.X_OK,
            )
        ):

            return executable.parent

    raise RuntimeError(
        "The downloaded archive does not "
        "contain an Antigravity IDE executable."
    )


# ============================================================
# ICON HANDLING
# ============================================================

def file_hash(path: Path):

    h = hashlib.sha256()

    with path.open(
        "rb"
    ) as f:

        while True:

            chunk = f.read(
                1024 * 1024
            )

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def find_icon(
    application_root: Path,
):

    """
    Find the actual application icon.

    We do NOT simply choose the first PNG.

    Priority:

        1. icon files in resources/app
        2. icon files containing "antigravity"
        3. SVG icon files
        4. PNG icon files
        5. ICO files

    This prevents selecting unrelated Chromium/Electron
    artwork.
    """

    roots = [
        application_root
        / "resources"
        / "app",

        application_root
        / "resources",
    ]

    candidates = []

    for root in roots:

        if not root.exists():
            continue

        for extension in (
            "*.svg",
            "*.png",
            "*.ico",
        ):

            for path in root.rglob(
                extension
            ):

                name = (
                    path.name
                    .lower()
                )

                score = 0

                if (
                    "antigravity"
                    in name
                ):
                    score += 100

                if (
                    "icon"
                    in name
                ):
                    score += 50

                if (
                    "logo"
                    in name
                ):
                    score += 40

                if (
                    "application"
                    in name
                ):
                    score += 30

                # Avoid obvious Chromium icons.
                if (
                    "chrome"
                    in name
                    or
                    "chromium"
                    in name
                ):
                    score -= 100

                candidates.append(
                    (
                        score,
                        path,
                    )
                )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return candidates[0][1]


def install_icon(
    application_root: Path,
):

    icon = find_icon(
        application_root
    )

    if not icon:

        warn(
            "Could not find the IDE icon "
            "inside the downloaded application."
        )

        return None

    info(
        f"Using application icon:\n"
        f"  {icon}"
    )

    LOCAL_ICON_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = ICON_FILE

    # --------------------------------------------------------
    # PNG
    # --------------------------------------------------------

    if (
        icon.suffix.lower()
        == ".png"
    ):

        shutil.copy2(
            icon,
            destination,
        )

        return destination

    # --------------------------------------------------------
    # SVG
    # --------------------------------------------------------

    if (
        icon.suffix.lower()
        == ".svg"
    ):

        # Prefer ImageMagick if available.
        if command_exists(
            "convert"
        ):

            result = run(
                [
                    "convert",
                    "-background",
                    "none",
                    str(icon),
                    str(destination),
                ],
                check=False,
            )

            if result.returncode == 0:
                return destination

        # Try rsvg-convert.
        if command_exists(
            "rsvg-convert"
        ):

            result = run(
                [
                    "rsvg-convert",
                    "-w",
                    "256",
                    "-h",
                    "256",
                    str(icon),
                    "-o",
                    str(destination),
                ],
                check=False,
            )

            if result.returncode == 0:
                return destination

        warn(
            "IDE icon is SVG, but no SVG-to-PNG "
            "converter is installed."
        )

        warn(
            "Install one with:\n"
            "  sudo apt install librsvg2-bin"
        )

        # We can still use the SVG directly.
        svg_destination = (
            LOCAL_ICON_DIR
            / "antigravity-ide.svg"
        )

        shutil.copy2(
            icon,
            svg_destination,
        )

        return svg_destination

    # --------------------------------------------------------
    # ICO
    # --------------------------------------------------------

    if (
        icon.suffix.lower()
        == ".ico"
    ):

        if command_exists(
            "convert"
        ):

            result = run(
                [
                    "convert",
                    str(icon),
                    "-thumbnail",
                    "256x256",
                    str(destination),
                ],
                check=False,
            )

            if result.returncode == 0:
                return destination

    return None


# ============================================================
# DESKTOP FILE
# ============================================================

def create_launcher(
    application_root=None,
):

    executable = detect_ide()

    if not executable:

        raise RuntimeError(
            "Antigravity IDE is not installed."
        )

    LOCAL_APPLICATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    icon = None

    if application_root:
        icon = install_icon(
            application_root
        )

    if not icon and ICON_FILE.exists():
        icon = ICON_FILE

    lines = [
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        "Name=Antigravity IDE",
        "GenericName=AI Development Environment",
        "Comment=Google Antigravity IDE",
        f"Exec={executable} %F",
        "Terminal=false",
        "Categories=Development;IDE;",
        "StartupNotify=true",
        "StartupWMClass=antigravity",
    ]

    if icon:
        lines.append(
            f"Icon={icon}"
        )

    DESKTOP_FILE.write_text(
        "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )

    DESKTOP_FILE.chmod(
        0o755
    )

    if command_exists(
        "update-desktop-database"
    ):

        run(
            [
                "update-desktop-database",
                str(
                    LOCAL_APPLICATION_DIR
                ),
            ],
            check=False,
        )

    ok(
        "Antigravity IDE application launcher created."
    )

    print(
        f"  {DESKTOP_FILE}"
    )

    if icon:
        print(
            f"  Icon: {icon}"
        )


# ============================================================
# DESKTOP SHORTCUT
# ============================================================

def desktop_path():

    if command_exists(
        "xdg-user-dir"
    ):

        result = run(
            [
                "xdg-user-dir",
                "DESKTOP",
            ],
            check=False,
            capture=True,
        )

        directory = (
            result.stdout.strip()
        )

        if directory:
            return Path(
                directory
            )

    return (
        Path.home()
        / "Desktop"
    )


def create_desktop_icon():

    if not DESKTOP_FILE.exists():

        create_launcher()

    desktop = desktop_path()

    desktop.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        desktop
        / "Antigravity IDE.desktop"
    )

    shutil.copy2(
        DESKTOP_FILE,
        destination,
    )

    destination.chmod(
        0o755
    )

    # GNOME/Nautilus may mark desktop files
    # as untrusted.

    if command_exists("gio"):

        run(
            [
                "gio",
                "set",
                str(destination),
                "metadata::trusted",
                "true",
            ],
            check=False,
        )

    ok(
        "Desktop icon created."
    )

    print(
        f"  {destination}"
    )


# ============================================================
# IDE INSTALL
# ============================================================

def install_ide():

    current = detect_ide()

    current_version = (
        installed_version(
            IDE_DIR
        )
        if current
        else None
    )

    if current:

        print()
        print(
            "Installed version:"
        )

        print(
            f"  {current_version or 'Unknown'}"
        )

        print()
        print(
            "Location:"
        )

        print(
            f"  {IDE_DIR}"
        )

        print()

        if not ask(
            "Update Antigravity IDE?"
        ):
            return

    else:

        warn(
            "Antigravity IDE is NOT installed."
        )

        print()

        if not ask(
            "Would you like to install "
            "Antigravity IDE?"
        ):
            return

    # --------------------------------------------------------
    # Selenium discovery
    # --------------------------------------------------------

    try:

        release = (
            scrape_google_ide()
        )

    except Exception as exc:

        fail(
            str(exc)
        )

        print()

        print(
            "Official page:"
        )

        print(
            f"  {GOOGLE_DOWNLOAD_PAGE}"
        )

        return

    version = release[
        "version"
    ]

    url = release[
        "url"
    ]

    print()

    print(
        bold(
            "Google Antigravity IDE release"
        )
    )

    print(
        f"  Version : {version}"
    )

    print(
        f"  URL     : {url}"
    )

    print()

    # --------------------------------------------------------
    # Version check
    # --------------------------------------------------------

    if (
        current_version
        and
        same_version(
            current_version,
            version,
        )
    ):

        ok(
            "Antigravity IDE is already up to date."
        )

        if ask(
            "Repair/update the application launcher?"
        ):

            create_launcher(
                IDE_DIR
            )

        return

    # --------------------------------------------------------
    # Temporary directory
    # --------------------------------------------------------

    temporary = Path(
        tempfile.mkdtemp(
            prefix="antigravity-ide-"
        )
    )

    try:

        archive = (
            temporary
            / "ide.tar.gz"
        )

        extracted = (
            temporary
            / "extracted"
        )

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        download(
            url,
            archive,
        )

        # ----------------------------------------------------
        # Extract
        # ----------------------------------------------------

        extract_archive(
            archive,
            extracted,
        )

        application_root = (
            locate_application(
                extracted
            )
        )

        print()

        print(
            "Detected application root:"
        )

        print(
            f"  {application_root}"
        )

        # ----------------------------------------------------
        # Backup existing installation
        # ----------------------------------------------------

        if IDE_DIR.exists():

            info(
                "Creating backup of existing IDE..."
            )

            sudo(
                [
                    "rm",
                    "-rf",
                    str(BACKUP_DIR),
                ],
                check=False,
            )

            sudo(
                [
                    "mv",
                    str(IDE_DIR),
                    str(BACKUP_DIR),
                ]
            )

        # ----------------------------------------------------
        # Install
        # ----------------------------------------------------

        info(
            "Installing Antigravity IDE..."
        )

        sudo(
            [
                "mkdir",
                "-p",
                str(IDE_DIR),
            ]
        )

        sudo(
            [
                "cp",
                "-a",
                f"{application_root}/.",
                str(IDE_DIR),
            ]
        )

        # ----------------------------------------------------
        # Executable permissions
        # ----------------------------------------------------

        for executable_name in (
            "antigravity-ide",
            "antigravity",
        ):

            executable = (
                IDE_DIR
                / executable_name
            )

            if executable.exists():

                sudo(
                    [
                        "chmod",
                        "+x",
                        str(executable),
                    ],
                    check=False,
                )

        # ----------------------------------------------------
        # Chromium sandbox
        # ----------------------------------------------------

        sandbox = (
            IDE_DIR
            / "chrome-sandbox"
        )

        if sandbox.exists():

            info(
                "Configuring Chromium sandbox..."
            )

            sudo(
                [
                    "chown",
                    "root:root",
                    str(sandbox),
                ],
                check=False,
            )

            sudo(
                [
                    "chmod",
                    "4755",
                    str(sandbox),
                ],
                check=False,
            )

        # ----------------------------------------------------
        # Verify
        # ----------------------------------------------------

        installed = detect_ide()

        if not installed:

            fail(
                "The new installation could not "
                "be verified."
            )

            sudo(
                [
                    "rm",
                    "-rf",
                    str(IDE_DIR),
                ],
                check=False,
            )

            if BACKUP_DIR.exists():

                sudo(
                    [
                        "mv",
                        str(BACKUP_DIR),
                        str(IDE_DIR),
                    ]
                )

            raise RuntimeError(
                "Update failed; previous "
                "installation restored."
            )

        # ----------------------------------------------------
        # New version
        # ----------------------------------------------------

        new_version = (
            installed_version(
                IDE_DIR
            )
            or
            version
        )

        ok(
            "Antigravity IDE installed successfully."
        )

        print()
        print(
            f"Version : {new_version}"
        )

        print(
            f"Location: {IDE_DIR}"
        )

        # ----------------------------------------------------
        # Icon
        # ----------------------------------------------------

        print()

        icon = install_icon(
            IDE_DIR
        )

        if icon:

            ok(
                "Correct Antigravity IDE icon extracted."
            )

        # ----------------------------------------------------
        # Launcher
        # ----------------------------------------------------

        print()

        if ask(
            "Create/update the application launcher?"
        ):

            create_launcher(
                IDE_DIR
            )

        # ----------------------------------------------------
        # Desktop
        # ----------------------------------------------------

        print()

        if ask(
            "Create a Desktop icon?"
        ):

            create_desktop_icon()

        # ----------------------------------------------------
        # Remove old backup only after success
        # ----------------------------------------------------

        if BACKUP_DIR.exists():

            if ask(
                "Remove the previous IDE backup?"
            ):

                sudo(
                    [
                        "rm",
                        "-rf",
                        str(BACKUP_DIR),
                    ]
                )

    finally:

        shutil.rmtree(
            temporary,
            ignore_errors=True,
        )


# ============================================================
# CLI
# ============================================================

def install_cli():

    cli = detect_cli()

    if cli:

        print(
            f"Installed version:"
        )

        print(
            f"  {cli_version(cli) or 'Unknown'}"
        )

        print()

        if not ask(
            "Update Antigravity CLI?"
        ):
            return

    else:

        warn(
            "Antigravity CLI is NOT installed."
        )

        print()

        if not ask(
            "Would you like to install "
            "Antigravity CLI?"
        ):
            return

    temporary = Path(
        tempfile.mkdtemp(
            prefix="antigravity-cli-"
        )
    )

    try:

        installer = (
            temporary
            / "install.sh"
        )

        download(
            GOOGLE_CLI_INSTALLER,
            installer,
        )

        installer.chmod(
            0o700
        )

        info(
            "Running Google's official CLI installer..."
        )

        result = subprocess.run(
            [
                "bash",
                str(installer),
            ],
            check=False,
        )

        if result.returncode != 0:

            raise RuntimeError(
                "Google CLI installer failed."
            )

        if not detect_cli():

            raise RuntimeError(
                "Installer completed, but "
                "agy was not found."
            )

        ok(
            "Antigravity CLI installed/updated."
        )

        print(
            f"Version: "
            f"{cli_version(detect_cli()) or 'Unknown'}"
        )

    finally:

        shutil.rmtree(
            temporary,
            ignore_errors=True,
        )


# ============================================================
# ANTIGRAVITY 2.0
# ============================================================

def install_antigravity():

    current = detect_antigravity()

    if current:

        current_version = (
            installed_version(
                ANTIGRAVITY_DIR
            )
        )

        print(
            f"Installed version:"
        )

        print(
            f"  {current_version or 'Unknown'}"
        )

        print()

        if not ask(
            "Update Antigravity 2.0?"
        ):
            return

    else:

        warn(
            "Antigravity 2.0 is NOT installed."
        )

        print()

        if not ask(
            "Would you like to install "
            "Antigravity 2.0?"
        ):
            return

    # --------------------------------------------------------
    # Use Google's official APT repository.
    # --------------------------------------------------------

    info(
        "Configuring Google's official APT repository..."
    )

    sudo(
        [
            "mkdir",
            "-p",
            "/etc/apt/keyrings",
        ]
    )

    key_url = (
        "https://us-central1-apt.pkg.dev/"
        "doc/repo-signing-key.gpg"
    )

    temporary = Path(
        tempfile.mktemp(
            prefix="antigravity-key-"
        )
    )

    try:

        download(
            key_url,
            temporary,
        )

        sudo(
            [
                "gpg",
                "--dearmor",
                "--yes",
                "-o",
                "/etc/apt/keyrings/"
                "antigravity-repo-key.gpg",
                str(temporary),
            ]
        )

    finally:

        temporary.unlink(
            missing_ok=True
        )

    repo = (
        "deb [signed-by="
        "/etc/apt/keyrings/"
        "antigravity-repo-key.gpg] "
        "https://us-central1-apt.pkg.dev/"
        "projects/"
        "antigravity-auto-updater-dev/ "
        "antigravity-debian main"
    )

    repo_file = (
        "/etc/apt/sources.list.d/"
        "antigravity.list"
    )

    temporary_repo = Path(
        tempfile.mktemp(
            prefix="antigravity-repo-"
        )
    )

    try:

        temporary_repo.write_text(
            repo + "\n",
            encoding="utf-8",
        )

        sudo(
            [
                "cp",
                str(temporary_repo),
                repo_file,
            ]
        )

    finally:

        temporary_repo.unlink(
            missing_ok=True
        )

    sudo(
        [
            "apt",
            "update",
        ]
    )

    sudo(
        [
            "apt",
            "install",
            "-y",
            "antigravity",
        ]
    )

    ok(
        "Antigravity 2.0 installed/updated."
    )


# ============================================================
# MENU
# ============================================================

def menu():

    while True:

        os.system(
            "clear"
        )

        show_status()

        print(
            bold(
                "Select an operation:"
            )
        )

        print()

        print(
            "  1) Antigravity CLI"
        )

        print(
            "  2) Antigravity IDE"
        )

        print(
            "  3) Antigravity 2.0"
        )

        print(
            "  4) CLI + IDE"
        )

        print(
            "  5) IDE + Antigravity 2.0"
        )

        print(
            "  6) Everything"
        )

        print(
            "  7) Recreate IDE launcher/icon"
        )

        print(
            "  8) Refresh"
        )

        print(
            "  9) Exit"
        )

        print()

        try:

            choice = input(
                "Choose [1-9]: "
            ).strip()

        except EOFError:

            return

        try:

            if choice == "1":

                install_cli()
                pause()

            elif choice == "2":

                install_ide()
                pause()

            elif choice == "3":

                install_antigravity()
                pause()

            elif choice == "4":

                install_cli()
                print()
                install_ide()
                pause()

            elif choice == "5":

                install_ide()
                print()
                install_antigravity()
                pause()

            elif choice == "6":

                install_cli()
                print()
                install_ide()
                print()
                install_antigravity()
                pause()

            elif choice == "7":

                create_launcher(
                    IDE_DIR
                )

                print()

                if ask(
                    "Create a Desktop icon?"
                ):

                    create_desktop_icon()

                pause()

            elif choice == "8":

                continue

            elif choice == "9":

                print(
                    "\nGoodbye."
                )

                return

            else:

                warn(
                    "Invalid choice."
                )

                pause()

        except KeyboardInterrupt:

            print(
                "\n\nCancelled."
            )

            pause()

        except Exception as exc:

            print()

            fail(
                str(exc)
            )

            pause()


# ============================================================
# MAIN
# ============================================================

def main():

    if os.geteuid() == 0:

        print(
            red(
                "Do not run this script with sudo."
            )
        )

        print()

        print(
            "Run:"
        )

        print(
            "  python3 antigravity-manager.py"
        )

        print()

        print(
            "The script will request sudo "
            "only when modifying /opt."
        )

        sys.exit(1)

    menu()


if __name__ == "__main__":
    main()

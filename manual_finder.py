
# manual_finder.py (with PDF file validation and browser fallback)

import os
import re
import difflib
import requests
import platform
import webbrowser
from urllib.parse import urlparse, unquote
from ddgs import DDGS
from pathlib import Path

TRUSTED_DOMAINS = ['.trane.com', '.carrier.com', '.daikin.com', '.york.com', '.lg.com']

# Dynamically determine download path
if platform.system() == "Windows":
    OUTPUT_DIR = Path.cwd() / "downloads"
else:
    OUTPUT_DIR = Path("/mnt/data")

def domain_score(url, make):
    domain = urlparse(url).netloc
    score = 0
    if any(manuf in domain for manuf in TRUSTED_DOMAINS):
        score += 3
    if make.lower() in domain.lower():
        score += 2
    return score

def file_score(title, make, model):
    combined = f"{make} {model}".lower()
    return difflib.SequenceMatcher(None, combined, title.lower()).ratio()

def is_accessible_url(url):
    try:
        r = requests.head(url, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            return True, None
        elif r.status_code == 403:
            return False, "🔒 Access forbidden (login required)"
        elif r.status_code == 404:
            return False, "❌ File not found (404)"
        else:
            return False, f"⚠️ HTTP {r.status_code} returned"
    except Exception as e:
        return False, f"⚠️ Error checking link: {e}"

def is_valid_pdf(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"%PDF"
    except:
        return False

def download_file(url, filename=None):
    try:
        r = requests.get(url, stream=True, timeout=10)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "")
        if not filename:
            filename = os.path.basename(urlparse(url).path)
        filename = unquote(filename or "manual.pdf")
        safe_filename = filename.replace(" ", "_").replace("(", "").replace(")", "")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / safe_filename
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        # Validate content
        if not is_valid_pdf(path):
            print("❌ File downloaded but is NOT a valid PDF (likely a web page).")
            path.unlink(missing_ok=True)
            offer_open_in_browser(url)
            return "⚠️ Invalid PDF content"
        return str(path.resolve())
    except Exception as e:
        return f"⚠️ Download failed: {e}"

def offer_open_in_browser(url):
    answer = input("🌐 Open the manual link in your browser? (y/n): ").strip().lower()
    if answer == "y":
        webbrowser.open(url)
        print("🌐 Browser opened.")

def find_manual(make=None, model=None):
    while True:
        if not make:
            make = input("Enter the Make (e.g., Trane): ").strip()
        if not model:
            model = input("Enter the Model (e.g., RTU-1234): ").strip()

        query = f"{make} {model} operations and maintenance manual"
        print(f"\n🔎 Searching for: {query}\n")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=15))

        if not results:
            msg = "❌ No results found."
            print(msg)
            retry = input("🔁 Try a different Make/Model? (y/n): ").lower()
            if retry == "y":
                make = model = None
                continue
            return msg

        scored = []
        for r in results:
            url = r.get("href") or r.get("url")
            title = r.get("title") or ""
            if not url:
                continue
            accessible, reason = is_accessible_url(url)
            if not accessible:
                continue
            score = file_score(title, make, model) + domain_score(url, make)
            scored.append((score, title, url))

        if not scored:
            for r in results:
                url = r.get("href") or r.get("url")
                title = r.get("title") or ""
                if not url:
                    continue
                accessible, reason = is_accessible_url(url)
                if not accessible:
                    print(f"⚠️ Closest result was blocked: {title}\n{reason}")
                    print(f"🔗 Raw URL: {url}")
                    retry = input("🔁 Try a different Make/Model? (y/n): ").lower()
                    if retry == "y":
                        make = model = None
                        continue
                    return f"⚠️ No accessible manuals found. Exiting."
            print("❌ No accessible manuals found.")
            return "❌ No accessible manuals found."

        scored.sort(reverse=True)
        best_score, best_title, best_url = scored[0]
        close_match = best_score > 0.5

        print(f"✅ Best match: {best_title}\n🔗 {best_url}\n")

        if close_match:
            confirm = input("📥 Download this manual? (y/n): ").lower()
            if confirm == "y":
                saved = download_file(best_url)
                if saved.startswith("⚠️"):
                    retry = input("🔁 Try a different Make/Model? (y/n): ").lower()
                    if retry == "y":
                        make = model = None
                        continue
                    return saved
                print(f"✅ File saved to: {saved}")
                return saved
            else:
                print("📎 Here's the link to check it yourself:")
                print(best_url)
                offer_open_in_browser(best_url)
                return best_url
        else:
            print("⚠️ Could not find an exact match, but this might help:")
            print(best_url)
            offer_open_in_browser(best_url)
            return best_url

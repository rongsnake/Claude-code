#!/usr/bin/env python3
"""Fetch Risk Books PDFs you are entitled to, file them on the PiNAS, sync to Drive.

Run this ON YOUR OWN MACHINE / THE PI — not in cloud CI: risk.net is
subscriber-gated and needs your logged-in browser cookies, and the NAS lives
on your LAN.

Setup (once):
  1. Export risk.net cookies from the logged-in browser to Netscape format
     ("Get cookies.txt" extension or equivalent) -> riskbooks/cookies.txt
  2. pip install requests beautifulsoup4
  3. Optional Drive leg: rclone config   (create a remote, e.g. "gdrive")

Usage:
  python3 fetch_riskbooks.py --wave 1                          # banking Tier-1 core first
  python3 fetch_riskbooks.py --wave 1 2                        # banking + all credit & regulatory
  python3 fetch_riskbooks.py --bank-model                      # whole 49-book banking-model set (waves 1-3)
  python3 fetch_riskbooks.py --regime insurance               # the 8-book Solvency II set
  python3 fetch_riskbooks.py --bank-model --dest /mnt/pinas/RiskBooks --drive gdrive:RiskBooks

Regimes are filed in separate top-level folders under <dest> (and on Drive):
"Banking" and "Insurance (Solvency II)" — two distinct prudential regimes.

Downloads land under <dest>/<Tier N - Theme>/<Book Title>/, one PDF per
chapter/file found, with a manifest.csv logging every fetch. Re-runs skip
files already present. If a book page yields no PDF links the manifest says
so — the page layout differs per title, so check one such URL in a browser
and adjust PDF_LINK_HINTS below.
"""
import argparse, csv, os, re, sys, time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from http.cookiejar import MozillaCookieJar

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux aarch64) personal-archive/1.0"}
# href fragments that mark a downloadable asset on risk.net book pages
PDF_LINK_HINTS = (".pdf", "/system/files/", "/download", "attachment")

def safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', " ", name).strip()[:150]

REGIME_FOLDER = {"Banking": "Banking", "Insurance": "Insurance (Solvency II)"}

def load_plan(regime, waves):
    """Load the download plan, keeping rows in the chosen regime whose wave is
    in `waves`. Falls back to the older mapped CSV if the plan is absent."""
    plan = HERE / "RiskBooks_download_plan.csv"
    path = plan if plan.exists() else (HERE / "RiskBooks_mapped.csv")
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("regime") and r["regime"] != regime:
                continue
            w = r.get("wave") or ""
            if w.isdigit() and int(w) in waves:
                out.append(r)
    out.sort(key=lambda r: int(r["wave"]))
    return out

def session_with_cookies():
    s = requests.Session()
    s.headers.update(UA)
    jar_path = HERE / "cookies.txt"
    if not jar_path.exists():
        sys.exit("cookies.txt missing — export your logged-in risk.net cookies first (see docstring).")
    jar = MozillaCookieJar(str(jar_path))
    jar.load(ignore_discard=True, ignore_expires=True)
    s.cookies = jar
    return s

def pdf_links(html, base):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(h in href.lower() for h in PDF_LINK_HINTS):
            out.append((a.get_text(" ", strip=True) or "download", urljoin(base, href)))
    # de-dup preserving order
    seen, uniq = set(), []
    for label, url in out:
        if url not in seen:
            seen.add(url); uniq.append((label, url))
    return uniq

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", choices=["banking", "insurance"], default="banking",
                    help="prudential regime to fetch; filed in its own folder. Default: banking")
    ap.add_argument("--wave", nargs="+", type=int, default=[1],
                    help="banking waves to fetch (1=Tier-1 core, 2=credit+regulatory, 3=rest of banking model). Default: 1")
    ap.add_argument("--bank-model", action="store_true",
                    help="fetch the whole banking-model set (waves 1, 2 and 3)")
    ap.add_argument("--dest", default="/mnt/pinas/RiskBooks", help="NAS-mounted destination root")
    ap.add_argument("--drive", default="", help="rclone remote:path for the Google Drive leg (optional)")
    ap.add_argument("--delay", type=float, default=5.0, help="seconds between requests (be polite)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    regime = "Insurance" if args.regime == "insurance" else "Banking"
    if regime == "Insurance":
        waves = {1}
    else:
        waves = {1, 2, 3} if args.bank_model else set(args.wave)
    books = load_plan(regime, waves)
    regime_root = dest / REGIME_FOLDER[regime]
    print(f"{len(books)} books in regime {regime}, wave(s) {sorted(waves)} -> {regime_root}")
    dest = Path(args.dest)
    s = session_with_cookies()
    manifest = HERE / "manifest.csv"
    new_manifest = not manifest.exists()
    with open(manifest, "a", newline="") as mf:
        mw = csv.writer(mf)
        if new_manifest:
            mw.writerow(["ts", "wave", "title", "asset_label", "url", "path", "status"])
        for b in books:
            folder = regime_root / safe(f"Wave {b['wave']} - {b['theme']}") / safe(b["title"])
            print(f"\n== {b['title']}")
            try:
                r = s.get(b["url"], timeout=60)
                r.raise_for_status()
            except Exception as e:
                print(f"   page fetch failed: {e}")
                mw.writerow([time.strftime("%F %T"), b["wave"], b["title"], "", b["url"], "", f"page-error: {e}"])
                continue
            links = pdf_links(r.text, r.url)
            if not links:
                print("   no PDF links found on page — layout may differ, inspect in browser")
                mw.writerow([time.strftime("%F %T"), b["wave"], b["title"], "", b["url"], "", "no-pdf-links"])
                continue
            for label, url in links:
                fname = safe(label) or "download"
                if not fname.lower().endswith(".pdf"):
                    fname += ".pdf"
                out = folder / fname
                if out.exists():
                    print(f"   have {fname}")
                    continue
                if args.dry_run:
                    print(f"   would fetch {url} -> {out}")
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                try:
                    with s.get(url, stream=True, timeout=120) as dl:
                        dl.raise_for_status()
                        ct = dl.headers.get("content-type", "")
                        if "html" in ct:
                            mw.writerow([time.strftime("%F %T"), b["wave"], b["title"], label, url, "", "got-html-not-pdf (login?)"])
                            print(f"   {label}: got HTML back, not a PDF — cookie expired or not entitled")
                            continue
                        with open(out, "wb") as fh:
                            for chunk in dl.iter_content(1 << 16):
                                fh.write(chunk)
                    print(f"   saved {out.name} ({out.stat().st_size//1024} KB)")
                    mw.writerow([time.strftime("%F %T"), b["wave"], b["title"], label, url, str(out), "ok"])
                except Exception as e:
                    print(f"   {label}: {e}")
                    mw.writerow([time.strftime("%F %T"), b["wave"], b["title"], label, url, "", f"error: {e}"])
                time.sleep(args.delay)
            time.sleep(args.delay)

    if args.drive and not args.dry_run:
        sub = REGIME_FOLDER[regime]
        print(f"\nSyncing {regime_root} -> {args.drive}/{sub} via rclone …")
        os.system(f'rclone copy "{regime_root}" "{args.drive}/{sub}" --progress')

if __name__ == "__main__":
    main()

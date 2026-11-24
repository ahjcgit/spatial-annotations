#!/usr/bin/env python3
"""Browser checks for the static pilot dashboard, with preserved local screenshots."""

import argparse
import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8029/dashboard/")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}, device_scale_factor=1
        )
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.url)
        expect(page.locator("#load-error")).to_be_hidden()
        expect(page.locator("#integrity")).to_contain_text("81 archive files")
        expect(page.locator("#audit-count")).to_contain_text("257 / 257")
        expect(page.locator("#trial-select option")).to_have_count(13)
        checks.append("Archive inventory and 257 audit checks rendered")
        expect(page.locator(".timing-row")).to_have_count(6)
        page.locator("#timing-filter").select_option("no_labels")
        expect(page.locator(".timing-row")).to_have_count(2)
        page.locator("#timing-filter").select_option("two_labels")
        expect(page.locator(".timing-row")).to_have_count(4)
        page.locator("#timing-filter").select_option("all")
        checks.append("Timing filters separate two-label and no-label cases")
        page.locator("#trial-filter").select_option("failed")
        expect(page.locator("#trial-select option")).to_have_count(3)
        expect(page.locator("#source-missing")).to_contain_text("No source image")
        page.locator("#trial-select").select_option("large-text/trial-03")
        expect(page.locator("#trial-explanation")).to_contain_text("source_expired")
        expect(page.locator("#trial-metrics")).to_contain_text("137.71 s")
        page.locator("#trial-filter").select_option("review_only")
        expect(page.locator("#trial-select option")).to_have_count(4)
        page.locator("#trial-select").select_option("qualitative-baseline/trial-03")
        expect(page.locator("#labels")).to_contain_text("uncertain")
        expect(page.locator("#display-figure")).to_be_hidden()
        page.locator("#show-boxes").uncheck()
        expect(page.locator("#boxes")).to_be_hidden()
        page.locator("#show-boxes").check()
        checks.append(
            "Failure, image-only and uncertain proposals retain distinct states"
        )
        page.locator("#trial-filter").select_option("all")
        page.locator("#trial-select").select_option("large-text/trial-02")
        expect(page.locator("#expiry")).to_contain_text("unresolved")
        page.locator("#next-trial").click()
        expect(page.locator("#trial-select")).to_have_value("large-text/trial-03")
        page.locator("#previous").click()
        expect(page.locator("#trial-select")).to_have_value("large-text/trial-02")
        checks.append("Trial navigation and unresolved expiry state")
        data = page.evaluate("window.PILOT_DATA")
        links = {f["url"] for t in data["trials"] for f in t["files"]}
        links.update(data["links"].values())
        links.update(
            ["analysis.json", "trials.csv", "dashboard.css", "dashboard.js", "data.js"]
        )
        for link in sorted(links):
            response = page.request.get(urljoin(args.url, link))
            assert response.status == 200, (link, response.status)
        checks.append(f"All {len(links)} referenced local files return HTTP 200")
        page.locator("#trial-select").select_option("large-text/trial-04")
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(args.out / "desktop.png"), full_page=True)
        page.screenshot(path=str(args.out / "desktop-top.png"))
        page.locator("#trials").evaluate("el => el.scrollIntoView({block:'start'})")
        page.screenshot(path=str(args.out / "desktop-trials.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("window.scrollTo(0,0)")
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        for selector in ("#findings-table", "#failure-table"):
            assert page.locator(selector).evaluate(
                "table => table.scrollWidth <= window.innerWidth - 32"
            )
            assert page.locator(selector + " tbody tr").first.evaluate(
                "row => getComputedStyle(row).display === 'block'"
            )
        page.screenshot(path=str(args.out / "mobile.png"), full_page=True)
        page.screenshot(path=str(args.out / "mobile-top.png"))
        page.locator("#gaps").evaluate("el => el.scrollIntoView({block:'start'})")
        page.screenshot(path=str(args.out / "mobile-gaps.png"))
        checks.append("390px responsive layout has no horizontal page overflow")
        assert not errors, errors
        browser.close()
    (args.out / "results.json").write_text(
        json.dumps({"checks": checks, "page_errors": errors}, indent=2) + "\n"
    )
    print(f"PASS: {len(checks)} browser checks")


if __name__ == "__main__":
    main()

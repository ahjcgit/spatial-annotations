#!/usr/bin/env python3
"""Browser validation. Session races use HTTP interception; backend ACLs have separate tests."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8026")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1320, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        expect(page.locator("#position")).to_contain_text("Frame 1 /")
        assert not page.locator("#evaluation").is_checked()
        expect(page.locator("#tracks")).not_to_contain_text("GT")
        page.locator("#run").select_option(
            label="H1 · Pass A · events · trial 1 · mock"
        )
        expect(page.locator("#tracks")).to_contain_text("Synthetic red")
        page.locator("#evaluation").check()
        expect(page.locator("#tracks")).to_contain_text("GT")
        page.locator("#next").click()
        expect(page.locator("#position")).to_contain_text("Frame 2 /")
        checks.append("run switching, frame controls, opt-in ground truth")
        page.screenshot(path=str(out / "desktop.png"), full_page=True)
        page.locator("#sequence").select_option("6")
        page.locator("#run").select_option(
            label="H4 · Pass A · events · trial 1 · mock"
        )
        page.locator("#scrubber").fill("7")
        page.locator("#scrubber").dispatch_event("input")
        expect(page.locator("#position")).to_contain_text("Frame 8 /")
        expect(page.locator("#tracks")).to_contain_text("unknown")
        expect(page.locator("#events")).to_contain_text("local")
        checks.append("abstentions and reasoning events")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(out / "mobile.png"), full_page=True)
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        checks.append("390px responsive layout without horizontal page overflow")
        page.locator("#sequence").select_option("0")
        page.locator("#run").select_option(
            label="H1 · Pass A · events · trial 1 · mock"
        )
        expect(page.locator("#position")).to_contain_text("Frame 1 /")
        page.locator("#play").click()
        expect(page.locator("#position")).to_contain_text("Frame 2 /")
        page.locator("#play").click()
        checks.append("playback start/pause")
        # Mock only the sign-in transport to test browser isolation without capturing real notes.
        page.route(
            "**/api/study",
            lambda route: route.fulfill(
                json={**route.fetch().json(), "annotations_enabled": True}
            ),
        )
        page.route(
            "**/api/session",
            lambda route: route.fulfill(
                json={"access_token": route.request.post_data_json["username"]}
            ),
        )
        held = []

        def notes(route):
            if route.request.headers.get("authorization") == "Bearer alice":
                held.append(route)
            else:
                route.fulfill(
                    json={
                        "notes": [
                            {
                                "visibility": "public",
                                "author_id": "bob",
                                "content": "BOB_PUBLIC_TEST",
                            }
                        ],
                        "limit": 100,
                    }
                )

        page.route("**/api/notes/**", notes)
        page.reload()
        expect(page.locator("#position")).to_contain_text("Frame 1 /")
        page.locator("#run").select_option(
            label="H1 · Pass A · events · trial 1 · mock"
        )
        page.locator("#username").fill("alice")
        page.locator("#password").fill("test-password")
        page.locator("#login button").click()
        expect(page.locator("#session")).to_contain_text("Signed in as alice")
        page.wait_for_timeout(100)
        assert held
        page.locator("#username").fill("bob")
        page.locator("#password").fill("test-password")
        page.locator("#login button").click()
        expect(page.locator("#notes")).to_contain_text("BOB_PUBLIC_TEST")
        for route in held:
            try:
                route.fulfill(
                    json={
                        "notes": [
                            {
                                "visibility": "private",
                                "author_id": "alice",
                                "content": "ALICE_PRIVATE_TEST",
                            }
                        ],
                        "limit": 100,
                    }
                )
            except Exception:
                pass  # Aborted requests may already be closed.
        page.wait_for_timeout(100)
        expect(page.locator("#notes")).not_to_contain_text("ALICE_PRIVATE_TEST")
        page.locator("#signout").click()
        expect(page.locator("#notes")).to_be_empty()
        assert page.evaluate("localStorage.length") == 0
        checks.append(
            "mock delayed Alice response discarded after Bob login; sign-out clears notes; no token storage"
        )
        assert not errors, errors
        browser.close()
    (out / "results.json").write_text(
        json.dumps(
            {
                "environment": "headless Chromium, viewer via LAN; auth race transport mocked",
                "checks": checks,
                "page_errors": errors,
            },
            indent=2,
        )
    )
    print("PASS:", len(checks), "browser checks")


if __name__ == "__main__":
    main()

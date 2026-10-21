"""Offline tests: every network call is blocked, the model is a fake, WordPress is mocked.
Run: python -m unittest discover -s tests"""
import datetime as dt
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from seo_agent_team import autofix, llm, pipeline, rankmath, research, settings, team, wp, writer  # noqa: E402

SITE = "https://example.com"
KW = "website cost"


def article_md(kw=KW, site=SITE, sections=9, paras=3):
    """A draft that should pass Rank Math: ~2,700 words, keyword ~1.2%, three keyword headings, links, markers."""
    filler = ("Most owners start with a simple question about budget, then find the real work is in planning the "
              "pages, the words and the photos before anyone writes code. A clear brief saves weeks later, and it "
              "keeps every quote you get comparable. Ask what is included, who owns the site afterwards, and what "
              "happens when you want a change next year. Small details like hosting, email and backups add up over "
              "time, so write them down early and check them against each quote you receive this month.")
    out = [f"The {kw} question comes up early for every small firm. {filler}", "[TOC]"]
    for s in range(sections):
        title = f"{kw.capitalize()} part {s + 1}" if s < 3 else f"Planning step {s + 1}"
        out.append(f"## {title}")
        for p in range(paras):
            out.append(f"Here the {kw} matters again. {filler}")
        if s in (1, 4, 7):
            out.append(f"[IMAGE {(s - 1) // 3 + 1}: A simple chart about {kw}]")
    out.append(f"Read [our pricing]({site}/pricing/) and [our process]({site}/process/), and the "
               f"[official guidance](https://www.gov.uk/guidance) too.")
    return "\n\n".join(out)


def article(**kw):
    a = {"focus_keyword": KW, "title": "Website cost: a guide", "seo_title": "Website cost: 7 Proven Honest Tips 2026",
         "meta": "Website cost explained for small businesses: what you pay for, what to avoid and how to compare "
                 "quotes without surprises later on.", "slug": "website-cost",
         "markdown": article_md(), "featured": {"headline": "What a website costs"},
         "images": [{"n": n, "alt": f"{KW} chart {n}", "kind": k, "title": "t", "items": [{"label": "a", "value": 3},
                                                                                          {"label": "b", "value": 5}]}
                    for n, k in ((1, "steps"), (2, "bars"), (3, "checklist"))]}
    a.update(kw)
    a["alts"] = [i["alt"] for i in a["images"]]
    return a


def no_network(*a, **k):
    raise AssertionError("network call in a test")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(settings, "DATA_DIR", self.tmp),
                        mock.patch.object(settings, "SITE_URL", SITE),
                        mock.patch.object(settings, "BING_KEY", ""),
                        mock.patch.object(settings, "GSC_KEY_FILE", ""),
                        mock.patch.object(requests, "request", no_network),
                        mock.patch.object(requests, "get", no_network),
                        mock.patch.object(requests, "post", no_network)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        llm.backend = None
        pipeline.approve = pipeline.default_approve


class RankMathTest(Base):
    def test_good_draft_scores_95_plus(self):
        r = rankmath.check(article(), set(), "example.com")
        self.assertGreaterEqual(r["score"], 95, r["failed"])
        self.assertNotIn("density", r["failed"])

    def test_misses_are_named_with_hints(self):
        r = rankmath.check(article(markdown="Too short about nothing."), set(), "example.com")
        self.assertLess(r["score"], 60)
        self.assertIn("length", r["failed"])
        self.assertTrue(any("2,500" in h for h in r["hints"]))

    def test_used_keyword_fails(self):
        self.assertIn("unique_kw", rankmath.check(article(), {KW}, "example.com")["failed"])


class ResearchTest(Base):
    def test_facts_kept_only_when_the_page_says_so(self):
        pages = {"https://a.example/x": "In 2026 the average small business website cost £2,400 according to the survey."}
        good = {"url": "https://a.example/x", "fact": "Average cost was £2,400 in 2026.",
                "quote": "the average small business website cost £2,400 according to the survey"}
        self.assertTrue(research.verified(good, pages))
        self.assertFalse(research.verified({**good, "fact": "Average cost was £9,999."}, pages))   # number not on page
        self.assertFalse(research.verified({**good, "quote": "a sentence that is not on the page at all, no"}, pages))

    def test_used_keywords_round_trip(self):
        research.mark_used("Website Cost ")
        self.assertEqual(research.used_keywords(), {"website cost"})


class AutofixTest(Base):
    def test_mechanical_fixes_the_rule_based_checks(self):
        md = "Intro paragraph with nothing in it.\n\n## Why it matters\n\nText.\n\n## Planning\n\nText.\n\n## Costs\n\nText."
        a = autofix.mechanical(article(seo_title="A title", meta="", markdown=md),
                               [{"title": "Pricing", "link": f"{SITE}/pricing/", "kind": "page"},
                                {"title": "Blog", "link": f"{SITE}/blog/", "kind": "page"}],
                               [{"source_name": "Source", "url": "https://a.example/x", "fact": "f"}])
        self.assertTrue(a["seo_title"].lower().startswith(KW))
        self.assertIn(KW, a["meta"].lower())
        self.assertIn("[TOC]", a["markdown"])
        self.assertEqual(sum(KW in h.lower() for h in a["markdown"].split("\n") if h.startswith("## ")), 3)
        self.assertIn(f"{SITE}/pricing/", a["markdown"])
        self.assertIn("## Sources", a["markdown"])


class LLMTest(Base):
    def test_waits_out_a_rate_limit_then_answers(self):
        busy = mock.Mock(status_code=429, headers={"retry-after": "1"}, text="slow down")
        ok = mock.Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": "<think>x</think>Hi"}}]})
        with mock.patch.object(requests, "post", side_effect=[busy, ok]), mock.patch.object(llm.time, "sleep") as s:
            self.assertEqual(llm.call("s", "u"), "Hi")
        s.assert_called_once_with(1.0)

    def test_daily_limit_fails_fast(self):
        busy = mock.Mock(status_code=429, headers={"retry-after": "3600"}, text="per day")
        with mock.patch.object(requests, "post", return_value=busy):
            with self.assertRaises(llm.LLMError):
                llm.call("s", "u")

    def test_parse_json(self):
        self.assertEqual(llm.parse_json('Sure!\n```json\n{"a": [1]}\n```'), {"a": [1]})


class PipelineTest(Base):
    def _reply(self, a):
        head = {k: a[k] for k in ("title", "seo_title", "meta", "slug", "featured", "images")}
        return "```json\n" + json.dumps(head) + "\n```\n" + writer.SPLIT + "\n" + a["markdown"]

    def _run(self, a, rank_math_saved=True):
        llm.backend = lambda s, u, m, t: self._reply(a)
        held = []
        pipeline.approve = held.append
        ids = iter(range(100, 200))
        with mock.patch.object(wp, "site_links", return_value=[]), \
                mock.patch.object(research, "facts", return_value=[]), \
                mock.patch.object(research, "link_ok", return_value=True), \
                mock.patch.object(wp, "upload_image", side_effect=lambda p, alt, title="": {"id": next(ids), "url": f"{SITE}/{p.name}", "alt": alt}), \
                mock.patch.object(wp, "save_post", return_value={"id": 7, "link": None, "status": "draft"}), \
                mock.patch.object(wp, "set_rank_math", return_value=rank_math_saved), \
                mock.patch.object(wp, "publish", return_value={"id": 7, "link": f"{SITE}/website-cost/", "status": "publish"}) as pub:
            state = pipeline.write({"focus_keyword": KW, "title": "t"})
        return state, held, pub

    def test_95_plus_goes_live_and_is_indexed(self):
        state, held, pub = self._run(article())
        self.assertEqual(state["status"], "published")
        pub.assert_called_once()
        self.assertEqual(held, [])
        self.assertIn(f"{SITE}/website-cost/", team.load()["index"])
        self.assertEqual(pipeline.published()[0]["keyword"], KW)
        self.assertTrue(Path(state["preview_file"]).exists())

    def test_under_95_waits_for_a_human(self):
        a = article()
        a["markdown"] = a["markdown"].replace("[TOC]", "").replace("](https://www.gov.uk/guidance)", "]")
        with mock.patch.object(autofix, "mechanical", side_effect=lambda a, *x: a):   # leave the misses in place
            state, held, pub = self._run(a)
        pub.assert_not_called()
        self.assertEqual(len(held), 1)
        self.assertLess(state["check"]["score"], 95)

    def test_rank_math_boxes_not_saved_means_no_auto_publish(self):
        state, held, pub = self._run(article(), rank_math_saved=False)
        pub.assert_not_called()
        self.assertEqual(len(held), 1)


class TeamTest(Base):
    def test_bing_gets_the_url(self):
        ok = mock.Mock(ok=True)
        with mock.patch.object(settings, "BING_KEY", "k"), mock.patch.object(requests, "post", return_value=ok) as post:
            out = team.submit(f"{SITE}/a/")
        self.assertEqual(out["bing"], "submitted")
        self.assertEqual(post.call_args.kwargs["json"]["urlList"], [f"{SITE}/a/"])

    def test_refresher_picks_the_page_two_article_with_most_impressions(self):
        old = (dt.datetime.now() - dt.timedelta(days=40)).isoformat()
        arts = [{"url": "u1", "published": old, "google": {"impressions": 100, "position": 12}},
                {"url": "u2", "published": old, "google": {"impressions": 300, "position": 15}},
                {"url": "u3", "published": old, "google": {"impressions": 900, "position": 3}},      # already page 1
                {"url": "u4", "published": dt.datetime.now().isoformat(), "google": {"impressions": 999, "position": 10}}]
        self.assertEqual(team.pick_refresh({"articles": arts}, {})["url"], "u2")
        self.assertEqual(team.pick_refresh({"articles": arts}, {"refreshed": {"u2": time.time()}})["url"], "u1")

    def test_daily_routine_follows_the_days(self):
        with mock.patch.object(team, "track", return_value={"articles": []}), \
                mock.patch.object(team, "write_next", return_value="wrote") as w, \
                mock.patch.object(team, "refresh_one", side_effect=RuntimeError("boom")) as r, \
                mock.patch.object(settings, "WRITE_DAYS", ["mon"]), mock.patch.object(settings, "REFRESH_DAY", "sat"):
            team.run(dt.date(2026, 10, 19))   # a Monday
            sat = team.run(dt.date(2026, 10, 24))
        w.assert_called_once()
        r.assert_called_once()
        self.assertIn("[refresh] failed: boom", sat)   # one job failing doesn't stop the others


if __name__ == "__main__":
    unittest.main()

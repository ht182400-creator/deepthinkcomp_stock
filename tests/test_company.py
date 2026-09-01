# -*- coding: utf-8 -*-
"""公司综合数据源单元测试：announcements / finance / holder_num（mock http_get，无网络）。"""
import unittest
from unittest.mock import patch

from tests.helpers import FakeResponse


# 公告 mock body
def _ann_body():
    return {
        "data": {
            "list": [
                {"art_code": "AN202607171827064564", "title": "贵州茅台:贵州茅台重大事项公告",
                 "notice_date": "2026-07-18 00:00:00"},
                {"art_code": "AN202606211823708334", "title": "贵州茅台:贵州茅台2025年年度权益分派",
                 "notice_date": "2026-06-22 00:00:00"},
            ],
            "page_index": 1, "page_size": 10, "total_hits": 2,
        }
    }


def _fin_body():
    return {
        "success": True,
        "result": {
            "data": [{
                "REPORT_DATE": "2026-03-31 00:00:00",
                "REPORT_DATE_NAME": "2026一季报",
                "TOTALOPERATEREVE": 54702912385.23,
                "PARENTNETPROFIT": 27242512886.45,
                "TOTALOPERATEREVETZ": 6.336009277123,
                "PARENTNETPROFITTZ": 1.471418294983,
                "EPSJB": 21.76,
                "ROEJQ": 10.57,
            }],
        },
    }


def _holder_body():
    return {
        "gdrs": [
            {"END_DATE": "2026-03-31 00:00:00", "HOLDER_TOTAL_NUM": 243159,
             "TOTAL_NUM_RATIO": -4.9759, "AVG_FREE_SHARES": 5150},
            {"END_DATE": "2025-12-31 00:00:00", "HOLDER_TOTAL_NUM": 255892,
             "TOTAL_NUM_RATIO": 7.2868, "AVG_FREE_SHARES": 4893},
        ]
    }


def _margin_body():
    return {"success": True, "result": {"data": [{
        "DATE": "2026-08-12 00:00:00", "SCODE": "600519", "SECNAME": "贵州茅台",
        "RZYE": 17498563427, "RQYE": 125179687, "RZRQYE": 17623743114, "RZYEZB": 1.04228868,
    }]}}


def _lhb_body():
    return {"success": True, "result": {"data": [{
        "TRADE_DATE": "2013-01-28 00:00:00", "SECURITY_CODE": "600519",
        "BILLBOARD_DEAL_AMT": 987176704.46, "EXPLAIN": "5家机构卖出，成功率48.38%",
        "CHANGE_RATE": -5.581,
    }]}}


def _company_body():
    return {"jbzl": [{
        "ORG_NAME": "贵州茅台酒股份有限公司", "EM2016": "食品饮料-饮料-白酒",
        "TRADE_MARKET": "上海证券交易所", "INDUSTRYCSRC1": "制造业-酒、饮料和精制茶制造业",
    }]}


def _forecast_body():
    return {"success": True, "result": {"data": [{
        "SECURITY_CODE": "600519", "RATING_ORG_NUM": 44, "RATING_BUY_NUM": 37, "RATING_ADD_NUM": 7,
        "YEAR1": 2025, "YEAR_MARK1": "A", "EPS1": 65.85,
        "YEAR2": 2026, "YEAR_MARK2": "E", "EPS2": 68.73,
        "YEAR3": 2027, "YEAR_MARK3": "E", "EPS3": 72.48,
        "YEAR4": 2028, "YEAR_MARK4": "E", "EPS4": 76.04,
    }]}}


def _ann_content_body():
    """公告正文接口 mock（含 HTML 标签，验证去标签 + 提取 PDF 链接）。"""
    return {"success": True, "data": {
        "art_code": "AN202607171827064564",
        "notice_title": "贵州茅台:贵州茅台重大事项公告",
        "notice_date": "2026-07-18 00:00:00",
        "notice_content": "<p>证券代码：600519</p><p>重大事项公告</p><p>本公司董事会及全体董事保证...</p>",
        "attach_url": "https://pdf.dfcfw.com/pdf/H2_AN202607171827064564_1.pdf",
    }}


class TestCompanySource(unittest.TestCase):

    def _patch(self, fake):
        patcher = patch("sources.company.http_get", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_announcement_content_parse(self):
        """公告正文：去 HTML 标签 + 提取标题/日期/PDF 链接。"""
        from sources.company import get_announcement_content
        self._patch(FakeResponse(json_data=_ann_content_body()))
        d = get_announcement_content("AN202607171827064564")
        self.assertEqual(d["title"], "贵州茅台:贵州茅台重大事项公告")
        self.assertEqual(d["date"], "2026-07-18")
        self.assertIn("证券代码", d["content"])
        self.assertNotIn("<p>", d["content"])   # HTML 标签已去除
        self.assertIn("pdf.dfcfw.com", d["pdf_url"])

    def test_announcement_content_empty(self):
        """公告正文空 data → 返回空 dict（前端隐藏内容）。"""
        from sources.company import get_announcement_content
        self._patch(FakeResponse(json_data={"success": True, "data": {}}))
        self.assertEqual(get_announcement_content("ANxxx"), {})

    def test_announcements_parse(self):
        from sources.company import get_announcements
        self._patch(FakeResponse(json_data=_ann_body()))
        out = get_announcements("sh600519", limit=2)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["date"], "2026-07-18")
        self.assertIn("重大事项", out[0]["title"])

    def test_finance_parse(self):
        from sources.company import get_finance_summary
        self._patch(FakeResponse(json_data=_fin_body()))
        d = get_finance_summary("sh600519")
        self.assertEqual(d["report_type"], "2026一季报")
        self.assertEqual(d["revenue"], 54702912385.23)
        self.assertEqual(d["net_profit"], 27242512886.45)
        self.assertEqual(d["eps"], 21.76)
        self.assertEqual(d["roe"], 10.57)
        self.assertEqual(d["yoy_revenue"], 6.336009277123)

    def test_holder_num_parse(self):
        from sources.company import get_holder_num
        self._patch(FakeResponse(json_data=_holder_body()))
        out = get_holder_num("sh600519", limit=2)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["total"], 243159)
        self.assertEqual(out[0]["change_pct"], -4.9759)
        self.assertEqual(out[0]["date"], "2026-03-31")

    def test_secucode_market_prefix(self):
        """_secucode 必须正确判断 sh/sz/bj 市场前缀，不受 pure_code 剥前缀影响。"""
        from sources.company import _secucode
        self.assertEqual(_secucode("sh600519"), "600519.SH")
        self.assertEqual(_secucode("sz000858"), "000858.SZ")
        self.assertEqual(_secucode("bj830799"), "830799.BJ")

    def test_finance_empty_on_failure(self):
        from sources.company import get_finance_summary
        self._patch(FakeResponse(json_data={"success": False, "code": 9501, "message": "fail"}))
        self.assertEqual(get_finance_summary("sh600519"), {})

    def test_margin_parse(self):
        from sources.company import get_margin
        self._patch(FakeResponse(json_data=_margin_body()))
        out = get_margin("sh600519", limit=1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["rzye"], 17498563427)
        self.assertEqual(out[0]["rqye"], 125179687)
        self.assertEqual(out[0]["rzrqye"], 17623743114)
        self.assertEqual(out[0]["rzyezb"], 1.04228868)

    def test_lhb_parse(self):
        from sources.company import get_lhb
        self._patch(FakeResponse(json_data=_lhb_body()))
        out = get_lhb("sh600519", limit=1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["amount"], 987176704.46)
        self.assertIn("机构卖出", out[0]["explain"])

    def test_company_profile_parse(self):
        from sources.company import get_company_profile
        self._patch(FakeResponse(json_data=_company_body()))
        d = get_company_profile("sh600519")
        self.assertEqual(d["org_name"], "贵州茅台酒股份有限公司")
        self.assertEqual(d["industry"], "食品饮料-饮料-白酒")
        self.assertEqual(d["market"], "上海证券交易所")

    def test_forecast_parse(self):
        from sources.company import get_forecast
        self._patch(FakeResponse(json_data=_forecast_body()))
        d = get_forecast("sh600519")
        self.assertEqual(d["org_num"], 44)
        self.assertEqual(d["buy_num"], 37)
        self.assertEqual(d["eps_years"][1]["year"], 2026)
        self.assertEqual(d["eps_years"][1]["mark"], "E")

    def test_sentiment_fund_based(self):
        """多空情绪：基于分钟级主力资金正负占比。"""
        from services.quote_service import _compute_sentiment
        # 30 分钟：20 正 / 10 负 → 多头 66.7%
        fund = [{"main": 1000000 if i % 3 else -500000} for i in range(30)]
        d = _compute_sentiment(fund)
        self.assertEqual(d["days"], 30)
        self.assertAlmostEqual(d["bull_pct"], 66.7, delta=0.1)
        self.assertAlmostEqual(d["bear_pct"], 33.3, delta=0.1)
        # 数据不足返回空
        self.assertEqual(_compute_sentiment([{"main": 1}]), {})

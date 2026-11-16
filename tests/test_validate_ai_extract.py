import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("validate_ai_extract", ROOT / "scripts" / "validate_ai_extract.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

URL = "https://www.city.example.jp/a.pdf"
TEXTS = {URL: mod.norm("第1多目的運動場 ★8 グラウンド・ゴルフ体験 グラウンド・ゴルフ協会\n令和8年4月29日(水)8:30~正午\n連絡先 090-1234-5678")}


def doc(**row):
    base = {"municipality_code": "11239", "documents": [{"pdf_url": URL, "title": "t"}], "events": [dict({"event_name": "x", "date_start": "2026-04-29", "period": "期間内", "evidence": "グラウンド・ゴルフ体験 グラウンド・ゴルフ協会", "pdf_url": URL}, **row)]}
    return base


def test_valid_row_passes():
    assert mod.validate(doc(), TEXTS) == []


def test_evidence_must_exist_in_the_text_verbatim():
    p = mod.validate(doc(evidence="10m、20m、30m各コースでボールを打つ"), TEXTS)
    assert len(p) == 1 and "根拠が本文にそのままは無い" in p[0]
    assert any("根拠(evidence)が空" in x for x in mod.validate(doc(evidence=""), TEXTS))


def test_missing_url_code_and_unknown_url():
    d = doc(pdf_url="")
    d["municipality_code"] = ""
    d["documents"][0]["pdf_url"] = ""
    p = " ".join(mod.validate(d, TEXTS))
    assert "municipality_code が空" in p and "documents: pdf_url が空" in p and "どの資料の行か分からない" in p
    assert "保存した本文に無い" in " ".join(mod.validate(doc(pdf_url="https://other.jp/z.pdf"), TEXTS))


def test_dates_and_period_and_personal_contacts():
    assert any("period が日付と合わない" in x for x in mod.validate(doc(period="期間外"), TEXTS))
    assert any("period が日付と合わない" in x for x in mod.validate(doc(date_start="2023-09-24", date_end="2023-09-24", period="期間内"), TEXTS))
    assert any("YYYY-MM-DD でない" in x for x in mod.validate(doc(date_start="2026/4/29"), TEXTS))
    assert any("携帯電話番号" in x for x in mod.validate(doc(contact_phone="090-1234-5678"), TEXTS))
    assert any("メールアドレス" in x for x in mod.validate(doc(contact_phone="a-b@smile.ocn.ne.jp"), TEXTS))
    assert mod.validate(doc(contact_phone="048-123-4567"), TEXTS) == []
    assert mod.validate(doc(date_start="", date_end="", period="日付不明"), TEXTS) == []


def test_load_texts_reads_saved_pdf_and_page_texts(tmp_path):
    from localgov_crawler import survey as sv
    m = {"code": "11239", "name": "坂戸市", "prefecture": "埼玉県"}
    for sub, key, rec in (("_pdftext", "pdfs", {"url": URL, "text": "グラウンド ゴルフ"}), ("_pagetext", "pages", {"url": "https://www.city.example.jp/p", "text": "施設名 | 住所"})):
        p = tmp_path / "grandgolf" / "r" / sub / "11" / "11239.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"municipality": m, "keyword": "grandgolf", "route": "r", key: [rec]}, ensure_ascii=False), encoding="utf-8")
    t = mod.load_texts(tmp_path, "grandgolf", ["r"], "11239")
    assert set(t) == {URL, "https://www.city.example.jp/p"} and t[URL] == "グラウンドゴルフ"
    assert mod.load_texts(tmp_path, "grandgolf", ["r"], "99999") == {}

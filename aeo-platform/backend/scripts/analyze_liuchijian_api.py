"""丽齿健 V2/V3/V4 三次 API 采集一致性分析脚本"""
import sqlite3
import json
import sys
from difflib import SequenceMatcher
from collections import defaultdict

DB_PATH = "specta_dev.db"

# Message IDs for v2, v3, v4
VERSION_IDS = {
    "v2": "ccfff71f52b94c878d81d0ae97f3b46e",
    "v3": "8a10a7536d704a259170b40d9560b15d",
    "v4": "3b383c52773d468eae4e2c250d6129b2",
}

PLATFORMS = ["豆包", "混元", "Kimi"]

BRAND_KEYWORDS = [
    "丽齿健", "安利", "Amway", "云南白药", "舒适达", "Sensodyne", "高露洁", "Colgate",
    "佳洁士", "Crest", "黑人", "DARLIE", "中华", "冷酸灵", "舒克", "Saky",
    "狮王", "LION", "花王", "KAO", "欧乐B", "Oral-B", "飞利浦", "Philips",
    "皓乐齿", "参半", "NYSCPS", "牙博士", "片仔癀", "两面针", "纳美",
    "惠百施", "EBiSU", "小林制药", "elmex", "贝亲", "Pigeon",
    "好来", "usmile", "素士", "SOOCAS", "奥乐V", "Oralove",
    "半诗彩", "olioli", "萌大夫", "Regenerate", "比那氏", "Propolinse",
    "舒冷清", "GUM", "黑妹", "田七", "蒲地蓝", "幽螺莎星",
    "parodontax", "益周适", "MARVIS", "Aesop",
]

PRODUCT_KEYWORDS = [
    "牙膏", "牙刷", "电动牙刷", "漱口水", "牙线", "牙贴", "美白牙贴",
    "冲牙器", "水牙线", "牙粉", "护龈", "抗敏", "美白", "防蛀",
    "含氟", "无氟", "益生菌", "酵素", "小苏打", "活性炭",
    "氨基酸", "烟酰胺", "生物活性玻璃", "羟基磷灰石", "氯己定",
    "白茶", "茶多酚", "木糖醇", "薄荷", "草本",
]

STANCE_MAP = {
    "推荐": ["推荐", "建议使用", "值得", "不错", "好用", "首选", "优选", "适合"],
    "不推荐": ["不推荐", "不建议", "慎用", "避免", "不适合", "智商税"],
    "视情况": ["因人而异", "看情况", "根据需求", "取决于", "具体情况"],
    "就医": ["就医", "看牙医", "口腔科", "牙周病", "医生"],
    "综合对比": ["对比", "比较", "各有", "优缺点", "区别"],
}


def extract_brands(text):
    found = set()
    lower = text.lower()
    for b in BRAND_KEYWORDS:
        if b.lower() in lower:
            found.add(b)
    return found


def extract_products(text):
    return {p for p in PRODUCT_KEYWORDS if p in text}


def extract_stances(text):
    found = set()
    for stance, kws in STANCE_MAP.items():
        for kw in kws:
            if kw in text:
                found.add(stance)
                break
    return found


def extract_urls(citations):
    urls = set()
    for ci in citations:
        if isinstance(ci, dict) and ci.get("url"):
            urls.add(ci["url"].rstrip("/"))
    return urls


def jaccard(s1, s2):
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def avg(lst):
    return sum(lst) / len(lst) if lst else 0


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Load data
    all_data = {}
    for ver, mid in VERSION_IDS.items():
        c.execute("SELECT output_data FROM messages WHERE id = ?", (mid,))
        raw = json.loads(c.fetchone()[0])
        all_data[ver] = raw.get("fetchResults", [])

    # Build structured data
    structured = {}
    for ver in ["v2", "v3", "v4"]:
        structured[ver] = {}
        for qi, r in enumerate(all_data[ver]):
            structured[ver][qi] = {}
            for pr in r.get("platform_results", []):
                pname = pr.get("platform_name", pr.get("platform", ""))
                if not pr.get("success", False):
                    continue
                answer = pr.get("answer", {})
                content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
                citations = pr.get("citations", [])
                structured[ver][qi][pname] = {
                    "content": content,
                    "brands": extract_brands(content),
                    "products": extract_products(content),
                    "stances": extract_stances(content),
                    "urls": extract_urls(citations),
                    "word_count": len(content),
                }

    pairs = [("v2", "v3"), ("v2", "v4"), ("v3", "v4")]

    print("=" * 80)
    print("丽齿健 V2/V3/V4 三次 API 采集一致性分析")
    print("=" * 80)

    # Per-pair stats
    for va, vb in pairs:
        print(f"\n### {va} <-> {vb}")
        header = f"{'平台':<8} {'对数':>4} {'文本':>8} {'引用':>8} {'品牌':>8} {'产品':>8} {'立场':>8} {'关键点':>8}"
        print(header)

        all_metrics = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}

        for platform in PLATFORMS:
            metrics = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}

            for qi in range(11):
                da = structured[va].get(qi, {}).get(platform)
                db = structured[vb].get(qi, {}).get(platform)
                if not da or not db:
                    continue

                ts = SequenceMatcher(None, da["content"], db["content"]).ratio()
                us = jaccard(da["urls"], db["urls"])
                bs = jaccard(da["brands"], db["brands"])
                ps = jaccard(da["products"], db["products"])
                ss = jaccard(da["stances"], db["stances"])
                ks = bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15

                for k, v in [("text", ts), ("url", us), ("brand", bs), ("product", ps), ("stance", ss), ("key", ks)]:
                    metrics[k].append(v)
                    all_metrics[k].append(v)

            n = len(metrics["text"])
            if n > 0:
                print(f"{platform:<8} {n:>4} {avg(metrics['text']):>7.1%} {avg(metrics['url']):>7.1%} {avg(metrics['brand']):>7.1%} {avg(metrics['product']):>7.1%} {avg(metrics['stance']):>7.1%} {avg(metrics['key']):>7.1%}")

        n = len(all_metrics["text"])
        print(f"{'全平台':<8} {n:>4} {avg(all_metrics['text']):>7.1%} {avg(all_metrics['url']):>7.1%} {avg(all_metrics['brand']):>7.1%} {avg(all_metrics['product']):>7.1%} {avg(all_metrics['stance']):>7.1%} {avg(all_metrics['key']):>7.1%}")

    # Grand averages
    print("\n" + "=" * 80)
    print("三版总均值")
    print("=" * 80)

    grand = {p: {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]} for p in PLATFORMS + ["全平台"]}

    for va, vb in pairs:
        for platform in PLATFORMS:
            for qi in range(11):
                da = structured[va].get(qi, {}).get(platform)
                db = structured[vb].get(qi, {}).get(platform)
                if not da or not db:
                    continue

                ts = SequenceMatcher(None, da["content"], db["content"]).ratio()
                us = jaccard(da["urls"], db["urls"])
                bs = jaccard(da["brands"], db["brands"])
                ps = jaccard(da["products"], db["products"])
                ss = jaccard(da["stances"], db["stances"])
                ks = bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15

                for k, v in [("text", ts), ("url", us), ("brand", bs), ("product", ps), ("stance", ss), ("key", ks)]:
                    grand[platform][k].append(v)
                    grand["全平台"][k].append(v)

    print(f"\n{'平台':<8} {'对数':>4} {'文本':>8} {'引用':>8} {'品牌':>8} {'产品':>8} {'立场':>8} {'关键点':>8}")
    for p in PLATFORMS + ["全平台"]:
        d = grand[p]
        n = len(d["text"])
        print(f"{p:<8} {n:>4} {avg(d['text']):>7.1%} {avg(d['url']):>7.1%} {avg(d['brand']):>7.1%} {avg(d['product']):>7.1%} {avg(d['stance']):>7.1%} {avg(d['key']):>7.1%}")

    # Brand frequency
    print("\n" + "=" * 80)
    print("品牌提及频次（三版合并, 33条/平台）")
    print("=" * 80)

    brand_freq = defaultdict(lambda: defaultdict(int))
    for ver in ["v2", "v3", "v4"]:
        for qi in range(11):
            for platform in PLATFORMS:
                d = structured[ver].get(qi, {}).get(platform)
                if not d:
                    continue
                for b in d["brands"]:
                    brand_freq[b][platform] += 1
                    brand_freq[b]["total"] += 1

    sorted_brands = sorted(brand_freq.items(), key=lambda x: x[1]["total"], reverse=True)
    print(f"\n{'品牌':<16} {'豆包':>6} {'混元':>6} {'Kimi':>6} {'总计':>6}")
    for brand, counts in sorted_brands[:25]:
        print(f"{brand:<16} {counts.get('豆包', 0):>6} {counts.get('混元', 0):>6} {counts.get('Kimi', 0):>6} {counts['total']:>6}")

    # 丽齿健 mention rate
    print("\n" + "=" * 80)
    print("丽齿健/安利品牌提及率（按版本×平台）")
    print("=" * 80)
    for ver in ["v2", "v3", "v4"]:
        for platform in PLATFORMS:
            mentioned = 0
            total = 0
            for qi in range(11):
                d = structured[ver].get(qi, {}).get(platform)
                if d:
                    total += 1
                    if "丽齿健" in d["brands"] or "安利" in d["brands"] or "Amway" in d["brands"]:
                        mentioned += 1
            if total > 0:
                print(f"  {ver} {platform:<6}: {mentioned}/{total} ({mentioned / total:.0%})")

    # Per-question variance analysis
    print("\n" + "=" * 80)
    print("问题级别方差分析（哪些问题一致性最高/最低）")
    print("=" * 80)

    q_texts = {qi: all_data["v2"][qi]["question_text"] for qi in range(11)}
    q_key_scores = defaultdict(list)

    for va, vb in pairs:
        for qi in range(11):
            for platform in PLATFORMS:
                da = structured[va].get(qi, {}).get(platform)
                db = structured[vb].get(qi, {}).get(platform)
                if not da or not db:
                    continue
                bs = jaccard(da["brands"], db["brands"])
                ps = jaccard(da["products"], db["products"])
                ss = jaccard(da["stances"], db["stances"])
                us = jaccard(da["urls"], db["urls"])
                ks = bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15
                q_key_scores[qi].append(ks)

    print(f"\n{'Q#':>3} {'关键点':>8} {'对数':>4}  问题")
    sorted_qs = sorted(q_key_scores.items(), key=lambda x: avg(x[1]), reverse=True)
    for qi, scores in sorted_qs:
        print(f"Q{qi + 1:>2} {avg(scores):>7.1%} {len(scores):>4}  {q_texts[qi][:50]}")

    conn.close()


if __name__ == "__main__":
    main()

"""丽齿健 V5 vs V7 Browser 采集一致性分析脚本"""
import sqlite3
import json
from difflib import SequenceMatcher
from collections import defaultdict

DB_PATH = "specta_dev.db"

VERSION_IDS = {
    "v5": "3d32794d04604ce1abf860bf5e3c567c",
    "v7": "a31cfd7dd034451f8c7d73e0d5560a92",
}

PLATFORMS = ["DeepSeek", "Kimi", "混元", "豆包"]

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
    for ver in ["v5", "v7"]:
        structured[ver] = {}
        for qi, r in enumerate(all_data[ver]):
            structured[ver][qi] = {}
            for pr in r.get("platform_results", []):
                pname = pr.get("platform_name", pr.get("platform", ""))
                if not pr.get("success", False):
                    structured[ver][qi][pname] = None  # Mark as failed
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

    print("=" * 80)
    print("丽齿健 V5 vs V7 Browser 采集一致性分析")
    print("=" * 80)

    # Success rate comparison
    print("\n### 采集成功率")
    print(f"{'平台':<10} {'v5':>8} {'v7':>8}")
    for platform in PLATFORMS:
        v5_success = sum(1 for qi in range(11) if structured["v5"].get(qi, {}).get(platform) is not None)
        v7_success = sum(1 for qi in range(11) if structured["v7"].get(qi, {}).get(platform) is not None)
        v5_total = sum(1 for qi in range(11) if platform in structured["v5"].get(qi, {}))
        v7_total = sum(1 for qi in range(11) if platform in structured["v7"].get(qi, {}))
        print(f"{platform:<10} {v5_success}/{v5_total:>2}     {v7_success}/{v7_total:>2}")

    # Pairwise comparison v5 vs v7
    print(f"\n### v5 <-> v7 一致性")
    header = f"{'平台':<10} {'对数':>4} {'文本':>8} {'引用':>8} {'品牌':>8} {'产品':>8} {'立场':>8} {'关键点':>8}"
    print(header)

    grand = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}

    platform_metrics = {}
    for platform in PLATFORMS:
        metrics = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}

        for qi in range(11):
            da = structured["v5"].get(qi, {}).get(platform)
            db = structured["v7"].get(qi, {}).get(platform)
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
                grand[k].append(v)

        platform_metrics[platform] = metrics
        n = len(metrics["text"])
        if n > 0:
            print(f"{platform:<10} {n:>4} {avg(metrics['text']):>7.1%} {avg(metrics['url']):>7.1%} {avg(metrics['brand']):>7.1%} {avg(metrics['product']):>7.1%} {avg(metrics['stance']):>7.1%} {avg(metrics['key']):>7.1%}")

    n = len(grand["text"])
    print(f"{'全平台':<10} {n:>4} {avg(grand['text']):>7.1%} {avg(grand['url']):>7.1%} {avg(grand['brand']):>7.1%} {avg(grand['product']):>7.1%} {avg(grand['stance']):>7.1%} {avg(grand['key']):>7.1%}")

    # Word count comparison
    print(f"\n### 回答字数对比")
    print(f"{'平台':<10} {'v5均值':>8} {'v7均值':>8} {'变化':>8}")
    for platform in PLATFORMS:
        v5_wc = []
        v7_wc = []
        for qi in range(11):
            da = structured["v5"].get(qi, {}).get(platform)
            db = structured["v7"].get(qi, {}).get(platform)
            if da:
                v5_wc.append(da["word_count"])
            if db:
                v7_wc.append(db["word_count"])
        if v5_wc and v7_wc:
            diff = avg(v7_wc) - avg(v5_wc)
            print(f"{platform:<10} {avg(v5_wc):>7.0f} {avg(v7_wc):>7.0f} {diff:>+7.0f}")

    # Brand frequency comparison
    print(f"\n### 品牌提及频次对比（v5 vs v7）")
    brand_freq = {"v5": defaultdict(lambda: defaultdict(int)), "v7": defaultdict(lambda: defaultdict(int))}
    for ver in ["v5", "v7"]:
        for qi in range(11):
            for platform in PLATFORMS:
                d = structured[ver].get(qi, {}).get(platform)
                if not d:
                    continue
                for b in d["brands"]:
                    brand_freq[ver][b][platform] += 1
                    brand_freq[ver][b]["total"] += 1

    all_brands = set(brand_freq["v5"].keys()) | set(brand_freq["v7"].keys())
    sorted_brands = sorted(all_brands, key=lambda b: brand_freq["v5"][b]["total"] + brand_freq["v7"][b]["total"], reverse=True)

    print(f"\n{'品牌':<16} {'v5总计':>6} {'v7总计':>6} {'变化':>6}")
    for brand in sorted_brands[:20]:
        v5t = brand_freq["v5"][brand]["total"]
        v7t = brand_freq["v7"][brand]["total"]
        diff = v7t - v5t
        print(f"{brand:<16} {v5t:>6} {v7t:>6} {diff:>+6}")

    # 丽齿健/安利 mention details
    print(f"\n### 丽齿健/安利提及详情")
    for ver in ["v5", "v7"]:
        print(f"\n{ver}:")
        for qi in range(11):
            q_text = all_data[ver][qi]["question_text"][:40]
            for platform in PLATFORMS:
                d = structured[ver].get(qi, {}).get(platform)
                if d and ("丽齿健" in d["brands"] or "安利" in d["brands"] or "Amway" in d["brands"]):
                    print(f"  Q{qi+1} {platform}: {q_text}...")

    # Per-question consistency
    print(f"\n### 问题级别一致性（v5 vs v7）")
    q_texts = {qi: all_data["v5"][qi]["question_text"] for qi in range(11)}
    q_scores = {}
    for qi in range(11):
        scores = []
        for platform in PLATFORMS:
            da = structured["v5"].get(qi, {}).get(platform)
            db = structured["v7"].get(qi, {}).get(platform)
            if not da or not db:
                continue
            bs = jaccard(da["brands"], db["brands"])
            ps = jaccard(da["products"], db["products"])
            ss = jaccard(da["stances"], db["stances"])
            us = jaccard(da["urls"], db["urls"])
            ks = bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15
            scores.append(ks)
        q_scores[qi] = scores

    print(f"\n{'Q#':>3} {'关键点':>8} {'对数':>4}  问题")
    sorted_qs = sorted(q_scores.items(), key=lambda x: avg(x[1]), reverse=True)
    for qi, scores in sorted_qs:
        print(f"Q{qi+1:>2} {avg(scores):>7.1%} {len(scores):>4}  {q_texts[qi][:50]}")

    # Cross-channel comparison: API avg vs Browser
    print(f"\n\n{'=' * 80}")
    print("API (v2/v3/v4 均值) vs Browser (v5↔v7) 通道对比")
    print("=" * 80)

    api_key = {"豆包": 53.8, "混元": 73.1, "Kimi": 52.7, "全平台": 59.9}
    browser_key = {}
    for platform in PLATFORMS:
        m = platform_metrics.get(platform, {}).get("key", [])
        if m:
            browser_key[platform] = avg(m) * 100
    browser_key["全平台"] = avg(grand["key"]) * 100

    print(f"\n{'平台':<10} {'API关键点':>10} {'Browser关键点':>13} {'差异':>8}")
    for p in ["豆包", "混元", "Kimi", "全平台"]:
        api_v = api_key.get(p, 0)
        br_v = browser_key.get(p, 0)
        if api_v and br_v:
            print(f"{p:<10} {api_v:>9.1f}% {br_v:>12.1f}% {br_v - api_v:>+7.1f}pp")

    # DeepSeek (browser only)
    ds_v = browser_key.get("DeepSeek", 0)
    if ds_v:
        print(f"{'DeepSeek':<10} {'N/A':>10} {ds_v:>12.1f}% {'(仅Browser)':>10}")

    # Citation comparison
    print(f"\n### 引用数量对比")
    print(f"{'平台':<10} {'v5引用':>8} {'v7引用':>8} {'变化':>8}")
    for platform in PLATFORMS:
        v5_cites = 0
        v7_cites = 0
        for qi in range(11):
            da = structured["v5"].get(qi, {}).get(platform)
            db = structured["v7"].get(qi, {}).get(platform)
            if da:
                v5_cites += len(da["urls"])
            if db:
                v7_cites += len(db["urls"])
        print(f"{platform:<10} {v5_cites:>8} {v7_cites:>8} {v7_cites - v5_cites:>+8}")

    conn.close()


if __name__ == "__main__":
    main()

"""丽齿健 V5 vs V7 Browser 逐题逐平台详细对比"""
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

    all_data = {}
    for ver, mid in VERSION_IDS.items():
        c.execute("SELECT output_data FROM messages WHERE id = ?", (mid,))
        raw = json.loads(c.fetchone()[0])
        all_data[ver] = raw.get("fetchResults", [])

    structured = {}
    for ver in ["v5", "v7"]:
        structured[ver] = {}
        for qi, r in enumerate(all_data[ver]):
            structured[ver][qi] = {}
            for pr in r.get("platform_results", []):
                pname = pr.get("platform_name", pr.get("platform", ""))
                if not pr.get("success", False):
                    structured[ver][qi][pname] = None
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

    q_texts = {qi: all_data["v5"][qi]["question_text"] for qi in range(11)}

    print("=" * 100)
    print("丽齿健 V5 vs V7 Browser 采集 — 纯 Browser 逐题逐平台详细对比")
    print("=" * 100)

    # ========== SECTION 1: 采集成功率 ==========
    print("\n## 1. 采集成功率")
    print(f"{'平台':<10} {'v5成功/总':>10} {'v7成功/总':>10}")
    total_v5_ok, total_v5_all, total_v7_ok, total_v7_all = 0, 0, 0, 0
    for platform in PLATFORMS:
        v5s = sum(1 for qi in range(11) if structured["v5"].get(qi, {}).get(platform) is not None)
        v5t = sum(1 for qi in range(11) if platform in structured["v5"].get(qi, {}))
        v7s = sum(1 for qi in range(11) if structured["v7"].get(qi, {}).get(platform) is not None)
        v7t = sum(1 for qi in range(11) if platform in structured["v7"].get(qi, {}))
        total_v5_ok += v5s; total_v5_all += v5t; total_v7_ok += v7s; total_v7_all += v7t
        print(f"{platform:<10} {v5s:>4}/{v5t:<4}     {v7s:>4}/{v7t:<4}")
    print(f"{'合计':<10} {total_v5_ok:>4}/{total_v5_all:<4}     {total_v7_ok:>4}/{total_v7_all:<4}")

    # ========== SECTION 2: 各平台汇总 ==========
    print("\n## 2. 各平台 v5↔v7 一致性汇总")
    print(f"{'平台':<10} {'对数':>4} {'文本':>8} {'引用':>8} {'品牌':>8} {'产品':>8} {'立场':>8} {'关键点':>8}")

    grand = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}
    platform_details = {}  # platform -> list of (qi, metrics_dict)

    for platform in PLATFORMS:
        metrics = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}
        details = []

        for qi in range(11):
            da = structured["v5"].get(qi, {}).get(platform)
            db = structured["v7"].get(qi, {}).get(platform)
            if not da or not db:
                details.append((qi, None))
                continue

            ts = SequenceMatcher(None, da["content"], db["content"]).ratio()
            us = jaccard(da["urls"], db["urls"])
            bs = jaccard(da["brands"], db["brands"])
            ps = jaccard(da["products"], db["products"])
            ss = jaccard(da["stances"], db["stances"])
            ks = bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15

            row = {"text": ts, "url": us, "brand": bs, "product": ps, "stance": ss, "key": ks,
                   "v5_brands": da["brands"], "v7_brands": db["brands"],
                   "v5_urls": da["urls"], "v7_urls": db["urls"],
                   "v5_wc": da["word_count"], "v7_wc": db["word_count"],
                   "v5_stances": da["stances"], "v7_stances": db["stances"]}
            details.append((qi, row))

            for k, v in [("text", ts), ("url", us), ("brand", bs), ("product", ps), ("stance", ss), ("key", ks)]:
                metrics[k].append(v)
                grand[k].append(v)

        platform_details[platform] = details
        n = len(metrics["text"])
        if n > 0:
            print(f"{platform:<10} {n:>4} {avg(metrics['text']):>7.1%} {avg(metrics['url']):>7.1%} {avg(metrics['brand']):>7.1%} {avg(metrics['product']):>7.1%} {avg(metrics['stance']):>7.1%} {avg(metrics['key']):>7.1%}")

    n = len(grand["text"])
    print(f"{'全平台':<10} {n:>4} {avg(grand['text']):>7.1%} {avg(grand['url']):>7.1%} {avg(grand['brand']):>7.1%} {avg(grand['product']):>7.1%} {avg(grand['stance']):>7.1%} {avg(grand['key']):>7.1%}")

    # ========== SECTION 3: 逐题逐平台详细表 ==========
    print("\n## 3. 逐题逐平台 v5↔v7 对比明细")
    print("=" * 100)

    for qi in range(11):
        q = q_texts[qi]
        print(f"\n### Q{qi+1}: {q}")
        print(f"{'平台':<10} {'文本':>7} {'引用':>7} {'品牌':>7} {'关键点':>7} | {'v5字数':>6} {'v7字数':>6} | v5品牌 / v7品牌")
        print("-" * 100)

        q_key_scores = []
        for platform in PLATFORMS:
            for _, row in platform_details[platform]:
                if _ == qi:
                    if row is None:
                        print(f"{platform:<10} {'SKIP':>7} {'':>7} {'':>7} {'':>7} | {'':>6} {'':>6} | (v5或v7采集失败)")
                    else:
                        v5b_str = ",".join(sorted(row["v5_brands"]))[:40] if row["v5_brands"] else "(无)"
                        v7b_str = ",".join(sorted(row["v7_brands"]))[:40] if row["v7_brands"] else "(无)"
                        print(f"{platform:<10} {row['text']:>6.1%} {row['url']:>6.1%} {row['brand']:>6.1%} {row['key']:>6.1%} | {row['v5_wc']:>6} {row['v7_wc']:>6} | {v5b_str} / {v7b_str}")
                        q_key_scores.append(row["key"])
                    break

        if q_key_scores:
            print(f"{'Q均值':<10} {'':>7} {'':>7} {'':>7} {avg(q_key_scores):>6.1%} |")

    # ========== SECTION 4: 问题级别汇总排序 ==========
    print("\n\n## 4. 问题级别关键点一致性排序（v5↔v7）")
    print(f"{'Q#':>3} {'关键点':>8} {'文本':>8} {'引用':>8} {'品牌':>8} {'对数':>4}  问题")

    q_agg = {}
    for qi in range(11):
        agg = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}
        for platform in PLATFORMS:
            for idx, row in platform_details[platform]:
                if idx == qi and row is not None:
                    for k in agg:
                        agg[k].append(row[k])
                    break
        q_agg[qi] = agg

    sorted_qs = sorted(q_agg.items(), key=lambda x: avg(x[1]["key"]), reverse=True)
    for qi, agg in sorted_qs:
        n = len(agg["key"])
        if n > 0:
            print(f"Q{qi+1:>2} {avg(agg['key']):>7.1%} {avg(agg['text']):>7.1%} {avg(agg['url']):>7.1%} {avg(agg['brand']):>7.1%} {n:>4}  {q_texts[qi][:50]}")

    # ========== SECTION 5: 引用详情 ==========
    print("\n\n## 5. 引用数量与重叠详情")
    print(f"{'平台':<10} {'v5引用总':>8} {'v7引用总':>8} {'交集':>6} {'Jaccard':>8}")
    for platform in PLATFORMS:
        v5_all_urls = set()
        v7_all_urls = set()
        for qi in range(11):
            da = structured["v5"].get(qi, {}).get(platform)
            db = structured["v7"].get(qi, {}).get(platform)
            if da:
                v5_all_urls |= da["urls"]
            if db:
                v7_all_urls |= db["urls"]
        inter = len(v5_all_urls & v7_all_urls)
        j = jaccard(v5_all_urls, v7_all_urls)
        print(f"{platform:<10} {len(v5_all_urls):>8} {len(v7_all_urls):>8} {inter:>6} {j:>7.1%}")

    # ========== SECTION 6: 品牌提及对比 ==========
    print("\n\n## 6. 品牌提及频次对比")
    brand_freq = {"v5": defaultdict(int), "v7": defaultdict(int)}
    for ver in ["v5", "v7"]:
        for qi in range(11):
            for platform in PLATFORMS:
                d = structured[ver].get(qi, {}).get(platform)
                if d:
                    for b in d["brands"]:
                        brand_freq[ver][b] += 1

    all_brands = set(brand_freq["v5"].keys()) | set(brand_freq["v7"].keys())
    sorted_brands = sorted(all_brands, key=lambda b: brand_freq["v5"][b] + brand_freq["v7"][b], reverse=True)

    print(f"{'品牌':<16} {'v5次数':>6} {'v7次数':>6} {'变化':>6}")
    for brand in sorted_brands[:25]:
        v5 = brand_freq["v5"][brand]
        v7 = brand_freq["v7"][brand]
        print(f"{brand:<16} {v5:>6} {v7:>6} {v7-v5:>+6}")

    # ========== SECTION 7: 品牌集合对比 ==========
    print("\n\n## 7. 品牌集合 v5 vs v7 对比")
    v5_all_brands = set(brand_freq["v5"].keys())
    v7_all_brands = set(brand_freq["v7"].keys())
    common = v5_all_brands & v7_all_brands
    v5_only = v5_all_brands - v7_all_brands
    v7_only = v7_all_brands - v5_all_brands
    print(f"v5 总品牌数: {len(v5_all_brands)}")
    print(f"v7 总品牌数: {len(v7_all_brands)}")
    print(f"共有品牌:    {len(common)}")
    print(f"v5独有:      {len(v5_only)} -> {sorted(v5_only)}")
    print(f"v7独有:      {len(v7_only)} -> {sorted(v7_only)}")
    print(f"品牌集合 Jaccard: {jaccard(v5_all_brands, v7_all_brands):.1%}")

    # ========== SECTION 8: 字数对比 ==========
    print("\n\n## 8. 回答字数对比")
    print(f"{'平台':<10} {'v5均值':>8} {'v7均值':>8} {'变化':>8} {'变化率':>8}")
    for platform in PLATFORMS:
        v5_wc, v7_wc = [], []
        for qi in range(11):
            da = structured["v5"].get(qi, {}).get(platform)
            db = structured["v7"].get(qi, {}).get(platform)
            if da: v5_wc.append(da["word_count"])
            if db: v7_wc.append(db["word_count"])
        if v5_wc and v7_wc:
            d = avg(v7_wc) - avg(v5_wc)
            pct = d / avg(v5_wc) * 100 if avg(v5_wc) > 0 else 0
            print(f"{platform:<10} {avg(v5_wc):>7.0f} {avg(v7_wc):>7.0f} {d:>+7.0f} {pct:>+7.1f}%")

    # ========== SECTION 9: 集合大小统计 ==========
    print("\n\n## 9. 集合大小统计（品牌/引用/产品/立场）")
    print("用于评估 Jaccard 的可靠性 — 小集合会导致极端值")
    print(f"\n{'维度':<8} {'v5均值':>8} {'v7均值':>8} {'v5 min':>8} {'v5 max':>8} {'v7 min':>8} {'v7 max':>8}")
    for dim_name, dim_key in [("品牌", "brands"), ("引用", "urls"), ("产品", "products"), ("立场", "stances")]:
        v5_sizes, v7_sizes = [], []
        for qi in range(11):
            for platform in PLATFORMS:
                da = structured["v5"].get(qi, {}).get(platform)
                db = structured["v7"].get(qi, {}).get(platform)
                if da:
                    v5_sizes.append(len(da[dim_key]))
                if db:
                    v7_sizes.append(len(db[dim_key]))
        print(f"{dim_name:<8} {avg(v5_sizes):>7.1f} {avg(v7_sizes):>7.1f} {min(v5_sizes):>8} {max(v5_sizes):>8} {min(v7_sizes):>8} {max(v7_sizes):>8}")

    conn.close()


if __name__ == "__main__":
    main()

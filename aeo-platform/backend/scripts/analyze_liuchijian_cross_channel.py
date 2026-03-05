"""丽齿健 API vs Browser 跨通道一致性分析脚本
对比 v2/v3/v4 (API) 与 v5/v7 (Browser) 的差异
共 3 API版本 × 2 Browser版本 × 3共同平台 × 11问题 = 最多 198 对比对
"""
import sqlite3
import json
from difflib import SequenceMatcher
from collections import defaultdict

DB_PATH = "specta_dev.db"

VERSION_IDS = {
    "v2": "ccfff71f52b94c878d81d0ae97f3b46e",
    "v3": "8a10a7536d704a259170b40d9560b15d",
    "v4": "3b383c52773d468eae4e2c250d6129b2",
    "v5": "3d32794d04604ce1abf860bf5e3c567c",
    "v7": "a31cfd7dd034451f8c7d73e0d5560a92",
}

# 共同平台（API和Browser都有的）
COMMON_PLATFORMS = ["豆包", "混元", "Kimi"]
# Browser独有
BROWSER_ONLY = ["DeepSeek"]

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

    # Load all versions
    all_data = {}
    for ver, mid in VERSION_IDS.items():
        c.execute("SELECT output_data FROM messages WHERE id = ?", (mid,))
        raw = json.loads(c.fetchone()[0])
        all_data[ver] = raw.get("fetchResults", [])

    # Build structured data for all versions
    structured = {}
    for ver in VERSION_IDS:
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

    q_texts = {qi: all_data["v2"][qi]["question_text"] for qi in range(11)}

    api_versions = ["v2", "v3", "v4"]
    browser_versions = ["v5", "v7"]

    # Cross-channel pairs: each API version × each Browser version
    cross_pairs = [(a, b) for a in api_versions for b in browser_versions]
    # Same-channel pairs for comparison
    api_pairs = [("v2", "v3"), ("v2", "v4"), ("v3", "v4")]
    browser_pairs = [("v5", "v7")]

    print("=" * 90)
    print("丽齿健 API vs Browser 跨通道一致性分析")
    print("=" * 90)

    # ===== Section 1: Cross-channel per pair =====
    print("\n## 1. 跨通道各配对一致性（API版本 × Browser版本）")
    print(f"\n{'配对':<12} {'对数':>4} {'文本':>8} {'引用':>8} {'品牌':>8} {'产品':>8} {'立场':>8} {'关键点':>8}")

    all_cross = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}

    for api_v, br_v in cross_pairs:
        metrics = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}
        for qi in range(11):
            for platform in COMMON_PLATFORMS:
                da = structured[api_v].get(qi, {}).get(platform)
                db = structured[br_v].get(qi, {}).get(platform)
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
                    all_cross[k].append(v)

        n = len(metrics["text"])
        print(f"{api_v}<->{br_v}    {n:>4} {avg(metrics['text']):>7.1%} {avg(metrics['url']):>7.1%} {avg(metrics['brand']):>7.1%} {avg(metrics['product']):>7.1%} {avg(metrics['stance']):>7.1%} {avg(metrics['key']):>7.1%}")

    n = len(all_cross["text"])
    print(f"{'跨通道总计':<12} {n:>4} {avg(all_cross['text']):>7.1%} {avg(all_cross['url']):>7.1%} {avg(all_cross['brand']):>7.1%} {avg(all_cross['product']):>7.1%} {avg(all_cross['stance']):>7.1%} {avg(all_cross['key']):>7.1%}")

    # ===== Section 2: Cross-channel per platform =====
    print("\n\n## 2. 跨通道各平台一致性（所有 API×Browser 配对合并）")
    print(f"\n{'平台':<10} {'对数':>4} {'文本':>8} {'引用':>8} {'品牌':>8} {'产品':>8} {'立场':>8} {'关键点':>8}")

    platform_cross = {}
    for platform in COMMON_PLATFORMS:
        metrics = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}
        for api_v, br_v in cross_pairs:
            for qi in range(11):
                da = structured[api_v].get(qi, {}).get(platform)
                db = structured[br_v].get(qi, {}).get(platform)
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
        platform_cross[platform] = metrics
        n = len(metrics["text"])
        print(f"{platform:<10} {n:>4} {avg(metrics['text']):>7.1%} {avg(metrics['url']):>7.1%} {avg(metrics['brand']):>7.1%} {avg(metrics['product']):>7.1%} {avg(metrics['stance']):>7.1%} {avg(metrics['key']):>7.1%}")

    # ===== Section 3: Three-way comparison =====
    print("\n\n## 3. 三维对比：同通道 vs 跨通道")

    # Compute same-channel averages
    api_same = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}
    for va, vb in api_pairs:
        for qi in range(11):
            for platform in COMMON_PLATFORMS:
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
                    api_same[k].append(v)

    browser_same = {k: [] for k in ["text", "url", "brand", "product", "stance", "key"]}
    for va, vb in browser_pairs:
        for qi in range(11):
            for platform in COMMON_PLATFORMS:  # Use common platforms for fair comparison
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
                    browser_same[k].append(v)

    print(f"\n{'对比类型':<16} {'对数':>4} {'文本':>8} {'引用':>8} {'品牌':>8} {'产品':>8} {'立场':>8} {'关键点':>8}")
    print(f"{'API同通道':<16} {len(api_same['text']):>4} {avg(api_same['text']):>7.1%} {avg(api_same['url']):>7.1%} {avg(api_same['brand']):>7.1%} {avg(api_same['product']):>7.1%} {avg(api_same['stance']):>7.1%} {avg(api_same['key']):>7.1%}")
    print(f"{'Browser同通道':<16} {len(browser_same['text']):>4} {avg(browser_same['text']):>7.1%} {avg(browser_same['url']):>7.1%} {avg(browser_same['brand']):>7.1%} {avg(browser_same['product']):>7.1%} {avg(browser_same['stance']):>7.1%} {avg(browser_same['key']):>7.1%}")
    print(f"{'API<->Browser':<16} {len(all_cross['text']):>4} {avg(all_cross['text']):>7.1%} {avg(all_cross['url']):>7.1%} {avg(all_cross['brand']):>7.1%} {avg(all_cross['product']):>7.1%} {avg(all_cross['stance']):>7.1%} {avg(all_cross['key']):>7.1%}")

    # Delta
    api_key = avg(api_same["key"])
    br_key = avg(browser_same["key"])
    cross_key = avg(all_cross["key"])
    print(f"\n  跨通道 vs API同通道:     {(cross_key - api_key)*100:>+.1f}pp")
    print(f"  跨通道 vs Browser同通道: {(cross_key - br_key)*100:>+.1f}pp")

    # ===== Section 4: Per-platform three-way =====
    print("\n\n## 4. 各平台三维对比（关键点一致性）")
    print(f"\n{'平台':<10} {'API同通道':>12} {'Browser同通道':>14} {'API<->Browser':>14} {'跨通道降幅':>12}")

    for platform in COMMON_PLATFORMS:
        # API same-channel for this platform
        api_p = []
        for va, vb in api_pairs:
            for qi in range(11):
                da = structured[va].get(qi, {}).get(platform)
                db = structured[vb].get(qi, {}).get(platform)
                if not da or not db:
                    continue
                bs = jaccard(da["brands"], db["brands"])
                ps = jaccard(da["products"], db["products"])
                ss = jaccard(da["stances"], db["stances"])
                us = jaccard(da["urls"], db["urls"])
                api_p.append(bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15)

        # Browser same-channel for this platform
        br_p = []
        for va, vb in browser_pairs:
            for qi in range(11):
                da = structured[va].get(qi, {}).get(platform)
                db = structured[vb].get(qi, {}).get(platform)
                if not da or not db:
                    continue
                bs = jaccard(da["brands"], db["brands"])
                ps = jaccard(da["products"], db["products"])
                ss = jaccard(da["stances"], db["stances"])
                us = jaccard(da["urls"], db["urls"])
                br_p.append(bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15)

        cross_p = platform_cross[platform]["key"]
        a = avg(api_p)
        b = avg(br_p)
        x = avg(cross_p)
        same_avg = (a + b) / 2
        drop = (x - same_avg) * 100
        print(f"{platform:<10} {a:>11.1%} {b:>13.1%} {x:>13.1%} {drop:>+11.1f}pp")

    # ===== Section 5: Per-question cross-channel =====
    print("\n\n## 5. 问题级别跨通道一致性")
    print(f"\n{'Q#':>3} {'API同通道':>12} {'Browser同通道':>14} {'跨通道':>10} {'降幅':>8}  问题")

    for qi in range(11):
        # API same
        api_q = []
        for va, vb in api_pairs:
            for platform in COMMON_PLATFORMS:
                da = structured[va].get(qi, {}).get(platform)
                db = structured[vb].get(qi, {}).get(platform)
                if not da or not db:
                    continue
                bs = jaccard(da["brands"], db["brands"])
                ps = jaccard(da["products"], db["products"])
                ss = jaccard(da["stances"], db["stances"])
                us = jaccard(da["urls"], db["urls"])
                api_q.append(bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15)

        # Browser same
        br_q = []
        for va, vb in browser_pairs:
            for platform in COMMON_PLATFORMS:
                da = structured[va].get(qi, {}).get(platform)
                db = structured[vb].get(qi, {}).get(platform)
                if not da or not db:
                    continue
                bs = jaccard(da["brands"], db["brands"])
                ps = jaccard(da["products"], db["products"])
                ss = jaccard(da["stances"], db["stances"])
                us = jaccard(da["urls"], db["urls"])
                br_q.append(bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15)

        # Cross
        cross_q = []
        for api_v, br_v in cross_pairs:
            for platform in COMMON_PLATFORMS:
                da = structured[api_v].get(qi, {}).get(platform)
                db = structured[br_v].get(qi, {}).get(platform)
                if not da or not db:
                    continue
                bs = jaccard(da["brands"], db["brands"])
                ps = jaccard(da["products"], db["products"])
                ss = jaccard(da["stances"], db["stances"])
                us = jaccard(da["urls"], db["urls"])
                cross_q.append(bs * 0.3 + ps * 0.25 + ss * 0.3 + us * 0.15)

        a = avg(api_q)
        b = avg(br_q)
        x = avg(cross_q)
        same_avg = (a + b) / 2
        drop = (x - same_avg) * 100
        print(f"Q{qi+1:>2} {a:>11.1%} {b:>13.1%} {x:>9.1%} {drop:>+7.1f}pp  {q_texts[qi][:42]}")

    # ===== Section 6: Brand overlap API vs Browser =====
    print("\n\n## 6. 品牌提及交集分析（API vs Browser）")

    # Aggregate brands per platform across API versions and Browser versions
    for platform in COMMON_PLATFORMS:
        api_brands = defaultdict(int)  # brand -> count across all API versions & questions
        br_brands = defaultdict(int)
        for ver in api_versions:
            for qi in range(11):
                d = structured[ver].get(qi, {}).get(platform)
                if d:
                    for b in d["brands"]:
                        api_brands[b] += 1
        for ver in browser_versions:
            for qi in range(11):
                d = structured[ver].get(qi, {}).get(platform)
                if d:
                    for b in d["brands"]:
                        br_brands[b] += 1

        api_set = set(api_brands.keys())
        br_set = set(br_brands.keys())
        both = api_set & br_set
        api_only = api_set - br_set
        br_only = br_set - api_set

        j = jaccard(api_set, br_set)
        print(f"\n{platform}: 品牌Jaccard={j:.1%}, 共有={len(both)}, API独有={len(api_only)}, Browser独有={len(br_only)}")
        if api_only:
            print(f"  API独有: {', '.join(sorted(api_only))}")
        if br_only:
            print(f"  Browser独有: {', '.join(sorted(br_only))}")

    # ===== Section 7: Word count comparison =====
    print("\n\n## 7. 回答字数对比（API vs Browser）")
    print(f"\n{'平台':<10} {'API均值':>8} {'Browser均值':>11} {'变化':>8} {'变化率':>8}")
    for platform in COMMON_PLATFORMS:
        api_wc = []
        br_wc = []
        for ver in api_versions:
            for qi in range(11):
                d = structured[ver].get(qi, {}).get(platform)
                if d:
                    api_wc.append(d["word_count"])
        for ver in browser_versions:
            for qi in range(11):
                d = structured[ver].get(qi, {}).get(platform)
                if d:
                    br_wc.append(d["word_count"])
        if api_wc and br_wc:
            a = avg(api_wc)
            b = avg(br_wc)
            print(f"{platform:<10} {a:>7.0f} {b:>10.0f} {b-a:>+7.0f} {(b-a)/a*100:>+7.1f}%")

    # ===== Section 8: Citation overlap cross-channel =====
    print("\n\n## 8. 引用来源跨通道重叠")
    for platform in COMMON_PLATFORMS:
        overlaps = []
        for api_v, br_v in cross_pairs:
            for qi in range(11):
                da = structured[api_v].get(qi, {}).get(platform)
                db = structured[br_v].get(qi, {}).get(platform)
                if not da or not db:
                    continue
                j = jaccard(da["urls"], db["urls"])
                overlaps.append(j)
        if overlaps:
            print(f"{platform}: 跨通道引用Jaccard = {avg(overlaps):.1%} ({len(overlaps)}对)")

    conn.close()


if __name__ == "__main__":
    main()

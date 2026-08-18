import os
import re
import requests
from supabase import create_client

# 環境変数の取得
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 計算パラメーター
USD_TO_JPY = 155.0         # 1ドルあたりの円換算レート
IMPORT_TAX_RATE = 1.10     # 輸入消費税等 (10%)
SHIPPING_COST_USD = 15.0   # 1枚あたりの国際送料 ($15)
JP_PLATFORM_FEE = 0.09     # 国内販売手数料 (9%)
JP_SHIPPING_JPY = 500      # 国内発送送料 (500円)

# 簡易国内相場データベース
JAPAN_MARKET_DATABASE = {
    "229/BW-P": {"name": "ピカチュウ BW-P", "jp_price": 28000},
    "068/028":  {"name": "ミュウツー&ミュウGX", "jp_price": 45000},
    "154/XY-P": {"name": "ポンチョを着たピカチュウ", "jp_price": 180000},
    "001/S-P":  {"name": "ピカチュウ VMAX", "jp_price": 35000},
    "201/S-P":  {"name": "ピカチュウV", "jp_price": 22000},
}

def estimate_jp_market_price(title):
    """カード名・タイトルから日本の相場価格(JPY)を推定"""
    title_upper = title.upper()
    
    for code, info in JAPAN_MARKET_DATABASE.items():
        if code.upper() in title_upper:
            return info["jp_price"], info["name"]

    if "CHARIZARD" in title_upper or "リザードン" in title_upper:
        return 35000, "リザードン PSA10"
    elif "PIKACHU" in title_upper or "ピカチュウ" in title_upper:
        return 25000, "ピカチュウ PSA10"
    elif "MARNIE" in title_upper or "マリィ" in title_upper:
        return 40000, "マリィ PSA10"
    elif "LILLIE" in title_upper or "リーリエ" in title_upper:
        return 120000, "リーリエ PSA10"

    return 22000, "PSA10 Trading Card"

def fetch_ebay_api_items(keyword):
    """eBay Internal API Endpoint (IPブロック回避＆JSON取得)"""
    encoded_kw = requests.utils.quote(keyword)
    # 即決(BIN) / 新着順 / 自動JSONエンドポイント
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded_kw}&_sop=10&LH_BIN=1&_reqcnt=1&rt=nc"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.ebay.com/"
    }
    
    items = []
    try:
        session = requests.Session()
        # ホームに一度アクセスしてCookieを取得（Cloudflare対策）
        session.get("https://www.ebay.com", headers=headers, timeout=5)
        
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html_text = response.text
            
            # HTML内の商品データ（s-item）ブロックを正規表現で高速抽出
            titles = re.findall(r'class="s-item__title"[^>]*><span[^>]*>(.*?)</span>', html_text)
            prices = re.findall(r'class="s-item__price"[^>]*>(.*?)</span>', html_text)
            links = re.findall(r'href="(https://www\.ebay\.com/itm/[^"?]+)', html_text)

            min_len = min(len(titles), len(prices), len(links))
            for i in range(min_len):
                title = re.sub('<[^<]+?>', '', titles[i]).strip() # HTMLタグ除去
                price_str = prices[i]
                link = links[i]

                if "Shop on eBay" in title or not title:
                    continue

                # 価格の抽出 ($123.45)
                price_match = re.search(r'\$\s*([0-9,]+(?:\.[0-9]{1,2})?)', price_str)
                if price_match:
                    price_usd = float(price_match.group(1).replace(',', ''))
                    items.append({
                        "title": title,
                        "url": link,
                        "price_usd": price_usd
                    })
    except Exception as e:
        print(f"⚠️ 取得エラー ({keyword}): {e}")
        
    return items

def run_auto_research():
    print("🔍 API・セッション模倣版 自動リサーチを開始します...")

    search_keywords = [
        "Pokemon PSA 10 Japanese",
        "Yu-Gi-Oh PSA 10 Japanese",
        "One Piece Card PSA 10 Japanese",
        "Weiss Schwarz PSA 10 Japanese"
    ]

    total_found = 0

    for keyword in search_keywords:
        print(f"📡 巡回中: {keyword}")
        ebay_items = fetch_ebay_api_items(keyword)
        print(f"   ➔ 取得件数: {len(ebay_items)} 件")

        for item in ebay_items[:10]:
            title = item["title"]
            ebay_url = item["url"]
            actual_price_usd = item["price_usd"]

            # DB重複チェック
            existing = supabase.table("profit_cards").select("id").eq("ebay_url", ebay_url).execute()
            if existing.data:
                continue

            jp_market_jpy, matched_name = estimate_jp_market_price(title)

            # 利益計算
            total_cost_jpy = (actual_price_usd + SHIPPING_COST_USD) * USD_TO_JPY * IMPORT_TAX_RATE
            net_sales_jpy = jp_market_jpy * (1.0 - JP_PLATFORM_FEE) - JP_SHIPPING_JPY
            profit_jpy = round(net_sales_jpy - total_cost_jpy)
            roi_percent = round((profit_jpy / total_cost_jpy) * 100, 1)

            # 利益2,000円以上 ＆ ROI 15%以上 のみ通知
            if profit_jpy >= 2000 and roi_percent >= 15.0:
                total_found += 1
                print(f"🔥 お宝発見!: {title}")
                print(f"   仕入(実売): ${actual_price_usd} (約{round(total_cost_jpy):,}円) ➔ 想定利益: {profit_jpy:,}円 (ROI: {roi_percent}%)")

                # Supabase保存
                supabase.table("profit_cards").insert({
                    "card_name": f"{title} [{matched_name}]",
                    "ebay_price_usd": actual_price_usd,
                    "jp_price_jpy": jp_market_jpy,
                    "profit_jpy": profit_jpy,
                    "roi_percent": roi_percent,
                    "ebay_url": ebay_url
                }).execute()

                # Discord通知
                if DISCORD_WEBHOOK_URL:
                    payload = {
                        "embeds": [{
                            "title": f"🔥 【利益 {profit_jpy:,}円 / ROI {roi_percent}%】お宝カード発見！",
                            "description": (
                                f"**カード名:** {title}\n"
                                f"**eBay出品価格:** `${actual_price_usd}` (約{round(total_cost_jpy):,}円)\n"
                                f"**国内想定相場:** `¥{jp_market_jpy:,}`\n"
                                f"**想定利益:** `¥{profit_jpy:,}`\n\n"
                                f"👉 [eBayで商品ページを開く]({ebay_url})"
                            ),
                            "color": 5814783
                        }]
                    }
                    requests.post(DISCORD_WEBHOOK_URL, json=payload)

    print(f"✅ リサーチ完了: 今回発見したお宝カード {total_found} 件")

if __name__ == "__main__":
    run_auto_research()

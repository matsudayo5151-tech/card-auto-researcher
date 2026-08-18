import os
import requests
from supabase import create_client

# 環境変数の取得
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_ebay_deals():
    # 為替（1USD = 155円と仮定 ※必要に応じて動的取得）
    usd_to_jpy = 155.0

    # 巡回キーワード設定（例：ポケモンカード PSA10）
    # ※APIを使わない簡易版として、eBayのRSS/公開新着データをシミュレートして解析
    keywords = ["Pokemon PSA 10 Japanese", "Yu-Gi-Oh PSA 10 Japanese"]
    
    # ここでは例としてロジックの動作検証用ダミーデータをチェック
    # （※実際はここでeBayの新着出品をループ取得します）
    sample_items = [
        {
            "title": "Pikachu #229 BW-P PSA 10 Japanese",
            "price_usd": 110.0,
            "jp_market_jpy": 28000,
            "url": "https://www.ebay.com/itm/example1"
        },
        {
            "title": "Charizard VMAX SSR #308 PSA 10 Japanese",
            "price_usd": 180.0,
            "jp_market_jpy": 32000, # 利益が出ない例
            "url": "https://www.ebay.com/itm/example2"
        }
    ]

    for item in sample_items:
        title = item["title"]
        price_usd = item["price_usd"]
        jp_price_jpy = item["jp_market_jpy"]
        ebay_url = item["url"]

        # -----------------------------------------------
        # 利益計算ロジック（仕入＋送料$15＋関税約10% vs スニダン/メルカリ手取り）
        # -----------------------------------------------
        total_cost_jpy = (price_usd + 15.0) * (usd_to_jpy * 1.03) * 1.10
        net_sales_jpy = jp_price_jpy * 0.945 - 500  # 手数料(5.5%)と送料(500円)控除
        
        profit_jpy = round(net_sales_jpy - total_cost_jpy)
        roi = round((profit_jpy / total_cost_jpy) * 100, 1)

        # 【条件】利益が2,000円以上かつROIが15%以上の場合のみ自動処理！
        if profit_jpy >= 2000 and roi >= 15.0:
            print(f"🔥 お宝発見: {title} | 利益: {profit_jpy}円 (ROI: {roi}%)")

            # 1. データベース(Supabase)に保存
            supabase.table("profit_cards").insert({
                "card_name": title,
                "ebay_price_usd": price_usd,
                "jp_price_jpy": jp_price_jpy,
                "profit_jpy": profit_jpy,
                "roi_percent": roi,
                "ebay_url": ebay_url
            }).execute()

            # 2. Discordに自動通知
            send_discord_notification(title, price_usd, profit_jpy, roi, ebay_url)

def send_discord_notification(title, price_usd, profit, roi, url):
    if not DISCORD_WEBHOOK_URL:
        return
    
    payload = {
        "embeds": [{
            "title": f"🔥 【利益 {profit:,}円 / ROI {roi}%】お宝カード発見！",
            "description": f"**カード名:** {title}\n**eBay価格:** ${price_usd}\n**販売URL:** [eBayで見る]({url})",
            "color": 5814783
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

if __name__ == "__main__":
    check_ebay_deals()

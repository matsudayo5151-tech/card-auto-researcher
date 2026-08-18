import { createClient } from '@supabase/supabase-js';
import { useEffect, useState } from 'react';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_KEY;
const supabase = createClient(supabaseUrl, supabaseAnonKey);

export default function Home() {
  const [cards, setCards] = useState([]);

  useEffect(() => {
    async function fetchCards() {
      const { data, error } = await supabase
        .from('profit_cards')
        .select('*')
        .order('created_at', { ascending: false });

      if (!error && data) {
        setCards(data);
      }
    }
    fetchCards();
  }, []);

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif', backgroundColor: '#f4f6f8', minHeight: '100vh' }}>
      <h1 style={{ textAlign: 'center', color: '#1a202c' }}>🔥 自動検出 利益カード一覧</h1>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '20px', maxWidth: '1200px', margin: '0 auto' }}>
        {cards.map((card) => (
          <div key={card.id} style={{ border: '1px solid #e2e8f0', borderRadius: '12px', padding: '16px', backgroundColor: '#fff', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
            <h3 style={{ fontSize: '1.1rem', margin: '0 0 10px 0', color: '#2d3748' }}>{card.card_name}</h3>
            
            <div style={{ marginBottom: '8px' }}>
              <span style={{ color: '#718096' }}>eBay仕入価格: </span>
              <strong>${card.ebay_price_usd}</strong>
            </div>
            
            <div style={{ marginBottom: '8px' }}>
              <span style={{ color: '#718096' }}>国内相場: </span>
              <strong>¥{card.jp_price_jpy?.toLocaleString()}</strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #edf2f7' }}>
              <div style={{ color: '#e53e3e', fontWeight: 'bold', fontSize: '1.1rem' }}>
                利益: ¥{card.profit_jpy?.toLocaleString()}
              </div>
              <div style={{ backgroundColor: '#ebf8ff', color: '#3182ce', padding: '4px 8px', borderRadius: '6px', fontWeight: 'bold', fontSize: '0.9rem' }}>
                ROI {card.roi_percent}%
              </div>
            </div>

            <a href={card.ebay_url} target="_blank" rel="noreferrer" style={{ display: 'block', textAlign: 'center', marginTop: '12px', padding: '8px', backgroundColor: '#3182ce', color: '#fff', textDecoration: 'none', borderRadius: '6px', fontWeight: 'bold' }}>
              eBayで確認する
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}

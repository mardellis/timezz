/* global TrelloPowerUp */

console.log('🚀 TimeZZ Power-Up yükleniyor...');

// En basit power-up konfigürasyonu
TrelloPowerUp.initialize({
    'card-buttons': function(t, opts) {
        console.log('✅ Card buttons yüklendi');
        
        return [
            {
                icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/play-circle.svg',
                text: 'Timer Başlat',
                callback: function(t) {
                    console.log('Timer başlatıldı!');
                    return t.alert({
                        message: '⏱️ TimeZZ Timer Başlatıldı!',
                        duration: 3
                    });
                }
            },
            {
                icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/bar-chart-2.svg', 
                text: 'Dashboard',
                callback: function(t) {
                    return t.popup({
                        title: 'TimeZZ Dashboard',
                        url: 'data:text/html,<div style="padding:30px;font-family:Arial,sans-serif;text-align:center;"><h2 style="color:#0079bf;">🎉 TimeZZ Çalışıyor!</h2><p>Power-Up başarıyla yüklendi.</p><button onclick="window.close()" style="background:#0079bf;color:white;border:none;padding:10px 20px;border-radius:5px;cursor:pointer;">Kapat</button></div>',
                        height: 200
                    });
                }
            }
        ];
    },
    
    'board-buttons': function(t, opts) {
        console.log('✅ Board buttons yüklendi');
        
        return [{
            icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/clock.svg',
            text: 'TimeZZ',
            callback: function(t) {
                return t.popup({
                    title: 'TimeZZ Dashboard', 
                    url: 'data:text/html,<div style="padding:30px;font-family:Arial,sans-serif;"><h2 style="color:#0079bf;">📊 TimeZZ Dashboard</h2><p>Zaman takibi başarıyla çalışıyor!</p><div style="background:#f5f5f5;padding:15px;border-radius:8px;margin:10px 0;"><strong>Bugün:</strong> 2.5 saat<br><strong>Bu hafta:</strong> 18.2 saat</div></div>',
                    height: 300
                });
            }
        }];
    },
    
    'card-badges': function(t, opts) {
        // Test için sabit badge
        return [{
            text: '⏱ 0:25:30',
            color: 'green'
        }];
    }
});

console.log('✅ TimeZZ Power-Up başarıyla yüklendi!');

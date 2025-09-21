/* global TrelloPowerUp */

// Basit test için minimal power-up
TrelloPowerUp.initialize({
    'card-buttons': function(t, opts) {
        console.log('TimeZZ Power-Up loaded successfully!');
        
        return [{
            icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/clock.svg',
            text: '⏱️ TimeZZ Test',
            callback: function(t) {
                return t.alert({
                    message: '🎉 TimeZZ Power-Up çalışıyor!',
                    duration: 3
                });
            }
        }];
    },
    
    'board-buttons': function(t, opts) {
        return [{
            icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/activity.svg',
            text: 'TimeZZ Dashboard',
            callback: function(t) {
                return t.popup({
                    title: 'TimeZZ Test Popup',
                    url: 'data:text/html,<div style="padding:20px;font-family:Arial;"><h2>🎉 TimeZZ Power-Up Başarıyla Yüklendi!</h2><p>Power-Up çalışıyor. Şimdi gerçek özellikleri ekleyebilirsiniz.</p></div>',
                    height: 200
                });
            }
        }];
    }
});

console.log('TimeZZ Power-Up initialized!');

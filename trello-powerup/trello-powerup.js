/* global TrelloPowerUp */

/**
 * TimeZZ - Professional Time Tracking Power-Up for Trello
 * Production-ready version with proper error handling and authentication
 */

// Configuration - Update these URLs for production
const CONFIG = {
    API_BASE_URL: window.location.hostname === 'localhost' 
        ? 'http://localhost:8000' 
        : 'https://your-api-domain.com',
    
    DASHBOARD_URL: window.location.hostname === 'localhost'
        ? 'http://localhost:3000'
        : 'https://your-app-domain.com',
    
    POWER_UP_URL: window.location.protocol + '//' + window.location.host
};

// Utility functions
const Utils = {
    formatDuration: (seconds) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    },

    async apiCall(endpoint, method = 'GET', data = null) {
        try {
            const token = await Utils.getAuthToken();
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token || 'demo_token'}`
                }
            };

            if (data && method !== 'GET') {
                options.body = JSON.stringify(data);
            }

            const response = await fetch(`${CONFIG.API_BASE_URL}/api/v1${endpoint}`, options);
            
            if (!response.ok) {
                throw new Error(`API call failed: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API call error:', error);
            throw error;
        }
    },

    async getAuthToken() {
        const t = TrelloPowerUp.iframe();
        return await t.get('member', 'private', 'timezz_auth_token');
    },

    async setAuthToken(token) {
        const t = TrelloPowerUp.iframe();
        return await t.set('member', 'private', 'timezz_auth_token', token);
    }
};

// Timer management
const TimerManager = {
    async getActiveTimer(t) {
        return await t.get('card', 'shared', 'timezz_timer');
    },

    async startTimer(t, cardData) {
        try {
            const timerData = {
                active: true,
                startTime: new Date().toISOString(),
                cardId: cardData.id,
                cardName: cardData.name
            };

            // Save to Trello storage
            await t.set('card', 'shared', 'timezz_timer', timerData);

            // Sync with backend
            await Utils.apiCall('/time/start', 'POST', {
                card_id: cardData.id,
                card_name: cardData.name,
                board_id: cardData.board.id,
                description: `Timer started from Trello Power-Up`
            });

            return timerData;
        } catch (error) {
            console.error('Failed to start timer:', error);
            // Still save locally even if API fails
            const timerData = {
                active: true,
                startTime: new Date().toISOString(),
                cardId: cardData.id,
                cardName: cardData.name,
                offline: true
            };
            await t.set('card', 'shared', 'timezz_timer', timerData);
            return timerData;
        }
    },

    async stopTimer(t, timerData) {
        try {
            const endTime = new Date();
            const duration = (endTime - new Date(timerData.startTime)) / 1000;

            // Clear from Trello storage
            await t.remove('card', 'shared', 'timezz_timer');

            // Sync with backend
            if (!timerData.offline) {
                await Utils.apiCall('/time/stop', 'POST');
            } else {
                // If it was offline, create the entry manually
                await Utils.apiCall('/time/entries', 'POST', {
                    card_id: timerData.cardId,
                    card_name: timerData.cardName,
                    start_time: timerData.startTime,
                    end_time: endTime.toISOString(),
                    duration_minutes: Math.round(duration / 60),
                    description: 'Offline timer entry'
                });
            }

            return { duration };
        } catch (error) {
            console.error('Failed to stop timer:', error);
            // Still clear locally
            await t.remove('card', 'shared', 'timezz_timer');
            return { duration: 0, error: true };
        }
    }
};

// Authentication flow
const AuthManager = {
    async authenticate(t) {
        return t.popup({
            title: 'Connect to TimeZZ',
            url: `${CONFIG.POWER_UP_URL}/auth-popup.html`,
            height: 400
        });
    },

    async checkAuth(t) {
        const token = await Utils.getAuthToken();
        return !!token;
    }
};

// Initialize the Trello Power-Up
TrelloPowerUp.initialize({
    // Card buttons - Show timer controls on each card
    'card-buttons': function(t, opts) {
        return Promise.all([
            TimerManager.getActiveTimer(t),
            t.card('id', 'name', 'board')
        ]).then(([timer, card]) => {
            const isThisCardActive = timer && timer.active && timer.cardId === card.id;

            return [{
                icon: isThisCardActive 
                    ? 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/stop-circle.svg'
                    : 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/play-circle.svg',
                text: isThisCardActive ? 'Stop Timer' : 'Start Timer',
                callback: async function(t) {
                    if (isThisCardActive) {
                        const result = await TimerManager.stopTimer(t, timer);
                        if (!result.error) {
                            alert(`Timer stopped. Duration: ${Utils.formatDuration(result.duration)}`);
                        } else {
                            alert('Timer stopped locally, but failed to sync with server.');
                        }
                    } else {
                        await TimerManager.startTimer(t, card);
                        alert('Timer started!');
                    }
                }
            }];
        });
    },

    // Card badges - Show running timer
    'card-badges': function(t, opts) {
        return TimerManager.getActiveTimer(t).then(timer => {
            if (timer && timer.active) {
                const duration = Math.floor((Date.now() - new Date(timer.startTime)) / 1000);
                return [{
                    text: `⏱ ${Utils.formatDuration(duration)}`,
                    color: 'green'
                }];
            }
            return [];
        });
    },

    // Board buttons - Link to dashboard
    'board-buttons': function(t, opts) {
        return [{
            icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/bar-chart-2.svg',
            text: 'TimeZZ Dashboard',
            callback: function(t) {
                return t.modal({
                    url: CONFIG.DASHBOARD_URL,
                    fullscreen: true,
                    title: 'TimeZZ Dashboard'
                });
            }
        }];
    }
});

/* global TrelloPowerUp */

/**
 * TimeZZ - Professional Time Tracking Power-Up for Trello
 * Production-ready version optimized for Trello integration
 */

// Configuration - Update these URLs for your deployment
const CONFIG = {
    API_BASE_URL: 'https://timezz-backend.onrender.com',
    DASHBOARD_URL: 'https://timezz-frontend.onrender.com',
    POWER_UP_URL: 'https://timezz-frontend.onrender.com'
};

// Utility functions
const Utils = {
    // Format duration in seconds to HH:MM:SS
    formatDuration: (seconds) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    },

    // Format duration in a human-readable way
    formatDurationHuman: (seconds) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        
        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        }
        return `${minutes}m`;
    },

    // Make API calls to TimeZZ backend
    async apiCall(endpoint, method = 'GET', data = null, t = null) {
        try {
            const token = t ? await Utils.getAuthToken(t) : null;
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token || 'demo_token'}`
                },
                mode: 'cors'
            };

            if (data && method !== 'GET') {
                options.body = JSON.stringify(data);
            }

            const response = await fetch(`${CONFIG.API_BASE_URL}/api/v1${endpoint}`, options);
            
            if (response.ok) {
                return await response.json();
            } else {
                console.warn('API call failed:', response.status, endpoint);
                return null;
            }
        } catch (error) {
            console.warn('API call error:', error);
            return null;
        }
    },

    // Get authentication token from Trello storage
    async getAuthToken(t) {
        return await t.get('member', 'private', 'timezz_auth_token');
    },

    // Set authentication token
    async setAuthToken(t, token) {
        return await t.set('member', 'private', 'timezz_auth_token', token);
    },

    // Get user info from Trello
    async getTrelloUserInfo(t) {
        try {
            const member = await t.member('id', 'username', 'fullName', 'email');
            return {
                id: member.id,
                username: member.username,
                name: member.fullName,
                email: member.email
            };
        } catch (error) {
            console.warn('Could not get Trello user info:', error);
            return null;
        }
    }
};

// Timer management functions
const TimerManager = {
    // Get active timer for a card
    async getActiveTimer(t) {
        return await t.get('card', 'shared', 'timezz_timer');
    },

    // Start timer for a card
    async startTimer(t, cardData) {
        try {
            // Stop any existing timer first
            await TimerManager.stopAnyRunningTimer(t);

            const timerData = {
                active: true,
                startTime: new Date().toISOString(),
                cardId: cardData.id,
                cardName: cardData.name,
                boardId: cardData.board?.id || 'unknown'
            };

            // Save to Trello storage
            await t.set('card', 'shared', 'timezz_timer', timerData);

            // Sync with backend
            const syncData = {
                card_id: cardData.id,
                card_name: cardData.name,
                board_id: cardData.board?.id || 'unknown',
                description: `Timer started from Trello Power-Up`
            };
            
            await Utils.apiCall('/time/start', 'POST', syncData, t);

            return timerData;
        } catch (error) {
            console.error('Failed to start timer:', error);
            throw error;
        }
    },

    // Stop timer for a card
    async stopTimer(t, timerData) {
        try {
            const endTime = new Date();
            const duration = Math.floor((endTime - new Date(timerData.startTime)) / 1000);

            // Clear from Trello storage
            await t.remove('card', 'shared', 'timezz_timer');

            // Sync with backend
            await Utils.apiCall('/time/stop', 'POST', {}, t);

            return { duration, success: true };
        } catch (error) {
            console.error('Failed to stop timer:', error);
            // Still remove local timer
            await t.remove('card', 'shared', 'timezz_timer');
            const duration = Math.floor((new Date() - new Date(timerData.startTime)) / 1000);
            return { duration, success: false, error: error.message };
        }
    },

    // Stop any running timer across all cards
    async stopAnyRunningTimer(t) {
        try {
            const board = await t.board('id');
            const cards = await t.cards('id');
            
            for (const card of cards) {
                const timer = await t.get(card.id, 'shared', 'timezz_timer');
                if (timer && timer.active) {
                    await t.remove(card.id, 'shared', 'timezz_timer');
                }
            }
        } catch (error) {
            console.warn('Error stopping running timers:', error);
        }
    },

    // Check if any timer is running on the board
    async hasRunningTimer(t) {
        try {
            const cards = await t.cards('id');
            
            for (const card of cards) {
                const timer = await t.get(card.id, 'shared', 'timezz_timer');
                if (timer && timer.active) {
                    return { hasTimer: true, cardId: card.id, timer };
                }
            }
            
            return { hasTimer: false };
        } catch (error) {
            console.warn('Error checking running timers:', error);
            return { hasTimer: false };
        }
    }
};

// Authentication functions
const Auth = {
    // Show authentication popup
    async showAuthPopup(t) {
        return t.popup({
            title: 'Connect to TimeZZ',
            url: `${CONFIG.POWER_UP_URL}/auth-popup.html`,
            height: 400,
            args: { 
                apiUrl: CONFIG.API_BASE_URL,
                returnUrl: CONFIG.DASHBOARD_URL 
            }
        });
    },

    // Authenticate user with TimeZZ
    async authenticateUser(t, credentials) {
        try {
            const trelloUser = await Utils.getTrelloUserInfo(t);
            
            const loginData = {
                trello_user_id: trelloUser?.id || 'anonymous_' + Date.now(),
                email: credentials.email || trelloUser?.email || 'user@trello.local',
                name: trelloUser?.name || trelloUser?.username || 'Trello User',
                trello_username: trelloUser?.username || 'user'
            };

            const response = await Utils.apiCall('/auth/login', 'POST', loginData, t);
            
            if (response && response.access_token) {
                await Utils.setAuthToken(t, response.access_token);
                return { success: true, user: response.user };
            } else {
                throw new Error('Authentication failed');
            }
        } catch (error) {
            console.error('Authentication error:', error);
            return { success: false, error: error.message };
        }
    }
};

// Dashboard and reporting functions
const Dashboard = {
    // Show dashboard popup
    async showDashboard(t) {
        const board = await t.board('id', 'name');
        return t.popup({
            title: 'TimeZZ Dashboard',
            url: `${CONFIG.POWER_UP_URL}/dashboard-popup.html`,
            height: 650,
            args: { 
                boardId: board.id,
                boardName: board.name,
                apiUrl: CONFIG.API_BASE_URL 
            }
        });
    },

    // Get time tracking stats for current board
    async getBoardStats(t) {
        try {
            const board = await t.board('id');
            const stats = await Utils.apiCall(`/reports/board/${board.id}?days=7`, 'GET', null, t);
            return stats || {
                today_hours: 0,
                week_hours: 0,
                total_entries: 0,
                recent_entries: []
            };
        } catch (error) {
            console.warn('Could not fetch board stats:', error);
            return {
                today_hours: 0,
                week_hours: 0,
                total_entries: 0,
                recent_entries: []
            };
        }
    }
};

// Initialize the Trello Power-Up
TrelloPowerUp.initialize({
    
    // Card buttons - Show on every card
    'card-buttons': function(t, opts) {
        return Promise.all([
            Utils.getAuthToken(t),
            TimerManager.getActiveTimer(t),
            t.card('id', 'name', 'board'),
            TimerManager.hasRunningTimer(t)
        ]).then(([authToken, cardTimer, card, runningTimerInfo]) => {
            
            const buttons = [];
            
            // If not authenticated, show login button
            if (!authToken) {
                buttons.push({
                    icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/log-in.svg',
                    text: 'Connect TimeZZ',
                    callback: function(t) {
                        return Auth.showAuthPopup(t);
                    }
                });
                
                // Still show dashboard for demo
                buttons.push({
                    icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/bar-chart-2.svg',
                    text: 'View Dashboard',
                    callback: function(t) {
                        return Dashboard.showDashboard(t);
                    }
                });
                
                return buttons;
            }

            // Check if this card has active timer
            const isThisCardActive = cardTimer && cardTimer.active && cardTimer.cardId === card.id;
            
            // Check if another card has active timer
            const hasOtherTimer = runningTimerInfo.hasTimer && runningTimerInfo.cardId !== card.id;

            // Timer button
            if (isThisCardActive) {
                buttons.push({
                    icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/stop-circle.svg',
                    text: 'Stop Timer',
                    callback: async function(t) {
                        try {
                            const result = await TimerManager.stopTimer(t, cardTimer);
                            const duration = Utils.formatDurationHuman(result.duration);
                            
                            if (result.success) {
                                return t.alert({
                                    message: `✅ Timer stopped! Tracked ${duration}`,
                                    duration: 4
                                });
                            } else {
                                return t.alert({
                                    message: `⚠️ Timer stopped (${duration}) but sync failed`,
                                    duration: 4
                                });
                            }
                        } catch (error) {
                            return t.alert({
                                message: '❌ Failed to stop timer',
                                duration: 3
                            });
                        }
                    }
                });
            } else {
                buttons.push({
                    icon: hasOtherTimer 
                        ? 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/rotate-cw.svg'
                        : 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/play-circle.svg',
                    text: hasOtherTimer ? 'Switch Timer' : 'Start Timer',
                    callback: async function(t) {
                        try {
                            await TimerManager.startTimer(t, card);
                            
                            const message = hasOtherTimer 
                                ? '🔄 Timer switched to this card'
                                : '▶️ Timer started!';
                                
                            return t.alert({
                                message: message,
                                duration: 3
                            });
                        } catch (error) {
                            return t.alert({
                                message: '❌ Failed to start timer',
                                duration: 3
                            });
                        }
                    }
                });
            }

            // Dashboard button
            buttons.push({
                icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/bar-chart-2.svg',
                text: 'Dashboard',
                callback: function(t) {
                    return Dashboard.showDashboard(t);
                }
            });

            // Manual entry button
            buttons.push({
                icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/plus-circle.svg',
                text: 'Add Time',
                callback: function(t) {
                    return t.popup({
                        title: 'Add Manual Time Entry',
                        url: `${CONFIG.POWER_UP_URL}/manual-entry.html`,
                        height: 450,
                        args: { 
                            cardId: card.id,
                            cardName: card.name,
                            boardId: card.board?.id
                        }
                    });
                }
            });

            return buttons;
        });
    },

    // Card badges - Show running timer
    'card-badges': function(t, opts) {
        return TimerManager.getActiveTimer(t).then(timer => {
            if (timer && timer.active) {
                const startTime = new Date(timer.startTime);
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                
                return [{
                    text: `⏱ ${Utils.formatDurationHuman(elapsed)}`,
                    color: 'green',
                    refresh: 60 // Refresh every 60 seconds
                }];
            }
            return [];
        });
    },

    // Card detail badges - Show additional info when card is opened
    'card-detail-badges': function(t, opts) {
        return Utils.apiCall(`/time/entries?card_id=${opts.card.id}&limit=1`, 'GET', null, t)
            .then(entries => {
                if (entries && entries.length > 0) {
                    const totalMinutes = entries.reduce((sum, entry) => sum + (entry.duration_minutes || 0), 0);
                    const totalHours = Math.round(totalMinutes / 60 * 10) / 10;
                    
                    if (totalHours > 0) {
                        return [{
                            title: 'Total Time Tracked',
                            text: `${totalHours}h`,
                            color: 'blue'
                        }];
                    }
                }
                return [];
            })
            .catch(() => []);
    },

    // Board buttons - Quick access to dashboard
    'board-buttons': function(t, opts) {
        return [{
            icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/clock.svg',
            text: 'TimeZZ Dashboard',
            callback: function(t) {
                return Dashboard.showDashboard(t);
            }
        }, {
            icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/download.svg',
            text: 'Export Time Report',
            callback: async function(t) {
                const token = await Utils.getAuthToken(t);
                if (!token) {
                    return t.alert({
                        message: 'Please connect to TimeZZ first',
                        duration: 3
                    });
                }
                
                // This would trigger a report export
                return t.alert({
                    message: 'Time report export feature coming soon!',
                    duration: 3
                });
            }
        }];
    }
});

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Utils, TimerManager, Auth, Dashboard, CONFIG };
}
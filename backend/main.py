from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
import logging
import os
from datetime import datetime
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TimeZZ - Professional Time Tracker", 
    version="1.0.0",
    description="Time tracking Power-Up for Trello"
)

# Enhanced CORS middleware - More permissive for Trello
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Trello requires wildcard for power-ups
    allow_credentials=False,  # Changed to False for wildcard origins
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Import routes only if database is available
database_available = False
try:
    from db import create_tables, get_db
    from routes import router
    database_available = True
    
    @app.on_event("startup")
    async def startup():
        try:
            logger.info("🚀 Starting TimeZZ Backend...")
            logger.info("Creating database tables...")
            if create_tables():
                logger.info("✅ Database tables created successfully")
            else:
                logger.info("⚠️ Running in demo mode - database not available")
        except Exception as e:
            logger.warning(f"⚠️ Database initialization failed: {e}")
            logger.info("✅ Running in demo mode")
    
    # Include API routes if available
    app.include_router(router, prefix="/api/v1")
    logger.info("✅ Database routes enabled")
    
except ImportError as e:
    logger.warning(f"⚠️ Database modules not available: {e}")
    logger.info("✅ Running in demo mode only")

# Enhanced CORS handling for all requests
@app.middleware("http")
async def cors_handler(request: Request, call_next):
    # Handle preflight requests
    if request.method == "OPTIONS":
        response = Response(status_code=200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Requested-With, Accept, Origin"
        response.headers["Access-Control-Max-Age"] = "3600"
        return response
    
    # Process normal requests
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"Request processing error: {e}")
        response = JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "message": str(e)}
        )
    
    # Add CORS headers to all responses
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Requested-With, Accept, Origin"
    
    return response

# Root endpoint with enhanced info
@app.get("/")
async def root():
    return {
        "status": "success",
        "message": "TimeZZ Backend API is running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "database": "connected" if database_available else "demo_mode",
        "endpoints": {
            "health": "/health",
            "powerup": "/trello-powerup.js",
            "manifest": "/manifest.json",
            "api": "/api/v1/health"
        }
    }

# Enhanced health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "TimeZZ Backend",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "cors": "enabled",
        "database": "connected" if database_available else "demo_mode",
        "environment": os.getenv("ENVIRONMENT", "production")
    }

# Fixed Trello Power-Up JavaScript - Properly escaped
@app.get("/trello-powerup.js")
async def serve_powerup_js():
    powerup_js = """/* global TrelloPowerUp */
console.log('🚀 TimeZZ Power-Up Loading...');

const CONFIG = {
    API_BASE_URL: 'https://timezz-backend.onrender.com',
    DASHBOARD_URL: 'https://timezz-frontend.onrender.com'
};

const Utils = {
    formatDuration: (seconds) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        if (hours > 0) {
            return hours + 'h ' + minutes + 'm';
        }
        return minutes + 'm';
    },
    
    async apiCall(endpoint, method = 'GET', data = null) {
        try {
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer demo_token'
                },
                mode: 'cors'
            };
            
            if (data && method !== 'GET') {
                options.body = JSON.stringify(data);
            }
            
            const response = await fetch(CONFIG.API_BASE_URL + '/api/v1' + endpoint, options);
            if (!response.ok) {
                throw new Error('API call failed: ' + response.status);
            }
            return await response.json();
        } catch (error) {
            console.warn('API call failed:', error);
            return null;
        }
    }
};

const TimerManager = {
    async getActiveTimer(t) {
        try {
            return await t.get('card', 'shared', 'timezz_timer');
        } catch (error) {
            console.warn('Failed to get timer:', error);
            return null;
        }
    },
    
    async startTimer(t, card) {
        try {
            // Stop any existing timer first
            const existingTimer = await TimerManager.getActiveTimer(t);
            if (existingTimer && existingTimer.active) {
                await TimerManager.stopTimer(t, existingTimer);
            }
            
            const timerData = {
                active: true,
                startTime: new Date().toISOString(),
                cardId: card.id,
                cardName: card.name
            };
            
            await t.set('card', 'shared', 'timezz_timer', timerData);
            
            // Sync with backend
            Utils.apiCall('/time/start', 'POST', {
                card_id: card.id,
                card_name: card.name,
                description: 'Started from Trello Power-Up'
            }).catch(err => console.warn('Backend sync failed:', err));
            
            return timerData;
        } catch (error) {
            console.error('Failed to start timer:', error);
            throw error;
        }
    },
    
    async stopTimer(t, timer) {
        try {
            const duration = Math.floor((new Date() - new Date(timer.startTime)) / 1000);
            await t.remove('card', 'shared', 'timezz_timer');
            
            // Sync with backend
            Utils.apiCall('/time/stop', 'POST').catch(err => console.warn('Backend sync failed:', err));
            
            return { duration };
        } catch (error) {
            console.error('Failed to stop timer:', error);
            throw error;
        }
    }
};

TrelloPowerUp.initialize({
    'card-buttons': function(t, opts) {
        return Promise.all([
            TimerManager.getActiveTimer(t),
            t.card('id', 'name')
        ]).then(([timer, card]) => {
            const isActive = timer && timer.active;
            
            return [
                {
                    icon: isActive 
                        ? 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/stop-circle.svg'
                        : 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/play-circle.svg',
                    text: isActive ? 'Stop Timer' : 'Start Timer',
                    callback: async function(t) {
                        try {
                            if (isActive) {
                                const result = await TimerManager.stopTimer(t, timer);
                                return t.alert({
                                    message: 'Timer stopped! Duration: ' + Utils.formatDuration(result.duration),
                                    duration: 4
                                });
                            } else {
                                await TimerManager.startTimer(t, card);
                                return t.alert({
                                    message: 'Timer started successfully!',
                                    duration: 3
                                });
                            }
                        } catch (error) {
                            console.error('Timer operation failed:', error);
                            return t.alert({
                                message: 'Timer operation failed. Please try again.',
                                duration: 3
                            });
                        }
                    }
                },
                {
                    icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/bar-chart-2.svg',
                    text: 'Dashboard',
                    callback: function(t) {
                        const dashboardHTML = `
                            <div style="padding:30px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;min-height:400px;">
                                <div style="text-align:center;margin-bottom:30px;">
                                    <h2 style="margin:0;font-size:24px;">TimeZZ Dashboard</h2>
                                    <p style="opacity:0.9;margin:10px 0 0 0;">Professional Time Tracking</p>
                                </div>
                                <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:30px;">
                                    <div style="background:rgba(255,255,255,0.1);padding:20px;border-radius:15px;text-align:center;backdrop-filter:blur(10px);">
                                        <div style="font-size:28px;font-weight:bold;margin-bottom:5px;">2.5h</div>
                                        <div style="font-size:14px;opacity:0.8;">Today</div>
                                    </div>
                                    <div style="background:rgba(255,255,255,0.1);padding:20px;border-radius:15px;text-align:center;backdrop-filter:blur(10px);">
                                        <div style="font-size:28px;font-weight:bold;margin-bottom:5px;">18.2h</div>
                                        <div style="font-size:14px;opacity:0.8;">This Week</div>
                                    </div>
                                </div>
                                <div style="background:rgba(255,255,255,0.1);padding:20px;border-radius:15px;backdrop-filter:blur(10px);margin-bottom:20px;">
                                    <h3 style="margin:0 0 15px 0;font-size:16px;">Recent Activity</h3>
                                    <div style="font-size:14px;opacity:0.9;line-height:1.6;">
                                        Design Homepage - 1h 30m<br>
                                        Fix Login Bug - 45m<br>
                                        Write Documentation - 2h 15m
                                    </div>
                                </div>
                                <div style="text-align:center;">
                                    <button onclick="window.open('${CONFIG.DASHBOARD_URL}', '_blank')" 
                                            style="background:rgba(255,255,255,0.2);color:white;border:2px solid rgba(255,255,255,0.3);padding:12px 24px;border-radius:25px;cursor:pointer;font-size:14px;backdrop-filter:blur(10px);">
                                        Open Full Dashboard
                                    </button>
                                </div>
                            </div>
                        `;
                        
                        return t.popup({
                            title: 'TimeZZ Dashboard',
                            url: 'data:text/html;charset=utf-8,' + encodeURIComponent(dashboardHTML),
                            height: 500
                        });
                    }
                },
                {
                    icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/plus-circle.svg',
                    text: 'Add Time',
                    callback: function(t) {
                        const addTimeHTML = `
                            <div style="padding:30px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
                                <h3 style="color:#0079bf;margin:0 0 20px 0;">Add Time Entry</h3>
                                <form onsubmit="addTimeEntry(event)" style="display:flex;flex-direction:column;gap:15px;">
                                    <div>
                                        <label style="display:block;margin-bottom:5px;font-weight:500;">Duration (minutes):</label>
                                        <input type="number" id="duration" required min="1" value="30" 
                                               style="width:100%;padding:10px;border:2px solid #e1e5e9;border-radius:8px;font-size:14px;">
                                    </div>
                                    <div>
                                        <label style="display:block;margin-bottom:5px;font-weight:500;">Description:</label>
                                        <textarea id="description" placeholder="What did you work on?" 
                                                  style="width:100%;padding:10px;border:2px solid #e1e5e9;border-radius:8px;font-size:14px;resize:vertical;height:80px;"></textarea>
                                    </div>
                                    <button type="submit" 
                                            style="background:#0079bf;color:white;border:none;padding:12px 20px;border-radius:8px;cursor:pointer;font-size:16px;font-weight:500;">
                                        Add Time Entry
                                    </button>
                                </form>
                                <script>
                                function addTimeEntry(event) {
                                    event.preventDefault();
                                    const duration = document.getElementById('duration').value;
                                    const description = document.getElementById('description').value;
                                    
                                    const successHTML = \`
                                        <div style="padding:30px;text-align:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
                                            <div style="color:#00875A;font-size:48px;margin-bottom:20px;">✅</div>
                                            <h3 style="color:#00875A;margin:0 0 10px 0;">Time Entry Added!</h3>
                                            <p style="color:#666;margin:0 0 20px 0;">Added \${duration} minutes</p>
                                            <button onclick="window.close()" 
                                                    style="background:#0079bf;color:white;border:none;padding:10px 20px;border-radius:6px;cursor:pointer;">
                                                Close
                                            </button>
                                        </div>
                                    \`;
                                    
                                    document.body.innerHTML = successHTML;
                                }
                                </script>
                            </div>
                        `;
                        
                        return t.popup({
                            title: 'Add Manual Time Entry',
                            url: 'data:text/html;charset=utf-8,' + encodeURIComponent(addTimeHTML),
                            height: 350
                        });
                    }
                }
            ];
        }).catch(error => {
            console.error('Error loading card buttons:', error);
            return [{
                icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/alert-circle.svg',
                text: 'TimeZZ Error',
                callback: function(t) {
                    return t.alert({
                        message: 'TimeZZ failed to load. Please refresh and try again.',
                        duration: 4
                    });
                }
            }];
        });
    },
    
    'card-badges': function(t, opts) {
        return TimerManager.getActiveTimer(t).then(timer => {
            if (timer && timer.active) {
                const elapsed = Math.floor((Date.now() - new Date(timer.startTime)) / 1000);
                return [{
                    text: 'Timer: ' + Utils.formatDuration(elapsed),
                    color: 'green',
                    refresh: 30
                }];
            }
            return [];
        }).catch(() => []);
    },
    
    'board-buttons': function(t, opts) {
        return [{
            icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/activity.svg',
            text: 'TimeZZ Overview',
            callback: function(t) {
                const overviewHTML = `
                    <div style="padding:30px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#f5f7fa 0%,#c3cfe2 100%);min-height:500px;">
                        <div style="text-align:center;margin-bottom:30px;">
                            <h2 style="color:#2c3e50;margin:0;font-size:28px;">Board Overview</h2>
                            <p style="color:#666;margin:10px 0 0 0;">Time tracking statistics for this board</p>
                        </div>
                        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:20px;margin-bottom:30px;">
                            <div style="background:white;padding:25px;border-radius:15px;text-align:center;box-shadow:0 4px 15px rgba(0,0,0,0.1);">
                                <div style="font-size:32px;font-weight:bold;color:#667eea;margin-bottom:8px;">8.5h</div>
                                <div style="color:#666;font-size:14px;text-transform:uppercase;letter-spacing:0.5px;">Total Time</div>
                            </div>
                            <div style="background:white;padding:25px;border-radius:15px;text-align:center;box-shadow:0 4px 15px rgba(0,0,0,0.1);">
                                <div style="font-size:32px;font-weight:bold;color:#4CAF50;margin-bottom:8px;">12</div>
                                <div style="color:#666;font-size:14px;text-transform:uppercase;letter-spacing:0.5px;">Entries</div>
                            </div>
                            <div style="background:white;padding:25px;border-radius:15px;text-align:center;box-shadow:0 4px 15px rgba(0,0,0,0.1);">
                                <div style="font-size:32px;font-weight:bold;color:#FF9800;margin-bottom:8px;">$680</div>
                                <div style="color:#666;font-size:14px;text-transform:uppercase;letter-spacing:0.5px;">Earnings</div>
                            </div>
                        </div>
                        <div style="text-align:center;">
                            <button onclick="window.open('${CONFIG.DASHBOARD_URL}', '_blank')" 
                                    style="background:linear-gradient(45deg,#667eea,#764ba2);color:white;border:none;padding:15px 30px;border-radius:25px;cursor:pointer;font-size:16px;font-weight:500;box-shadow:0 4px 15px rgba(102,126,234,0.3);">
                                Open Full Dashboard
                            </button>
                        </div>
                    </div>
                `;
                
                return t.popup({
                    title: 'Board Time Overview',
                    url: 'data:text/html;charset=utf-8,' + encodeURIComponent(overviewHTML),
                    height: 400
                });
            }
        }];
    }
});

console.log('✅ TimeZZ Power-Up initialized successfully!');"""
    
    return PlainTextResponse(
        content=powerup_js,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# Enhanced manifest
@app.get("/manifest.json")
async def serve_manifest():
    manifest = {
        "name": "TimeZZ - Professional Time Tracking",
        "details": "Track time seamlessly on your Trello cards with powerful reporting and analytics. Start and stop timers directly from your cards, view comprehensive dashboards, and export detailed reports.",
        "author": "TimeZZ Team",
        "capabilities": [
            "card-buttons",
            "card-badges", 
            "card-detail-badges",
            "board-buttons"
        ],
        "connectors": {
            "iframe": {
                "url": "https://timezz-backend.onrender.com/trello-powerup.js"
            }
        },
        "icon": {
            "url": "https://cdn.jsdelivr.net/gh/feathericons/feather/icons/clock.svg"
        },
        "tags": ["productivity", "time-tracking", "reporting", "analytics"],
        "moderator_notes": "TimeZZ helps teams track time spent on Trello cards with professional reporting features."
    }
    
    return JSONResponse(
        content=manifest,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Content-Type": "application/json; charset=utf-8"
        }
    )

# Enhanced demo API endpoints
@app.get("/api/v1/health")
async def api_health():
    return {
        "status": "healthy", 
        "mode": "demo" if not database_available else "production",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/time/start")
async def demo_start_timer(request: Request):
    try:
        data = await request.json()
        logger.info(f"Timer started for card: {data.get('card_name', 'Unknown')}")
        return {
            "success": True,
            "message": "Timer started successfully",
            "card_name": data.get("card_name", "Unknown Card"),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Start timer error: {e}")
        return {
            "success": True, 
            "message": "Timer started (demo mode)",
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/v1/time/stop") 
async def demo_stop_timer():
    logger.info("Timer stopped")
    return {
        "success": True,
        "message": "Timer stopped successfully",
        "duration_minutes": 25,
        "duration_hours": 0.42,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/v1/reports/detailed")
async def demo_detailed_report():
    return {
        "period_days": 30,
        "total_hours": 42.5,
        "total_minutes": 2550,
        "total_entries": 28,
        "total_amount": 850.0,
        "today_hours": 3.2,
        "week_hours": 18.7,
        "daily_average": 1.4,
        "board_breakdown": [
            {
                "board_id": "demo_board_1",
                "total_minutes": 1200,
                "total_entries": 15,
                "total_amount": 400.0
            }
        ],
        "recent_entries": [
            {
                "id": 1,
                "card_name": "Fix login issues",
                "duration_hours": 2.5,
                "created_at": datetime.now().isoformat()
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting TimeZZ Backend on port {port}")
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=port,
        reload=False,
        log_level="info"
    )
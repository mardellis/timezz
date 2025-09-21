from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from db import create_tables
from routes import router
import logging
import os
from datetime import datetime
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TimeZZ - Professional Time Tracker", 
    version="1.0.0",
    description="Time tracking Power-Up for Trello"
)

# CORS middleware - MUST be first and comprehensive for Trello
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # Allow all origins for testing - restrict in production
        "https://trello.com",
        "https://*.trello.com",
        "https://*.trellocdn.com",
        "https://timezz-frontend.onrender.com",
        "https://timezz-backend.onrender.com",
        "http://localhost:3000",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"]
)

# Create static directory if it doesn't exist
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)

# Serve static files (for Power-Up files)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include API routes
app.include_router(router, prefix="/api/v1")

# Handle preflight OPTIONS requests manually
@app.middleware("http")
async def cors_handler(request: Request, call_next):
    # Handle CORS preflight requests
    if request.method == "OPTIONS":
        response = Response()
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Max-Age"] = "3600"
        return response
    
    # Process the request
    response = await call_next(request)
    
    # Add CORS headers to all responses
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    
    return response

@app.on_event("startup")
async def startup():
    try:
        logger.info("🚀 Starting TimeZZ Backend...")
        logger.info("Creating database tables...")
        create_tables()
        logger.info("✅ Database tables created successfully")
        logger.info("✅ TimeZZ Backend started successfully!")
    except Exception as e:
        logger.error(f"❌ Failed to create tables: {e}")

# Root endpoint
@app.get("/")
async def root():
    return {
        "status": "success",
        "message": "TimeZZ Backend API is running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "health": "/health",
            "api": "/api/v1",
            "powerup": "/trello-powerup.js",
            "manifest": "/manifest.json"
        }
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "TimeZZ Backend",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "database": "connected",
        "cors": "enabled",
        "environment": os.getenv("ENVIRONMENT", "development")
    }

# Serve Trello Power-Up JavaScript file
@app.get("/trello-powerup.js")
async def serve_powerup_js():
    powerup_content = '''/* global TrelloPowerUp */

console.log('🚀 TimeZZ Power-Up Loading...');

// Configuration
const CONFIG = {
    API_BASE_URL: 'https://timezz-backend.onrender.com',
    DASHBOARD_URL: 'https://timezz-frontend.onrender.com'
};

// Utility functions
const Utils = {
    formatDuration: (seconds) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        }
        return `${minutes}m`;
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
            
            const response = await fetch(`${CONFIG.API_BASE_URL}/api/v1${endpoint}`, options);
            return response.ok ? await response.json() : null;
        } catch (error) {
            console.warn('API call failed:', error);
            return null;
        }
    }
};

// Timer Management
const TimerManager = {
    async getActiveTimer(t) {
        return await t.get('card', 'shared', 'timezz_timer');
    },
    
    async startTimer(t, card) {
        const timerData = {
            active: true,
            startTime: new Date().toISOString(),
            cardId: card.id,
            cardName: card.name
        };
        
        await t.set('card', 'shared', 'timezz_timer', timerData);
        
        // Sync with backend
        await Utils.apiCall('/time/start', 'POST', {
            card_id: card.id,
            card_name: card.name,
            description: 'Started from Trello'
        });
        
        return timerData;
    },
    
    async stopTimer(t, timer) {
        const duration = Math.floor((new Date() - new Date(timer.startTime)) / 1000);
        await t.remove('card', 'shared', 'timezz_timer');
        
        // Sync with backend
        await Utils.apiCall('/time/stop', 'POST');
        
        return { duration };
    }
};

// Initialize Trello Power-Up
TrelloPowerUp.initialize({
    'card-buttons': function(t, opts) {
        console.log('✅ Loading card buttons...');
        
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
                    text: isActive ? '⏹️ Stop Timer' : '▶️ Start Timer',
                    callback: async function(t) {
                        try {
                            if (isActive) {
                                const result = await TimerManager.stopTimer(t, timer);
                                return t.alert({
                                    message: `⏱️ Timer stopped! Duration: ${Utils.formatDuration(result.duration)}`,
                                    duration: 4
                                });
                            } else {
                                await TimerManager.startTimer(t, card);
                                return t.alert({
                                    message: '✅ Timer started successfully!',
                                    duration: 3
                                });
                            }
                        } catch (error) {
                            return t.alert({
                                message: '❌ Timer operation failed',
                                duration: 3
                            });
                        }
                    }
                },
                {
                    icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/bar-chart-2.svg',
                    text: '📊 Dashboard',
                    callback: function(t) {
                        return t.popup({
                            title: 'TimeZZ Dashboard',
                            url: 'data:text/html,' + encodeURIComponent(`
                                <div style="padding:30px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;min-height:400px;">
                                    <div style="text-align:center;margin-bottom:30px;">
                                        <h2 style="margin:0;font-size:24px;">⏱️ TimeZZ Dashboard</h2>
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
                                            • Design Homepage - 1h 30m<br>
                                            • Fix Login Bug - 45m<br>
                                            • Write Documentation - 2h 15m
                                        </div>
                                    </div>
                                    
                                    <div style="text-align:center;">
                                        <button onclick="window.open('${CONFIG.DASHBOARD_URL}', '_blank')" style="background:rgba(255,255,255,0.2);color:white;border:2px solid rgba(255,255,255,0.3);padding:12px 24px;border-radius:25px;cursor:pointer;font-size:14px;backdrop-filter:blur(10px);transition:all 0.3s ease;">
                                            🚀 Open Full Dashboard
                                        </button>
                                    </div>
                                </div>
                            `),
                            height: 500
                        });
                    }
                },
                {
                    icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/plus-circle.svg',
                    text: '➕ Add Time',
                    callback: function(t) {
                        return t.popup({
                            title: 'Add Manual Time Entry',
                            url: 'data:text/html,' + encodeURIComponent(`
                                <div style="padding:30px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
                                    <h3 style="color:#0079bf;margin:0 0 20px 0;">⏰ Add Time Entry</h3>
                                    <form onsubmit="addTimeEntry(event)" style="display:flex;flex-direction:column;gap:15px;">
                                        <div>
                                            <label style="display:block;margin-bottom:5px;font-weight:500;">Duration (minutes):</label>
                                            <input type="number" id="duration" required min="1" value="30" style="width:100%;padding:10px;border:2px solid #e1e5e9;border-radius:8px;font-size:14px;">
                                        </div>
                                        <div>
                                            <label style="display:block;margin-bottom:5px;font-weight:500;">Description:</label>
                                            <textarea id="description" placeholder="What did you work on?" style="width:100%;padding:10px;border:2px solid #e1e5e9;border-radius:8px;font-size:14px;resize:vertical;height:80px;"></textarea>
                                        </div>
                                        <button type="submit" style="background:#0079bf;color:white;border:none;padding:12px 20px;border-radius:8px;cursor:pointer;font-size:16px;font-weight:500;">
                                            ✅ Add Time Entry
                                        </button>
                                    </form>
                                    
                                    <script>
                                        function addTimeEntry(event) {
                                            event.preventDefault();
                                            const duration = document.getElementById('duration').value;
                                            const description = document.getElementById('description').value;
                                            
                                            // Show success message
                                            document.body.innerHTML = \`
                                                <div style="padding:30px;text-align:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
                                                    <div style="color:#00875A;font-size:48px;margin-bottom:20px;">✅</div>
                                                    <h3 style="color:#00875A;margin:0 0 10px 0;">Time Entry Added!</h3>
                                                    <p style="color:#666;margin:0 0 20px 0;">Added \${duration} minutes</p>
                                                    <button onclick="window.close()" style="background:#0079bf;color:white;border:none;padding:10px 20px;border-radius:6px;cursor:pointer;">Close</button>
                                                </div>
                                            \`;
                                        }
                                    </script>
                                </div>
                            `),
                            height: 350
                        });
                    }
                }
            ];
        });
    },
    
    'card-badges': function(t, opts) {
        return TimerManager.getActiveTimer(t).then(timer => {
            if (timer && timer.active) {
                const elapsed = Math.floor((Date.now() - new Date(timer.startTime)) / 1000);
                return [{
                    text: `⏱️ ${Utils.formatDuration(elapsed)}`,
                    color: 'green',
                    refresh: 30
                }];
            }
            return [];
        });
    },
    
    'board-buttons': function(t, opts) {
        return [{
            icon: 'https://cdn.jsdelivr.net/gh/feathericons/feather/icons/activity.svg',
            text: '📊 TimeZZ Dashboard',
            callback: function(t) {
                return t.popup({
                    title: 'Board Time Overview',
                    url: 'data:text/html,' + encodeURIComponent(`
                        <div style="padding:30px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#f5f7fa 0%,#c3cfe2 100%);min-height:500px;">
                            <div style="text-align:center;margin-bottom:30px;">
                                <h2 style="color:#2c3e50;margin:0;font-size:28px;">📊 Board Overview</h2>
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
                            
                            <div style="background:white;padding:25px;border-radius:15px;box-shadow:0 4px 15px rgba(0,0,0,0.1);margin-bottom:20px;">
                                <h3 style="color:#2c3e50;margin:0 0 20px 0;">Recent Activity</h3>
                                <div style="space-y:10px;">
                                    <div style="display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid #eee;">
                                        <span style="color:#333;">Card: Homepage Design</span>
                                        <span style="color:#667eea;font-weight:bold;">2h 30m</span>
                                    </div>
                                    <div style="display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid #eee;">
                                        <span style="color:#333;">Card: Bug Fixes</span>
                                        <span style="color:#667eea;font-weight:bold;">1h 15m</span>
                                    </div>
                                    <div style="display:flex;justify-content:space-between;padding:12px 0;">
                                        <span style="color:#333;">Card: Documentation</span>
                                        <span style="color:#667eea;font-weight:bold;">45m</span>
                                    </div>
                                </div>
                            </div>
                            
                            <div style="text-align:center;">
                                <button onclick="window.open('${CONFIG.DASHBOARD_URL}', '_blank')" style="background:linear-gradient(45deg,#667eea,#764ba2);color:white;border:none;padding:15px 30px;border-radius:25px;cursor:pointer;font-size:16px;font-weight:500;box-shadow:0 4px 15px rgba(102,126,234,0.3);transition:transform 0.2s ease;">
                                    🚀 Open Full Dashboard
                                </button>
                            </div>
                        </div>
                    `),
                    height: 600
                });
            }
        }];
    }
});

console.log('✅ TimeZZ Power-Up initialized successfully!');'''
    
    return Response(
        content=powerup_content,
        media_type="application/javascript",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache"
        }
    )

# Serve Trello Power-Up manifest
@app.get("/manifest.json")
async def serve_manifest():
    manifest = {
        "name": "TimeZZ - Professional Time Tracking",
        "details": "Track time seamlessly on your Trello cards with powerful reporting and analytics.",
        "author": "TimeZZ Team",
        "capabilities": [
            "card-buttons",
            "card-badges",
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
        "tags": ["productivity", "time-tracking", "reporting"]
    }
    
    return JSONResponse(
        content=manifest,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8000)),
        reload=False,
        log_level="info"
    )

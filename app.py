from flask import Flask, render_template, request, session, jsonify
import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import hashlib



from dotenv import load_dotenv
load_dotenv()

# Get API key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
print(f"🔑 API Key loaded: {'Yes' if GEMINI_API_KEY else 'No'}")

# Initialize Flask
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())

# Crypto database
crypto_db = {
    "Bitcoin": {
        "price_trend": "rising",
        "market_cap": "high",
        "energy_use": "high",
        "sustainability_score": 3,
        "sentiment": "bullish",
        "category": "Store of Value"
    },
    "Ethereum": {
        "price_trend": "stable",
        "market_cap": "high",
        "energy_use": "medium",
        "sustainability_score": 6,
        "sentiment": "neutral",
        "category": "Smart Contracts"
    },
    "Cardano": {
        "price_trend": "rising",
        "market_cap": "medium",
        "energy_use": "low",
        "sustainability_score": 8,
        "sentiment": "bullish",
        "category": "Proof of Stake"
    },
    "Solana": {
        "price_trend": "volatile",
        "market_cap": "high",
        "energy_use": "low",
        "sustainability_score": 7,
        "sentiment": "mixed",
        "category": "High Throughput"
    },
    "Polkadot": {
        "price_trend": "stable",
        "market_cap": "medium",
        "energy_use": "low",
        "sustainability_score": 8,
        "sentiment": "neutral",
        "category": "Interoperability"
    }
}

# Database functions
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('cryptopal.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_session_id ON conversations(session_id)')
    
    conn.commit()
    conn.close()
    print("💾 Database initialized")

init_db()

def get_session_id():
    """Get or create session ID"""
    if 'session_id' not in session:
        session['session_id'] = hashlib.md5(os.urandom(32)).hexdigest()[:16]
    return session['session_id']

def save_message(session_id, role, content):
    """Save message to database"""
    conn = sqlite3.connect('cryptopal.db', check_same_thread=False)
    c = conn.cursor()
    c.execute(
        'INSERT INTO conversations (session_id, role, content) VALUES (?, ?, ?)',
        (session_id, role, content)
    )
    conn.commit()
    conn.close()

def get_messages(session_id, limit=20):
    """Get messages from database"""
    conn = sqlite3.connect('cryptopal.db', check_same_thread=False)
    c = conn.cursor()
    c.execute(
        'SELECT role, content, timestamp FROM conversations WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?',
        (session_id, limit)
    )
    rows = c.fetchall()

    messages = []
    for row in rows:
        role, content, ts = row[0], row[1], row[2]
        # Normalize timestamp to use 'T' (ISO format) so templates can safely split('T')
        if ts:
            try:
                if isinstance(ts, str):
                    if 'T' not in ts and ' ' in ts:
                        ts = ts.replace(' ', 'T')
                else:
                    ts = datetime.fromisoformat(str(ts)).isoformat()
            except Exception:
                ts = str(ts)
        messages.append({'role': role, 'content': content, 'timestamp': ts})
    conn.close()
    return messages

def clear_messages(session_id):
    """Clear messages for session"""
    conn = sqlite3.connect('cryptopal.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('DELETE FROM conversations WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

# Gemini AI functions
def get_available_models():
    """Get available Gemini models"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        models = genai.list_models()
        
        # Filter for text generation models
        text_models = []
        for model in models:
            if 'gemini' in model.name.lower() and 'generateContent' in model.supported_generation_methods:
                text_models.append(model.name)
        
        return text_models
    except Exception as e:
        print(f"Error getting models: {str(e)}")
        return []

def test_gemini_key(api_key):
    """Test if Gemini API key works"""
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        
        # Get available models
        models = get_available_models()
        print(f"🤖 Available Gemini models: {models[:5]}...")  
        
        if not models:
            print("❌ No Gemini models found")
            return False
        
        #
        try_model = None
        preferred_models = [
            'models/gemini-2.0-flash',
            'models/gemini-2.0-flash-001',
            'models/gemini-flash-latest',
            'models/gemini-2.5-flash',
            'models/gemini-pro-latest'
        ]
        
        for model_name in preferred_models:
            if model_name in models:
                try_model = model_name
                break
        
        if not try_model and models:
            try_model = models[0]  
        
        print(f"✅ Testing with model: {try_model}")
        
        model = genai.GenerativeModel(try_model)
        response = model.generate_content(
            "Hello",
            safety_settings={
                'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
                'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
                'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
            }
        )
        
        print(f"✅ Gemini API test successful")
        print(f"   Model: {try_model}")
        print(f"   Response: {response.text[:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ Gemini API test failed: {str(e)}")
        return False

def get_gemini_response(user_query, conversation_history):
    """Get response from Gemini AI"""
    try:
        if not GEMINI_API_KEY:
            return "🔑 **API Key Required**\n\nPlease add your Gemini API key to the `.env` file.\n\nGet a free key: https://aistudio.google.com/app/apikey"
        
        import google.generativeai as genai
        
        genai.configure(api_key=GEMINI_API_KEY)
        
        
        models = get_available_models()
        if not models:
            return "❌ No Gemini models available. Please check your API key."
        
        
        chosen_model = None
        preferred_models = [
            'models/gemini-2.0-flash',
            'models/gemini-2.0-flash-001',
            'models/gemini-flash-latest',
            'models/gemini-2.5-flash',
            'models/gemini-pro-latest'
        ]
        
        for model_name in preferred_models:
            if model_name in models:
                chosen_model = model_name
                break
        
        if not chosen_model:
            chosen_model = models[0]  
        
        print(f"🤖 Using model: {chosen_model}")
        
        # Create model
        model = genai.GenerativeModel(chosen_model)
        
        # Build conversation context
        context = "Previous conversation:\n"
        for msg in conversation_history[-6:]:
            speaker = "User" if msg['role'] == 'user' else "Assistant"
            context += f"{speaker}: {msg['content']}\n"
        
        # Create prompt
        prompt = f"""You are CryptoPal AI, a cryptocurrency investment advisor.

Current Crypto Data:
{json.dumps(crypto_db, indent=2)}

Date: {datetime.now().strftime('%Y-%m-%d')}

{context}

User: {user_query}

"""

        # Generate response
        response = model.generate_content(
            prompt,
            generation_config={
                'temperature': 0.7,
                'top_p': 0.9,
                'top_k': 40,
                'max_output_tokens': 1024,
            },
            safety_settings=[
                {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_NONE'},
            ]
        )
        
        return response.text
        
    except Exception as e:
        print(f"Gemini API Error: {str(e)}")
        return get_fallback_response(user_query)

def get_fallback_response(user_query):
    """Fallback responses when Gemini is unavailable"""
    query_lower = user_query.lower()
    
    responses = {
        "hello": "👋 Hello! I'm CryptoPal AI. I can help you with crypto investment advice, market analysis, and more. What interests you about cryptocurrencies?",
        "sustain": "🌱 **Sustainable Cryptos**:\n• Cardano (8/10) - Energy-efficient\n• Polkadot (8/10) - Eco-friendly\n• Solana (7/10) - Low energy use\n\nWhat aspect of sustainability interests you?",
        "trend": "📈 **Current Trends**:\n• Bitcoin - Rising as digital gold\n• Cardano - Growing adoption\n• Market - Cautiously optimistic\n\nWant analysis on specific coins?",
        "profit": "💰 **Profit Potential**:\n• Short-term: Trading opportunities\n• Long-term: BTC, ETH fundamentals\n• Diversify across sectors\n\nWhat's your investment horizon?",
        "risk": "⚠️ **Risk Levels**:\n• High: New tokens\n• Medium: Mid-cap coins\n• Lower: Established projects\n\nWhat's your risk tolerance?",
        "beginner": "🎯 **For Beginners**:\n1. Start with Bitcoin/ETH\n2. Learn security basics\n3. Use dollar-cost averaging\n4. Stay informed\n\nWhat's your main goal?",
        "bitcoin": "₿ **Bitcoin**:\n• Category: Store of Value\n• Trend: Rising\n• Sustainability: 3/10\n• Energy: High (PoW)\n• Sentiment: Bullish\n\nWant to compare with other coins?",
        "ethereum": "Ξ **Ethereum**:\n• Category: Smart Contracts\n• Trend: Stable\n• Sustainability: 6/10\n• Energy: Medium\n• Sentiment: Neutral\n\nInterested in Ethereum upgrades?",
        "cardano": "ADA **Cardano**:\n• Category: Proof of Stake\n• Trend: Rising\n• Sustainability: 8/10\n• Energy: Low\n• Sentiment: Bullish\n\nWant details on Cardano projects?",
    }
    
    for keyword, response in responses.items():
        if keyword in query_lower:
            return response
    
    
    for coin in crypto_db.keys():
        if coin.lower() in query_lower:
            data = crypto_db[coin]
            return f"""🔍 **{coin}**:
• Category: {data['category']}
• Trend: {data['price_trend'].title()}
• Sustainability: {data['sustainability_score']}/10
• Energy: {data['energy_use'].title()}
• Sentiment: {data['sentiment'].title()}

What would you like to know about {coin}?"""
    
    return f"""🤔 I understand you're asking about: "{user_query}"

Based on current crypto data:
• Market offers mixed opportunities
• Sustainable coins gaining traction
• Bitcoin maintains dominance

💡 **Suggestions**:
1. Research before investing
2. Consider sustainability
3. Diversify your portfolio

⚠️ **Remember**: Crypto is volatile. Invest responsibly.

What specific aspect would you like to explore?"""

# Routes
@app.route("/", methods=["GET", "POST"])
def index():
    """Main page"""
    session_id = get_session_id()
    
    # Get conversation
    messages = get_messages(session_id)
    
    # Add welcome if empty
    if not messages:
        welcome_msg = "Hello! I'm CryptoPal AI, your cryptocurrency investment advisor. How can I help you today? 💎"
        save_message(session_id, 'assistant', welcome_msg)
        messages = [{'role': 'assistant', 'content': welcome_msg, 'timestamp': datetime.now().isoformat()}]
    
    # Handle form submission
    if request.method == "POST":
        user_query = request.form.get("query", "").strip()
        if user_query:
            save_message(session_id, 'user', user_query)
            history = get_messages(session_id)
            ai_response = get_gemini_response(user_query, history)
            save_message(session_id, 'assistant', ai_response)
            messages = get_messages(session_id)
    
    # Check Gemini status
    gemini_configured = False
    if GEMINI_API_KEY:
        gemini_configured = test_gemini_key(GEMINI_API_KEY)
    
    return render_template(
        "index.html",
        conversation=messages,
        gemini_configured=gemini_configured
    )

@app.route("/clear", methods=["POST"])
def clear_chat():
    """Clear chat"""
    session_id = get_session_id()
    clear_messages(session_id)
    
    welcome_msg = "Chat cleared! How can I help you with cryptocurrencies today? 💎"
    save_message(session_id, 'assistant', welcome_msg)
    
    return jsonify({"status": "success"})

@app.route("/api/chat", methods=["POST"])
def chat_api():
    """API endpoint for AJAX"""
    try:
        data = request.get_json()
        user_query = data.get('message', '').strip()
        
        if not user_query:
            return jsonify({"error": "No message"}), 400
        
        session_id = get_session_id()
        
        save_message(session_id, 'user', user_query)
        history = get_messages(session_id)
        ai_response = get_gemini_response(user_query, history)
        save_message(session_id, 'assistant', ai_response)
        
        return jsonify({
            "response": ai_response,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Chat API Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/status")
def status():
    """Check API status"""
    gemini_valid = False
    if GEMINI_API_KEY:
        gemini_valid = test_gemini_key(GEMINI_API_KEY)
    
    return jsonify({
        "gemini_configured": gemini_valid,
        "database": "connected",
        "cryptos_loaded": len(crypto_db)
    })

@app.route("/api/models")
def list_models():
    """List available models"""
    models = get_available_models()
    return jsonify({"models": models})

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 CRYPTOPAL AI - Starting Server")
    print("="*60)
    
    if GEMINI_API_KEY:
        print(f"🔑 API Key found: {GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-4:]}")
        is_valid = test_gemini_key(GEMINI_API_KEY)
        if is_valid:
            print("✅ Gemini API: Ready")
        else:
            print("⚠️  Gemini API: Some issues detected, but fallback mode available")
    else:
        print("⚠️  No API key found")
        print("   Create .env file with: GEMINI_API_KEY=your_key_here")
        print("   Get free key: https://aistudio.google.com/app/apikey")
    
    print(f"📊 Crypto database: {len(crypto_db)} coins")
    print(f"🌐 Starting at: http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
# app.py - Railway Optimized Version
import os
from flask import Flask, request, jsonify, render_template_string, send_from_directory, Response
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import json
import logging
from datetime import datetime, timedelta
import time
import random
import string
import requests
import re
from werkzeug.utils import secure_filename

# ==================== 1. RAILWAY CONFIGURATION ====================
# Get from Railway Environment Variables
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8295150408:AAF1P_IcRG-z8L54PNzZVFKNXts0Uwy0TtY')
ADMIN_ID = os.environ.get('ADMIN_ID', '8435248854')
BASE_URL = os.environ.get('BASE_URL', 'https://flask-production-04ac.up.railway.app')
PORT = int(os.environ.get('PORT', 8080))

# Directory Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

# File Paths
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
WITHDRAWALS_FILE = os.path.join(DATA_DIR, "withdrawals.json")
GIFTS_FILE = os.path.join(DATA_DIR, "gifts.json")
LEADERBOARD_FILE = os.path.join(DATA_DIR, "leaderboard.json")

# Logging for Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# App Setup
app = Flask(__name__, static_folder=STATIC_DIR)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Initialize Bot
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Ensure Directories
for d in [DATA_DIR, STATIC_DIR, UPLOAD_FOLDER]:
    os.makedirs(d, exist_ok=True)

# Initialize default files
def init_default_files():
    default_files = {
        USERS_FILE: {},
        SETTINGS_FILE: {
            "bot_name": "CYBER EARN ULTIMATE",
            "min_withdrawal": 100.0,
            "welcome_bonus": 50.0,
            "channels": [],
            "admins": [],
            "auto_withdraw": False,
            "bots_disabled": False,
            "ignore_device_check": False,
            "withdraw_disabled": False,
            "logo_filename": "logo_default.png",
            "min_refer_reward": 10.0,
            "max_refer_reward": 50.0
        },
        WITHDRAWALS_FILE: [],
        GIFTS_FILE: [],
        LEADERBOARD_FILE: {"last_updated": "2000-01-01", "data": []}
    }
    
    for filepath, default_data in default_files.items():
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=4)
            logger.info(f"Created default file: {filepath}")

# Run initialization
init_default_files()

# ==================== 2. DATA MANAGEMENT ====================
def load_json(filepath, default):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
        return default

def save_json(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving {filepath}: {e}")
        return False

def get_settings():
    defaults = {
        "bot_name": "CYBER EARN ULTIMATE",
        "min_withdrawal": 100.0,
        "welcome_bonus": 50.0,
        "channels": [],
        "admins": [],
        "auto_withdraw": False,
        "bots_disabled": False,
        "ignore_device_check": False,
        "withdraw_disabled": False,
        "logo_filename": "logo_default.png",
        "min_refer_reward": 10.0,
        "max_refer_reward": 50.0
    }
    current = load_json(SETTINGS_FILE, defaults)
    for k, v in defaults.items():
        if k not in current:
            current[k] = v
    return current

def is_admin(user_id):
    s = get_settings()
    uid = str(user_id)
    return uid == str(ADMIN_ID) or uid in s.get('admins', [])

# ==================== 3. UTILS ====================
def safe_send_message(chat_id, text, reply_markup=None):
    try:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Send Error {chat_id}: {e}")

def get_user_full_name(user):
    name_parts = []
    if user.first_name:
        name_parts.append(user.first_name)
    if user.last_name:
        name_parts.append(user.last_name)
    return " ".join(name_parts) if name_parts else "User"

def generate_code(length=5):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_refer_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))

def update_leaderboard():
    try:
        users = load_json(USERS_FILE, {})
        leaderboard = []
        
        for uid, user_data in users.items():
            leaderboard.append({
                "user_id": uid,
                "name": user_data.get("name", "Unknown"),
                "balance": float(user_data.get("balance", 0)),
                "total_refers": len(user_data.get("referred_users", []))
            })
        
        leaderboard.sort(key=lambda x: x["balance"], reverse=True)
        leaderboard = leaderboard[:20]
        
        data = {"last_updated": datetime.now().isoformat(), "data": leaderboard}
        save_json(LEADERBOARD_FILE, data)
        return data
    except Exception as e:
        logger.error(f"Error updating leaderboard: {e}")
        return {"last_updated": datetime.now().isoformat(), "data": []}

def check_gift_code_expiry():
    gifts = load_json(GIFTS_FILE, [])
    updated = False
    current_time = datetime.now()
    
    for gift in gifts[:]:
        if "expiry" in gift:
            try:
                expiry_time = datetime.fromisoformat(gift["expiry"])
                if expiry_time < current_time:
                    gift["expired"] = True
                    updated = True
            except:
                pass
    
    if updated:
        save_json(GIFTS_FILE, gifts)
    return gifts

# Custom Jinja2 filter for datetime parsing
def datetime_from_isoformat(value):
    try:
        return datetime.fromisoformat(value)
    except:
        return datetime.now()

app.jinja_env.filters['fromisoformat'] = datetime_from_isoformat

# ==================== 4. BOT HANDLERS ====================
@bot.chat_join_request_handler()
def auto_approve(message):
    try:
        bot.approve_chat_join_request(message.chat.id, message.from_user.id)
    except Exception as e:
        logger.error(f"Auto approve error: {e}")

@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        settings = get_settings()
        uid = str(message.from_user.id)
        
        if settings['bots_disabled'] and not is_admin(uid):
            safe_send_message(message.chat.id, "⛔ *System Maintenance*")
            return
        
        refer_code = None
        if len(message.text.split()) > 1:
            refer_code = message.text.split()[1]
        
        users = load_json(USERS_FILE, {})
        is_new = uid not in users
        
        if is_new:
            user_refer_code = generate_refer_code()
            while any(user.get('refer_code') == user_refer_code for user in users.values()):
                user_refer_code = generate_refer_code()
            
            full_name = get_user_full_name(message.from_user)
            users[uid] = {
                "balance": 0.0,
                "verified": False,
                "name": full_name,
                "joined_date": datetime.now().isoformat(),
                "ip": None,
                "device_id": None,
                "refer_code": user_refer_code,
                "referred_by": refer_code if refer_code else None,
                "referred_users": [],
                "claimed_gifts": []
            }
            
            # NOTE: Referral bonus will ONLY be given when the referred user verifies
            # We don't give bonus at registration anymore
            
            save_json(USERS_FILE, users)
            
            msg = f"🔔 *New User*\nName: {full_name}\nID: `{uid}`"
            if refer_code:
                msg += f"\nReferred by: `{refer_code}`"
            safe_send_message(ADMIN_ID, msg)
            for adm in settings.get('admins', []):
                safe_send_message(adm, msg)
        
        display_name = message.from_user.first_name or "USER"
        img_url = f"https://res.cloudinary.com/dneusgyzc/image/upload/l_text:Stalinist%20One_90_bold_center:{display_name},co_white,g_center/v1767253426/botpy_fdkyke.jpg"
        
        markup = InlineKeyboardMarkup(row_width=1)
        for ch in settings['channels']:
            markup.add(InlineKeyboardButton(ch.get('btn_name', 'Channel'), url=ch.get('link', '#')))
        
        web_app = WebAppInfo(url=f"{BASE_URL}/mini_app?user_id={uid}")
        markup.add(InlineKeyboardButton("✅ VERIFY & START EARNING", web_app=web_app))
        
        if is_admin(uid):
            markup.add(InlineKeyboardButton("👑 Open Admin Panel", url=f"{BASE_URL}/admin_panel?user_id={uid}"))

        cap = f"👋 *WELCOME {display_name}!*\n\n🚀 Complete the steps below to start earning ₹{settings['welcome_bonus']}!"
        
        try:
            bot.send_photo(message.chat.id, img_url, caption=cap, parse_mode="Markdown", reply_markup=markup)
        except:
            safe_send_message(message.chat.id, cap, reply_markup=markup)
            
    except Exception as e:
        logger.error(f"Start handler error: {e}")

# ==================== 5. WEBAPP ROUTES ====================
@app.route('/')
def home():
    return "Telegram Bot is running! Use /start in Telegram."

@app.route('/mini_app')
def mini_app():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return "User ID required", 400
            
        users = load_json(USERS_FILE, {})
        settings = get_settings()
        user = users.get(str(uid), {"name": "Guest", "balance": 0.0, "verified": False})
        
        # Get initial data for fast loading
        leaderboard_data = load_json(LEADERBOARD_FILE, {"last_updated": "2000-01-01", "data": []})
        
        return render_template_string(MINI_APP_TEMPLATE, 
            user=user, 
            user_id=uid, 
            settings=settings, 
            base_url=BASE_URL, 
            timestamp=int(time.time()),
            leaderboard=leaderboard_data.get("data", []),
            now=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Mini app error: {e}")
        return "Internal Server Error", 500

@app.route('/get_pfp')
def get_pfp():
    uid = request.args.get('uid')
    try:
        photos = bot.get_user_profile_photos(uid)
        if photos.total_count > 0:
            file_id = photos.photos[0][0].file_id
            file_info = bot.get_file(file_id)
            dl_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
            return Response(requests.get(dl_url).content, mimetype='image/jpeg')
    except Exception as e:
        logger.error(f"PFP error: {e}")
    return "No Image", 404

@app.route('/api/verify', methods=['POST'])
def api_verify():
    try:
        data = request.json
        uid = str(data.get('user_id', ''))
        fp = str(data.get('fp', ''))
        client_ip = request.remote_addr
        
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json(USERS_FILE, {})
        settings = get_settings()
        
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        # Check if already verified
        if users[uid].get('verified'):
            return jsonify({'ok': True, 'msg': 'Already verified', 'verified': True, 'balance': users[uid].get('balance', 0)})
        
        # Check channel membership
        channel_errors = []
        if settings['channels']:
            for ch in settings['channels']:
                try:
                    if ch.get('id'):
                        status = bot.get_chat_member(ch['id'], uid).status
                        if status not in ['member', 'administrator', 'creator', 'restricted']:
                            channel_errors.append(ch.get('btn_name', 'Channel'))
                except Exception as e:
                    logger.error(f"Channel check error: {e}")
                    channel_errors.append(ch.get('btn_name', 'Channel'))
        
        # Device check
        device_error = None
        if not settings.get('ignore_device_check', False) and fp and fp != 'skip':
            for u_id, u_data in users.items():
                if u_id == uid: 
                    continue
                if u_data.get('verified') and str(u_data.get('device_id', '')) == fp:
                    device_error = '⚠️ Device already used by another account!'
                    break
        
        # Return specific errors
        if channel_errors and device_error:
            return jsonify({'ok': False, 'msg': f"Join channels: {', '.join(channel_errors)} & Device issue: {device_error}", 'type': 'both'})
        elif channel_errors:
            return jsonify({'ok': False, 'msg': f"Please join: {', '.join(channel_errors)}", 'type': 'channels'})
        elif device_error:
            return jsonify({'ok': False, 'msg': device_error, 'type': 'device'})
        
        try: 
            bonus = float(settings.get('welcome_bonus', 50))
        except: 
            bonus = 50.0
        
        users[uid].update({
            'verified': True, 
            'device_id': fp if fp != 'skip' else users[uid].get('device_id', ''),
            'ip': client_ip,
            'balance': float(users[uid].get('balance', 0)) + bonus
        })
        
        # Give referral bonus to referrer ONLY when referred user verifies
        if users[uid].get('referred_by'):
            refer_code = users[uid]['referred_by']
            for referrer_id, referrer_data in users.items():
                if referrer_data.get('refer_code') == refer_code:
                    if uid not in referrer_data.get('referred_users', []):
                        min_reward = float(settings.get('min_refer_reward', 10))
                        max_reward = float(settings.get('max_refer_reward', 50))
                        reward = random.uniform(min_reward, max_reward)
                        reward = round(reward, 2)
                        
                        referrer_data['balance'] = float(referrer_data.get('balance', 0)) + reward
                        if 'referred_users' not in referrer_data:
                            referrer_data['referred_users'] = []
                        referrer_data['referred_users'].append(uid)
                        
                        w_list = load_json(WITHDRAWALS_FILE, [])
                        w_list.append({
                            "tx_id": f"REF-VERIFY-{generate_code(5)}",
                            "user_id": referrer_id,
                            "name": "Referral Bonus (Verified)",
                            "amount": reward,
                            "upi": "-",
                            "status": "completed",
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                        })
                        save_json(WITHDRAWALS_FILE, w_list)
                        
                        safe_send_message(referrer_id, f"🎉 *Referral Bonus!*\nYou earned ₹{reward} for {users[uid]['name']}'s verification")
                    break
        
        save_json(USERS_FILE, users)
        
        w_list = load_json(WITHDRAWALS_FILE, [])
        w_list.append({
            "tx_id": "BONUS", 
            "user_id": uid, 
            "name": "Signup Bonus",
            "amount": bonus, 
            "upi": "-", 
            "status": "completed",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        save_json(WITHDRAWALS_FILE, w_list)
        return jsonify({'ok': True, 'bonus': bonus, 'balance': users[uid]['balance'], 'verified': True})
    
    except Exception as e:
        logger.error(f"Verify error: {e}")
        return jsonify({'ok': False, 'msg': f"Error: {str(e)}"})

@app.route('/api/check_verification')
def api_check_verification():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json(USERS_FILE, {})
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        user = users[uid]
        return jsonify({
            'ok': True,
            'verified': user.get('verified', False),
            'balance': float(user.get('balance', 0)),
            'name': user.get('name', 'User')
        })
    except Exception as e:
        logger.error(f"Check verification error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/withdraw', methods=['POST'])
def api_withdraw():
    try:
        data = request.json
        uid = str(data.get('user_id', ''))
        try: 
            amt = float(data.get('amount', 0))
        except: 
            return jsonify({'ok': False, 'msg': 'Invalid Amount'})
        upi = str(data.get('upi', ''))
        
        users = load_json(USERS_FILE, {})
        settings = get_settings()
        
        if settings.get('withdraw_disabled'):
            return jsonify({'ok': False, 'msg': '❌ Withdrawals are currently disabled'})
        
        if not re.match(r"[\w\.\-_]{2,}@[\w]{2,}", upi):
            return jsonify({'ok': False, 'msg': '❌ Invalid UPI Format'})
            
        min_w = float(settings.get('min_withdrawal', 100))
        if amt < min_w:
            return jsonify({'ok': False, 'msg': f'⚠️ Min Withdraw: ₹{min_w}'})
            
        cur_bal = float(users.get(uid, {}).get('balance', 0))
        if cur_bal < amt:
            return jsonify({'ok': False, 'msg': '❌ Insufficient Balance'})
        
        users[uid]['balance'] = cur_bal - amt
        save_json(USERS_FILE, users)
        
        tx_id = generate_code(5)
        record = {
            "tx_id": tx_id, 
            "user_id": uid, 
            "name": users[uid].get('name', 'User'), 
            "amount": amt, 
            "upi": upi, 
            "status": "pending", 
            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        
        is_auto = settings.get('auto_withdraw', False)
        msg_client = ""
        
        if is_auto:
            record['status'] = 'completed'
            record['utr'] = f"AUTO-{int(time.time())}"
            msg_client = f"✅ PAID! UTR: {record['utr']}"
            safe_send_message(uid, f"✅ *Auto-Withdrawal Paid!*\nAmt: ₹{amt}\nUTR: `{record['utr']}`\nTxID: `{tx_id}`")
        else:
            msg_client = "✅ Request Sent! Waiting for Admin..."
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Open Admin Panel", url=f"{BASE_URL}/admin_panel?user_id={ADMIN_ID}"))
            
            msg_adm = f"💸 *New Withdrawal*\nUser: {users[uid]['name']}\nAmt: ₹{amt}\nTxID: `{tx_id}`"
            safe_send_message(ADMIN_ID, msg_adm, reply_markup=markup)
            for adm in settings.get('admins', []):
                safe_send_message(adm, msg_adm, reply_markup=markup)

        w_list = load_json(WITHDRAWALS_FILE, [])
        w_list.append(record)
        save_json(WITHDRAWALS_FILE, w_list)
        
        return jsonify({
            'ok': True, 
            'msg': msg_client, 
            'auto': is_auto, 
            'utr': record.get('utr', ''), 
            'tx_id': tx_id,
            'new_balance': users[uid]['balance']
        })
        
    except Exception as e:
        logger.error(f"Withdraw Error: {e}")
        return jsonify({'ok': False, 'msg': f"Error: {str(e)}"})

@app.route('/api/get_balance')
def api_get_balance():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json(USERS_FILE, {})
        user = users.get(str(uid), {})
        
        return jsonify({
            'ok': True,
            'balance': float(user.get('balance', 0)),
            'verified': user.get('verified', False)
        })
    except Exception as e:
        logger.error(f"Get balance error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/history')
def api_history():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify([])
        
        history = [w for w in load_json(WITHDRAWALS_FILE, []) if w.get('user_id') == uid]
        return jsonify(history[::-1][:10])  # Limit to 10 items for faster loading
    except Exception as e:
        logger.error(f"History error: {e}")
        return jsonify([])

@app.route('/api/contact_upload', methods=['POST'])
def api_contact():
    try:
        uid = request.form.get('user_id')
        msg = request.form.get('msg', '')
        f = request.files.get('image')
        
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
            
        cap = f"📩 *Message from {uid}*\n{msg}"
        recipients = [ADMIN_ID] + get_settings().get('admins', [])
        
        if f:
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)
            
            with open(path, 'rb') as img:
                file_data = img.read()
                for adm in recipients:
                    try: 
                        bot.send_photo(adm, file_data, caption=cap, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"Send photo error to {adm}: {e}")
            os.remove(path)
        else:
            for adm in recipients:
                safe_send_message(adm, cap)
                
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Contact error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/claim_gift', methods=['POST'])
def api_claim_gift():
    try:
        data = request.json
        uid = str(data.get('user_id', ''))
        code = str(data.get('code', '')).strip().upper()
        
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json(USERS_FILE, {})
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        if 'claimed_gifts' not in users[uid]:
            users[uid]['claimed_gifts'] = []
        
        if code in users[uid]['claimed_gifts']:
            return jsonify({'ok': False, 'msg': 'Already claimed this code'})
        
        gifts = check_gift_code_expiry()
        
        for gift in gifts:
            if gift.get('code') == code:
                if gift.get('expired'):
                    return jsonify({'ok': False, 'msg': '❌ Gift code expired'})
                if not gift.get('is_active', True):
                    return jsonify({'ok': False, 'msg': 'Code is inactive'})
                
                if len(gift.get('used_by', [])) >= gift.get('total_uses', 1):
                    return jsonify({'ok': False, 'msg': 'Code usage limit reached'})
                
                amount = random.uniform(
                    float(gift.get('min_amount', 10)),
                    float(gift.get('max_amount', 50))
                )
                amount = round(amount, 2)
                
                users[uid]['balance'] = float(users[uid].get('balance', 0)) + amount
                users[uid]['claimed_gifts'].append(code)
                
                if 'used_by' not in gift:
                    gift['used_by'] = []
                gift['used_by'].append(uid)
                
                w_list = load_json(WITHDRAWALS_FILE, [])
                w_list.append({
                    "tx_id": f"GIFT-{generate_code(5)}",
                    "user_id": uid,
                    "name": "Gift Code Reward",
                    "amount": amount,
                    "upi": "-",
                    "status": "completed",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                
                save_json(USERS_FILE, users)
                save_json(GIFTS_FILE, gifts)
                save_json(WITHDRAWALS_FILE, w_list)
                
                return jsonify({
                    'ok': True, 
                    'msg': f'🎉 Gift code claimed! ₹{amount} added to your balance',
                    'amount': amount,
                    'new_balance': users[uid]['balance']
                })
        
        return jsonify({'ok': False, 'msg': 'Invalid gift code'})
    except Exception as e:
        logger.error(f"Claim gift error: {e}")
        return jsonify({'ok': False, 'msg': f'Error: {str(e)}'})

@app.route('/api/get_refer_info')
def api_get_refer_info():
    try:
        uid = request.args.get('user_id')
        if not uid:
            return jsonify({'ok': False, 'msg': 'User ID required'})
        
        users = load_json(USERS_FILE, {})
        
        if uid not in users:
            return jsonify({'ok': False, 'msg': 'User not found'})
        
        user = users[uid]
        
        if not user.get('refer_code'):
            user['refer_code'] = generate_refer_code()
            save_json(USERS_FILE, users)
        
        refer_code = user.get('refer_code', '')
        
        try:
            bot_username = bot.get_me().username
        except:
            bot_username = "telegram_bot"
        
        referred_users = user.get('referred_users', [])
        referred_details = []
        total_pending = 0
        total_verified = 0
        
        for ref_uid in referred_users[:20]:  # Limit to 20 for faster loading
            if ref_uid in users:
                is_verified = users[ref_uid].get('verified', False)
                status = "✅ VERIFIED" if is_verified else "⏳ PENDING"
                if is_verified:
                    total_verified += 1
                else:
                    total_pending += 1
                    
                referred_details.append({
                    'id': ref_uid,
                    'name': users[ref_uid].get('name', 'Unknown'),
                    'status': status,
                    'verified': is_verified
                })
        
        return jsonify({
            'ok': True,
            'refer_code': refer_code,
            'refer_link': f'https://t.me/{bot_username}?start={refer_code}',
            'referred_users': referred_details,
            'total_refers': len(referred_users),
            'verified_refers': total_verified,
            'pending_refers': total_pending
        })
    except Exception as e:
        logger.error(f"Refer info error: {e}")
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/leaderboard')
def api_leaderboard():
    try:
        data = update_leaderboard()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return jsonify({"last_updated": datetime.now().isoformat(), "data": []})

# ==================== 6. ADMIN PANEL ====================
@app.route('/admin_panel')
def admin_panel():
    try:
        uid = request.args.get('user_id')
        if not uid or not is_admin(uid): 
            return "⛔ Unauthorized"
        
        all_withdrawals = load_json(WITHDRAWALS_FILE, [])
        filtered_withdrawals = []
        for w in all_withdrawals:
            tx_id = w.get('tx_id', '')
            if tx_id != "BONUS" and not tx_id.startswith('REF-') and not tx_id.startswith('GIFT-'):
                filtered_withdrawals.append(w)
        
        gifts = check_gift_code_expiry()
        
        current_time = datetime.now()
        for gift in gifts:
            if 'expiry' in gift:
                try:
                    expiry_time = datetime.fromisoformat(gift['expiry'])
                    remaining_minutes = max(0, int((expiry_time - current_time).total_seconds() / 60))
                    gift['remaining_minutes'] = remaining_minutes
                except:
                    gift['remaining_minutes'] = 0
        
        users = load_json(USERS_FILE, {})
        # Prepare user data for the table
        user_list = []
        for user_id, user_data in users.items():
            user_list.append({
                'id': user_id,
                'name': user_data.get('name', 'Unknown'),
                'balance': float(user_data.get('balance', 0)),
                'refer_code': user_data.get('refer_code', 'N/A'),
                'verified': user_data.get('verified', False),
                'refer_count': len(user_data.get('referred_users', []))
            })
        
        return render_template_string(ADMIN_TEMPLATE, 
            settings=get_settings(), 
            users=user_list,
            withdrawals=filtered_withdrawals[::-1], 
            stats={
                "total_users": len(users), 
                "pending_count": len([w for w in filtered_withdrawals if w.get('status') == 'pending'])
            },
            timestamp=int(time.time()),
            admin_id=uid,
            gifts=gifts,
            now=current_time
        )
    except Exception as e:
        logger.error(f"Admin panel error: {e}")
        return f"Internal Server Error: {str(e)}", 500

# ==================== 7. SETUP ====================
@app.route('/static/<path:filename>')
def serve_static(filename): 
    return send_from_directory(STATIC_DIR, filename)

@app.route('/setup_webhooks')
def setup_webhooks():
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(f"{BASE_URL}/webhook/main")
        return "✅ Webhook Configured"
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/webhook/main', methods=['POST'])
def wm():
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return ''
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return 'Error', 500
    return 'OK', 200

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

# ==================== 9. HTML TEMPLATES ====================

MINI_APP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
    <style>
        :root { --bg: #050508; --cyan: #00f3ff; --gold: #ffd700; --panel: rgba(255,255,255,0.05); }
        body { background: radial-gradient(circle at top, #111122, var(--bg)); color: white; font-family: 'Rajdhani', sans-serif; margin: 0; padding: 0; box-sizing: border-box; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; overflow-x: hidden; width: 100%; }
        .hidden { display: none !important; }
        .header { display: flex; align-items: center; justify-content: center; gap: 15px; margin: 15px 0; width: 100%; padding: 0 5%; }
        .logo { width: 50px; height: 50px; border-radius: 50%; border: 2px solid var(--cyan); box-shadow: 0 0 15px rgba(0,243,255,0.3); object-fit: cover; }
        .title { font-size: 22px; font-weight: 800; text-shadow: 0 0 10px var(--cyan); letter-spacing: 1px; }
        .nav-bar { display: flex; width: 100%; max-width: 500px; background: rgba(0,0,0,0.7); border-radius: 15px; margin: 10px auto; padding: 5px; justify-content: space-around; border: 1px solid rgba(255,255,255,0.1); }
        .nav-btn { background: transparent; border: none; color: #aaa; padding: 8px 5px; border-radius: 10px; font-weight: bold; font-size: 14px; display: flex; flex-direction: column; align-items: center; gap: 2px; cursor: pointer; transition: all 0.3s; width: 25%; }
        .nav-btn i { font-size: 20px; }
        .nav-text { font-size: 10px; margin-top: 2px; color: #888; }
        .nav-btn.active { background: rgba(0,243,255,0.15); color: var(--cyan); box-shadow: 0 0 10px rgba(0,243,255,0.3); }
        .nav-btn.active .nav-text { color: var(--cyan); }
        .tab-content { width: 100%; max-width: 500px; padding: 0 5% 20px 5%; box-sizing: border-box; }
        .card-metal, .card-gold, .card-silver, .card-purple { width: 100%; box-sizing: border-box; border-radius: 16px; padding: 25px; margin-bottom: 20px; position: relative; overflow: hidden; }
        .card-metal { background: linear-gradient(135deg, #e0e0e0 0%, #bdc3c7 20%, #88929e 50%, #bdc3c7 80%, #e0e0e0 100%); border: 1px solid #fff; box-shadow: 0 10px 20px rgba(0,0,0,0.5), inset 0 0 15px rgba(255,255,255,0.5); display: flex; align-items: center; color: #222; }
        .card-metal::before { content: ''; position: absolute; top: 0; left: -150%; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.8), transparent); animation: shine 3.5s infinite; transform: skewX(-20deg); }
        @keyframes shine { 100% { left: 200%; } }
        .p-pic-wrapper { position: relative; width: 60px; height: 60px; margin-right: 15px; z-index: 2; flex-shrink: 0; }
        .p-pic { width: 100%; height: 100%; border-radius: 50%; border: 3px solid #333; object-fit: cover; }
        .p-icon { display: none; width: 100%; height: 100%; border-radius: 50%; border: 3px solid #333; background: #ddd; align-items: center; justify-content: center; font-size: 24px; color: #333; }
        .card-gold { background: radial-gradient(ellipse at center, #ffd700 0%, #d4af37 40%, #b8860b 100%); text-align: center; color: #2e2003; border: 2px solid #fff2ad; box-shadow: 0 0 25px rgba(255, 215, 0, 0.4), inset 0 0 10px rgba(255, 255, 255, 0.4); animation: pulse-gold 3s infinite; position: relative; }
        .card-gold::after { content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: radial-gradient(circle, rgba(255,255,255,0.3) 0%, transparent 60%); transform: rotate(30deg); pointer-events: none; }
        @keyframes pulse-gold { 50% { box-shadow: 0 0 40px rgba(255,215,0,0.6); } }
        .glass-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); backdrop-filter: blur(5px); display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 16px; z-index: 10; }
        .unlock-btn { background: linear-gradient(135deg, #00f3ff, #0088ff); color: white; border: none; padding: 15px 30px; border-radius: 30px; font-weight: 800; font-size: 16px; cursor: pointer; display: inline-flex; align-items: center; gap: 10px; font-family: 'Rajdhani'; box-shadow: 0 5px 20px rgba(0,243,255,0.4); margin-top: 15px; }
        .unlock-btn:active { transform: scale(0.95); }
        .card-silver { background: linear-gradient(135deg, #c0c0c0 0%, #d0d0d0 30%, #e0e0e0 50%, #d0d0d0 70%, #c0c0c0 100%); border: 1px solid #fff; box-shadow: 0 10px 20px rgba(0,0,0,0.3); color: #222; text-align: center; aspect-ratio: 16/9; display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .card-purple { background: linear-gradient(135deg, #9d4edd 0%, #7b2cbf 50%, #5a189a 100%); border: 1px solid #c77dff; box-shadow: 0 0 20px rgba(157,78,221,0.5); color: white; text-align: center; aspect-ratio: 16/9; display: flex; flex-direction: column; justify-content: center; align-items: center; position: relative; padding: 20px; }
        .card-purple::before { content: ''; position: absolute; top: -10px; left: -10px; right: -10px; bottom: -10px; background: linear-gradient(45deg, #9d4edd, #7b2cbf, #5a189a, #9d4edd); z-index: -1; border-radius: 20px; opacity: 0.5; filter: blur(10px); }
        .btn { background: #111; color: var(--gold); border: none; padding: 14px 30px; border-radius: 30px; font-weight: 800; font-size: 16px; margin-top: 15px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 10px; font-family: 'Rajdhani'; box-shadow: 0 5px 15px rgba(0,0,0,0.3); transition: transform 0.2s; position: relative; z-index: 5; }
        .btn:active { transform: scale(0.95); }
        .btn-purple { background: #5a189a; color: white; }
        .btn-cyan { background: #00f3ff; color: #000; }
        .popup { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); backdrop-filter: blur(5px); display: none; justify-content: center; align-items: center; z-index: 9999; padding: 20px; box-sizing: border-box; }
        .popup-content { background: #1a1a20; padding: 30px; border-radius: 20px; width: 100%; max-width: 350px; border: 1px solid var(--cyan); text-align: center; box-shadow: 0 0 30px rgba(0,243,255,0.2); }
        .popup-content h3 { margin-top: 0; color: var(--cyan); }
        input, textarea { width: 100%; padding: 12px; margin: 10px 0; background: #2a2a30; border: 1px solid #444; color: white; border-radius: 8px; box-sizing: border-box; font-family: inherit; }
        .hist-item { background: var(--panel); border-radius: 8px; padding: 12px; margin-bottom: 8px; display: flex; justify-content: space-between; border-left: 3px solid #333; width: 100%; box-sizing: border-box; }
        .status-completed { color: #00ff00; } .status-pending { color: orange; } .status-rejected { color: red; }
        .overlay-loader { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 2000; display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .spinner { width: 40px; height: 40px; border: 5px solid #333; border-top: 5px solid var(--cyan); border-radius: 50%; animation: spin 1s linear infinite; margin: 20px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .refer-code-box { background: rgba(255,255,255,0.1); border: 2px dashed var(--cyan); padding: 15px 10px; border-radius: 10px; margin: 10px 0; font-family: monospace; font-size: 24px; letter-spacing: 3px; cursor: pointer; text-align: center; word-break: break-all; margin-left: 20px; margin-right: 20px; }
        .leaderboard-table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }
        .leaderboard-table tr { border-bottom: 1px solid rgba(255,255,255,0.1); }
        .leaderboard-table td { padding: 10px 5px; }
        .leaderboard-table .highlight { background: rgba(0,243,255,0.1); border-left: 3px solid var(--cyan); }
        .code-input { font-size: 24px; letter-spacing: 5px; text-align: center; text-transform: uppercase; width: 100%; margin: 10px 0; padding: 15px; border-radius: 10px; border: 2px solid silver; background: white; color: #222; }
        .gift-result { text-align: center; margin-top: 20px; padding: 15px; border-radius: 10px; background: rgba(0,0,0,0.3); }
        .referrals-list { max-height: 300px; overflow-y: auto; padding-right: 5px; }
        .referrals-list::-webkit-scrollbar { width: 5px; }
        .referrals-list::-webkit-scrollbar-track { background: rgba(255,255,255,0.1); }
        .referrals-list::-webkit-scrollbar-thumb { background: var(--cyan); border-radius: 5px; }
        .verify-popup { z-index: 10000; }
        .verify-popup .popup-content { max-width: 400px; }
        .verify-actions { display: flex; gap: 10px; margin-top: 20px; }
        .verify-actions button { flex: 1; }
        .balance-loading { font-size: 48px; font-weight: 900; margin: 5px 0; text-shadow: 0 2px 5px rgba(0,0,0,0.2); color: #666; }
        .skeleton { background: linear-gradient(90deg, #333 25%, #444 50%, #333 75%); background-size: 200% 100%; animation: loading 1.5s infinite; }
        @keyframes loading { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .action-loading { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 99999; justify-content: center; align-items: center; flex-direction: column; }
        .action-loader { font-size: 16px; color: white; margin-top: 15px; font-weight: bold; }
        .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #333; color: white; padding: 12px 24px; border-radius: 8px; z-index: 10000; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        .toast-success { background: #28a745; }
        .toast-error { background: #dc3545; }
        .toast-info { background: #17a2b8; }
        .progress-bar { width: 100%; height: 4px; background: #333; border-radius: 2px; overflow: hidden; margin-top: 10px; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #00f3ff, #0088ff); width: 0%; transition: width 0.3s; }
        .verification-success { color: #00ff00; font-weight: bold; margin: 10px 0; }
        .verification-error { color: #ff4444; font-weight: bold; margin: 10px 0; }
        .loading-screen { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: radial-gradient(circle at top, #111122, #050508); display: flex; flex-direction: column; justify-content: center; align-items: center; z-index: 99999; }
        .loading-logo { width: 80px; height: 80px; border-radius: 50%; border: 3px solid var(--cyan); box-shadow: 0 0 20px rgba(0,243,255,0.5); margin-bottom: 20px; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.05); opacity: 0.8; } }
        .loading-text { color: var(--cyan); font-size: 18px; font-weight: bold; margin-top: 20px; }
        .resource-bar { width: 80%; max-width: 300px; margin-top: 20px; }
        .resource-text { color: #888; font-size: 12px; margin-top: 5px; }
    </style>
</head>
<body>
    <div id="loading-screen" class="loading-screen">
        <img src="{{ base_url }}/static/{{ settings.logo_filename }}?v={{ timestamp }}" class="loading-logo">
        <div class="loading-text">{{ settings.bot_name }}</div>
        <div class="resource-bar">
            <div class="progress-bar">
                <div id="resource-progress" class="progress-fill"></div>
            </div>
            <div id="resource-text" class="resource-text">Loading resources...</div>
        </div>
    </div>
    
    <div id="action-loading" class="action-loading">
        <div class="spinner"></div>
        <div id="action-loader-text" class="action-loader">Processing...</div>
    </div>
    
    <div id="toast" class="toast"></div>
    
    <div id="app" class="hidden" style="width:100%; display:flex; flex-direction:column; align-items:center;">
        <div class="header"><img src="{{ base_url }}/static/{{ settings.logo_filename }}?v={{ timestamp }}" class="logo"><div class="title">{{ settings.bot_name }}</div></div>
        
        <div class="nav-bar">
            <button class="nav-btn active" onclick="switchTab('home')">
                <i class="fas fa-home"></i>
                <div class="nav-text">HOME</div>
            </button>
            <button class="nav-btn" onclick="switchTab('gift')">
                <i class="fas fa-gift"></i>
                <div class="nav-text">GIFT</div>
            </button>
            <button class="nav-btn" onclick="switchTab('refer')">
                <i class="fas fa-users"></i>
                <div class="nav-text">REFER</div>
            </button>
            <button class="nav-btn" onclick="switchTab('leaderboard')">
                <i class="fas fa-trophy"></i>
                <div class="nav-text">RANK</div>
            </button>
        </div>
        
        <div id="tab-home" class="tab-content">
            <div class="card-metal">
                <div class="p-pic-wrapper"><img src="/get_pfp?uid={{ user_id }}" class="p-pic" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"><div class="p-icon"><i class="fas fa-user"></i></div></div>
                <div style="z-index:2;">
                    <div style="font-size:18px; font-weight:800;">{{ user.name }}</div>
                    <div onclick="openPop('contact')" style="color:#0044cc; font-size:13px; margin-top:5px; cursor:pointer; text-decoration:underline; font-weight:bold;">Contact Admin</div>
                </div>
            </div>
            
            <div class="card-gold" id="balance-card">
                <div id="glass-overlay" class="glass-overlay {% if user.verified %}hidden{% endif %}">
                    <div style="text-align: center; padding: 20px;">
                        <i class="fas fa-lock" style="font-size: 40px; color: #ff9900; margin-bottom: 15px;"></i>
                        <div style="font-size: 18px; font-weight: bold; color: white;">Account Locked</div>
                        <div style="font-size: 14px; color: #aaa; margin-top: 10px; max-width: 250px;">
                            Complete verification to unlock your wallet and earn ₹{{ settings.welcome_bonus }}
                        </div>
                        <button class="unlock-btn" onclick="startVerification()">
                            <i class="fas fa-unlock-alt"></i> UNLOCK NOW
                        </button>
                    </div>
                </div>
                <div style="font-size:14px; font-weight:800; opacity:0.8; letter-spacing:2px;">WALLET BALANCE</div>
                <div id="balance-amount" style="font-size:48px; font-weight:900; margin:5px 0; text-shadow:0 2px 5px rgba(0,0,0,0.2);">₹{{ "%.2f"|format(user.balance) }}</div>
                <button class="btn" onclick="openPop('withdraw')" {% if not user.verified %}disabled style="opacity:0.5;"{% endif %}><i class="fas fa-wallet"></i> WITHDRAW</button>
            </div>
            
            <div style="margin-top:20px; width:100%;">
                <div style="color:#888; font-size:13px; font-weight:bold; margin-bottom:10px;">RECENT ACTIVITY</div>
                <div id="history-list">
                    <div class="hist-item skeleton" style="height:60px;"></div>
                    <div class="hist-item skeleton" style="height:60px;"></div>
                </div>
            </div>
        </div>
        
        <div id="tab-gift" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:20px;">
                <h2 style="margin:0; color:var(--cyan);">GIFT CODE</h2>
                <p style="color:#aaa; margin-top:5px;">Enter 5-character code</p>
            </div>
            <div class="card-silver">
                <input type="text" id="gift-code" class="code-input" maxlength="5" placeholder="ABCDE" oninput="this.value = this.value.toUpperCase()">
                <button class="btn" onclick="claimGift()" style="background:#222; color:silver;"><i class="fas fa-gift"></i> CLAIM NOW</button>
            </div>
            <div id="gift-result" class="gift-result"></div>
        </div>
        
        <div id="tab-refer" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:20px;">
                <h2 style="margin:0; color:#9d4edd;">REFER & EARN</h2>
                <p style="color:#aaa; margin-top:5px;">Share your code and earn rewards</p>
            </div>
            <div class="card-purple">
                <div id="refer-code-display" class="refer-code-box" onclick="copyReferCode()">LOADING...</div>
                <button class="btn btn-purple" onclick="shareReferLink()" style="margin-top:20px;"><i class="fas fa-share-alt"></i> SHARE LINK</button>
            </div>
            <div style="width:100%; margin-top:20px;">
                <h3 style="color:#9d4edd; margin-bottom:10px;">YOUR REFERRALS</h3>
                <div id="referrals-list" class="referrals-list">
                    <div style="text-align:center; color:#666; padding:20px;">Loading referrals...</div>
                </div>
            </div>
        </div>
        
        <div id="tab-leaderboard" class="tab-content hidden">
            <div style="text-align:center; margin-bottom:20px;">
                <h2 style="margin:0; color:var(--gold);">LEADERBOARD</h2>
                <p style="color:#aaa; font-size:14px;">Top 20 Users by Balance</p>
            </div>
            <table class="leaderboard-table">
                <thead>
                    <tr style="background:rgba(255,215,0,0.1);">
                        <td style="font-weight:bold; color:var(--gold);">RANK</td>
                        <td style="font-weight:bold; color:var(--gold);">NAME</td>
                        <td style="font-weight:bold; color:var(--gold); text-align:right;">BALANCE</td>
                        <td style="font-weight:bold; color:var(--gold); text-align:right;">REFERS</td>
                    </tr>
                </thead>
                <tbody id="leaderboard-list">
                    {% for user in leaderboard %}
                    <tr {% if user.user_id == user_id %}class="highlight"{% endif %}>
                        <td style="font-weight:bold; color:#ccc;">{{ loop.index }}</td>
                        <td>
                            <div style="font-weight:bold;">{{ user.name[:15] }}{% if user.name|length > 15 %}...{% endif %}</div>
                            <div style="font-size:10px; color:#888;">{{ user.user_id[:8] }}...</div>
                        </td>
                        <td style="text-align:right; font-weight:bold; color:var(--gold);">₹{{ "%.2f"|format(user.balance) }}</td>
                        <td style="text-align:right; font-size:12px; color:#aaa;">{{ user.total_refers }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    
    <!-- Popups -->
    <div id="pop-contact" class="popup">
        <div class="popup-content">
            <h3>Contact Admin</h3>
            <textarea id="c-msg" rows="3" placeholder="Your message..."></textarea>
            <input type="file" id="c-file" accept="image/*">
            <button class="btn" onclick="sendContact()">SEND MESSAGE</button>
            <button class="btn" onclick="closePop()" style="background:transparent; color:#f44; margin-top:10px;">Close</button>
        </div>
    </div>
    
    <div id="pop-withdraw" class="popup">
        <div class="popup-content">
            <h3>Withdraw Money</h3>
            <input id="w-upi" placeholder="Enter UPI ID (e.g. name@bank)">
            <input id="w-amt" type="number" placeholder="Amount (Min: ₹{{ settings.min_withdrawal }})">
            <button class="btn" onclick="submitWithdraw()">WITHDRAW</button>
            <button class="btn" onclick="closePop()" style="background:transparent; color:#f44; margin-top:10px;">Cancel</button>
        </div>
    </div>
    
    <div id="pop-verify" class="popup verify-popup">
        <div class="popup-content">
            <h3>⚠️ Verification Required</h3>
            <p id="verify-error-msg" style="color:#ff9900; margin:15px 0;">Please complete verification to continue</p>
            <div class="verify-actions">
                <button class="btn" onclick="closePop()" style="background:#f44; color:white;">CLOSE</button>
            </div>
        </div>
    </div>
    
    <script>
        const UID = "{{ user_id }}";
        let referData = null;
        let isVerified = {{ user.verified|lower }};
        let resourcesLoaded = false;
        
        // Fast loading - show loading screen first, then app
        window.onload = function() {
            // Simulate resource loading
            simulateResourceLoading();
        };
        
        function simulateResourceLoading() {
            let progress = 0;
            const progressBar = document.getElementById('resource-progress');
            const resourceText = document.getElementById('resource-text');
            
            const interval = setInterval(() => {
                progress += 10;
                progressBar.style.width = progress + '%';
                
                if (progress <= 30) {
                    resourceText.textContent = 'Loading core modules...';
                } else if (progress <= 60) {
                    resourceText.textContent = 'Fetching user data...';
                } else if (progress <= 90) {
                    resourceText.textContent = 'Initializing interface...';
                } else {
                    resourceText.textContent = 'Ready!';
                }
                
                if (progress >= 100) {
                    clearInterval(interval);
                    setTimeout(() => {
                        document.getElementById('loading-screen').style.display = 'none';
                        document.getElementById('app').classList.remove('hidden');
                        resourcesLoaded = true;
                        
                        // Start loading data after UI is visible
                        setTimeout(() => {
                            loadCriticalData();
                        }, 300);
                    }, 500);
                }
            }, 100);
        }
        
        function loadCriticalData() {
            // Load history
            loadHistory();
            
            // Load refer info
            loadReferInfo();
            
            // If not verified, show unlock overlay (already shown from template)
            if (!isVerified) {
                // We already show the glass overlay from template
                console.log('User not verified, showing unlock overlay');
            } else {
                // User is already verified, enable withdrawal button
                document.querySelector('#balance-card .btn').disabled = false;
                document.querySelector('#balance-card .btn').style.opacity = '1';
            }
        }
        
        function startVerification() {
            showActionLoader('Checking verification...');
            
            // Generate a simple fingerprint (for demo)
            const fingerprint = 'user-' + UID + '-' + Date.now();
            
            fetch('/api/verify', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: UID, fp: fingerprint, bot_type: 'main'})
            })
            .then(r => r.json())
            .then(data => {
                hideActionLoader();
                
                if (data.ok) {
                    // Success - user verified
                    isVerified = true;
                    
                    // Hide glass overlay
                    document.getElementById('glass-overlay').classList.add('hidden');
                    
                    // Enable withdrawal button
                    const withdrawBtn = document.querySelector('#balance-card .btn');
                    withdrawBtn.disabled = false;
                    withdrawBtn.style.opacity = '1';
                    
                    // Update balance
                    if (data.balance !== undefined) {
                        document.getElementById('balance-amount').textContent = '₹' + data.balance.toFixed(2);
                    }
                    
                    // Show success message
                    showToast(`✅ Verification successful! ₹${data.bonus || 50} bonus added!`, 'success', 5000);
                    
                    // Load updated history
                    loadHistory();
                    
                    // Load updated refer info
                    loadReferInfo();
                    
                    // Show confetti
                    if (typeof confetti === 'function') {
                        confetti({particleCount: 150, spread: 70});
                    }
                } else {
                    // Verification failed
                    showVerificationError(data.msg, data.type || 'general');
                }
            })
            .catch(err => {
                hideActionLoader();
                showToast('Verification failed. Please try again.', 'error');
                console.error('Verification error:', err);
            });
        }
        
        function showVerificationError(message, errorType) {
            let errorMsg = message;
            
            if (errorType === 'channels') {
                errorMsg = '❌ Please join required channels first!';
            } else if (errorType === 'device') {
                errorMsg = '❌ Device verification failed!';
            } else if (errorType === 'both') {
                errorMsg = '❌ Please join channels and use a different device!';
            }
            
            document.getElementById('verify-error-msg').textContent = errorMsg;
            document.getElementById('pop-verify').style.display = 'flex';
        }
        
        function showActionLoader(text = 'Processing...') {
            document.getElementById('action-loader-text').textContent = text;
            document.getElementById('action-loading').style.display = 'flex';
        }
        
        function hideActionLoader() {
            document.getElementById('action-loading').style.display = 'none';
        }
        
        function showToast(message, type = 'info', duration = 3000) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast';
            toast.classList.add('toast-' + type);
            toast.style.display = 'block';
            
            setTimeout(() => {
                toast.style.display = 'none';
            }, duration);
        }
        
        function updateBalance() {
            fetch('/api/get_balance?user_id=' + UID)
                .then(r => r.json())
                .then(data => {
                    if (data.ok) {
                        document.getElementById('balance-amount').textContent = '₹' + data.balance.toFixed(2);
                    }
                })
                .catch(() => {
                    // Keep current balance on error
                });
        }
        
        function switchTab(tabName) {
            if (!resourcesLoaded) return;
            
            // Update active nav button
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            event.target.closest('.nav-btn').classList.add('active');
            
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.add('hidden'));
            
            // Show selected tab
            document.getElementById('tab-' + tabName).classList.remove('hidden');
            
            // Load data for specific tabs
            if (tabName === 'leaderboard') {
                loadLeaderboard();
            } else if (tabName === 'refer') {
                loadReferInfo();
            }
        }
        
        function submitWithdraw() {
            if (!isVerified) {
                showToast('Please verify your account first!', 'error');
                return;
            }
            
            const upi = document.getElementById('w-upi').value.trim();
            const amount = document.getElementById('w-amt').value;
            
            if (!upi || !amount) {
                showToast('Please fill all fields', 'error');
                return;
            }
            
            closePop();
            
            showActionLoader('Processing withdrawal...');
            
            fetch('/api/withdraw', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: UID, amount: amount, upi: upi})
            })
            .then(r => r.json())
            .then(data => {
                hideActionLoader();
                
                if (data.ok) {
                    showToast(data.msg, 'success', 5000);
                    if (data.auto) {
                        if (typeof confetti === 'function') {
                            confetti({particleCount: 150, spread: 80});
                        }
                    }
                    // Update balance with new value from server
                    if (data.new_balance !== undefined) {
                        document.getElementById('balance-amount').textContent = '₹' + data.new_balance.toFixed(2);
                    } else {
                        updateBalance();
                    }
                    loadHistory();
                } else {
                    showToast(data.msg, 'error');
                }
            })
            .catch(err => {
                hideActionLoader();
                showToast('Withdrawal failed. Please try again.', 'error');
                console.error('Withdraw error:', err);
            });
        }
        
        function sendContact() {
            const message = document.getElementById('c-msg').value;
            const fileInput = document.getElementById('c-file');
            
            if (!message.trim()) {
                showToast('Please enter a message', 'error');
                return;
            }
            
            showActionLoader('Sending message...');
            
            const formData = new FormData();
            formData.append('user_id', UID);
            formData.append('msg', message);
            if (fileInput.files[0]) {
                formData.append('image', fileInput.files[0]);
            }
            
            fetch('/api/contact_upload', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                hideActionLoader();
                if (data.ok) {
                    showToast('Message sent successfully!', 'success');
                    closePop();
                    document.getElementById('c-msg').value = '';
                    document.getElementById('c-file').value = '';
                } else {
                    showToast('Failed to send: ' + data.msg, 'error');
                }
            })
            .catch(err => {
                hideActionLoader();
                showToast('Failed to send message', 'error');
                console.error('Contact error:', err);
            });
        }
        
        function loadHistory() {
            fetch('/api/history?user_id=' + UID)
            .then(r => r.json())
            .then(history => {
                const container = document.getElementById('history-list');
                if (!history || history.length === 0) {
                    container.innerHTML = '<div style="text-align:center; color:#555; padding:20px;">No activity yet</div>';
                    return;
                }
                
                container.innerHTML = history.map(item => `
                    <div class="hist-item" style="border-left-color:${item.status === 'completed' ? '#0f0' : item.status === 'pending' ? 'orange' : 'red'}">
                        <div>
                            <div style="font-weight:bold;">${item.name || 'Transaction'}</div>
                            <div style="font-size:11px;color:#888;">${item.date || ''}</div>
                            ${item.tx_id && item.tx_id !== 'BONUS' ? `<div style="font-size:10px;color:#aaa;">ID: ${item.tx_id}</div>` : ''}
                        </div>
                        <div style="text-align:right;">
                            <div style="font-weight:bold;">₹${(item.amount || 0).toFixed(2)}</div>
                            <div class="status-${item.status}">${(item.status || '').toUpperCase()}</div>
                            ${item.utr ? `<div style="font-size:10px;color:#aaa;">${item.utr}</div>` : ''}
                        </div>
                    </div>
                `).join('');
            })
            .catch(err => {
                console.error('History error:', err);
                const container = document.getElementById('history-list');
                container.innerHTML = '<div style="text-align:center; color:#555; padding:20px;">Failed to load history</div>';
            });
        }
        
        function loadReferInfo() {
            fetch('/api/get_refer_info?user_id=' + UID)
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    referData = data;
                    document.getElementById('refer-code-display').textContent = data.refer_code;
                    
                    const referralsList = document.getElementById('referrals-list');
                    if (data.referred_users && data.referred_users.length > 0) {
                        referralsList.innerHTML = data.referred_users.map(user => `
                            <div style="background:rgba(157,78,221,0.1); padding:10px; border-radius:8px; margin-bottom:5px;">
                                <div style="font-weight:bold;">${user.name}</div>
                                <div style="font-size:10px; color:#888;">ID: ${user.id}</div>
                                <div style="font-size:11px; margin-top:5px; font-weight:bold; color:${user.verified ? '#0f0' : 'orange'}">
                                    ${user.status}
                                </div>
                            </div>
                        `).join('');
                    } else {
                        referralsList.innerHTML = '<div style="text-align:center; color:#666; padding:20px;">No referrals yet. Share your code!</div>';
                    }
                }
            })
            .catch(err => {
                console.error('Refer info error:', err);
                document.getElementById('refer-code-display').textContent = 'ERROR';
            });
        }
        
        function copyReferCode() {
            if (!referData) return;
            
            navigator.clipboard.writeText(referData.refer_code)
                .then(() => {
                    showToast('Refer code copied!', 'success', 2000);
                })
                .catch(() => showToast('Failed to copy', 'error'));
        }
        
        function shareReferLink() {
            if (!referData) return;
            
            const text = `🎉 Join {{ settings.bot_name }} and earn money! Use my refer code: ${referData.refer_code}\n${referData.refer_link}`;
            const url = `https://t.me/share/url?url=${encodeURIComponent(referData.refer_link)}&text=${encodeURIComponent(text)}`;
            window.open(url, '_blank');
        }
        
        function claimGift() {
            const code = document.getElementById('gift-code').value.trim().toUpperCase();
            
            if (!code || code.length !== 5) {
                showToast('Please enter a valid 5-character code', 'error');
                return;
            }
            
            showActionLoader('Claiming gift...');
            
            fetch('/api/claim_gift', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_id: UID, code: code})
            })
            .then(r => r.json())
            .then(data => {
                hideActionLoader();
                
                const resultDiv = document.getElementById('gift-result');
                if (data.ok) {
                    resultDiv.innerHTML = `<div style="color:#0f0; font-weight:bold; font-size:18px;">${data.msg}</div>`;
                    document.getElementById('gift-code').value = '';
                    
                    showToast(data.msg, 'success', 5000);
                    
                    if (typeof confetti === 'function') {
                        confetti({particleCount: 200, spread: 90});
                    }
                    
                    // Update balance with new value from server
                    if (data.new_balance !== undefined) {
                        document.getElementById('balance-amount').textContent = '₹' + data.new_balance.toFixed(2);
                    } else {
                        updateBalance();
                    }
                    loadHistory();
                } else {
                    resultDiv.innerHTML = `<div style="color:#f44; font-weight:bold;">${data.msg}</div>`;
                    showToast(data.msg, 'error');
                }
                
                // Clear result after 5 seconds
                setTimeout(() => {
                    resultDiv.innerHTML = '';
                }, 5000);
            })
            .catch(err => {
                hideActionLoader();
                showToast('Failed to claim gift code', 'error');
                console.error('Claim error:', err);
            });
        }
        
        function loadLeaderboard() {
            fetch('/api/leaderboard')
            .then(r => r.json())
            .then(data => {
                const container = document.getElementById('leaderboard-list');
                if (!data.data || data.data.length === 0) {
                    container.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:20px; color:#666;">No data available</td></tr>';
                    return;
                }
                
                container.innerHTML = data.data.map((user, index) => `
                    <tr ${user.user_id == UID ? 'class="highlight"' : ''}>
                        <td style="font-weight:bold; color:#ccc;">${index + 1}</td>
                        <td>
                            <div style="font-weight:bold;">${(user.name || '').substring(0, 15)}${(user.name || '').length > 15 ? '...' : ''}</div>
                            <div style="font-size:10px; color:#888;">${(user.user_id || '').substring(0, 8)}...</div>
                        </td>
                        <td style="text-align:right; font-weight:bold; color:var(--gold);">₹${(user.balance || 0).toFixed(2)}</td>
                        <td style="text-align:right; font-size:12px; color:#aaa;">${user.total_refers || 0}</td>
                    </tr>
                `).join('');
            })
            .catch(err => {
                console.error('Leaderboard error:', err);
            });
        }
        
        function openPop(id) {
            document.getElementById('pop-' + id).style.display = 'flex';
        }
        
        function closePop() {
            document.querySelectorAll('.popup').forEach(popup => {
                popup.style.display = 'none';
            });
        }
    </script>
</body>
</html>
"""

# ==================== 9. START APP ====================
if __name__ == '__main__':
    # Initialize default files
    init_default_files()
    
    # Railway provides PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

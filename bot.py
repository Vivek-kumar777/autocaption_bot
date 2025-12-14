import requests
import time
import json
import os
import math

TOKEN = "8432572527:AAEQVRWvbSbrMfIBLidcjBvEg26JAwtHke8"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
BOT_ID = None
BOT_USERNAME = None

DEFAULT_RETRY = 3


def _request_with_backoff(method, url, max_retries=DEFAULT_RETRY, backoff_factor=1.5, **kwargs):
    """Send HTTP request with special handling for Telegram 429 responses.

    On 429, reads `retry_after` from JSON `parameters` when available and sleeps
    that many seconds before retrying. Uses exponential backoff otherwise.
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
        except Exception as e:
            sleep_time = backoff_factor ** attempt
            print(f"Request exception: {e}. Sleeping {sleep_time}s before retry {attempt}/{max_retries}")
            time.sleep(sleep_time)
            continue

        # Try to parse JSON safely
        try:
            j = resp.json()
        except Exception:
            j = None

        # Check for explicit Telegram 429 in status code or JSON error_code
        is_429 = resp.status_code == 429 or (isinstance(j, dict) and j.get('error_code') == 429)
        if is_429:
            retry_after = None
            if isinstance(j, dict):
                retry_after = j.get('parameters', {}).get('retry_after')
            if retry_after is None:
                # exponential backoff fallback
                retry_after = int(math.ceil(backoff_factor ** attempt))
            print(f"Telegram 429 received. Sleeping {retry_after}s before retry {attempt}/{max_retries}")
            time.sleep(int(retry_after))
            continue

        # Non-429 response — return it
        return resp

    # Exhausted retries — return last response object if available, else raise
    return resp
episode_counter = 1
episode_counters = {}
last_update_id = 0
user_quality = {}
user_waiting_quality = set()
user_waiting_episode = set()
user_videos = {}
bot_messages = {}
all_messages = {}
video_messages = {}
started_users = set()

STATE_FILE = "bot_state.json"


def save_state():
    try:
        state = {
            'episode_counters': {str(k): v for k, v in episode_counters.items()},
            'user_quality': {str(k): v for k, v in user_quality.items()},
            'started_users': list(started_users)
        }
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        print("State saved")
    except Exception as e:
        print(f"Failed to save state: {e}")


def load_state():
    global episode_counter, user_quality, started_users
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
        ecs = state.get('episode_counters', {})
        for k, v in ecs.items():
            episode_counters[int(k)] = int(v)
        uq = state.get('user_quality', {})
        user_quality = {int(k): v for k, v in uq.items()}
        started_users = set(state.get('started_users', []))
        print("State loaded")
    except Exception as e:
        print(f"Failed to load state: {e}")


def get_start_text(chat_id=None):
    ep = episode_counters.get(chat_id, episode_counter)
    return f"""🎬 Welcome to Auto Caption Bot!

📺 I automatically add captions to your anime videos with:
• Episode numbers (Current: {ep})
• Hindi Dub labels
• Quality indicators
• Channel promotion

🚀 How to use:
1. Use /autocaption to set quality (480p/720p/1080p/2160p)
2. Send me video(s) - I'll caption them automatically!
3. Higher quality = more videos needed

⚙️ Commands:
/autocaption - Choose quality settings
/refresh - Reset episode counter
/del - Delete bot text messages
/all_del - Delete ALL messages (including videos)
/help - Show detailed help
/stop - Deactivate bot in this chat/channel

Send your first video to begin! 🎯"""


def get_help_text(chat_id=None):
    ep = episode_counters.get(chat_id, episode_counter)
    return f"""🤖 Anime Caption Bot Help

📹 Send me a video and I'll add episode captions automatically!

✨ Features:
• Auto episode numbering
• Hindi dub labels
• Quality tags
• Channel promotion

📺 Current episode: {ep}

Commands:
/autocaption - Set quality options
/refresh - Reset episode counter
/del - Delete bot text messages
/all_del - Delete ALL messages
/stop - Deactivate bot in this chat/channel

Just send a video to get started!"""


def handle_text(chat_id, text):
    global episode_counter
    # Auto-enable for groups/channels
    if chat_id < 0:
        started_users.add(chat_id)

    print(f"Text message: {text} (chat_id: {chat_id})")

    # If we're waiting for episode number and the user sends a non-command, accept it
    if chat_id in user_waiting_episode and not text.startswith('/'):
        txt = text.strip()
        if txt.isdigit():
            episode_counters[chat_id] = int(txt)
            user_waiting_episode.discard(chat_id)
            send_message(chat_id, f"Episode set to {txt}. Send your video(s) to begin.")
            save_state()
        else:
            send_message(chat_id, "Please send a valid episode number (e.g., 5).")
        return

    if text == '/start' or text.startswith('/start@'):
        started_users.add(chat_id)
        # Reset per-chat episode counter and clear quality (require selection)
        episode_counters[chat_id] = 1
        user_quality.pop(chat_id, None)
        user_videos.pop(chat_id, None)
        user_waiting_quality.discard(chat_id)
        save_state()

        # Activate the bot and show current settings
        send_message(chat_id, get_start_text(chat_id))
        send_message(chat_id, "Bot activated and reset: episode set to 1, quality cleared. Use /autocaption to set quality.")
    elif text == '/stop' or text.startswith('/stop@'):
        if chat_id in started_users:
            started_users.discard(chat_id)
            user_videos.pop(chat_id, None)
            user_quality.pop(chat_id, None)
            user_waiting_quality.discard(chat_id)
            send_message(chat_id, "Bot deactivated in this chat. Send /start to activate again.")
            print(f"Bot stopped for chat {chat_id}")
            save_state()
        else:
            send_message(chat_id, "Bot is already inactive in this chat.")
    elif chat_id not in started_users and chat_id > 0:
        send_message(chat_id, "Please send /start first to activate the bot! 🚀")
    elif text == '/help' or text.startswith('/help@'):
        send_message(chat_id, get_help_text(chat_id))
    elif text == '/autocaption' or text.startswith('/autocaption@'):
        keyboard = {
            "inline_keyboard": [
                [{"text": "480p (1x)", "callback_data": "480"}],
                [{"text": "720p (2x)", "callback_data": "720"}],
                [{"text": "1080p (3x)", "callback_data": "1080"}],
                [{"text": "2160p (4x)", "callback_data": "2160"}]
            ]
        }
        import json
        send_message(chat_id, "Select Quality:", json.dumps(keyboard))
        user_waiting_quality.add(chat_id)
        save_state()
    elif text == '/refresh' or text.startswith('/refresh@'):
        # Reset episode counter only for the requesting chat
        episode_counters[chat_id] = 1
        # clear any queued videos for this chat
        user_videos.pop(chat_id, None)
        send_message(chat_id, "✅ Your episode counter has been reset to 1.")
        print(f"Server refreshed by user {chat_id}")
        save_state()
    elif text == '/del' or text.startswith('/del@'):
        # In channels/groups: delete all bot text messages and other non-video messages,
        # but keep forwarded/sent videos with captions (tracked in `video_messages`).
        if chat_id < 0:
            if chat_id in all_messages and len(all_messages[chat_id]) > 0:
                # If bot is admin, delete everything (including user messages & videos)
                if is_bot_admin(chat_id):
                    deleted_count = 0
                    for message_id in list(all_messages.get(chat_id, [])):
                        delete_message(chat_id, message_id)
                        deleted_count += 1
                        time.sleep(0.1)
                    all_messages[chat_id] = []
                    bot_messages[chat_id] = []
                    video_messages[chat_id] = []
                    print(f"Admin delete: Deleted ALL {deleted_count} messages for channel {chat_id}")
                else:
                    to_keep = set(video_messages.get(chat_id, []))
                    deleted_count = 0
                    remaining = []
                    for message_id in all_messages.get(chat_id, []):
                        if message_id in to_keep:
                            remaining.append(message_id)
                        else:
                            delete_message(chat_id, message_id)
                            deleted_count += 1
                            time.sleep(0.1)
                    all_messages[chat_id] = remaining
                    # Clear bot_messages for this chat since text messages are deleted
                    bot_messages[chat_id] = []
                    print(f"Deleted {deleted_count} messages for channel {chat_id}; kept {len(remaining)} video(s)")
            else:
                print(f"No messages to delete for chat {chat_id}")
        else:
            # Private chat/group non-channel behavior: delete bot text messages only
            if chat_id in bot_messages:
                deleted_ids = []
                deleted_count = 0
                for message_id in bot_messages[chat_id]:
                    delete_message(chat_id, message_id)
                    deleted_ids.append(message_id)
                    deleted_count += 1
                    time.sleep(0.1)
                bot_messages[chat_id] = []
                # Remove deleted ids from all_messages as well
                if chat_id in all_messages:
                    all_messages[chat_id] = [m for m in all_messages[chat_id] if m not in set(deleted_ids)]
                print(f"Deleted {deleted_count} bot messages for chat {chat_id}")
            else:
                print(f"No messages to delete for chat {chat_id}")
    elif text == '/all_del' or text.startswith('/all_del@'):
        if chat_id in all_messages:
            deleted_count = 0
            for message_id in all_messages[chat_id]:
                delete_message(chat_id, message_id)
                deleted_count += 1
                time.sleep(0.1)
            all_messages[chat_id] = []
            bot_messages[chat_id] = []
            print(f"Deleted ALL {deleted_count} messages for chat {chat_id}")
        else:
            print(f"No messages to delete for chat {chat_id}")
    elif chat_id in user_waiting_quality and text in ['480', '720', '1080', '2160']:
        user_quality[chat_id] = text
        user_waiting_quality.remove(chat_id)
        send_message(chat_id, f"Quality set to {text}p!")
        save_state()


def handle_video(chat_id, video_file_id):
    global episode_counter
    chat_type = "group/channel" if chat_id < 0 else "private"
    print(f"Received video from {chat_type} chat_id: {chat_id}")

    # Require the user to select quality first
    if chat_id not in user_quality:
        send_message(chat_id, "please select the quality first")
        return

    if chat_id not in started_users and chat_id > 0:
        send_message(chat_id, "Please send /start first to activate the bot! 🚀")
        return

    max_quality = user_quality.get(chat_id, '480')

    if chat_id not in user_videos:
        user_videos[chat_id] = []

    user_videos[chat_id].append(video_file_id)

    quality_levels = ['480', '720', '1080', '2160']
    quality_labels = {'480': 'SD', '720': 'HD', '1080': 'FHD', '2160': '4K'}
    max_index = quality_levels.index(max_quality)
    required_videos = max_index + 1

    if len(user_videos[chat_id]) >= required_videos:
        ep = episode_counters.get(chat_id, episode_counter)
        for i in range(required_videos):
            current_quality = quality_levels[i]
            current_label = quality_labels[current_quality]
            current_video = user_videos[chat_id][i]

            caption = f"""Episode :- {ep}
🗣 Language :- Hindi Dub
🟡 Quality :- {current_quality}p [{current_label}]
@NEW_HINDI_ANIME_OFFICIAL_DUB"""

            send_video(chat_id, current_video, caption)
            time.sleep(1)

        user_videos[chat_id] = []
        episode_counters[chat_id] = ep + 1
        save_state()
        print(f"Processed episode {ep} with {required_videos} different quality videos")
    else:
        remaining = required_videos - len(user_videos[chat_id])
        send_message(chat_id, f"Video {len(user_videos[chat_id])}/{required_videos} received. Send {remaining} more video(s) for {max_quality}p quality.")

def send_message(chat_id, text, keyboard=None):
    url = f"{BASE_URL}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text
    }
    if keyboard:
        data['reply_markup'] = keyboard
    response = _request_with_backoff('post', url, data=data)
    try:
        result = response.json()
        if result.get('ok'):
            message_id = result['result']['message_id']
            if chat_id not in bot_messages:
                bot_messages[chat_id] = []
            bot_messages[chat_id].append(message_id)
            if chat_id not in all_messages:
                all_messages[chat_id] = []
            all_messages[chat_id].append(message_id)
        else:
            print(f"Failed to send message to {chat_id}: {result}")
    except Exception as e:
        print(f"Error sending message to {chat_id}: {e}")
    return response

def send_video(chat_id, video_file_id, caption):
    url = f"{BASE_URL}/sendVideo"
    data = {
        'chat_id': chat_id,
        'video': video_file_id,
        'caption': caption
    }
    response = _request_with_backoff('post', url, data=data)
    try:
        result = response.json()
        if result.get('ok'):
            message_id = result['result']['message_id']
            if chat_id not in all_messages:
                all_messages[chat_id] = []
            all_messages[chat_id].append(message_id)
            if chat_id not in video_messages:
                video_messages[chat_id] = []
            video_messages[chat_id].append(message_id)
            # Also track as a bot message if we sent it (so /del in private can remove it)
            if chat_id not in bot_messages:
                bot_messages[chat_id] = []
            bot_messages[chat_id].append(message_id)
    except:
        pass
    return response


def is_bot_admin(chat_id):
    """Return True if bot is admin/creator in chat_id."""
    global BOT_ID
    if BOT_ID is None:
        return False
    try:
        url = f"{BASE_URL}/getChatMember"
        params = {'chat_id': chat_id, 'user_id': BOT_ID}
        r = requests.get(url, params=params)
        j = r.json()
        if not j.get('ok'):
            return False
        status = j['result'].get('status')
        return status in ('administrator', 'creator')
    except Exception:
        return False

def delete_message(chat_id, message_id):
    url = f"{BASE_URL}/deleteMessage"
    data = {
        'chat_id': chat_id,
        'message_id': message_id
    }
    _request_with_backoff('post', url, data=data)

def get_updates():
    global last_update_id
    url = f"{BASE_URL}/getUpdates"
    params = {'offset': last_update_id + 1}
    response = requests.get(url, params=params)
    return response.json()

def main():
    global episode_counter, last_update_id
    load_state()
    # Get bot info
    bot_info_url = f"{BASE_URL}/getMe"
    bot_response = requests.get(bot_info_url)
    if bot_response.status_code == 200:
        bot_data = bot_response.json()
        if bot_data['ok']:
            BOT_ID = bot_data['result']['id']
            BOT_USERNAME = bot_data['result']['username']
            print(f"Bot started! Username: @{BOT_USERNAME}")
        else:
            print("Bot started!")
    else:
        print("Bot started!")
    
    while True:
        try:
            updates = get_updates()
            
            if updates['ok']:
                for update in updates['result']:
                    last_update_id = update['update_id']
                    
                    if 'callback_query' in update:
                        chat_id = update['callback_query']['message']['chat']['id']
                        # Auto-enable for groups/channels
                        if chat_id < 0:
                            started_users.add(chat_id)
                        elif chat_id not in started_users:
                            callback_url = f"{BASE_URL}/answerCallbackQuery"
                            callback_data = {'callback_query_id': update['callback_query']['id']}
                            requests.post(callback_url, data=callback_data)
                            send_message(chat_id, "Please send /start first to activate the bot! 🚀")
                            continue
                        
                        quality = update['callback_query']['data']
                        user_quality[chat_id] = quality
                        # clear waiting flag and persist selection
                        user_waiting_quality.discard(chat_id)
                        save_state()
                        
                        callback_url = f"{BASE_URL}/answerCallbackQuery"
                        callback_data = {'callback_query_id': update['callback_query']['id']}
                        requests.post(callback_url, data=callback_data)
                        
                        send_message(chat_id, f"Quality set to {quality}p!")
                        # Ask for episode number to start from (works in private and channels)
                        send_message(chat_id, "Please send the episode number to start from (e.g., 5).")
                        user_waiting_episode.add(chat_id)
                    
                    elif 'message' in update:
                        chat_id = update['message']['chat']['id']
                        # Track incoming user message ids so admin /del can remove them
                        msg_id = update['message'].get('message_id')
                        if msg_id is not None:
                            if chat_id not in all_messages:
                                all_messages[chat_id] = []
                            all_messages[chat_id].append(msg_id)
                        chat_type = "group/channel" if chat_id < 0 else "private"
                        print(f"Received message from {chat_type} chat_id: {chat_id}")
                        
                        # Auto-enable for groups/channels
                        if chat_id < 0:
                            started_users.add(chat_id)
                        
                        if 'text' in update['message']:
                            text = update['message']['text']
                            handle_text(chat_id, text)
                        
                        elif 'video' in update['message']:
                            # Track user's video message id as well
                            vid_msg_id = update['message'].get('message_id')
                            if vid_msg_id is not None:
                                if chat_id not in all_messages:
                                    all_messages[chat_id] = []
                                all_messages[chat_id].append(vid_msg_id)
                            video_file_id = update['message']['video']['file_id']
                            handle_video(chat_id, video_file_id)

                    # Handle posts in channels (they appear as 'channel_post' in updates)
                    elif 'channel_post' in update:
                        post = update['channel_post']
                        chat_id = post['chat']['id']
                        # Track incoming channel_post ids so admin /del can remove them
                        post_id = post.get('message_id')
                        if post_id is not None:
                            if chat_id not in all_messages:
                                all_messages[chat_id] = []
                            all_messages[chat_id].append(post_id)
                        chat_type = "group/channel" if chat_id < 0 else "private"
                        print(f"Received channel_post from {chat_type} chat_id: {chat_id}")

                        # Auto-enable for channels
                        if chat_id < 0:
                            started_users.add(chat_id)

                        if 'text' in post:
                            text = post['text']
                            handle_text(chat_id, text)

                        if 'video' in post:
                            video_file_id = post['video']['file_id']
                            handle_video(chat_id, video_file_id)
            
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
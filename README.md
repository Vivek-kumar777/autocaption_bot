Telegram Bot Notes

Why the bot didn't reply in a channel

- Channel posts are delivered as `channel_post` updates (not `message`). The bot previously only handled `message` updates, so it ignored posts in channels.
- Telegram only delivers `channel_post` updates for channels where the bot is a member with appropriate permissions (usually the bot must be added as an administrator of the channel).

What I changed

- Added handling for `channel_post` in `bot.py` so the bot will process text and video posts in channels similarly to private messages and groups.- Refactored text/video handling into shared `handle_text` and `handle_video` functions so all commands now work the same in private chats, groups, and channels.
What you should check

1. Make sure the bot is added to the channel and given admin rights (at least permission to read/post messages).
2. Send `/start` in the channel (or make sure the bot is activated there) so the bot's `started_users` set can include that channel id. `/start` activates the bot and resets this chat's episode counter to 1 and quality to the default (480p). Use `/refresh` to also reset the episode counter (alternative) and `/stop` to deactivate the bot.
3. Keep your bot running (long-polling or webhook) so it receives updates.
Persistence

- The bot now saves `episode_counter`, `user_quality`, and `started_users` to `bot_state.json` whenever they change and loads them at startup. This prevents sending `/start` or restarting the process from resetting progress.
If you want, I can also add a small health-check endpoint or a webhook setup for production hosting.

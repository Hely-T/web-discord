# Archive Bot Source

Imported from `/Users/hely-t/Downloads/archive-2026-02-12T215354+0100`.

This folder keeps the imported Discord bot source beside the active Bleck Lous web app. The live unified entrypoint is `../main.py`; `../app.py` is the web module. The archive code is exposed on the website Commands page through `ARCHIVE_FEATURES`.

## Included Features

- Voice manager: join, leave, leave all, status, mic toggle, speaker toggle, set voice state, auto-reconnect.
- Spam tools: spam text, spam from `data/spam.txt`, stop one task, stop all tasks.
- Auto quotes: post rotating lines from `data/quotes.txt`, stop quote task.
- Monitoring: runtime status, ping, voice sessions, spam tasks, quote tasks.
- Help/reload: command menu, quick help, cog reload.

The authenticated web dashboard can update the shared bot presence and control voice rooms. Personal Discord Rich Presence remains separate for each user.

## Running This Archive Source

Create a real `config.json` from `config.example.json`, then run the unified app from the parent folder:

```bash
cd ..
python3 main.py
```

Do not commit real Discord tokens or webhook URLs.

For the unified app, use a Bot token from Discord Developer Portal and enable Message Content Intent if you want prefix commands to work.

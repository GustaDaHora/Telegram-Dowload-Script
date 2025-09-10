# Telegram Media Downloader

A simple, efficient Python script to download media from Telegram channels using Telethon. Built with async programming for performance, secure credential handling, and user-friendly CLI interactions.

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Features

- **Secure Authentication**: Loads Telegram API credentials from a `.env` file.
- **Channel Selection**: Lists all joined channels and allows selection by number.
- **Media Type Filtering**: Download images, videos, PDFs, ZIP files, or all media types.
- **Efficient Fetching**: Retrieves up to 2000 recent messages with async iterators.
- **Batch Downloads**: Concurrent downloads in batches (configurable, default: 5) to respect rate limits.
- **Progress Bars**: Real-time progress tracking with colored, multi-bar displays using tqdm and colorama.
- **Duplicate Skipping**: Checks and skips existing files in the destination folder.
- **Organized Storage**: Saves files to type-specific subfolders under `downloads/`.
- **Error Handling**: Graceful handling of invalid inputs, connection issues, and download failures.

## Installation

1. Clone the repository:

```

git clone https://github.com/yourusername/telegram-media-downloader.git
cd telegram-media-downloader

```

2. Install dependencies using pip (Python 3.8+ required):

```

pip install -r requirements.txt

```

The `requirements.txt` should include:

```

telethon==1.36.0
tqdm==4.66.5
colorama==0.4.6
python-dotenv==1.0.1

```

3. Create a `.env` file in the root directory with your Telegram API credentials:

```

API_ID=your_api_id
API_HASH=your_api_hash
SESSION_NAME=your_session_name (optional, default: default_session)
BATCH_SIZE=5 (optional, default: 5)

```

Obtain API_ID and API_HASH from [my.telegram.org](https://my.telegram.org).

## Usage

Run the script:

```

python main.py

```

- It will connect to Telegram and list your joined channels.
- Select a channel by number.
- Choose the media type (1-5).
- Media will be downloaded to `downloads/<type>/`, with progress bars shown.

Example output:

```

Connected successfully!
Joined channels:

1. Example Channel (@example) (ID: 123456789)
   Enter the number of the channel to select: 1
   Selected channel: Example Channel (ID: 123456789)
   Choose the type of content to download:
1. Images
   ...
   Enter your choice (1-5): 2
   Fetching media messages...
   Found 50 messages with matching media.
   [Progress bars for downloads...]

```

## Dependencies

- [Telethon](https://docs.telethon.dev/): For Telegram API interactions (v1.36.0, latest stable).
- [tqdm](https://tqdm.github.io/): For progress bars.
- [colorama](https://pypi.org/project/colorama/): For cross-platform colored console output.
- [python-dotenv](https://pypi.org/project/python-dotenv/): For loading environment variables.

All dependencies are pinned to stable versions for reliability. No extras like testing frameworks are included to avoid overengineering.

## Security Notes

- Credentials are stored in `.env` (gitignore'd by default—ensure it's in your .gitignore).
- The script does not handle sensitive data beyond API creds.
- Use at your own risk; respect Telegram's terms and channel permissions.

## Contributing

Contributions are welcome! Fork the repo, create a feature branch, and submit a PR. Keep changes focused on clean code, performance, and maintainability. No overengineering—justify additions.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Built with ❤️ by Gustavo da Hora. If you find this useful, star the repo!

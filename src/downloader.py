import asyncio
import os
import mimetypes
from datetime import datetime
from dotenv import load_dotenv
from colorama import Fore, Style
from tqdm import tqdm
from telethon import TelegramClient
from telethon.tl.types import (
    InputMessagesFilterVideo,
    InputMessagesFilterPhotos,
    InputMessagesFilterDocument,
    Photo,
    Document,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
)

# Load environment variables
load_dotenv()

# Retrieve values from .env with type safety and defaults
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
session_name = os.getenv("SESSION_NAME", "default_session")
batch_size = int(os.getenv("BATCH_SIZE", "5"))

def get_filename(message):
    """Helper to compute the original filename for the media without downloading."""
    if message.photo:
        return f"photo_{message.photo.id}.jpg"
    elif message.document:
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name
        ext = mimetypes.guess_extension(message.document.mime_type) or '.bin'
        # Check for video
        if any(isinstance(attr, DocumentAttributeVideo) for attr in message.document.attributes):
            ext = ext or '.mp4'
        return f"document_{message.document.id}{ext}"
    return None

def get_finished_messages(channel_id):
    """Load finished message IDs for the given channel from the log."""
    log_path = os.path.join('downloads', 'download_log.txt')
    finished = set()
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            for line in f:
                try:
                    parts = line.strip().split(' - ')
                    if len(parts) == 4:
                        timestamp = parts[0]
                        chan_str = parts[1]
                        msg_file = parts[2]
                        status = parts[3]
                        cid = int(chan_str.replace('Channel ', ''))
                        mid_str, _ = msg_file.split(': ', 1)
                        mid = int(mid_str.replace('Message ', ''))
                        if status == 'Finished' and cid == channel_id:
                            finished.add(mid)
                except ValueError:
                    pass  # Skip malformed lines
    return finished

def log_status(channel_id, message_id, filename, status):
    """Append a status entry to the download log."""
    log_path = os.path.join('downloads', 'download_log.txt')
    os.makedirs('downloads', exist_ok=True)
    with open(log_path, 'a') as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Channel {channel_id} - Message {message_id}: {filename} - {status}\n")

async def get_file_size(message):
    """Helper to get media file size safely."""
    if message.photo:
        return message.photo.sizes[-1].size if message.photo.sizes else 0
    elif message.document:
        return message.document.size
    return 0

async def download_file(message, download_path, progress_bars, channel_id, finished_ids):
    try:
        file_size = await get_file_size(message)
        if file_size == 0:
            return  # Skip if no media or size unknown

        orig_filename = get_filename(message)
        if not orig_filename:
            return  # Skip if unable to determine filename

        filename = f"{message.id}_{orig_filename}"

        if message.id in finished_ids:
            log_status(channel_id, message.id, filename, "Skipped")
            print(f"{Fore.YELLOW}Skipping already downloaded file: {filename}{Style.RESET_ALL}")
            return

        full_path = os.path.join(download_path, filename)

        log_status(channel_id, message.id, filename, "Downloading")

        # Assign position for multi-bar support (prevents overlapping outputs)
        position = len(progress_bars)
        progress_bar = tqdm(
            total=file_size,
            desc=f"Downloading {message.id}",
            ncols=100,
            unit="B",
            unit_scale=True,
            leave=True,
            position=position,
            bar_format=(
                "{l_bar}%s{bar}%s| {n_fmt}/{total_fmt} {unit} "
                "| Elapsed: {elapsed}/{remaining} | {rate_fmt}"
                % (Fore.BLUE, Style.RESET_ALL)
            ),
        )
        progress_bars.append(progress_bar)

        await message.download_media(
            file=full_path,
            progress_callback=lambda current, total: progress_bar.update(current - progress_bar.n),
        )

        # Update to finished state
        progress_bar.bar_format = (
            "{l_bar}%s{bar}%s| {n_fmt}/{total_fmt} {unit} "
            "| Elapsed: {elapsed} | {rate_fmt}" % (Fore.GREEN, Style.RESET_ALL)
        )
        progress_bar.set_description(f"Finished {message.id}")
        progress_bar.update(file_size - progress_bar.n)  # Ensure 100%
        progress_bar.refresh()

        log_status(channel_id, message.id, filename, "Finished")

    except Exception as e:
        print(f"{Fore.RED}Error downloading media for message {message.id}: {e}{Style.RESET_ALL}")
        if 'filename' in locals():
            log_status(channel_id, message.id, filename, f"Error: {e}")
    finally:
        if 'progress_bar' in locals():
            progress_bar.close()

async def download_in_batches(messages, download_path, batch_size, channel_id, finished_ids):
    progress_bars = []  # Shared list for all progress bars (positions accumulate)
    tasks = []
    for i, message in enumerate(messages):
        orig_filename = get_filename(message)
        if orig_filename:
            filename = f"{message.id}_{orig_filename}"
            log_status(channel_id, message.id, filename, "In Queue")
        tasks.append(download_file(message, download_path, progress_bars, channel_id, finished_ids))
        if len(tasks) == batch_size or (i + 1) == len(messages):
            await asyncio.gather(*tasks)
            tasks = []  # Reset tasks for next batch
    # Close all remaining bars after all batches
    for pb in progress_bars:
        pb.close()

async def main():
    try:
        async with TelegramClient(session_name, api_id, api_hash) as client:
            print(f"{Fore.GREEN}Connected successfully!{Style.RESET_ALL}")
            
            # Fetch all dialogs and filter for channels (joined/subscribed)
            dialogs = await client.get_dialogs()
            channels = [d for d in dialogs if d.is_channel]
            
            if not channels:
                print(f"{Fore.RED}No joined channels found. Exiting...{Style.RESET_ALL}")
                return
            
            print(f"{Fore.CYAN}Joined channels:{Style.RESET_ALL}")
            for i, dialog in enumerate(channels, 1):
                channel_entity = dialog.entity
                username = f" (@{channel_entity.username})" if channel_entity.username else ""
                print(f"{i}. {dialog.name}{username} (ID: {channel_entity.id})")
            
            # User selection
            try:
                selection = int(input(f"{Fore.CYAN}Enter the number of the channel to select: {Style.RESET_ALL}"))
                if 1 <= selection <= len(channels):
                    channel = channels[selection - 1].entity
                    print(f"{Fore.YELLOW}Selected channel: {channels[selection - 1].name} (ID: {channel.id}){Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}Invalid selection. Exiting...{Style.RESET_ALL}")
                    return
            except ValueError:
                print(f"{Fore.RED}Invalid input. Please enter a number. Exiting...{Style.RESET_ALL}")
                return

            channel_id = channel.id
            finished_ids = get_finished_messages(channel_id)

            print(
                f"{Fore.CYAN}Choose the type of content to download:{Style.RESET_ALL}\n"
                f"1. Images\n"
                f"2. Videos\n"
                f"3. PDFs\n"
                f"4. ZIP files\n"
                f"5. All media types\n"
            )
            choice = input(f"{Fore.CYAN}Enter your choice (1-5): {Style.RESET_ALL}")

            folder_name = ""
            filter_type = None
            mime_types = None

            if choice == "1":
                filter_type = InputMessagesFilterPhotos
                folder_name = "images"
            elif choice == "2":
                filter_type = InputMessagesFilterVideo
                folder_name = "videos"
            elif choice == "3":
                filter_type = InputMessagesFilterDocument
                folder_name = "pdfs"
                mime_types = ["application/pdf"]
            elif choice == "4":
                filter_type = InputMessagesFilterDocument
                folder_name = "zips"
                mime_types = ["application/zip"]
            elif choice == "5":
                filter_type = None  # Will filter for any media later
                folder_name = "all_media"
            else:
                print(f"{Fore.RED}Invalid choice! Exiting...{Style.RESET_ALL}")
                return

            download_path = f"downloads/{folder_name}"
            os.makedirs(download_path, exist_ok=True)

            print(f"{Fore.YELLOW}Fetching media messages...{Style.RESET_ALL}")
            # Use iter_messages for efficiency, collect up to limit
            media_messages = []
            async for msg in client.iter_messages(channel, filter=filter_type, limit=2000):
                if choice == "5":
                    if msg.media:  # Only include messages with any media
                        media_messages.append(msg)
                elif mime_types:
                    if msg.document and msg.document.mime_type in mime_types:
                        media_messages.append(msg)
                else:
                    media_messages.append(msg)

            print(f"{Fore.YELLOW}Found {len(media_messages)} messages with matching media.{Style.RESET_ALL}")

            if media_messages:
                await download_in_batches(media_messages, download_path, batch_size, channel_id, finished_ids)
            else:
                print(f"{Fore.RED}No media found for the selected type.{Style.RESET_ALL}")

    except ValueError as ve:
        print(f"{Fore.RED}Invalid input: {ve}. Please ensure valid selections.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error in main execution: {e}. Verify your API credentials and Telegram connection.{Style.RESET_ALL}")

if __name__ == "__main__":
    asyncio.run(main())
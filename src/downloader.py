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

def get_log_path(channel_id, channel_name):
    """Get the log file path for a specific channel."""
    # Clean channel name for filename (remove invalid characters)
    clean_name = "".join(c for c in channel_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    clean_name = clean_name.replace(' ', '_')
    log_filename = f"channel_{channel_id}_{clean_name}_log.txt"
    return os.path.join('downloads', log_filename)

def load_file_statuses(log_path):
    """Load file statuses from the log file. Returns dict {message_id: (filename, status)}."""
    file_statuses = {}
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    parts = line.strip().split(' - ')
                    if len(parts) >= 4:
                        # Extract message ID from "Message X: filename"
                        msg_part = parts[2]  # "Message 1707: 1707_filename.mp4"
                        if ': ' in msg_part:
                            msg_id_str = msg_part.split(': ')[0].replace('Message ', '')
                            msg_id = int(msg_id_str)
                            filename = msg_part.split(': ', 1)[1]
                            status = parts[-1]  # Last part is always status
                            file_statuses[msg_id] = (filename, status)
                except (ValueError, IndexError):
                    continue  # Skip malformed lines
    return file_statuses

def update_file_status(log_path, channel_id, message_id, filename, new_status, file_statuses):
    """Update the status of a specific file in the log and in-memory cache."""
    file_statuses[message_id] = (filename, new_status)
    
    # Rewrite the entire log file with updated statuses
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as f:
        for msg_id, (fname, status) in file_statuses.items():
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"{timestamp} - Channel {channel_id} - Message {msg_id}: {fname} - {status}\n")

def check_existing_files(download_path, file_statuses):
    """Check for existing files in download folder and mark them as Skipped."""
    if not os.path.exists(download_path):
        return file_statuses
    
    existing_files = set(os.listdir(download_path))
    updated_statuses = {}
    
    for msg_id, (filename, status) in file_statuses.items():
        if filename in existing_files and status == "In Queue":
            updated_statuses[msg_id] = (filename, "Skipped")
            print(f"{Fore.YELLOW}Found existing file, marking as Skipped: {filename}{Style.RESET_ALL}")
        else:
            updated_statuses[msg_id] = (filename, status)
    
    return updated_statuses

async def get_file_size(message):
    """Helper to get media file size safely."""
    if message.photo:
        return message.photo.sizes[-1].size if message.photo.sizes else 0
    elif message.document:
        return message.document.size
    return 0

async def download_file(message, download_path, progress_bars, channel_id, log_path, file_statuses):
    filename = None
    progress_bar = None
    
    try:
        file_size = await get_file_size(message)
        if file_size == 0:
            return  # Skip if no media or size unknown

        orig_filename = get_filename(message)
        if not orig_filename:
            return  # Skip if unable to determine filename

        filename = f"{message.id}_{orig_filename}"
        full_path = os.path.join(download_path, filename)

        # Check current status
        current_status = file_statuses.get(message.id, (filename, "In Queue"))[1]
        
        if current_status == "Skipped":
            print(f"{Fore.YELLOW}Skipping already downloaded file: {filename}{Style.RESET_ALL}")
            return
        elif current_status == "Finished":
            print(f"{Fore.GREEN}File already finished: {filename}{Style.RESET_ALL}")
            return
        elif current_status != "In Queue":
            # Reset to In Queue if it was stuck in Downloading state
            update_file_status(log_path, channel_id, message.id, filename, "In Queue", file_statuses)

        # Update status to Downloading
        update_file_status(log_path, channel_id, message.id, filename, "Downloading", file_statuses)

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

        # Update status to Finished
        update_file_status(log_path, channel_id, message.id, filename, "Finished", file_statuses)

    except Exception as e:
        print(f"{Fore.RED}Error downloading media for message {message.id}: {e}{Style.RESET_ALL}")
        if filename and message.id in file_statuses:
            update_file_status(log_path, channel_id, message.id, filename, f"Error: {e}", file_statuses)
    finally:
        if progress_bar:
            progress_bar.close()

async def download_in_batches(messages, download_path, batch_size, channel_id, log_path, file_statuses):
    progress_bars = []  # Shared list for all progress bars (positions accumulate)
    tasks = []
    
    # Only process files that are "In Queue"
    messages_to_download = [
        msg for msg in messages 
        if file_statuses.get(msg.id, ("", "In Queue"))[1] == "In Queue"
    ]
    
    print(f"{Fore.CYAN}Files to download: {len(messages_to_download)}{Style.RESET_ALL}")
    
    for i, message in enumerate(messages_to_download):
        tasks.append(download_file(message, download_path, progress_bars, channel_id, log_path, file_statuses))
        if len(tasks) == batch_size or (i + 1) == len(messages_to_download):
            await asyncio.gather(*tasks)
            tasks = []  # Reset tasks for next batch
    
    # Close all remaining bars after all batches
    for pb in progress_bars:
        pb.close()

async def initialize_log_file(messages, channel_id, channel_name, download_path):
    """Initialize log file with all found messages and check for existing files."""
    log_path = get_log_path(channel_id, channel_name)
    
    # Load existing statuses
    existing_statuses = load_file_statuses(log_path)
    
    # Create initial statuses for all messages
    file_statuses = {}
    for message in messages:
        orig_filename = get_filename(message)
        if orig_filename:
            filename = f"{message.id}_{orig_filename}"
            
            # Keep existing status if available, otherwise set to "In Queue"
            if message.id in existing_statuses:
                file_statuses[message.id] = existing_statuses[message.id]
            else:
                file_statuses[message.id] = (filename, "In Queue")
    
    # Check for existing files and update statuses
    file_statuses = check_existing_files(download_path, file_statuses)
    
    # Write the complete log file
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as f:
        for msg_id, (filename, status) in file_statuses.items():
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"{timestamp} - Channel {channel_id} - Message {msg_id}: {filename} - {status}\n")
    
    return log_path, file_statuses

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
                    channel_name = channels[selection - 1].name
                    print(f"{Fore.YELLOW}Selected channel: {channel_name} (ID: {channel.id}){Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}Invalid selection. Exiting...{Style.RESET_ALL}")
                    return
            except ValueError:
                print(f"{Fore.RED}Invalid input. Please enter a number. Exiting...{Style.RESET_ALL}")
                return

            channel_id = channel.id

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
                # Initialize log file and get file statuses
                log_path, file_statuses = await initialize_log_file(
                    media_messages, channel_id, channel_name, download_path
                )
                
                # Count files by status
                status_counts = {}
                for filename, status in file_statuses.values():
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                print(f"{Fore.CYAN}File status summary:{Style.RESET_ALL}")
                for status, count in status_counts.items():
                    color = Fore.GREEN if status == "Finished" else Fore.YELLOW if status == "Skipped" else Fore.WHITE
                    print(f"  {color}{status}: {count}{Style.RESET_ALL}")
                
                await download_in_batches(media_messages, download_path, batch_size, channel_id, log_path, file_statuses)
                
                print(f"{Fore.GREEN}Download process completed! Check the log file: {log_path}{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}No media found for the selected type.{Style.RESET_ALL}")

    except ValueError as ve:
        print(f"{Fore.RED}Invalid input: {ve}. Please ensure valid selections.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error in main execution: {e}. Verify your API credentials and Telegram connection.{Style.RESET_ALL}")

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
import platform
from base64 import b64encode
from datetime import datetime
from os import path as ospath
from pkg_resources import get_distribution, DistributionNotFound
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, path as aiopath, mkdir
from re import match as re_match
from time import time
from html import escape
from uuid import uuid4
from subprocess import run as srun
from psutil import disk_usage, disk_io_counters, Process, cpu_percent, swap_memory, cpu_count, cpu_freq, getloadavg, virtual_memory, net_io_counters, boot_time
from asyncio import create_subprocess_exec, create_subprocess_shell, run_coroutine_threadsafe, sleep
from asyncio.subprocess import PIPE
from functools import partial, wraps
from concurrent.futures import ThreadPoolExecutor

from aiohttp import ClientSession as aioClientSession
from psutil import virtual_memory, cpu_percent, disk_usage
from requests import get as rget
from mega import MegaApi
from pyrogram.enums import ChatType
from pyrogram.types import BotCommand
from pyrogram.errors import PeerIdInvalid

from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.themes import BotTheme
from bot.version import get_version
from bot import OWNER_ID, bot_name, bot_cache, DATABASE_URL, LOGGER, get_client, aria2, download_dict, download_dict_lock, botStartTime, user_data, config_dict, bot_loop, extra_buttons, user
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot.helper.ext_utils.shortners import short_url

THREADPOOL   = ThreadPoolExecutor(max_workers=1000)
MAGNET_REGEX = r'magnet:\?xt=urn:(btih|btmh):[a-zA-Z0-9]*\s*'
URL_REGEX    = r'^(?!\/)(rtmps?:\/\/|mms:\/\/|rtsp:\/\/|https?:\/\/|ftp:\/\/)?([^\/:]+:[^\/@]+@)?(www\.)?(?=[^\/:\s]+\.[^\/:\s]+)([^\/:\s]+\.[^\/:\s]+)(:\d+)?(\/[^#\s]*[\s\S]*)?(\?[^#\s]*)?(#.*)?$'
SIZE_UNITS   = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB']
STATUS_START = 0
PAGES        = 1
PAGE_NO      = 1


class MirrorStatus:
    if EMOJI_THEME is True:
        STATUS_UPLOADING = "📤 Upload"
        STATUS_DOWNLOADING = "📥 Download"
        STATUS_CLONING = "♻️ Clone"
        STATUS_WAITING = "💤 Queue"
        STATUS_PAUSED = "⛔️ Pause"
        STATUS_ARCHIVING = "🔐 Archive"
        STATUS_EXTRACTING = "📂 Extract"
        STATUS_SPLITTING = "✂️ Split"
        STATUS_CHECKING = "📝 CheckUp"
        STATUS_SEEDING = "🌧 Seed"
    else:
        STATUS_UPLOADING = "Upload"
        STATUS_DOWNLOADING = "Download"
        STATUS_CLONING = "Clone"
        STATUS_WAITING = "Queue"
        STATUS_PAUSED = "Pause"
        STATUS_ARCHIVING = "Archive"
        STATUS_EXTRACTING = "Extract"
        STATUS_SPLITTING = "Split"
        STATUS_CHECKING = "CheckUp"
        STATUS_SEEDING = "Seed"

class EngineStatus:
    STATUS_ARIA = "Aria2c📶"
    STATUS_GD = "Google Api♻️"
    STATUS_MEGA = "MegaSDK⭕️"
    STATUS_QB = "qBittorrent🦠"
    STATUS_TG = "Pyrogram💥"
    STATUS_YT = "YT-dlp🌟"
    STATUS_EXT = "Extract | pExtract⚔️"
    STATUS_SPLIT = "FFmpeg✂️"
    STATUS_ZIP = "p7zip🛠"

    
SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = Event()
        thread = Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time() + self.interval
        while not self.stopEvent.wait(nextTime - time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'

def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            if dl.gid() == gid:
                return dl
    return None

def getAllDownload(req_status: str):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if req_status in ['all', status]:
                return dl
    return None

def bt_selection_buttons(id_: str):
    if len(id_) > 20:
        gid = id_[:12]
    else:
        gid = id_

    pincode = ""
    for n in id_:
        if n.isdigit():
            pincode += str(n)
        if len(pincode) == 4:
            break

    buttons = ButtonMaker()
    if WEB_PINCODE:
        buttons.buildbutton("Select Files", f"{BASE_URL}/app/files/{id_}")
        buttons.sbutton("Pincode", f"btsel pin {gid} {pincode}")
    else:
        buttons.buildbutton("Select Files", f"{BASE_URL}/app/files/{id_}?pin_code={pincode}")
    buttons.sbutton("Done Selecting", f"btsel done {gid} {id_}")
    return buttons.build_menu(2)


def get_user_task(user_id):
    user_task = 0
    for task in list(download_dict.values()):
        userid = task.message.from_user.id
        if userid == user_id: user_task += 1
    return user_task

def timeformatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + " days, ") if days else "") + \
        ((str(hours) + " hours, ") if hours else "") + \
        ((str(minutes) + " min, ") if minutes else "") + \
        ((str(seconds) + " sec, ") if seconds else "") + \
        ((str(milliseconds) + " millisec, ") if milliseconds else "")
    return tmp[:-2]

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    p_str = '■' * cFull
    p_str += '□'  * (12 - cFull)
    p_str = f"[{p_str}]"
    return p_str


def get_readable_message():
    with download_dict_lock:
        msg = f""
        if STATUS_LIMIT is not None:
            tasks = len(download_dict)
            global pages
            globals()['PAGES'] = ceil(tasks/STATUS_LIMIT)
            if PAGE_NO > PAGES and PAGES != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
        for index, download in enumerate(list(download_dict.values())[COUNT:], start=1):
            msg += f"<b>╭ <a href='{download.message.link}'>{download.status()}</a>: </b>"
            msg += f"<code>{escape(str(download.name()))}</code>"
            if download.status() not in [MirrorStatus.STATUS_SEEDING, MirrorStatus.STATUS_SPLITTING]:
                if EMOJI_THEME is True:
                    msg += f"\n<b>├</b>{get_progress_bar_string(download)} {download.progress()}"
                    msg += f"\n<b>├🔄 Process:</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                    msg += f"\n<b>├⚡ Speed:</b> {download.speed()}"
                    msg += f"\n<b>├⏳ ETA:</b> {download.eta()}"
                    msg += f"<b> | Elapsed: </b>{get_readable_time(time() - download.message.date.timestamp())}"
                    msg += f"\n<b>├⛓️ Engine :</b> {download.eng()}"

                else:
                    msg += f"\n<b>├</b>{get_progress_bar_string(download)} {download.progress()}"
                    msg += f"\n<b>├ Process:</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                    msg += f"\n<b>├ Speed:</b> {download.speed()}"
                    msg += f"\n<b>├ ETA:</b> {download.eta()}"
                    msg += f"<b> | Elapsed: </b>{get_readable_time(time() - download.message.date.timestamp())}"
                    msg += f"\n<b>├ Engine :</b> {download.eng()}"

                if hasattr(download, 'seeders_num'):
                    try:
                        if EMOJI_THEME is True:
                            msg += f"\n<b>├🌱 Seeders:</b> {download.seeders_num()} | <b>🐌 Leechers:</b> {download.leechers_num()}"
                            # msg += f"\n<b>├🧿 To Select:</b> <code>/{BotCommands.BtSelectCommand} {download.gid()}</code>"
                        else:
                            msg += f"\n<b>├ Seeders:</b> {download.seeders_num()} | <b>Leechers:</b> {download.leechers_num()}"
                            # msg += f"\n<b>├ To Select:</b> <code>/{BotCommands.BtSelectCommand} {download.gid()}</code>"
                    except:
                        pass
                if download.message.chat.type != 'private':
                    try:
                        chatid = str(download.message.chat.id)[4:]
                        if EMOJI_THEME is True:
                            msg += f'\n<b>├🌐 Source: </b><a href="https://t.me/c/{chatid}/{download.message.message_id}">{download.message.from_user.first_name}</a> | <b>Id :</b> <code>{download.message.from_user.id}</code>'
                            msg += f"\n<b>╰❌ </b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"
                        else:
                            msg += f'\n<b>├ Source: </b><a href="https://t.me/c/{chatid}/{download.message.message_id}">{download.message.from_user.first_name}</a> | <b>Id :</b> <code>{download.message.from_user.id}</code>'
                            msg += f"\n<b>╰ </b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"                 
                    except:
                        pass
                else:
                    if EMOJI_THEME is True:
                        msg += f'\n<b>├👤 User:</b> ️<code>{download.message.from_user.first_name}</code> | <b>Id:</b> <code>{download.message.from_user.id}</code>'
                        msg += f"\n<b>╰❌ </b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"
                    else:
                        msg += f'\n<b>├ User:</b> ️<code>{download.message.from_user.first_name}</code> | <b>Id:</b> <code>{download.message.from_user.id}</code>'
                        msg += f"\n<b>╰ </b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"

            elif download.status() == MirrorStatus.STATUS_SEEDING:
                if EMOJI_THEME is True:
                    msg += f"\n<b>├📦 Size: </b>{download.size()}"
                    msg += f"\n<b>├⛓️ Engine:</b> <code>qBittorrent v4.4.2</code>"
                    msg += f"\n<b>├⚡ Speed: </b>{download.upload_speed()}"
                    msg += f"\n<b>├🔺 Uploaded: </b>{download.uploaded_bytes()}"
                    msg += f"\n<b>├📎 Ratio: </b>{download.ratio()}"
                    msg += f" | <b>⏲️ Time: </b>{download.seeding_time()}"
                    msg += f"\n<b>├⏳ Elapsed: </b>{get_readable_time(time() - download.message.date.timestamp())}"
                    msg += f"\n<b>╰❌ </b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"
                else:
                    msg += f"\n<b>├ Size: </b>{download.size()}"
                    msg += f"\n<b>├ Engine:</b> <code>qBittorrent v4.4.2</code>"
                    msg += f"\n<b>├ Speed: </b>{download.upload_speed()}"
                    msg += f"\n<b>├ Uploaded: </b>{download.uploaded_bytes()}"
                    msg += f"\n<b>├ Ratio: </b>{download.ratio()}"
                    msg += f" | <b> Time: </b>{download.seeding_time()}"
                    msg += f"\n<b>├ Elapsed: </b>{get_readable_time(time() - download.message.date.timestamp())}"
                    msg += f"\n<b>╰ </b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            else:
                if EMOJI_THEME is True:
                    msg += f"\n<b>├⛓️ Engine :</b> {download.eng()}"
                    msg += f"\n<b>╰📐 Size: </b>{download.size()}"
                else:
                    msg += f"\n<b>├ Engine :</b> {download.eng()}"
                    msg += f"\n<b>╰ Size: </b>{download.size()}"
            msg += f"\n<b>_________________________________</b>"
            msg += "\n\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        if len(msg) == 0:
            return None, None
        dl_speed = 0
        up_speed = 0
        for download in list(download_dict.values()):
            spd = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                spd = download.speed()
                if 'K' in spd:
                    dl_speed += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    dl_speed += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_UPLOADING:
                spd = download.speed()
                if 'KB/s' in spd:
                    up_speed += float(spd.split('K')[0]) * 1024
                elif 'MB/s' in spd:
                    up_speed += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                spd = download.upload_speed()
                if 'K' in spd:
                    up_speed += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    up_speed += float(spd.split('M')[0]) * 1048576
        if EMOJI_THEME is True:
            bmsg = f"<b>🖥 CPU:</b> {cpu_percent()}% | <b>💿 FREE:</b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
            bmsg += f"\n<b>🎮 RAM:</b> {virtual_memory().percent}% | <b>🟢 UPTIME:</b> {get_readable_time(time() - botStartTime)}"
            bmsg += f"\n<b>🔻 DL:</b> {get_readable_file_size(dl_speed)}/s | <b>🔺 UL:</b> {get_readable_file_size(up_speed)}/s"
        else:
            bmsg = f"<b>CPU:</b> {cpu_percent()}% | <b>FREE:</b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
            bmsg += f"\n<b>RAM:</b> {virtual_memory().percent}% | <b>UPTIME:</b> {get_readable_time(time() - botStartTime)}"
            bmsg += f"\n<b>DL:</b> {get_readable_file_size(dl_speed)}/s | <b>UL:</b> {get_readable_file_size(up_speed)}/s"
        
        buttons = ButtonMaker()
        buttons.sbutton("Refresh", "status refresh")
        buttons.sbutton("Statistics", str(THREE))
        buttons.sbutton("Close", "status close")
        sbutton = buttons.build_menu(3)
        
        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:
            msg += f"<b>Tasks:</b> {tasks}\n"
            buttons = ButtonMaker()
            if EMOJI_THEME is True:
                buttons.sbutton("⏪Previous", "status pre")
                buttons.sbutton(f"{PAGE_NO}/{PAGES}", str(THREE))
                buttons.sbutton("Next⏩", "status nex")
                buttons.sbutton("Refresh", "status refresh")
                buttons.sbutton("Close", "status close")
            else:
                buttons.sbutton("Previous", "status pre")
                buttons.sbutton(f"{PAGE_NO}/{PAGES}", str(THREE))
                buttons.sbutton("Next", "status nex")
                buttons.sbutton("Refresh", "status refresh")
                buttons.sbutton("Close", "status close")
            button = buttons.build_menu(3)
            return msg + bmsg, button
        return msg + bmsg, sbutton

def turn(data):
    try:
        with download_dict_lock:
            global COUNT, PAGE_NO
            if data[1] == "nex":
                if PAGE_NO == PAGES:
                    COUNT = 0
                    PAGE_NO = 1
                else:
                    COUNT += STATUS_LIMIT
                    PAGE_NO += 1
            elif data[1] == "pre":
                if PAGE_NO == 1:
                    COUNT = STATUS_LIMIT * (PAGES - 1)
                    PAGE_NO = PAGES
                else:
                    COUNT -= STATUS_LIMIT
                    PAGE_NO -= 1
        return True
    except:
        return False

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def is_url(url: str):
    url = re_findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_gdtot_link(url: str):
    url = re_match(r'https?://.+\.gdtot\.\S+', url)
    return bool(url)

def is_unified_link(url: str):
    url = re_match(r'https?://(appdrive|driveapp|driveace|gdflix|drivebit|drivesharer|drivepro)\.\S+', url)
    if bool(url) == True:
        return bool(url)
    else:
        return False

def is_udrive_link(url: str):
    if 'drivehub.ws' in url:
        return 'drivehub.ws' in url
    else:
        url = re_match(r'https?://(hubdrive|katdrive|kolop|drivefire|drivebuzz)\.\S+', url)
        return bool(url)

def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re_findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def get_content_type(link: str) -> str:
    try:
        res = rhead(link, allow_redirects=True, timeout=5, headers = {'user-agent': 'Wget/1.12'})
        content_type = res.headers.get('content-type')
    except:
        try:
            res = urlopen(link, timeout=5)
            info = res.info()
            content_type = info.get_content_type()
        except:
            content_type = None
    return content_type


ONE, TWO, THREE = range(3)
def pop_up_stats(update, context):
    query = update.callback_query
    stats = bot_sys_stats()
    query.answer(text=stats, show_alert=True)
def bot_sys_stats():
    currentTime = get_readable_time(time() - botStartTime)
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage(DOWNLOAD_DIR).percent
    total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
    num_active = 0
    num_upload = 0
    num_split = 0
    num_extract = 0
    num_archi = 0
    tasks = len(download_dict)
    for stats in list(download_dict.values()):
       if stats.status() == MirrorStatus.STATUS_DOWNLOADING:
                num_active += 1
       if stats.status() == MirrorStatus.STATUS_UPLOADING:
                num_upload += 1
       if stats.status() == MirrorStatus.STATUS_ARCHIVING:
                num_archi += 1
       if stats.status() == MirrorStatus.STATUS_EXTRACTING:
                num_extract += 1
       if stats.status() == MirrorStatus.STATUS_SPLITTING:
                num_split += 1
    stats = f"""
CPU : {cpu}% | RAM : {mem}%
DL : {num_active} | UP : {num_upload} | SPLIT : {num_split}
ZIP : {num_archi} | UNZIP : {num_extract} | TOTAL : {tasks}
Limits : T/D : {TORRENT_DIRECT_LIMIT}GB | Z/U : {ZIP_UNZIP_LIMIT}GB
                    L : {LEECH_LIMIT}GB | M : {MEGA_LIMIT}GB
Made with ❤️ by {CREDIT_NAME}
"""
    return stats
dispatcher.add_handler(
    CallbackQueryHandler(pop_up_stats, pattern="^" + str(THREE) + "$")
)
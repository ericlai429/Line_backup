import os
import sys
import shutil
import sqlite3

# Standard Apple & DearMob Backup Paths
BACKUP_PATHS = [
    os.path.expandvars(r"%USERPROFILE%\AppData\Roaming\Apple Computer\MobileSync\Backup"),
    os.path.expandvars(r"%USERPROFILE%\Apple\MobileSync\Backup"),
    os.path.expandvars(r"%USERPROFILE%\Documents\DearMobiPhoneManager\Backup"),
    os.path.expandvars(r"%USERPROFILE%\Documents\DearMobiPhoneManager")
]

OUTPUT_DIR = r"D:\LineExport"

def get_latest_backup_dir():
    newest_backup = None
    newest_time = 0
    
    # 1. Search standard paths
    for path in BACKUP_PATHS:
        if not os.path.exists(path):
            continue
        if os.path.exists(os.path.join(path, "Manifest.db")):
            mtime = os.path.getmtime(path)
            if mtime > newest_time:
                newest_time = mtime
                newest_backup = path
        else:
            try:
                for folder in os.listdir(path):
                    folder_path = os.path.join(path, folder)
                    if os.path.isdir(folder_path):
                        if os.path.exists(os.path.join(folder_path, "Manifest.db")):
                            mtime = os.path.getmtime(folder_path)
                            if mtime > newest_time:
                                newest_time = mtime
                                newest_backup = folder_path
            except Exception:
                pass

    # 2. Dynamic D: drive search up to depth 2 (for custom DearMob paths)
    for base_path in [r"D:\\"]:
        if not os.path.exists(base_path):
            continue
        try:
            for root, dirs, files in os.walk(base_path):
                # Calculate depth
                rel_path = os.path.relpath(root, base_path)
                depth = 0 if rel_path == '.' else len(rel_path.split(os.sep))
                if depth > 2:
                    dirs.clear() # don't go deeper
                    continue
                if "Manifest.db" in files:
                    mtime = os.path.getmtime(root)
                    if mtime > newest_time:
                        newest_time = mtime
                        newest_backup = root
        except Exception:
            pass
                    
    return newest_backup

def find_direct_sqlite():
    # Check output dir first
    paths_to_check = [
        os.path.join(OUTPUT_DIR, "Line.sqlite"),
        os.path.join(OUTPUT_DIR, "talk.sqlite"),
        "Line.sqlite",
        "talk.sqlite"
    ]
    for p in paths_to_check:
        if os.path.exists(p):
            return p
            
    # Search D:\ up to depth 3
    print("正在 D:\\ 槽中尋找是否有名為 Line.sqlite 或 talk.sqlite 的直接資料庫檔案...")
    for base_path in [r"D:\\"]:
        if not os.path.exists(base_path):
            continue
        try:
            for root, dirs, files in os.walk(base_path):
                rel_path = os.path.relpath(root, base_path)
                depth = 0 if rel_path == "." else len(rel_path.split(os.sep))
                if depth > 3:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower() in ["line.sqlite", "talk.sqlite"]:
                        return os.path.join(root, f)
        except Exception:
            pass
    return None

def extract_line_db():
    print("=== iPhone LINE 備份資料提取工具 ===")
    
    # 1. 優先檢查是否已有直接取得的 LINE 資料庫檔案
    direct_db = find_direct_sqlite()
    if direct_db:
        print(f"偵測到直接可用的 LINE 資料庫檔案：{direct_db}")
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
        dest_file = os.path.join(OUTPUT_DIR, "Line.sqlite")
        if os.path.abspath(direct_db) != os.path.abspath(dest_file):
            shutil.copy(direct_db, dest_file)
            print(f"已將資料庫檔案複製至：{dest_file}")
        print("\n接下來將啟動資料庫解析，將對話紀錄轉換為網頁 Viewer 支援的格式...")
        parse_line_sqlite()
        return

    # 2. 如果沒有直接的資料庫，才搜尋電腦上的備份目錄
    backup_dir = get_latest_backup_dir()
    if not backup_dir:
        print("錯誤：找不到任何已解密的 iTunes 備份資料夾，且找不到 Line.sqlite 檔案。")
        print("解決方案：")
        print("1. 可以使用 iMazing 匯出 LINE 的應用程式資料 (.imazingapp)，將其副檔名改為 .zip 並解壓縮，將裡面的 Line.sqlite 放到 D:\\ 槽或 D:\\LineExport 目錄下。")
        print("2. 或者，打開 iTunes 或「Apple 裝置」App，將您的 iPhone 連線並執行『立即備份』(請勿勾選『加密本機備份』)。")
        sys.exit(1)
        
    print(f"偵測到最新的備份資料夾：{backup_dir}")
    manifest_path = os.path.join(backup_dir, "Manifest.db")
    if not os.path.exists(manifest_path):
        print(f"錯誤：在備份目錄中找不到 Manifest.db！此備份可能已損壞或正在進行中。")
        sys.exit(1)
        
    print("正在讀取 Manifest.db 索引檔案...")
    conn = sqlite3.connect(manifest_path)
    cursor = conn.cursor()
    
    # Query for LINE database file
    # iOS LINE database path typically ends with "Line.sqlite" or "talk.sqlite"
    # Domain is usually "AppDomain-jp.naver.line"
    query = """
        SELECT fileID, relativePath 
        FROM Files 
        WHERE (domain = 'AppDomain-jp.naver.line' OR domain LIKE '%line%')
        AND (relativePath LIKE '%Line.sqlite%' OR relativePath LIKE '%talk.sqlite%')
    """
    
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"錯誤：讀取 Manifest.db 失敗 ({e})，此備份可能已被加密。請在 iTunes 中關閉「加密本機備份」並重新備份。")
        conn.close()
        sys.exit(1)
        
    if not rows:
        print("在備份中找不到 LINE 資料庫檔案 (Line.sqlite)。")
        print("這可能是因為您在 iTunes 備份時，該手機並未安裝 LINE，或者資料尚未同步。")
        conn.close()
        sys.exit(1)
        
    # Copy the database files
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    extracted_any = False
    for file_id, rel_path in rows:
        # File path in backup is grouped by the first two characters of fileID
        folder_prefix = file_id[:2]
        src_file = os.path.join(backup_dir, folder_prefix, file_id)
        
        # Fallback if not grouped in subfolders (older iTunes versions)
        if not os.path.exists(src_file):
            src_file = os.path.join(backup_dir, file_id)
            
        if os.path.exists(src_file):
            dest_file = os.path.join(OUTPUT_DIR, "Line.sqlite")
            shutil.copy(src_file, dest_file)
            print(f"\n[✔] 成功提取 LINE 資料庫！")
            print(f"原始路徑：{rel_path}")
            print(f"已儲存至：{dest_file}")
            extracted_any = True
            break
            
    conn.close()
    
    if not extracted_any:
        print("錯誤：在備份檔案夾中找不到對應的雜湊實體檔案！請確認備份是否完整。")
        sys.exit(1)
        
    print("\n接下來將啟動資料庫解析，將對話紀錄轉換為網頁 Viewer 支援的格式...")
    parse_line_sqlite()

def parse_line_sqlite():
    db_path = os.path.join(OUTPUT_DIR, "Line.sqlite")
    if not os.path.exists(db_path):
        print("資料庫不存在，無法解析。")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Dynamically find the tables to handle different LINE database versions
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    
    # iOS LINE table structures:
    # Chats are in ZCHAT, messages in ZMESSAGE, contacts/users in ZUSER
    # Let's verify table names
    has_zchat = "ZCHAT" in tables
    has_zmessage = "ZMESSAGE" in tables
    
    if not (has_zchat and has_zmessage):
        print("錯誤：資料庫表格結構不符合 iOS LINE 規範，無法解析。")
        conn.close()
        return
        
    # Extract users/contacts mapping
    contacts = {}
    if "ZUSER" in tables:
        try:
            # ZCUSTOMNAME is user nickname, ZNAME is original name
            cursor.execute("SELECT ZMID, ZNAME, ZCUSTOMNAME FROM ZUSER")
            for zmid, name, customname in cursor.fetchall():
                display_name = customname or name or zmid
                if zmid:
                    contacts[zmid] = display_name
        except Exception as e:
            print(f"讀取聯絡人資訊失敗: {e}")
            
    # Extract chats
    try:
        # ZMID is chat ID, ZNAME is chat group name
        cursor.execute("SELECT Z_PK, ZMID, ZNAME FROM ZCHAT")
        chats = cursor.fetchall()
    except Exception as e:
        print(f"讀取聊天室失敗: {e}")
        conn.close()
        return
        
    print(f"找到 {len(chats)} 個聊天對話。正在匯出...")
    
    for chat_pk, chat_mid, chat_name in chats:
        if not chat_mid:
            continue
            
        chat_display_name = chat_name or contacts.get(chat_mid, f"Chat_{chat_mid[:8]}")
        
        # Query messages for this chat sorted by creation time
        # ZCHAT in ZMESSAGE maps to the chat_pk
        # ZTEXT is the content, ZCREATEDTIME is the timestamp
        # ZTYPE is message type, ZSENDER is sender's MID
        try:
            cursor.execute("""
                SELECT ZTEXT, ZCREATEDTIME, ZTYPE, ZSENDER 
                FROM ZMESSAGE 
                WHERE ZCHAT = ? 
                ORDER BY ZCREATEDTIME ASC
            """, (chat_pk,))
            msg_rows = cursor.fetchall()
        except Exception as e:
            print(f"  查詢聊天室 {chat_display_name} 訊息失敗: {e}")
            continue
            
        if not msg_rows:
            continue
            
        messages_list = []
        senders = set()
        
        for text, created_time, msg_type, sender_mid in msg_rows:
            # created_time on iOS is CoreData timestamp (seconds since 2001-01-01) or standard epoch
            # CoreData epoch offset is 978307200 seconds
            if not created_time:
                continue
                
            # Detect epoch type (CoreData uses < 1e10, unix timestamp is similar but starts at different epoch)
            # Standard iOS CoreData time: seconds since Jan 1, 2001
            timestamp = created_time + 978307200 if created_time < 900000000 else created_time
            
            try:
                from datetime import datetime
                dt = datetime.fromtimestamp(timestamp)
                date_str = dt.strftime('%Y-%m-%d')
                time_str = dt.strftime('%H:%M')
            except Exception:
                date_str = "Unknown"
                time_str = "00:00"
                
            sender_name = contacts.get(sender_mid, sender_mid) if sender_mid else "SYSTEM"
            if sender_mid:
                senders.add(sender_name)
                
            # Map type codes
            # Type 1 = Text, 2 = Image, 3 = Video, 4 = Audio, 12 = Sticker, etc. (differs by version)
            m_type = 'text'
            content = text or ""
            
            if msg_type == 2 or "[圖片]" in content or "[Photo]" in content:
                m_type = 'image'
                content = "[圖片]"
            elif msg_type == 12 or "[貼圖]" in content or "[Sticker]" in content:
                m_type = 'sticker'
                content = "[貼圖]"
            elif msg_type == 3:
                m_type = 'video'
                content = "[影片]"
            elif msg_type == 4:
                m_type = 'voice'
                content = "[語音]"
                
            messages_list.append({
                "chatId": chat_mid,
                "date": date_str,
                "time": time_str,
                "sender": sender_name,
                "content": content,
                "type": m_type
            })
            
        if not messages_list:
            continue
            
        # Export chat JSON
        import json
        export_data = {
            "chatInfo": {
                "id": chat_mid,
                "name": chat_display_name,
                "importDate": datetime.now().strftime('%Y-%m-%d'),
                "messageCount": len([m for m in messages_list if m["sender"] != "SYSTEM"]),
                "senderCount": len(senders),
                "senders": list(senders)
            },
            "messages": messages_list
        }
        
        safe_name = "".join([c for c in chat_display_name if c.isalpha() or c.isdigit() or c in ' -_']).strip()
        if not safe_name:
            safe_name = f"chat_{chat_mid[:8]}"
            
        output_file = os.path.join(OUTPUT_DIR, f"line_backup_{safe_name}.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"  成功匯出聊天室: {chat_display_name} -> {output_file} ({len(messages_list)} 則訊息)")
        
    conn.close()
    print("\n資料庫備份檔解析完成！")
    print(f"請開啟瀏覽器 (http://localhost:8000)，將 '{OUTPUT_DIR}' 目錄下產生的所有 .json 檔案拖入即可開始瀏覽與分析！")

if __name__ == "__main__":
    extract_line_db()

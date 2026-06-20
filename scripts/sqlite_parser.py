#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Line SQLite Database Parser
---------------------------
This script extracts chats and messages from a decrypted Line SQLite database (talk.db)
and exports it as a JSON file compatible with the Line Backup Viewer web interface.

Usage:
    python sqlite_parser.py <path_to_talk.db> [output_directory]
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

# Line Message Content Types
TYPE_MAP = {
    0: 'text',     # Text
    1: 'image',    # Photo/Image
    2: 'video',    # Video
    3: 'voice',    # Voice message
    7: 'file',     # Location/File/etc.
    15: 'sticker', # Sticker
    18: 'call',    # Call/Video call
}

def parse_line_db(db_path, output_dir):
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at '{db_path}'")
        return

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Fetch Contacts for sender name mapping
    print("Reading contacts...")
    contacts = {}
    try:
        cursor.execute("SELECT m_id, name FROM contacts")
        for m_id, name in cursor.fetchall():
            contacts[m_id] = name
    except sqlite3.OperationalError as e:
        print(f"Warning mapping contacts: {e}. Attempting fallback queries...")
        # Fallback if table name differs
        try:
            cursor.execute("SELECT id, name FROM contact")
            for id_val, name in cursor.fetchall():
                contacts[id_val] = name
        except sqlite3.OperationalError:
            print("Could not load contact names. Sender IDs will be used instead.")

    # 2. Fetch Active Chats
    print("Reading chats/conversations...")
    chats = []
    try:
        cursor.execute("SELECT chat_id, name, last_message_id FROM chat")
        chats = cursor.fetchall()
    except sqlite3.OperationalError:
        try:
            cursor.execute("SELECT id, name FROM chat")
            chats = [(row[0], row[1], None) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            print(f"Error reading chat table: {e}")
            conn.close()
            return

    if not chats:
        print("No active chat sessions found in this database.")
        conn.close()
        return

    print(f"Found {len(chats)} chats. Starting export...")

    for index, chat_info in enumerate(chats):
        chat_id = chat_info[0]
        # Default name if empty
        chat_name = chat_info[1] or f"Chat_Group_{chat_id[:8]}"
        
        print(f"[{index+1}/{len(chats)}] Exporting: {chat_name} (ID: {chat_id})")

        # Fetch Messages for this chat
        messages_list = []
        senders = set()
        
        try:
            # Query messages sorted chronologically
            query = """
                SELECT id, from_mid, content, created_time, content_type 
                FROM message 
                WHERE chat_id = ? 
                ORDER BY created_time ASC
            """
            cursor.execute(query, (chat_id,))
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            print(f"  Failed to query message table for chat {chat_name}: {e}")
            continue

        for msg_id, from_mid, content, created_time_ms, content_type in rows:
            # Skip if essential fields are missing
            if not created_time_ms:
                continue

            # Convert timestamp (ms) to Date & Time
            timestamp_sec = created_time_ms / 1000.0
            dt = datetime.fromtimestamp(timestamp_sec)
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M')

            # Map sender
            sender_name = contacts.get(from_mid, from_mid)
            if not sender_name:
                sender_name = "System/Unknown" if from_mid is None else from_mid

            if from_mid:
                senders.add(sender_name)

            # Determine type
            msg_type = TYPE_MAP.get(content_type, 'text')
            
            # Map type-specific content
            msg_content = content or ""
            if msg_type == 'image':
                msg_content = "[圖片]"
            elif msg_type == 'sticker':
                msg_content = "[貼圖]"
            elif msg_type == 'voice':
                msg_content = "[語音]"
            elif msg_type == 'video':
                msg_content = "[影片]"
            elif msg_type == 'file':
                msg_content = "[檔案]"

            messages_list.append({
                "chatId": chat_id,
                "date": date_str,
                "time": time_str,
                "sender": "SYSTEM" if from_mid is None else sender_name,
                "content": msg_content,
                "type": "system" if from_mid is None else msg_type
            })

        # Skip empty chats
        if not messages_list:
            print(f"  Skipping (0 messages)")
            continue

        # Construct JSON export structure matching Viewer format
        export_data = {
            "chatInfo": {
                "id": chat_id,
                "name": chat_name,
                "importDate": datetime.now().strftime('%Y-%m-%d'),
                "messageCount": len([m for m in messages_list if m["sender"] != "SYSTEM"]),
                "senderCount": len(senders),
                "senders": list(senders)
            },
            "messages": messages_list
        }

        # Safe filename mapping
        safe_name = "".join([c for c in chat_name if c.isalpha() or c.isdigit() or c in ' -_']).strip()
        if not safe_name:
            safe_name = f"chat_{chat_id}"
        
        output_file = os.path.join(output_dir, f"line_backup_{safe_name}.json")
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            print(f"  Successfully saved to: {output_file} ({len(messages_list)} messages)")
        except Exception as e:
            print(f"  Error saving to file {output_file}: {e}")

    conn.close()
    print("Database export completed!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sqlite_parser.py <path_to_talk.db> [output_directory]")
        sys.exit(1)

    db_path = sys.argv[1]
    
    # Default to current directory if output directory is not specified
    output_dir = "."
    if len(sys.argv) >= 3:
        output_dir = sys.argv[2]
        
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    parse_line_db(db_path, output_dir)

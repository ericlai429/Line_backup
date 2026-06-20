/**
 * Line Backup Viewer - Core Application Logic
 * Features: Text Parser, IndexedDB Management, UI Rendering, Search, Photo Matching, and Analytics.
 */

// Global App State
const AppState = {
    db: null,
    isMemoryDB: false,
    chatsMemory: [],
    messagesMemory: [],
    photosMemory: new Map(), // key -> { photoKey, chatId, fileName, blob }
    activeChatId: null,
    activeTab: 'chat',
    displayedMessagesCount: 200, // Number of messages to display in chat tab (for progressive rendering)
    chats: [], // Loaded chats list
    messages: [], // Messages for the active chat
    photosMap: new Map(), // Map of filename -> Blob/File for currently loaded session photos
    currentFilters: {
        keyword: '',
        sender: '',
        dateFrom: '',
        dateTo: ''
    },
    charts: {
        sender: null,
        timeline: null,
        hourly: null
    }
};

// ==========================================================================
// 1. DATABASE MANAGEMENT (IndexedDB & Memory Fallback)
// ==========================================================================
const DB_NAME = 'LineBackupViewerDB';
const DB_VERSION = 1;

function initDB() {
    return new Promise((resolve) => {
        if (!window.indexedDB) {
            console.warn('IndexedDB is not supported. Falling back to in-memory storage.');
            AppState.isMemoryDB = true;
            resolve(null);
            return;
        }

        try {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = (e) => {
                console.warn('IndexedDB failed to open, falling back to in-memory storage:', e);
                AppState.isMemoryDB = true;
                resolve(null);
            };

            request.onsuccess = (e) => {
                AppState.db = e.target.result;
                resolve(AppState.db);
            };

            request.onupgradeneeded = (e) => {
                const db = e.target.result;
                
                // Create Chats Store
                if (!db.objectStoreNames.contains('chats')) {
                    db.createObjectStore('chats', { keyPath: 'id' });
                }
                
                // Create Messages Store
                if (!db.objectStoreNames.contains('messages')) {
                    const msgStore = db.createObjectStore('messages', { keyPath: 'id', autoIncrement: true });
                    msgStore.createIndex('chatId', 'chatId', { unique: false });
                }

                // Create Photos Store
                if (!db.objectStoreNames.contains('photos')) {
                    const photoStore = db.createObjectStore('photos', { keyPath: 'photoKey' }); // key: chatId + '_' + fileName
                    photoStore.createIndex('chatId', 'chatId', { unique: false });
                }
            };
        } catch (err) {
            console.warn('IndexedDB open threw an error, falling back to in-memory storage:', err);
            AppState.isMemoryDB = true;
            resolve(null);
        }
    });
}

// DB Helper Methods
async function saveChatToDB(chat, messages) {
    if (AppState.isMemoryDB) {
        // Clear existing chat and messages if any
        AppState.chatsMemory = AppState.chatsMemory.filter(c => c.id !== chat.id);
        AppState.chatsMemory.push(chat);

        AppState.messagesMemory = AppState.messagesMemory.filter(m => m.chatId !== chat.id);
        
        let startId = AppState.messagesMemory.length ? Math.max(...AppState.messagesMemory.map(m => m.id)) + 1 : 1;
        messages.forEach(msg => {
            msg.id = startId++;
            AppState.messagesMemory.push(msg);
        });
        return Promise.resolve();
    }

    // 1. Save chat info and delete any existing messages with the same chatId using index (extremely fast)
    await new Promise((resolve, reject) => {
        const transaction = AppState.db.transaction(['chats', 'messages'], 'readwrite');
        
        transaction.onerror = (e) => reject(e);
        transaction.oncomplete = () => resolve();

        const chatsStore = transaction.objectStore('chats');
        const msgsStore = transaction.objectStore('messages');

        chatsStore.put(chat);

        // Delete existing messages using index
        const index = msgsStore.index('chatId');
        const request = index.openCursor(IDBKeyRange.only(chat.id));
        request.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
                msgsStore.delete(cursor.primaryKey);
                cursor.continue();
            }
        };
    });

    // 2. Save messages in batches of 2000 to prevent browser out-of-memory crash
    const BATCH_SIZE = 2000;
    for (let i = 0; i < messages.length; i += BATCH_SIZE) {
        const chunk = messages.slice(i, i + BATCH_SIZE);
        await new Promise((resolve, reject) => {
            const transaction = AppState.db.transaction(['messages'], 'readwrite');
            
            transaction.onerror = (e) => reject(e);
            transaction.oncomplete = () => resolve();

            const msgsStore = transaction.objectStore('messages');
            chunk.forEach(msg => {
                msgsStore.add(msg);
            });
        });
    }
}

function savePhotoToDB(chatId, fileName, blob) {
    const photoKey = `${chatId}_${fileName.toLowerCase()}`;
    if (AppState.isMemoryDB) {
        AppState.photosMemory.set(photoKey, {
            photoKey,
            chatId,
            fileName: fileName.toLowerCase(),
            blob
        });
        return Promise.resolve(photoKey);
    }

    return new Promise((resolve, reject) => {
        const transaction = AppState.db.transaction(['photos'], 'readwrite');
        const store = transaction.objectStore('photos');
        
        const request = store.put({
            photoKey,
            chatId,
            fileName: fileName.toLowerCase(),
            blob
        });

        request.onsuccess = () => resolve(photoKey);
        request.onerror = (e) => reject(e);
    });
}

function getPhotosFromDB(chatId) {
    if (AppState.isMemoryDB) {
        const results = [];
        AppState.photosMemory.forEach(val => {
            if (val.chatId === chatId) {
                results.push(val);
            }
        });
        return Promise.resolve(results);
    }

    return new Promise((resolve, reject) => {
        const transaction = AppState.db.transaction(['photos'], 'readonly');
        const store = transaction.objectStore('photos');
        const index = store.index('chatId');
        const request = index.getAll(chatId);

        request.onsuccess = (e) => resolve(e.target.result || []);
        request.onerror = (e) => reject(e);
    });
}

function deleteChatFromDB(chatId) {
    if (AppState.isMemoryDB) {
        AppState.chatsMemory = AppState.chatsMemory.filter(c => c.id !== chatId);
        AppState.messagesMemory = AppState.messagesMemory.filter(m => m.chatId !== chatId);
        
        AppState.photosMemory.forEach((val, key) => {
            if (val.chatId === chatId) {
                AppState.photosMemory.delete(key);
            }
        });
        return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
        const transaction = AppState.db.transaction(['chats', 'messages', 'photos'], 'readwrite');
        transaction.oncomplete = () => resolve();
        transaction.onerror = (e) => reject(e);

        transaction.objectStore('chats').delete(chatId);

        // Delete messages using chatId index (very fast)
        const msgStore = transaction.objectStore('messages');
        const msgIndex = msgStore.index('chatId');
        const msgCursor = msgIndex.openCursor(IDBKeyRange.only(chatId));
        msgCursor.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
                msgStore.delete(cursor.primaryKey);
                cursor.continue();
            }
        };

        // Delete photos using chatId index (very fast)
        const photoStore = transaction.objectStore('photos');
        const photoIndex = photoStore.index('chatId');
        const photoCursor = photoIndex.openCursor(IDBKeyRange.only(chatId));
        photoCursor.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
                photoStore.delete(cursor.primaryKey);
                cursor.continue();
            }
        };
    });
}

function getChatsList() {
    if (AppState.isMemoryDB) {
        return Promise.resolve(AppState.chatsMemory);
    }

    return new Promise((resolve, reject) => {
        const transaction = AppState.db.transaction(['chats'], 'readonly');
        const store = transaction.objectStore('chats');
        const request = store.getAll();

        request.onsuccess = (e) => resolve(e.target.result || []);
        request.onerror = (e) => reject(e);
    });
}

function getChatMessages(chatId) {
    if (AppState.isMemoryDB) {
        const msgs = AppState.messagesMemory.filter(m => m.chatId === chatId);
        msgs.sort((a, b) => a.id - b.id);
        return Promise.resolve(msgs);
    }

    return new Promise((resolve, reject) => {
        const transaction = AppState.db.transaction(['messages'], 'readonly');
        const store = transaction.objectStore('messages');
        const index = store.index('chatId');
        const request = index.getAll(chatId);

        request.onsuccess = (e) => {
            const msgs = e.target.result || [];
            msgs.sort((a, b) => a.id - b.id);
            resolve(msgs);
        };
        request.onerror = (e) => reject(e);
    });
}


// ==========================================================================
// 2. LINE TEXT PARSER
// ==========================================================================
function parseLineBackupText(text, fileName) {
    const lines = text.split(/\r?\n/);
    let chatName = fileName.replace(/\.txt$/i, '');
    let importDate = new Date().toISOString().split('T')[0];
    
    // Attempt to extract chat name from header
    // Traditional Chinese: [LINE] 與「XXX」的對話, [LINE] 與XXX的對話
    // English: [LINE] Chat with XXX
    let headerLine1 = lines[0] || '';
    let chatNameMatch = headerLine1.match(/\[LINE\]\s+(?:與「?(.+?)」?的對話|Chat with\s+(.+)|(.+?)とのトーク)/i);
    if (chatNameMatch) {
        chatName = chatNameMatch[1] || chatNameMatch[2] || chatNameMatch[3] || chatName;
    }

    const messages = [];
    const senders = new Set();
    
    let currentDateStr = ''; // Keep track of current parsing date
    let currentMessage = null; // Multi-line message tracker

    // Date regex matching: YYYY/MM/DD(Day) or YYYY/MM/DD（Day） or YYYY.MM.DD
    const dateRegex = /^(\d{4})[/\.-](\d{1,2})[/\.-](\d{1,2})(?:[\s（(].*|$)/;

    // Time + Sender + Message regex:
    // Support standard 24h: "12:34\tSenderName\tMessage"
    // Support 12h: "下午12:34\tSenderName\tMessage" or "下午 12:34\tSenderName\tMessage"
    // Support English 12h: "12:34 PM\tSenderName\tMessage"
    const messageRegex = /^((?:[上下]午\s?)?\d{1,2}:\d{2}(?:\s?[APMapm]{2})?)\t([^\t\n]+)\t(.*)$/;
    
    // System actions: "12:34\tSystem message"
    const systemActionRegex = /^((?:[上下]午\s?)?\d{1,2}:\d{2}(?:\s?[APMapm]{2})?)\t([^\t\n]+)$/;

    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;

        // 1. Check if it's a date header
        const dateMatch = line.match(dateRegex);
        if (dateMatch && line.length < 30 && !line.includes('\t')) {
            const year = dateMatch[1];
            const month = dateMatch[2].padStart(2, '0');
            const day = dateMatch[3].padStart(2, '0');
            currentDateStr = `${year}-${month}-${day}`;
            
            // Add a date change indicator message
            messages.push({
                chatId: '', // Filled later
                date: currentDateStr,
                time: '',
                sender: 'SYSTEM',
                content: line,
                type: 'date'
            });
            continue;
        }

        // 2. Check if it's a message line (try Tab-separated first, fallback to Space-separated)
        let isMatched = false;
        let time = '';
        let sender = '';
        let content = '';

        const msgMatch = line.match(messageRegex);
        if (msgMatch) {
            time = msgMatch[1];
            sender = msgMatch[2];
            content = msgMatch[3];
            isMatched = true;
        } else {
            // Fallback for space-separated formats (e.g. copied text or different LINE PC export versions)
            // Regex matches: "Time Sender Message" or "Time [Sender] Message"
            const timePrefixMatch = line.match(/^((?:[上下]午\s?)?\d{1,2}:\d{2}(?:\s?[APMapm]{2})?)\s+(.+)$/);
            if (timePrefixMatch) {
                const tempTime = timePrefixMatch[1];
                const restOfLine = timePrefixMatch[2].trim();
                
                const tabIdx = restOfLine.indexOf('\t');
                if (tabIdx !== -1) {
                    sender = restOfLine.substring(0, tabIdx).trim();
                    content = restOfLine.substring(tabIdx + 1).trim();
                    time = tempTime;
                    isMatched = true;
                } else {
                    const spaceIdx = restOfLine.indexOf(' ');
                    if (spaceIdx !== -1) {
                        sender = restOfLine.substring(0, spaceIdx).trim();
                        content = restOfLine.substring(spaceIdx + 1).trim();
                        time = tempTime;
                        isMatched = true;
                    } else {
                        // System action fallback: no space in the rest of the line (e.g. "10:00 小明加入群組")
                        currentMessage = {
                            chatId: '',
                            date: currentDateStr || importDate,
                            time: tempTime,
                            sender: 'SYSTEM',
                            content: restOfLine,
                            type: 'system'
                        };
                        messages.push(currentMessage);
                        continue;
                    }
                }
            }
        }

        if (isMatched && sender && content) {
            senders.add(sender);

            // Determine message type
            let type = 'text';
            if (content === '[圖片]' || content === '[Photo]' || content.includes('[圖片]')) {
                type = 'image';
            } else if (content === '[貼圖]' || content === '[Sticker]') {
                type = 'sticker';
            } else if (content === '[語音]' || content === '[Voice message]') {
                type = 'voice';
            } else if (content === '[影片]' || content === '[Video]') {
                type = 'file'; // Fallback
            } else if (content === '[檔案]' || content === '[File]') {
                type = 'file';
            } else if (content.includes('通話時間') || content.includes('Call time') || content.includes('通話結果')) {
                type = 'call';
            }

            currentMessage = {
                chatId: '', // Filled later
                date: currentDateStr || importDate,
                time: time,
                sender: sender,
                content: content,
                type: type
            };
            messages.push(currentMessage);
            continue;
        }

        // 3. Check if it's a system action line (tab-separated standard case)
        const sysMatch = line.match(systemActionRegex);
        if (sysMatch) {
            const time = sysMatch[1];
            const action = sysMatch[2];
            
            currentMessage = {
                chatId: '',
                date: currentDateStr || importDate,
                time: time,
                sender: 'SYSTEM',
                content: action,
                type: 'system'
            };
            messages.push(currentMessage);
            continue;
        }

        // 4. If none of the above, it's a continuation of the previous message (multi-line)
        if (currentMessage && currentMessage.type === 'text') {
            currentMessage.content += '\n' + line;
        } else {
            // Edge case: text before any date/message
            messages.push({
                chatId: '',
                date: currentDateStr || importDate,
                time: '',
                sender: 'SYSTEM',
                content: line,
                type: 'system'
            });
        }
    }

    // Generate unique ID for this chat
    const chatId = 'chat_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
    
    // Fill chatId in all messages
    messages.forEach(m => m.chatId = chatId);

    const chat = {
        id: chatId,
        name: chatName,
        importDate: importDate,
        messageCount: messages.filter(m => m.sender !== 'SYSTEM').length,
        senderCount: senders.size,
        senders: Array.from(senders)
    };

    return { chat, messages };
}


// ==========================================================================
// 3. IMAGE MATCHING ALGORITHM
// ==========================================================================
// Match images inside the chat messages with imported files
function associatePhotos(chatId) {
    const imagesMessages = AppState.messages.filter(m => m.type === 'image');
    if (imagesMessages.length === 0 || AppState.photosMap.size === 0) return;

    // Convert photosMap keys to sorted array
    const availablePhotoNames = Array.from(AppState.photosMap.keys()).sort();

    // Strategy 1: Timestamp correlation
    // Line exports photos as YYYYMMDD_HHMMSS or similar.
    // We try to match message timestamp (e.g., Msg Date: 2023-10-24, Msg Time: 15:30)
    // with file names containing "20231024" and "1530".
    imagesMessages.forEach(msg => {
        if (msg.photoUrl) return; // Already matched

        const cleanDate = msg.date.replace(/[-/\.]/g, ''); // "20231024"
        
        // Parse time: "下午 03:30" or "下午15:30" or "15:30"
        let hour = '';
        let min = '';
        const timeDigits = msg.time.match(/(\d{1,2}):(\d{2})/);
        if (timeDigits) {
            let h = parseInt(timeDigits[1]);
            const m = timeDigits[2];
            
            // Adjust if Afternoon (PM)
            if (msg.time.includes('下午') || msg.time.toLowerCase().includes('pm')) {
                if (h < 12) h += 12;
            } else if (msg.time.includes('上午') || msg.time.toLowerCase().includes('am')) {
                if (h === 12) h = 0;
            }
            
            hour = h.toString().padStart(2, '0');
            min = m;
        }

        const timePattern = `${hour}${min}`; // "1530"
        const stampPattern = `${cleanDate}_${timePattern}`; // "20231024_1530"

        // Search for file name containing stampPattern
        const matchingFile = availablePhotoNames.find(name => {
            const cleanName = name.replace(/[-_]/g, '');
            return cleanName.includes(stampPattern) || (cleanName.includes(cleanDate) && cleanName.includes(timePattern));
        });

        if (matchingFile) {
            const blob = AppState.photosMap.get(matchingFile);
            msg.photoUrl = URL.createObjectURL(blob);
            msg.photoName = matchingFile;
            // Async Save to IndexedDB for persistence
            savePhotoToDB(chatId, matchingFile, blob);
        }
    });

    // Strategy 2: Chronological Sequence (Fallback)
    // If photos are still unmatched, match remaining image messages with remaining photo files chronologically.
    const unmatchedMsgs = imagesMessages.filter(m => !m.photoUrl);
    const unmatchedPhotoNames = availablePhotoNames.filter(name => {
        // Check if this photo has been assigned to any message
        return !imagesMessages.some(m => m.photoName === name);
    });

    const matchCount = Math.min(unmatchedMsgs.length, unmatchedPhotoNames.length);
    for (let i = 0; i < matchCount; i++) {
        const msg = unmatchedMsgs[i];
        const fileName = unmatchedPhotoNames[i];
        const blob = AppState.photosMap.get(fileName);
        
        msg.photoUrl = URL.createObjectURL(blob);
        msg.photoName = fileName;
        savePhotoToDB(chatId, fileName, blob);
    }
}


// ==========================================================================
// 4. UI RENDERING & INTERACTIONS
// ==========================================================================
function initUI() {
    // Theme Toggle
    const themeBtn = document.getElementById('theme-toggle');
    themeBtn.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        document.body.classList.toggle('light-mode');
        // Redraw charts if active to fit theme colors
        if (AppState.activeTab === 'stats') {
            renderStatsTab();
        }
    });

    // File Input Dropzones
    setupDropZone('txt-drop-zone', 'txt-file-input', handleTxtImport);
    setupDropZone('media-drop-zone', 'media-file-input', handleMediaImport, true);

    // Sidebar navigation tabs
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const tab = item.getAttribute('data-tab');
            switchTab(tab);
        });
    });

    // Search and Filters
    document.getElementById('search-input').addEventListener('input', debounce(applyFilters, 300));
    document.getElementById('sender-filter').addEventListener('change', applyFilters);
    document.getElementById('date-from').addEventListener('change', applyFilters);
    document.getElementById('date-to').addEventListener('change', applyFilters);
    document.getElementById('clear-filters').addEventListener('click', clearFilters);

    // Lightbox modal close
    const lightbox = document.getElementById('lightbox');
    const closeBtn = document.querySelector('.lightbox-close');
    closeBtn.addEventListener('click', () => {
        lightbox.style.display = 'none';
    });
    lightbox.addEventListener('click', (e) => {
        if (e.target === lightbox) {
            lightbox.style.display = 'none';
        }
    });

    // Delete Chat and Export JSON buttons
    document.getElementById('delete-chat-btn').addEventListener('click', deleteActiveChat);
    document.getElementById('export-json-btn').addEventListener('click', exportChatAsJSON);

    // Mobile Back Buttons
    document.querySelectorAll('.back-to-list-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const containerEl = document.getElementById('app-container');
            if (containerEl) {
                containerEl.classList.remove('chat-selected');
            }
        });
    });

    // Myself sender selection change
    const meSelect = document.getElementById('me-sender-select');
    if (meSelect) {
        meSelect.addEventListener('change', () => {
            if (AppState.activeChatId) {
                localStorage.setItem(`me_sender_${AppState.activeChatId}`, meSelect.value);
                renderChatMessages();
            }
        });
    }

    // Scroll listener on chat messages to auto-trigger loading history when scrolled to top
    const chatMessagesEl = document.getElementById('chat-messages');
    if (chatMessagesEl) {
        chatMessagesEl.addEventListener('scroll', () => {
            if (chatMessagesEl.scrollTop === 0) {
                loadMoreChatMessages();
            }
        });
    }

    // Load initial chat list
    refreshChatList();
}

// Drag & Drop Setup Helper
function setupDropZone(zoneId, inputId, handler, isDirectory = false) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(inputId);

    if (isDirectory) {
        input.setAttribute('webkitdirectory', '');
        input.setAttribute('directory', '');
    }

    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handler(e.dataTransfer.files);
        }
    });

    input.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handler(e.target.files);
        }
    });
}

// Switch tabs: 'chat', 'gallery', 'stats'
function switchTab(tabName) {
    if (!AppState.activeChatId) {
        alert('請先匯入或選擇一個聊天室！');
        return;
    }
    
    AppState.activeTab = tabName;
    
    // Update navigation styles
    document.querySelectorAll('.nav-item').forEach(btn => {
        if (btn.getAttribute('data-tab') === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Switch panels
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });

    if (tabName === 'chat') {
        document.getElementById('chat-panel').classList.add('active');
        renderChatMessages();
    } else if (tabName === 'gallery') {
        document.getElementById('gallery-panel').classList.add('active');
        renderGalleryTab();
    } else if (tabName === 'stats') {
        document.getElementById('stats-panel').classList.add('active');
        renderStatsTab();
    }
}

// ==========================================================================
// 5. IMPORT HANDLERS
// ==========================================================================
async function handleTxtImport(files) {
    const file = files[0];
    if (!file) return;

    showLoadingState(true);

    try {
        const text = await readFileAsText(file);
        let chat, messages;

        if (file.name.toLowerCase().endsWith('.json')) {
            try {
                const parsed = JSON.parse(text);
                if (parsed && parsed.chatInfo && parsed.messages) {
                    chat = parsed.chatInfo;
                    messages = parsed.messages;
                } else {
                    throw new Error('Invalid JSON structure');
                }
            } catch (jsonErr) {
                console.error('JSON parse error:', jsonErr);
                throw new Error('JSON 解析失敗，請確保這是正確的匯出 JSON 格式。');
            }
        } else {
            const parsed = parseLineBackupText(text, file.name);
            chat = parsed.chat;
            messages = parsed.messages;
        }

        // Check if database is ready
        if (!AppState.db) await initDB();

        // Save to IndexedDB
        await saveChatToDB(chat, messages);

        // Re-read chats and select the new one
        await refreshChatList();
        await selectChat(chat.id);

        showLoadingState(false);
    } catch (err) {
        console.error('Import failed:', err);
        alert('解析檔案失敗，請確保這是 Line 導出的對話紀錄文字檔。');
        showLoadingState(false);
    }
}

async function handleMediaImport(files) {
    if (!AppState.activeChatId) {
        alert('請先匯入或選擇聊天室，再匯入對齊相片！');
        return;
    }

    showLoadingState(true);
    let loadedCount = 0;

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (file.type.startsWith('image/')) {
            // Keep file in memory map
            AppState.photosMap.set(file.name.toLowerCase(), file);
            loadedCount++;
        }
    }

    if (loadedCount > 0) {
        // Execute the image auto-link algorithm
        associatePhotos(AppState.activeChatId);
        
        // Refresh active views
        if (AppState.activeTab === 'chat') {
            renderChatMessages();
        } else if (AppState.activeTab === 'gallery') {
            renderGalleryTab();
        }
        alert(`成功讀取 ${loadedCount} 張照片，已自動與聊天對話進行比對！`);
    } else {
        alert('未偵測到任何有效的相片檔案！');
    }
    showLoadingState(false);
}

// File Reader Promise Helper
function readFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = (e) => reject(e);
        reader.readAsText(file, 'UTF-8');
    });
}

function showLoadingState(isLoading) {
    const zones = document.querySelectorAll('.drop-zone');
    zones.forEach(z => {
        if (isLoading) {
            z.style.opacity = '0.5';
            z.style.pointerEvents = 'none';
        } else {
            z.style.opacity = '1';
            z.style.pointerEvents = 'auto';
        }
    });
}


// ==========================================================================
// 6. CHAT LIST MANAGEMENT
// ==========================================================================
async function refreshChatList() {
    if (!AppState.db) await initDB();
    
    AppState.chats = await getChatsList();
    const listEl = document.getElementById('chat-list');
    listEl.innerHTML = '';

    if (AppState.chats.length === 0) {
        listEl.innerHTML = `<div class="empty-state">尚無匯入的對話</div>`;
        return;
    }

    AppState.chats.forEach(chat => {
        const item = document.createElement('div');
        item.className = `chat-item ${chat.id === AppState.activeChatId ? 'active' : ''}`;
        item.setAttribute('data-id', chat.id);
        
        const initial = chat.name.charAt(0);
        
        item.innerHTML = `
            <div class="chat-avatar">${initial}</div>
            <div class="chat-details">
                <div class="chat-name">${escapeHTML(chat.name)}</div>
                <div class="chat-meta">
                    <span>${chat.messageCount} 則訊息</span>
                    <span>${chat.importDate}</span>
                </div>
            </div>
        `;

        item.addEventListener('click', () => selectChat(chat.id));
        listEl.appendChild(item);
    });
}

async function selectChat(chatId) {
    AppState.activeChatId = chatId;
    AppState.displayedMessagesCount = 200; // Reset display count for progressive rendering
    
    // Toggle mobile screen container view
    const containerEl = document.getElementById('app-container');
    if (containerEl) {
        containerEl.classList.add('chat-selected');
    }

    // Set active item class
    document.querySelectorAll('.chat-item').forEach(item => {
        if (item.getAttribute('data-id') === chatId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Load Chat Messages
    AppState.messages = await getChatMessages(chatId);
    
    // Clear current in-memory photos
    AppState.photosMap.clear();
    
    // Load previously matched photos from IndexedDB
    const savedPhotos = await getPhotosFromDB(chatId);
    savedPhotos.forEach(p => {
        AppState.photosMap.set(p.fileName, p.blob);
    });

    // Run photo association algorithm to link loaded photos to messages
    associatePhotos(chatId);

    // Populate sender filter dropdown
    const chat = AppState.chats.find(c => c.id === chatId);
    populateSenderFilter(chat ? chat.senders : []);
    populateMeSenderFilter(chat ? chat.senders : []);

    // Set header titles
    document.getElementById('active-chat-name').textContent = chat ? chat.name : '未知的對話';
    document.getElementById('active-chat-meta').textContent = `${AppState.messages.filter(m => m.sender !== 'SYSTEM').length} 則訊息 | ${chat ? chat.senders.length : 0} 位發言者`;

    // Show action buttons
    document.getElementById('delete-chat-btn').style.display = 'inline-flex';
    document.getElementById('export-json-btn').style.display = 'inline-flex';

    // Hide welcome panel, show active tab
    document.getElementById('welcome-panel').classList.remove('active');
    switchTab(AppState.activeTab);
}

function populateSenderFilter(senders) {
    const select = document.getElementById('sender-filter');
    select.innerHTML = '<option value="">所有發言者</option>';
    senders.forEach(sender => {
        const option = document.createElement('option');
        option.value = sender;
        option.textContent = sender;
        select.appendChild(option);
    });
}

function populateMeSenderFilter(senders) {
    const select = document.getElementById('me-sender-select');
    const wrapper = document.getElementById('user-select-me-wrapper');
    if (!select || !wrapper) return;
    
    select.innerHTML = '<option value="">(無)</option>';
    senders.forEach(sender => {
        const option = document.createElement('option');
        option.value = sender;
        option.textContent = sender;
        select.appendChild(option);
    });
    
    let savedMe = localStorage.getItem(`me_sender_${AppState.activeChatId}`);
    if (!savedMe) {
        // Try to guess: if there's a sender named "我", default to it
        if (senders.includes("我")) {
            savedMe = "我";
        } else if (senders.length > 1) {
            // In 1-on-1 chat, the friend's name is usually the chat name.
            // So the sender whose name is NOT equal to the chat name is most likely "Me"
            const chat = AppState.chats.find(c => c.id === AppState.activeChatId);
            if (chat) {
                const guessedMe = senders.find(s => s !== chat.name);
                if (guessedMe) {
                    savedMe = guessedMe;
                }
            }
        }
    }
    
    if (savedMe && senders.includes(savedMe)) {
        select.value = savedMe;
    } else {
        select.value = "";
    }
    
    wrapper.style.display = 'inline-flex';
}


// ==========================================================================
// 7. RENDER VIEWPORT: CHAT HISTORY
// ==========================================================================
function renderChatMessages(autoScroll = true) {
    const container = document.getElementById('chat-messages');
    container.innerHTML = '';

    // Apply active filters
    const filtered = getFilteredMessages();

    if (filtered.length === 0) {
        container.innerHTML = `<div class="system-msg"><span>查無符合篩選條件的訊息</span></div>`;
        return;
    }

    // Slice to only show the last N messages
    const sliced = filtered.slice(-AppState.displayedMessagesCount);

    // If there are more historical messages, show a "load more" button at the top
    if (filtered.length > AppState.displayedMessagesCount) {
        const loadMoreDiv = document.createElement('div');
        loadMoreDiv.className = 'load-more-container';
        loadMoreDiv.innerHTML = `
            <button class="btn btn-secondary btn-sm" onclick="loadMoreChatMessages()">
                向上滑動或點擊載入更多歷史訊息 (${filtered.length - AppState.displayedMessagesCount} 則)
            </button>
        `;
        container.appendChild(loadMoreDiv);
    }

    sliced.forEach((msg, index) => {
        // Date Separators or Date changes
        if (msg.type === 'date') {
            const dateDiv = document.createElement('div');
            dateDiv.className = 'date-separator';
            dateDiv.innerHTML = `<span>${escapeHTML(msg.content)}</span>`;
            container.appendChild(dateDiv);
            return;
        }

        // System messages
        if (msg.type === 'system') {
            const sysDiv = document.createElement('div');
            sysDiv.className = 'system-msg';
            sysDiv.innerHTML = `<span>${escapeHTML(msg.content)}</span>`;
            container.appendChild(sysDiv);
            return;
        }

        // Determine if left (partner) or right (me/owner)
        const meSelect = document.getElementById('me-sender-select');
        const meName = meSelect ? meSelect.value : '';
        let isRight = false;
        
        if (meName) {
            isRight = (msg.sender === meName);
        } else {
            // Fallback to original logic if no Me is explicitly selected
            const chat = AppState.chats.find(c => c.id === AppState.activeChatId);
            const ownerName = chat && chat.senders.length > 1 ? chat.senders[0] : '';
            isRight = msg.sender !== ownerName;
        }

        const msgDiv = document.createElement('div');
        msgDiv.className = `msg-item ${isRight ? 'right' : 'left'}`;
        msgDiv.id = `msg-${msg.id || index}`;

        // Deterministic avatar and sender name color hash
        const senderColor = getSenderColor(msg.sender);

        // Avatar
        const avatar = `<div class="msg-avatar" style="background-color: ${senderColor}; color: #ffffff;">${msg.sender.charAt(0)}</div>`;
        
        // Sender Name
        const senderName = `<span class="msg-sender" style="color: ${senderColor};">${escapeHTML(msg.sender)}</span>`;

        // Bubble Content based on message type
        let bubbleContent = '';
        if (msg.type === 'image') {
            if (msg.photoUrl) {
                bubbleContent = `
                    <div class="msg-image-placeholder" onclick="openLightbox('${msg.photoUrl}', '${escapeHTML(msg.sender)} - ${msg.date} ${msg.time}', '${msg.id || index}')">
                        <img src="${msg.photoUrl}" alt="Photo">
                    </div>`;
            } else {
                bubbleContent = `
                    <div class="msg-image-placeholder">
                        <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0-2-.9-2-2zM5 5h14v14H5V5zm12 6-3.5 4.5-2.5-3L7 17h10l-3-6z"/></svg>
                        <span>[圖片 - 尚未匯入]</span>
                    </div>`;
            }
        } else if (msg.type === 'sticker') {
            bubbleContent = `<div class="msg-sticker">貼圖</div>`;
        } else if (msg.type === 'voice') {
            bubbleContent = `<div class="msg-bubble">語音訊息</div>`;
        } else if (msg.type === 'video') {
            bubbleContent = `<div class="msg-bubble">影片</div>`;
        } else if (msg.type === 'file') {
            bubbleContent = `<div class="msg-bubble">檔案</div>`;
        } else if (msg.type === 'call') {
            bubbleContent = `<div class="msg-bubble">${escapeHTML(msg.content)}</div>`;
        } else {
            // Highlight text if keyword is active
            let txt = escapeHTML(msg.content);
            if (AppState.currentFilters.keyword) {
                const regex = new RegExp(`(${escapeRegExp(AppState.currentFilters.keyword)})`, 'gi');
                txt = txt.replace(regex, '<span class="highlight">$1</span>');
            }
            bubbleContent = `<div class="msg-bubble">${txt.replace(/\n/g, '<br>')}</div>`;
        }

        // Message Meta (Time & Unread)
        const meta = `
            <div class="msg-meta">
                <span class="msg-time">${msg.time}</span>
            </div>`;

        // Render Bubble Wrapper
        msgDiv.innerHTML = `
            ${isRight ? '' : avatar}
            <div class="msg-content-wrapper">
                ${isRight ? '' : senderName}
                <div class="msg-body-wrapper">
                    ${bubbleContent}
                    ${meta}
                </div>
            </div>
        `;

        container.appendChild(msgDiv);
    });

    // Auto-scroll to bottom of chat if no filters active and autoScroll is true
    if (autoScroll && !AppState.currentFilters.keyword) {
        container.scrollTop = container.scrollHeight;
    }
}

function loadMoreChatMessages() {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    // Check if we have more messages to load
    const filtered = getFilteredMessages();
    if (AppState.displayedMessagesCount >= filtered.length) return;

    // Save current scroll height to restore scroll position after rendering
    const oldScrollHeight = container.scrollHeight;

    // Load next batch
    AppState.displayedMessagesCount = Math.min(filtered.length, AppState.displayedMessagesCount + 200);

    // Re-render without auto scrolling to bottom
    renderChatMessages(false);

    // Restore scroll position
    const newScrollHeight = container.scrollHeight;
    container.scrollTop = newScrollHeight - oldScrollHeight;
}


// ==========================================================================
// 8. RENDER VIEWPORT: GALLERY TAB
// ==========================================================================
function renderGalleryTab() {
    const grid = document.getElementById('gallery-grid');
    grid.innerHTML = '';
    
    const imageMsgs = AppState.messages.filter(m => m.type === 'image' && m.photoUrl);

    if (imageMsgs.length === 0) {
        grid.innerHTML = `<div class="empty-state">此聊天室目前沒有已載入的照片</div>`;
        return;
    }

    const gridWrapper = document.createElement('div');
    gridWrapper.className = 'gallery-grid';

    imageMsgs.forEach((msg, index) => {
        const item = document.createElement('div');
        item.className = 'gallery-item';
        item.onclick = () => openLightbox(msg.photoUrl, `${msg.sender} - ${msg.date} ${msg.time}`, msg.id || index);

        item.innerHTML = `
            <img src="${msg.photoUrl}" alt="Photo" loading="lazy">
            <div class="gallery-item-info">
                <span class="gallery-sender">${escapeHTML(msg.sender)}</span>
                <span>${msg.date}</span>
            </div>
        `;
        gridWrapper.appendChild(item);
    });

    grid.appendChild(gridWrapper);
}

// Lightbox controller
function openLightbox(url, caption, messageId) {
    const lightbox = document.getElementById('lightbox');
    const img = document.getElementById('lightbox-img');
    const captionEl = document.getElementById('lightbox-caption');
    const jumpBtn = document.getElementById('lightbox-jump-btn');

    img.src = url;
    captionEl.textContent = caption;
    lightbox.style.display = 'block';

    // Jump to chat message bubble
    jumpBtn.onclick = () => {
        lightbox.style.display = 'none';
        switchTab('chat');
        setTimeout(() => {
            const targetEl = document.getElementById(`msg-${messageId}`);
            if (targetEl) {
                targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                targetEl.classList.add('highlight-pulse');
                setTimeout(() => targetEl.classList.remove('highlight-pulse'), 2000);
            }
        }, 100);
    };
}


// ==========================================================================
// 9. RENDER VIEWPORT: ANALYTICS TAB (Chart.js)
// ==========================================================================
function renderStatsTab() {
    const totalMsgsEl = document.getElementById('stat-total-messages');
    const totalDaysEl = document.getElementById('stat-total-days');
    const totalPhotosEl = document.getElementById('stat-total-photos');

    const cleanMsgs = AppState.messages.filter(m => m.sender !== 'SYSTEM');
    const photoMsgs = AppState.messages.filter(m => m.type === 'image' && m.photoUrl);

    // Compute Metrics
    const uniqueDates = new Set(cleanMsgs.map(m => m.date));
    totalMsgsEl.textContent = cleanMsgs.length;
    totalDaysEl.textContent = uniqueDates.size;
    totalPhotosEl.textContent = photoMsgs.length;

    // Sender Distribution
    const senderCounts = {};
    cleanMsgs.forEach(m => {
        senderCounts[m.sender] = (senderCounts[m.sender] || 0) + 1;
    });
    const senderLabels = Object.keys(senderCounts);
    const senderData = Object.values(senderCounts);

    // Timeline Trends (Messages by Date)
    const dateCounts = {};
    cleanMsgs.forEach(m => {
        dateCounts[m.date] = (dateCounts[m.date] || 0) + 1;
    });
    // Sort dates
    const sortedDates = Object.keys(dateCounts).sort();
    const timelineData = sortedDates.map(d => dateCounts[d]);

    // Hourly Distribution (0-23 hours)
    const hourlyCounts = Array(24).fill(0);
    cleanMsgs.forEach(m => {
        const timeMatch = m.time.match(/(\d{1,2}):\d{2}/);
        if (timeMatch) {
            let hour = parseInt(timeMatch[1]);
            // Adjust PM
            if (m.time.includes('下午') || m.time.toLowerCase().includes('pm')) {
                if (hour < 12) hour += 12;
            } else if (m.time.includes('上午') || m.time.toLowerCase().includes('am')) {
                if (hour === 12) hour = 0;
            }
            hourlyCounts[hour]++;
        }
    });

    // Themes colors
    const isDark = document.body.classList.contains('dark-mode');
    const textColor = isDark ? '#94a3b8' : '#64748b';
    const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)';
    const primaryColor = '#06C755';
    const accentColor = '#3b82f6';

    // Chart.js Default Config overrides
    Chart.defaults.color = textColor;
    Chart.defaults.borderColor = gridColor;

    // Render Sender Chart
    if (AppState.charts.sender) AppState.charts.sender.destroy();
    AppState.charts.sender = new Chart(document.getElementById('sender-chart'), {
        type: 'pie',
        data: {
            labels: senderLabels,
            datasets: [{
                data: senderData,
                backgroundColor: [primaryColor, accentColor, '#f59e0b', '#ec4899', '#8b5cf6'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });

    // Render Timeline Chart
    if (AppState.charts.timeline) AppState.charts.timeline.destroy();
    AppState.charts.timeline = new Chart(document.getElementById('timeline-chart'), {
        type: 'line',
        data: {
            labels: sortedDates,
            datasets: [{
                label: '訊息數量',
                data: timelineData,
                borderColor: primaryColor,
                backgroundColor: 'rgba(6, 199, 85, 0.1)',
                fill: true,
                tension: 0.3,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { display: false } },
                y: { beginAtZero: true }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });

    // Render Hourly Chart
    if (AppState.charts.hourly) AppState.charts.hourly.destroy();
    AppState.charts.hourly = new Chart(document.getElementById('hourly-chart'), {
        type: 'bar',
        data: {
            labels: Array.from({ length: 24 }, (_, i) => `${i}點`),
            datasets: [{
                label: '訊息數',
                data: hourlyCounts,
                backgroundColor: accentColor,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { display: false } },
                y: { beginAtZero: true }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}


// ==========================================================================
// 10. FILTERS & SEARCH ALGORITHMS
// ==========================================================================
function getFilteredMessages() {
    let filtered = AppState.messages;

    const { keyword, sender, dateFrom, dateTo } = AppState.currentFilters;

    // Apply Sender filter
    if (sender) {
        filtered = filtered.filter(m => m.sender === sender || m.type === 'date');
    }

    // Apply Date filters
    if (dateFrom) {
        filtered = filtered.filter(m => m.date >= dateFrom || m.type === 'date');
    }
    if (dateTo) {
        filtered = filtered.filter(m => m.date <= dateTo || m.type === 'date');
    }

    // Apply Keyword filter
    if (keyword) {
        const lowerKeyword = keyword.toLowerCase();
        filtered = filtered.filter(m => {
            if (m.type === 'date') return false; // Date separators are handled separately
            if (m.sender === 'SYSTEM') return false;
            return m.content && m.content.toLowerCase().includes(lowerKeyword);
        });
    }

    // Clean up empty date separators (e.g. if all messages on a date are filtered out, don't show the date header)
    const cleaned = [];
    for (let i = 0; i < filtered.length; i++) {
        const current = filtered[i];
        if (current.type === 'date') {
            // Check if there is at least one message following this date header before the next date header
            let hasMessage = false;
            for (let j = i + 1; j < filtered.length; j++) {
                if (filtered[j].type === 'date') break;
                if (filtered[j].sender !== 'SYSTEM') {
                    hasMessage = true;
                    break;
                }
            }
            if (hasMessage) {
                cleaned.push(current);
            }
        } else {
            cleaned.push(current);
        }
    }

    return cleaned;
}

function applyFilters() {
    AppState.currentFilters.keyword = document.getElementById('search-input').value.trim();
    AppState.currentFilters.sender = document.getElementById('sender-filter').value;
    AppState.currentFilters.dateFrom = document.getElementById('date-from').value;
    AppState.currentFilters.dateTo = document.getElementById('date-to').value;

    AppState.displayedMessagesCount = 200; // Reset display count when filters change

    if (AppState.activeTab === 'chat') {
        renderChatMessages();
    } else if (AppState.activeTab === 'gallery') {
        renderGalleryTab();
    }
}

function clearFilters() {
    document.getElementById('search-input').value = '';
    document.getElementById('sender-filter').value = '';
    document.getElementById('date-from').value = '';
    document.getElementById('date-to').value = '';
    
    AppState.currentFilters = { keyword: '', sender: '', dateFrom: '', dateTo: '' };
    AppState.displayedMessagesCount = 200; // Reset display count when filters are cleared
    
    if (AppState.activeTab === 'chat') {
        renderChatMessages();
    } else if (AppState.activeTab === 'gallery') {
        renderGalleryTab();
    }
}


// ==========================================================================
// 11. EXPORT & DELETE FUNCTIONS
// ==========================================================================
async function deleteActiveChat() {
    if (!AppState.activeChatId) return;
    
    if (confirm('確定要永久刪除此聊天紀錄與關聯的照片嗎？此動作無法復原。')) {
        await deleteChatFromDB(AppState.activeChatId);
        AppState.activeChatId = null;
        AppState.messages = [];
        AppState.photosMap.clear();
        
        // Hide UI sections and show welcome screen
        document.getElementById('chat-panel').classList.remove('active');
        document.getElementById('gallery-panel').classList.remove('active');
        document.getElementById('stats-panel').classList.remove('active');
        document.getElementById('welcome-panel').classList.add('active');
        
        document.getElementById('delete-chat-btn').style.display = 'none';
        document.getElementById('export-json-btn').style.display = 'none';
        
        // Remove active chat class from container
        const containerEl = document.getElementById('app-container');
        if (containerEl) {
            containerEl.classList.remove('chat-selected');
        }
        
        await refreshChatList();
        alert('聊天紀錄已成功刪除！');
    }
}

function exportChatAsJSON() {
    if (!AppState.messages || AppState.messages.length === 0) return;

    const chat = AppState.chats.find(c => c.id === AppState.activeChatId);
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify({
        chatInfo: chat,
        messages: AppState.messages
    }, null, 2));
    
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `${chat ? chat.name : 'line_backup'}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
}


// ==========================================================================
// 12. GENERAL UTILITIES
// ==========================================================================
function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, 
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

function getSenderColor(name) {
    // A palette of nice, distinct, highly-legible pastel colors
    const colors = [
        '#ef4444', '#f97316', '#eab308', '#10b981', 
        '#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6', '#d946ef'
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % colors.length;
    return colors[index];
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Start application
window.addEventListener('DOMContentLoaded', async () => {
    try {
        await initDB();
        initUI();
        
        // Register Service Worker for PWA offline capabilities
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('./sw.js')
                .then(() => console.log('Service Worker Registered'))
                .catch(err => console.log('Service Worker Registration Failed:', err));
        }
    } catch (e) {
        console.error('Failed to initialize app DB:', e);
    }
});

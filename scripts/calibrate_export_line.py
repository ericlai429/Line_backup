import os
import sys
import time
import ctypes
import json

# Win32 structures & functions for mouse/keyboard simulation (zero external dependencies)
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_pos():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def set_mouse_pos(x, y):
    ctypes.windll.user32.SetCursorPos(int(x), int(y))

def win32_click(x, y):
    """
    高度可靠的 Win32 滑鼠點擊模擬。
    在滑鼠按下 (down) 與彈起 (up) 之間加入 150 毫秒延遲，
    確保 Qt6 (LINE 電腦版) 能正確接收並處理點擊事件。
    """
    set_mouse_pos(x, y)
    time.sleep(0.15)
    # MOUSEEVENTF_LEFTDOWN = 0x0002
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.15)
    # MOUSEEVENTF_LEFTUP = 0x0004
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.15)

# Virtual Keys
VK_DOWN = 0x28
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B

def press_key(vk_code, hold_time=0.05, post_delay=0.2):
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(hold_time)
    ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
    time.sleep(post_delay)

def is_save_dialog_open():
    """
    透過 Windows API 檢查另存新檔或覆蓋確認視窗是否仍在畫面上。
    """
    for title in ["另存新檔", "Save As", "確認另存新檔", "Confirm Save As"]:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd != 0:
            return True
    return False

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                required_keys = ["chat_x", "chat_y", "menu_x", "menu_y", "save_x", "save_y"]
                if all(k in config for k in required_keys):
                    return config
        except Exception:
            pass
    return None

def save_config(chat_x, chat_y, menu_x, menu_y, save_x, save_y):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "chat_x": chat_x,
                "chat_y": chat_y,
                "menu_x": menu_x,
                "menu_y": menu_y,
                "save_x": save_x,
                "save_y": save_y
            }, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"無法儲存設定檔：{e}")

def main():
    print("====================================================")
    print("      LINE PC 物理座標直接點擊自動對話匯出工具")
    print("====================================================")
    print("說明：本工具採用滑鼠物理點擊與按鍵模擬，排除傳統向下鍵移動容易失敗的問題。")
    print("請確保您的 LINE 視窗在前方，不要被遮擋或最小化。")
    print("----------------------------------------------------\n")

    config = load_config()
    use_preset = False
    
    if config:
        print("偵測到上次的校準設定值：")
        print(f" - 第一個聊天室座標：({config['chat_x']}, {config['chat_y']})")
        print(f" - 右上角選單座標：({config['menu_x']}, {config['menu_y']})")
        print(f" - 傳送聊天紀錄座標：({config['save_x']}, {config['save_y']})")
        ans = input("是否直接使用上次的設定？ (Y/n)：").strip().lower()
        if ans in ("", "y", "yes"):
            chat_x = config['chat_x']
            chat_y = config['chat_y']
            menu_x = config['menu_x']
            menu_y = config['menu_y']
            save_x = config['save_x']
            save_y = config['save_y']
            use_preset = True
            print("已載入歷史設定。\n")

    if not use_preset:
        # 1. Calibrate Chat List Position
        print("【第一步：校準聊天列表位置】")
        print("1. 請將 LINE PC 視窗移到畫面上顯眼的位置（不要最小化或遮擋）。")
        print("2. 將滑鼠游標移到『左側聊天室列表的第一個聊天室』上方。")
        input("3. 移好後，請在此視窗按下 [Enter] 鍵鎖定座標...")
        chat_x, chat_y = get_mouse_pos()
        print(f"成功記錄第一個聊天室座標：({chat_x}, {chat_y})\n")
    
        # 2. Calibrate Menu Button Position
        print("【第二步：校準右上角選單按鈕位置】")
        print("1. 請用滑鼠點擊任意聊天室，讓右側顯示對話內容。")
        print("2. 將滑鼠游標移到對話視窗右上角的『選單按鈕』(三條線 ☰ 或 三個點 ⋯) 上方。")
        input("3. 移好後，請在此視窗按下 [Enter] 鍵鎖定座標...")
        menu_x, menu_y = get_mouse_pos()
        print(f"成功記錄選單按鈕座標：({menu_x}, {menu_y})\n")
    
        # 3. Calibrate Save Chat Position
        print("【第三步：校準『傳送聊天紀錄』選項位置】")
        print("1. 請手動點擊一下剛才的『選單按鈕』，讓選單彈出。")
        print("2. 將滑鼠游標移動到選單中的『傳送聊天紀錄』選項正上方（不要點擊）。")
        input("3. 移好後，請在此視窗按下 [Enter] 鍵鎖定座標...")
        save_x, save_y = get_mouse_pos()
        print(f"成功記錄傳送聊天紀錄座標：({save_x}, {save_y})\n")
        
        # Save config
        save_config(chat_x, chat_y, menu_x, menu_y, save_x, save_y)

    # 4. Testing Step (Single export test)
    while True:
        test_ans = input("是否要先進行『單次測試匯出』以驗證定位與按鍵是否正確？ (Y/n)：").strip().lower()
        if test_ans in ("", "y", "yes"):
            print("\n將在 3 秒後開始測試，請將 LINE 視窗顯示在最前...")
            for i in range(3, 0, -1):
                print(f"{i}...")
                time.sleep(1)
            
            print("\n[測試開始] 執行單次模擬...")
            # 1. 點擊第一個聊天室獲取焦點並選中
            win32_click(chat_x, chat_y)
            time.sleep(0.8)
            
            # 2. 點擊選單
            win32_click(menu_x, menu_y)
            # 移開滑鼠避免干擾焦點
            set_mouse_pos(chat_x, chat_y)
            time.sleep(1.0) # 給予選單時間展開
            
            # 3. 點擊傳送聊天紀錄
            print("直接點擊『傳送聊天紀錄』座標...")
            win32_click(save_x, save_y)
            time.sleep(1.5) # 等待另存新檔視窗跳出
            
            # Close the save dialog and menu to return to normal state
            press_key(VK_ESCAPE, post_delay=0.5)
            press_key(VK_ESCAPE, post_delay=0.5)
            
            print("\n----------------------------------------------------")
            print("測試模擬完成！")
            print("請檢查您的 LINE 剛才是否有正確彈出『另存新檔』視窗（已被程式按 ESC 自動取消）？")
            print("----------------------------------------------------")
            
            confirm = input("物理點擊位置是否完全正確？ (Y/n)：").strip().lower()
            if confirm in ("", "y", "yes"):
                print("非常好！驗證成功。")
                break
            else:
                print("\n設定可能不夠準確。請選擇以下操作：")
                print("1. 重新進行滑鼠座標校準")
                print("2. 放棄測試，直接進入大量匯出")
                choice = input("請輸入選項 (1-2)：").strip()
                if choice == "1":
                    use_preset = False
                    main()
                    return
                else:
                    break
        else:
            break

    print("----------------------------------------------------")
    print("準備開始全自動物理座標點擊匯出對話紀錄！")
    print("重要提示：")
    print("1. 程式執行時請勿移動滑鼠與鍵盤。")
    print("2. 儲存第一個聊天紀錄時，會彈出『另存新檔』視窗，請先『手動選擇』您要存檔的資料夾")
    print("   (例如 D:\\LineExport)，之後的存檔就會自動記住此路徑。")
    
    try:
        loop_count = int(input("請輸入您要自動匯出的聊天室數量 (例如 30)：") or "30")
    except ValueError:
        loop_count = 30
        
    print(f"\n將在 5 秒後開始執行，請立刻點選您的 LINE 視窗...")
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)
        
    print("\n[開始自動匯出] 隨時可以按 Ctrl+C 中斷執行...")
    
    for i in range(1, loop_count + 1):
        print(f"\n---> 正在匯出第 {i}/{loop_count} 個聊天室...")
        
        # 1. 點擊第一個聊天室，將滾動條拉回最上方，並強制重置焦點至聊天列表
        win32_click(chat_x, chat_y)
        time.sleep(0.5)
        
        # 2. 快速向下移動 (i - 1) 次以選取當前的第 i 個聊天室 (支援列表自動滾動)
        if i > 1:
            print(f"正在向下導航選取第 {i} 個聊天室...")
            for _ in range(i - 1):
                press_key(VK_DOWN, hold_time=0.02, post_delay=0.06)
            time.sleep(0.8) # 等待目標聊天內容與按鈕完全載入
            
        # 3. 直接點擊右上角選單按鈕
        win32_click(menu_x, menu_y)
        # 移開滑鼠避免干擾選單高亮
        set_mouse_pos(chat_x, chat_y)
        time.sleep(1.0)
        
        # 4. 直接點擊『傳送聊天紀錄』選項的物理座標
        win32_click(save_x, save_y)
        time.sleep(1.5) # 等待另存新檔視窗跳出
        
        # 5. 直接按 Enter 存檔
        print("按下 Enter 存檔...")
        press_key(VK_RETURN, post_delay=0.6)
        
        # 6. 偵測並處理「檔案已存在」覆蓋確認對話框
        if is_save_dialog_open():
            print("偵測到重覆檔案提示！發送 'Y' 鍵與 Enter 鍵覆蓋檔案...")
            press_key(0x59, post_delay=0.3) # 發送 'Y' (0x59) 鍵選擇取代
            press_key(VK_RETURN, post_delay=0.5)
            
            # 極限防卡死：如果按完取代後對話框還在，按兩次 ESC 關閉並放棄該聊天室
            if is_save_dialog_open():
                print("⚠️ 警告：存檔視窗依然開啟，強制按 ESC 放棄此聊天室以防卡死迴圈...")
                press_key(VK_ESCAPE, post_delay=0.5)
                press_key(VK_ESCAPE, post_delay=0.5)

        # 7. 等待 6.0 秒以防止寫入檔案與系統 Lag
        print("等待 6 秒防 Lag...")
        time.sleep(6.0)

    print("\n自動匯出排程已完成！")
    print("請將該資料夾下的所有 .txt 檔案拖入您的本地網頁網址 (http://localhost:8000) 即可瀏覽。")

if __name__ == "__main__":
    main()

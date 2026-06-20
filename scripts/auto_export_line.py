import os
import sys
import time
import uiautomation as auto

# Create output folder if it doesn't exist
OUTPUT_DIR = r"D:\LineExport\eric"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def find_line_window():
    # Search for LINE window by ClassName or Name
    window = auto.WindowControl(searchDepth=1, ClassName='Qt662QWindowIcon')
    if not window.Exists(0.5, 0.1):
        window = auto.WindowControl(searchDepth=1, Name='LINE')
    return window

def ensure_line_is_open():
    window = find_line_window()
    if window.Exists(1, 0.5):
        return window

    print("LINE window not found. Terminating any hidden LINE processes to force a fresh window launch...")
    import subprocess
    subprocess.call(["taskkill", "/F", "/IM", "LINE.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)

    print("Attempting to launch LINE.exe...")
    appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\user\AppData\Local")
    line_path = os.path.join(appdata, r"LINE\bin\current\LINE.exe")
    
    if os.path.exists(line_path):
        subprocess.Popen([line_path])
        print("Waiting for LINE window to open...")
        window = find_line_window()
        if window.Exists(15, 1):
            print("LINE window opened successfully!")
            return window

    # Try fallback to launcher
    line_launcher = os.path.join(appdata, r"LINE\LineLauncher.exe")
    if os.path.exists(line_launcher):
        subprocess.Popen([line_launcher])
        print("Waiting for LINE window to open...")
        window = find_line_window()
        if window.Exists(15, 1):
            print("LINE window opened successfully!")
            return window
            
    return None

def find_menu_button(window):
    # Walk the tree to find the menu button ("選單" or "Menu")
    for control, depth in auto.WalkControl(window, maxDepth=8):
        if control.ControlTypeName == "ButtonControl":
            name = control.Name
            if name == "選單" or name == "Menu" or "選單" in name or "Menu" in name:
                return control
    return None

def find_save_menu_item():
    # Look for menu item in the popped-up menus
    for control, depth in auto.WalkControl(auto.GetRootControl(), maxDepth=3):
        if control.ControlTypeName == "MenuItemControl":
            name = control.Name
            if name == "傳送聊天紀錄" or "傳送聊天紀錄" in name or "Save chat history" in name or name == "儲存聊天":
                return control
    return None

def main():
    print("=== LINE 聊天紀錄自動匯出工具 ===")
    
    # Try to launch if not open at all
    ensure_line_is_open()
    
    print("\n>>> 請在您電腦右下角系統匣（工作列旁）雙擊 LINE 的綠色圖示，將主視窗打開。")
    print("程式將在此等待您的操作，一旦偵測到視窗開啟，便會立刻接管全自動匯出對話！")
    print("等待中（超時時間：5 分鐘）...")
    
    line_window = None
    for sec in range(300):
        line_window = find_line_window()
        # Check if window is visible and has a handle
        if line_window.Exists(0.1, 0.1):
            try:
                # Test if we can focus it
                line_window.SetFocus()
                print("\n[OK] 成功偵測到 LINE 視窗！正在接管控制...")
                break
            except Exception:
                pass
        time.sleep(1)
        if sec > 0 and sec % 15 == 0:
            print(f"仍在等待視窗開啟中... ({sec}/300 秒)")
            
    if not line_window or not line_window.Exists(1, 1):
        print("\n錯誤：超時未偵測到 LINE 視窗，程式已結束。")
        sys.exit(1)

    line_window.ShowWindow(9) # 9 is SW_RESTORE
    time.sleep(1.5)

    print("正在等待 LINE 登入並載入聊天列表...")
    print("請確保您的 LINE 處於已登入狀態，且主視窗已顯示聊天列表。")
    print("程式將在此等待至聊天介面完全載入...")
    
    menu_btn = None
    # Wait up to 180 seconds (3 minutes) for chat window loading
    for sec in range(90):
        # Re-find the window to avoid COMError UIA_E_ELEMENTNOTAVAILABLE if window transitioned
        current_window = find_line_window()
        if not current_window.Exists(0.2, 0.1):
            time.sleep(1.5)
            continue
            
        try:
            current_window.SetFocus()
            auto.SendKeys("{Ctrl}2")
            time.sleep(0.5)
            auto.SendKeys("{Down}")
            time.sleep(1.0) # Wait for chat to load
            
            menu_btn = find_menu_button(current_window)
            if menu_btn:
                line_window = current_window # Update line_window to the active main window
                print("[OK] 成功偵測到聊天室「選單」按鈕，界面載入完成！")
                break
        except Exception:
            # If COMError occurs due to window closing/transitioning, ignore and retry
            pass
            
        time.sleep(1)
        if sec > 0 and sec % 5 == 0:
            print(f"仍在等待聊天介面載入中... ({sec * 2}/180 秒)")
            
    if not menu_btn:
        print("\n錯誤：超時未載入聊天介面（請確認已完成登入且開啟主視窗），程式結束。")
        sys.exit(1)

    print("開始自動匯出對話紀錄...")
    print(f"檔案將儲存至：{OUTPUT_DIR}")
    print("請勿移動滑鼠或鍵盤，直到自動化程式完成。")
    
    # We will export up to 100 chats. If the window stops changing or Down Arrow does not load new chats, we can stop.
    max_chats = 100
    exported_count = 0
    
    for i in range(1, max_chats + 1):
        print(f"\n--- 正在處理第 {i} 個聊天室 ---")
        
        # 1. Click Menu button
        menu_btn = find_menu_button(line_window)
        if not menu_btn:
            print("警告：找不到聊天室的「選單」按鈕。可能已到達列表底部，或者當前非聊天視窗。")
            break
            
        print("點擊選單按鈕...")
        menu_btn.Click(simulateMove=False)
        time.sleep(0.8)
        
        # 2. Click "傳送聊天紀錄"
        save_item = find_save_menu_item()
        if not save_item:
            print("警告：找不到「傳送聊天紀錄」選單項。正在嘗試關閉選單...")
            # Click somewhere neutral or press Esc
            auto.SendKeys("{Esc}")
            time.sleep(0.5)
            break
            
        print("點擊「傳送聊天紀錄」...")
        save_item.Click(simulateMove=False)
        
        # 3. Handle Save As Dialog
        print("等待另存新檔視窗...")
        save_dialog = auto.WindowControl(searchDepth=1, Name="另存新檔")
        if not save_dialog.Exists(3, 1):
            save_dialog = auto.WindowControl(searchDepth=1, Name="Save As")
            
        if not save_dialog.Exists(1, 1):
            print("錯誤：找不到存檔視窗，跳過。")
            auto.SendKeys("{Esc}")
            time.sleep(0.5)
            continue
            
        # Determine unique filename to avoid overwrite prompts
        filename = os.path.join(OUTPUT_DIR, f"chat_backup_{i}.txt")
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                filename = os.path.join(OUTPUT_DIR, f"chat_backup_{i}_{int(time.time())}.txt")
                
        print(f"輸入儲存路徑：{filename}")
        
        # Locate Edit box
        file_name_edit = save_dialog.EditControl(searchDepth=3, ClassName="Edit")
        if file_name_edit.Exists(2, 1):
            file_name_edit.SetValue(filename)
            time.sleep(0.5)
            
            # Click Save button
            save_btn = save_dialog.ButtonControl(Name="存檔")
            if not save_btn.Exists(0.5, 0.1):
                save_btn = save_dialog.ButtonControl(Name="Save")
            if not save_btn.Exists(0.5, 0.1):
                save_btn = save_dialog.ButtonControl(Name="存")
                
            if save_btn.Exists(1, 1):
                print("點擊存檔...")
                save_btn.Click(simulateMove=False)
                exported_count += 1
            else:
                print("找不到存檔按鈕，發送 Enter 鍵存檔...")
                auto.SendKeys("{Enter}")
                exported_count += 1
        else:
            print("找不到檔名輸入框，跳過。")
            auto.SendKeys("{Esc}")
            
        time.sleep(1.5) # Wait for dialog to close and file to write
        
        # 4. Switch to next chat room
        print("切換至下一個聊天室...")
        line_window.SetFocus()
        auto.SendKeys("{Down}")
        time.sleep(1.0) # Wait for chat to load

    print(f"\n自動化匯出完成！成功匯出 {exported_count} 個聊天室紀錄。")
    print(f"請至瀏覽器網頁 (http://localhost:8000) 將 '{OUTPUT_DIR}' 目錄下的所有 .txt 檔案拖入以進行瀏覽。")

if __name__ == "__main__":
    main()

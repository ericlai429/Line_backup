import os
import sys
import time
import json
import subprocess
import ctypes

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

# ====================================================
# 自動下載並安裝所需套件 (OpenCV, PyAutoGUI, NumPy, Pillow)
# ====================================================
def install_dependencies():
    packages = {
        "pyautogui": "pyautogui",
        "cv2": "opencv-python",
        "numpy": "numpy",
        "PIL": "pillow"
    }
    missing = []
    for module_name, pip_name in packages.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)
            
    if missing:
        print("偵測到未安裝圖像辨識所需套件，正在為您安裝，請稍候...")
        print(f"即將安裝：{', '.join(missing)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
            for pkg in missing:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
            print("套件安裝成功！\n")
        except Exception as e:
            print(f"自動安裝套件失敗：{e}")
            print("請手動開啟命令提示字元並執行以下指令：")
            print(f"pip install {' '.join(missing)}")
            sys.exit(1)

install_dependencies()

# 匯入套件
import pyautogui
import cv2
import numpy as np
from PIL import Image

# 虛擬鍵定義
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

# 設定檔路徑
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(CONFIG_DIR, "visual_config.json")
MENU_TEMPLATE_PATH = os.path.join(CONFIG_DIR, "menu_template.png")
SAVE_TEMPLATE_PATH = os.path.join(CONFIG_DIR, "save_template.png")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                required_keys = ["chat_x", "chat_y", "menu_x", "menu_y", "rel_save_x", "rel_save_y"]
                if all(k in config for k in required_keys):
                    return config
        except Exception:
            pass
    return None

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"無法儲存設定檔：{e}")

# ====================================================
# 圖像辨識核心函式
# ====================================================
def find_image_on_screen(template_path, threshold=0.8):
    """
    在螢幕上搜尋範本圖片，返回中心座標 (x, y) 與最大匹配值。
    """
    if not os.path.exists(template_path):
        return None
        
    try:
        screenshot = pyautogui.screenshot()
        screen_np = np.array(screenshot)
        screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_RGB2GRAY)
        
        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            return None
            
        h, w = template.shape[:2]
        
        result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= threshold:
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return center_x, center_y, max_val
    except Exception as e:
        print(f"圖像辨識時發生錯誤: {e}")
        
    return None

# ====================================================
# 校準流程
# ====================================================
def run_calibration():
    print("【畫面偵測校準步驟】")
    print("請將 LINE 視窗移到畫面上顯眼的位置（不要最小化或遮擋）。")
    print("----------------------------------------------------")
    
    # 1. 聊天室列表定位
    print("【第一步：校準聊天列表位置】")
    print("1. 將滑鼠游標移到『左側聊天室列表的第一個聊天室』上方。")
    input("2. 移好後，請在此視窗按下 [Enter] 鍵鎖定座標...")
    chat_x, chat_y = pyautogui.position()
    print(f"成功記錄第一個聊天室座標：({chat_x}, {chat_y})\n")
    
    # 2. 選單按鈕定位與範本擷取
    print("【第二步：校準右上角選單按鈕 (☰ 或 ⋯)】")
    print("1. 請先點擊任意聊天室，讓右側顯示對話內容。")
    print("2. 將滑鼠游標移到對話視窗右上角的『選單按鈕』正上方。")
    input("3. 移好後，請在此視窗按下 [Enter] 鍵...")
    menu_x, menu_y = pyautogui.position()
    
    print("正在自動擷取選單按鈕圖片範本...")
    time.sleep(0.5)
    screen = pyautogui.screenshot()
    
    left = max(0, menu_x - 20)
    top = max(0, menu_y - 20)
    right = min(screen.width, menu_x + 20)
    bottom = min(screen.height, menu_y + 20)
    
    menu_crop = screen.crop((left, top, right, bottom))
    menu_crop.save(MENU_TEMPLATE_PATH)
    print("選單按鈕範本已成功擷取並儲存！\n")
    
    # 3. 傳送聊天紀錄選項定位與範本擷取
    print("【第三步：校準選單內『傳送聊天紀錄』選項】")
    print("1. 請手動點選剛才的『選單按鈕』讓選單彈出。")
    print("2. 將滑鼠游標移到選單中的『傳送聊天紀錄』選項正中央。")
    input("3. 移好後，請在此視窗按下 [Enter] 鍵...")
    save_x, save_y = pyautogui.position()
    
    rel_save_x = save_x - menu_x
    rel_save_y = save_y - menu_y
    
    pyautogui.press('escape')
    time.sleep(0.5)
    
    print("\n【第四步：自動擷取無高亮乾淨範本】")
    print("請將您的滑鼠游標移到角落（例如畫面最右下角），不要碰觸 LINE 視窗。")
    print("程式將在 3 秒後自動打開選單並擷取乾淨的『傳送聊天紀錄』圖片...")
    for i in range(3, 0, -1):
        print(f"{i}...")
        time.sleep(1)
        
    win32_click(menu_x, menu_y)
    time.sleep(0.8)
    
    screen = pyautogui.screenshot()
    pyautogui.press('escape')
    
    left = max(0, save_x - 70)
    top = max(0, save_y - 13)
    right = min(screen.width, save_x + 70)
    bottom = min(screen.height, save_y + 13)
    
    save_crop = screen.crop((left, top, right, bottom))
    save_crop.save(SAVE_TEMPLATE_PATH)
    print("『傳送聊天紀錄』選項範本已成功擷取！\n")
    
    config = {
        "chat_x": chat_x,
        "chat_y": chat_y,
        "menu_x": menu_x,
        "menu_y": menu_y,
        "rel_save_x": rel_save_x,
        "rel_save_y": rel_save_y
    }
    save_config(config)
    print("校準檔案與圖片儲存完畢！\n")
    return config

def main():
    print("====================================================")
    print("      LINE PC 畫面圖像偵測自動對話匯出工具")
    print("====================================================")
    
    config = load_config()
    templates_exist = os.path.exists(MENU_TEMPLATE_PATH) and os.path.exists(SAVE_TEMPLATE_PATH)
    
    if config and templates_exist:
        print("偵測到先前的圖像校準設定與範本圖片。")
        ans = input("是否直接使用上次的設定？ (Y/n)：").strip().lower()
        if ans not in ("", "y", "yes"):
            config = run_calibration()
    else:
        config = run_calibration()
        
    chat_x = config["chat_x"]
    chat_y = config["chat_y"]
    menu_x = config["menu_x"]
    menu_y = config["menu_y"]
    rel_save_x = config["rel_save_x"]
    rel_save_y = config["rel_save_y"]
    
    # 驗證測試
    while True:
        test_ans = input("是否要先進行『單次偵測測試』以驗證圖像辨識與點擊是否準確？ (Y/n)：").strip().lower()
        if test_ans in ("", "y", "yes"):
            print("\n將在 3 秒後開始測試，請將 LINE 視窗顯示在最前...")
            for i in range(3, 0, -1):
                print(f"{i}...")
                time.sleep(1)
                
            print("\n[測試開始] 正在尋找選單按鈕...")
            win32_click(chat_x, chat_y)
            time.sleep(0.5)
            
            match = find_image_on_screen(MENU_TEMPLATE_PATH, threshold=0.8)
            if match:
                mx, my, val = match
                print(f"成功找到選單按鈕！位置：({mx}, {my})，匹配度：{val:.2f}")
                win32_click(mx, my)
            else:
                print("⚠️ 未找到選單按鈕圖片，改用歷史校準座標點擊...")
                win32_click(menu_x, menu_y)
                
            set_mouse_pos(chat_x, chat_y)
            time.sleep(1.0)
            
            match_save = find_image_on_screen(SAVE_TEMPLATE_PATH, threshold=0.8)
            if match_save:
                sx, sy, val = match_save
                print(f"成功找到『傳送聊天紀錄』選項！位置：({sx}, {sy})，匹配度：{val:.2f}")
                win32_click(sx, sy)
            else:
                print("⚠️ 未找到『傳送聊天紀錄』圖片，改用歷史相對座標進行物理點擊...")
                current_menu_x = mx if 'mx' in locals() else menu_x
                current_menu_y = my if 'my' in locals() else menu_y
                win32_click(current_menu_x + rel_save_x, current_menu_y + rel_save_y)
                
            time.sleep(1.5)
            
            # 按下 ESC 取消存檔框與選單
            press_key(VK_ESCAPE, post_delay=0.5)
            press_key(VK_ESCAPE, post_delay=0.5)
            
            print("\n----------------------------------------------------")
            print("測試模擬完成！")
            print("請檢查剛才 LINE 視窗是否有自動彈出『另存新檔』對話框並被自動關閉。")
            print("----------------------------------------------------")
            
            confirm = input("圖像辨識點擊是否完全正確？ (Y/n)：").strip().lower()
            if confirm in ("", "y", "yes"):
                print("驗證成功！")
                break
            else:
                print("\n點擊或辨識失敗。請重新校準。")
                config = run_calibration()
                chat_x = config["chat_x"]
                chat_y = config["chat_y"]
                menu_x = config["menu_x"]
                menu_y = config["menu_y"]
                rel_save_x = config["rel_save_x"]
                rel_save_y = config["rel_save_y"]
        else:
            break

    print("----------------------------------------------------")
    print("準備開始全自動圖像辨識匯出對話紀錄！")
    print("重要提示：")
    print("1. 程式執行時請勿移動滑鼠與鍵盤，也不要讓其他視窗遮擋 LINE。")
    print("2. 儲存第一個聊天紀錄時，會彈出『另存新檔』視窗，請先『手動選擇』您要存檔的資料夾")
    print("   (例如 D:\\LineExport)，之後的存檔就會自動記住此路徑。")
    
    try:
        loop_count = int(input("請輸入您要自動匯出的聊天室數量 (例如 30)：") or "30")
    except ValueError:
        loop_count = 30
        
    print(f"\n將在 5 秒後開始執行，請確保您的 LINE 視窗在最前方...")
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
            
        # 3. 尋找選單按鈕並點擊
        match = find_image_on_screen(MENU_TEMPLATE_PATH, threshold=0.8)
        current_menu_x, current_menu_y = menu_x, menu_y
        if match:
            current_menu_x, current_menu_y, _ = match
            win32_click(current_menu_x, current_menu_y)
        else:
            win32_click(menu_x, menu_y)
            
        # 移開滑鼠避免干擾
        set_mouse_pos(chat_x, chat_y)
        time.sleep(1.0)
        
        # 4. 尋找『傳送聊天紀錄』並點擊
        match_save = find_image_on_screen(SAVE_TEMPLATE_PATH, threshold=0.8)
        if match_save:
            sx, sy, _ = match_save
            win32_click(sx, sy)
        else:
            win32_click(current_menu_x + rel_save_x, current_menu_y + rel_save_y)
            
        time.sleep(1.5) # 等待另存新檔對話框彈出
        
        # 5. 按下 Enter 存檔
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

        # 7. 等待 6.0 秒以防止系統 Lag
        print("等待 6 秒防 Lag...")
        time.sleep(6.0)

print("\n自動匯出排程已完成！")
print("請將該資料夾下的所有 .txt 檔案拖入您的本地網頁網址 (http://localhost:8000) 即可瀏覽。")

if __name__ == "__main__":
    main()

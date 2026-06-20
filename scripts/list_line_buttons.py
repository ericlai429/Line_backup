import uiautomation as auto

def list_buttons():
    # Find the LINE window
    line_window = auto.WindowControl(searchDepth=1, ClassName='Qt662QWindowIcon')
    if not line_window.Exists(1, 1):
        line_window = auto.WindowControl(searchDepth=1, Name='LINE')
        
    if not line_window.Exists(1, 1):
        print("LINE window not found!")
        return

    print(f"Found LINE Window: Name='{line_window.Name}', ClassName='{line_window.ClassName}'")
    print("Listing all ButtonControls inside LINE window:")
    
    count = 0
    for control, depth in auto.WalkControl(line_window, maxDepth=8):
        if control.ControlTypeName == "ButtonControl":
            count += 1
            print(f"[{count}] Name: '{control.Name}', ClassName: '{control.ClassName}', AutomationId: '{control.AutomationId}', Description: '{control.HelpText}'")
            
    if count == 0:
        print("No ButtonControls found! Let's check other control types:")
        # Print first 20 controls found
        for i, (control, depth) in enumerate(auto.WalkControl(line_window, maxDepth=5)):
            if i > 50:
                break
            indent = "  " * depth
            print(f"{indent}ControlType: {control.ControlTypeName}, Name: '{control.Name}', ClassName: '{control.ClassName}'")

if __name__ == "__main__":
    list_buttons()

import os
import uiautomation as auto

def inspect():
    # Find the LINE window
    line_window = auto.WindowControl(searchDepth=1, ClassName='Qt662QWindowIcon')
    if not line_window.Exists(1, 1):
        line_window = auto.WindowControl(searchDepth=1, Name='LINE')
        
    if not line_window.Exists(1, 1):
        print("LINE window not found! Listing top-level windows:")
        for w, depth in auto.WalkControl(auto.GetRootControl(), maxDepth=1):
            if w.Name or w.ClassName:
                print(f"Window: Name='{w.Name}', ClassName='{w.ClassName}'")
        return

    print(f"Found LINE Window: Name='{line_window.Name}', ClassName='{line_window.ClassName}'")
    
    output_file = "line_ui_tree.txt"
    print(f"Dumping UI tree to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        for control, depth in auto.WalkControl(line_window, maxDepth=10):
            indent = "  " * depth
            f.write(f"{indent}ControlType: {control.ControlTypeName}, Name: '{control.Name}', ClassName: '{control.ClassName}'\n")
    print("UI tree successfully dumped!")

if __name__ == "__main__":
    inspect()

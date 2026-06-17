import os

# --- Configuration ---
TARGET_DIR = r"/Users/parham/Downloads/portfolio-dashboard"  # <-- Set your target folder path here

EXCLUDE_DIRS = {'.git', '__pycache__', 'venv', '.venv', '.idea', '.vscode'}


def is_target_file(filename):
    name = filename.lower()
    if name.endswith(('.py', '.sql')):
        return True
    if name.endswith('.json') and 'config' in name:
        return True
    if name.endswith(('.env', '.yaml', '.yml')):
        return True
    return False


def generate_smart_tree(startpath):
    tree_lines = []

    def build_tree(current_path, prefix=""):
        try:
            items = os.listdir(current_path)
        except PermissionError:
            return

        dirs  = sorted(i for i in items if os.path.isdir(os.path.join(current_path, i)) and i not in EXCLUDE_DIRS)
        files = sorted(i for i in items if os.path.isfile(os.path.join(current_path, i)) and is_target_file(i))

        all_items = dirs + files
        for index, item in enumerate(all_items):
            path = os.path.join(current_path, item)
            is_last = index == len(all_items) - 1
            connector = "└── " if is_last else "├── "
            new_prefix = prefix + ("    " if is_last else "│   ")

            if os.path.isdir(path):
                tree_lines.append(f"{prefix}{connector}📁 {item}/")
                build_tree(path, new_prefix)  # Always expand all directories
            else:
                tree_lines.append(f"{prefix}{connector}📄 {item}")

    tree_lines.append(f"📁 {os.path.basename(os.path.abspath(startpath))}/")
    build_tree(startpath)
    return "\n".join(tree_lines)


if __name__ == "__main__":
    output_file = os.path.join(TARGET_DIR, "structure.txt")

    print("⏳ Generating project tree...")
    tree_text = generate_smart_tree(TARGET_DIR)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(tree_text)

    print(f"✅ Structure saved to '{output_file}'")

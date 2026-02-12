import os

file_path = r"C:\Users\a_oohara\Downloads\teamH_noilen-master (3)\teamH_noilen-master\server.py"

# Second replacement: staff_user_invite_confirm_page function
old_content_confirm = """    print(f"DEBUG: staff_user_invite_confirm_page - session at start: {session})")
    invite_data = session.get('invite_data')

    if not invite_data:
        flash("招待データが見つかりません。再度入力してください。", "error")
        return redirect(url_for('staff_user_invite'))"""

new_content_confirm = """    print(f"DEBUG: staff_user_invite_confirm_page - session at start: {session})")
    invite_data = session.get('invite_data')
    print(f"DEBUG: staff_user_invite_confirm_page - invite_data value: {invite_data})")

    if not invite_data:
        flash("招待データが見つかりません。再度入力してください。", "error")
        return redirect(url_for('staff_user_invite'))"""

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Perform second replacement
if old_content_confirm in content:
    content = content.replace(old_content_confirm, new_content_confirm)
    print("Second replacement successful.")
else:
    print("Second old content not found. No replacement made.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("File modification script finished.")
